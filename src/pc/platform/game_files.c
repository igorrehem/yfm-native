/* Finding the player's disc (an image or an extracted folder, disc_source.h)
 * and reading the game's executable out of it (game_files.h). Plain reads at
 * startup, before the drive model (libds.c) opens the disc for the game. */
#include "pc/compat/fs.h"
#include "game_files.h"
#include "disc_source.h"
#include "paths.h"
#include "platform.h"
#include <dirent.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define RAW_SECTOR 2352
#define USER_DATA 24
#define SECTOR 2048
#define PATH_MAX_ 1024
#define EXECUTABLE "SLUS_014.11"
#ifdef _WIN32
#define SEPARATOR '\\'
#else
#define SEPARATOR '/'
#endif

static char found[PATH_MAX_];

static unsigned le32(const unsigned char *bytes)
{
    return bytes[0] | (unsigned)bytes[1] << 8 | (unsigned)bytes[2] << 16 | (unsigned)bytes[3] << 24;
}

int GameFiles_ReadSector(FILE *file, unsigned lba, unsigned char *out)
{
    unsigned char raw[RAW_SECTOR];
    if ((unsigned long long)lba * RAW_SECTOR > LONG_MAX) return 0;
    if (fseek(file, (long)lba * RAW_SECTOR, SEEK_SET) || fread(raw, 1, RAW_SECTOR, file) != RAW_SECTOR) return 0;
    memcpy(out, raw + USER_DATA, SECTOR);
    return 1;
}

/* The 2048 bytes of user data of a sector, from a FILE (another raw image)
 * or a DiscSource (the player's image or extracted folder). */
typedef int ReadData(void *context, unsigned lba, unsigned char *out);

static int read_file(void *context, unsigned lba, unsigned char *out)
{
    return GameFiles_ReadSector(context, lba, out);
}

static int read_source(void *context, unsigned lba, unsigned char *out)
{
    unsigned char raw[RAW_SECTOR];
    if (lba > INT_MAX || !DiscSource_Read(context, (int)lba, raw)) return 0;
    memcpy(out, raw + USER_DATA, SECTOR);
    return 1;
}

/* The directory record called `name` (ISO 9660's ";1" left off) in the
 * directory at `lba`, `size` bytes: 1 with its place and size. */
static int find_record(ReadData *reader, void *context, unsigned lba, unsigned size, const char *name, size_t length,
                       unsigned *at, unsigned *record_size, int *directory)
{
    unsigned char sector[SECTOR];
    unsigned done;
    if (size > 64 * SECTOR) return 0;
    for (done = 0; done < size; done += SECTOR) {
        unsigned offset = 0;
        if (!reader(context, lba + done / SECTOR, sector)) return 0;
        while (offset < SECTOR && sector[offset]) {
            const unsigned char *record = sector + offset;
            size_t n;
            if (record[0] < 34 || offset + record[0] > SECTOR) break;
            n = record[32];
            if (33u + n <= record[0]) {
                const char *id = (const char *)record + 33;
                size_t stem = 0;
                while (stem < n && id[stem] != ';') stem++;
                if (stem == length && !memcmp(id, name, length)) {
                    *at = le32(record + 2);
                    *record_size = le32(record + 10);
                    *directory = (record[25] & 2) != 0;
                    return 1;
                }
            }
            offset += record[0];
        }
    }
    return 0;
}

static int find_in(ReadData *reader, void *context, const char *path, unsigned *lba, unsigned *size)
{
    unsigned char sector[SECTOR];
    unsigned at, length;
    int directory = 1;
    if (!reader(context, 16, sector) || sector[0] != 1 || memcmp(sector + 1, "CD001", 5)) return 0;
    at = le32(sector + 156 + 2);
    length = le32(sector + 156 + 10);
    while (*path) {
        const char *slash = strchr(path, '/');
        size_t n = slash ? (size_t)(slash - path) : strlen(path);
        if (!directory || !find_record(reader, context, at, length, path, n, &at, &length, &directory)) return 0;
        path += n + (slash != NULL);
    }
    if (directory) return 0;
    *lba = at;
    *size = length;
    return 1;
}

int GameFiles_FindFile(FILE *file, const char *path, unsigned *lba, unsigned *size)
{
    return find_in(read_file, file, path, lba, size);
}

/* Where SLUS_014.11 is on the disc, or 0 when it is not that disc (not
 * raw, not ISO 9660, or another game). */
static int find_executable(DiscSource *disc, unsigned *lba, unsigned *size)
{
    return find_in(read_source, disc, EXECUTABLE, lba, size) && *size > SECTOR && *size < (4u << 20);
}

static int is_the_disc(const char *path)
{
    char why[256];
    DiscSource *disc = DiscSource_Open(path, why, sizeof(why));
    unsigned lba, size;
    unsigned char header[SECTOR];
    int yes;
    if (!disc) return 0;
    yes = find_executable(disc, &lba, &size) && read_source(disc, lba, header) &&
          !memcmp(header, "PS-X EXE", 8) &&
          read_source(disc, lba + (size - 1) / SECTOR, header);
    DiscSource_Close(disc);
    return yes;
}

static int ends_with_bin(const char *name)
{
    size_t length = strlen(name);
    return length > 4 && (!strcmp(name + length - 4, ".bin") || !strcmp(name + length - 4, ".BIN") ||
                          !strcmp(name + length - 4, ".Bin"));
}

/* The disc in a folder: the extracted one (yfm-disc.txt) first, then the
 * usual image name, then the other images in name order, so the choice does
 * not change between launches. */
static int search(const char *folder)
{
    DIR *directory;
    struct dirent *entry;
    char best[PATH_MAX_] = "";
    if (snprintf(found, sizeof(found), "%s/%s", folder, DISC_SOURCE_INDEX) < (int)sizeof(found) &&
        is_the_disc(found)) return 1;
    if (snprintf(found, sizeof(found), "%s/rpg-yfm.bin", folder) < (int)sizeof(found) && is_the_disc(found)) return 1;
    directory = opendir(folder);
    if (!directory) return 0;
    while ((entry = readdir(directory))) {
        if (!ends_with_bin(entry->d_name) || strlen(entry->d_name) >= sizeof(best)) continue;
        if (best[0] && strcmp(entry->d_name, best) >= 0) continue;
        if (snprintf(found, sizeof(found), "%s/%s", folder, entry->d_name) >= (int)sizeof(found)) continue;
        if (is_the_disc(found)) snprintf(best, sizeof(best), "%s", entry->d_name);
    }
    closedir(directory);
    return best[0] && snprintf(found, sizeof(found), "%s/%s", folder, best) < (int)sizeof(found);
}

const char *GameFiles_Disc(char *why, size_t why_size)
{
    const char *named = getenv("MEMORIES_DISC");
    char folder[PATH_MAX_];
    FILE *saved;
    if (found[0]) return found;
    if (named && *named) {
        if (strlen(named) < sizeof(found) && is_the_disc(named)) {
            snprintf(found, sizeof(found), "%s", named);
            return found;
        }
        snprintf(why, why_size, "MEMORIES_DISC names %s, which is neither a raw image of the Forbidden Memories "
                                "(USA) disc nor a yfm-disc.txt extracted from it.", named);
        return NULL;
    }
    if (!Paths_User(folder, sizeof(folder), "disc-path.txt") && (saved = fopen(folder, "rb"))) {
        size_t length = fread(found, 1, sizeof(found) - 1, saved);
        int complete = !ferror(saved) && fgetc(saved) == EOF;
        fclose(saved);
        found[length] = '\0';
        if (complete && length && strlen(found) == length && is_the_disc(found)) return found;
        found[0] = '\0';
    }
    if ((!Paths_Program(folder, sizeof(folder), "game") && search(folder)) || search(Paths_ProgramDir()) ||
        (!Paths_User(folder, sizeof(folder), "game") && search(folder)) || search("game")) {
        return found;
    }
    found[0] = '\0';
    snprintf(folder, sizeof(folder), "%s%cgame", Paths_ProgramDir(), SEPARATOR);
#ifdef _WIN32
    for (named = folder; *named; named++) {
        if (*named == '/') folder[named - folder] = '\\';   /* shown the way Explorer shows it */
    }
#endif
    snprintf(why, why_size,
             "The game's disc was not found.\n\n"
             "This port needs your own copy of Yu-Gi-Oh! Forbidden Memories (USA, SLUS-01411): the "
             ".bin of a .bin/.cue pair, or the folder tools/pc/extract_disc.py extracts from it "
             "(yfm-disc.txt and disc/). Put it in the \"game\" folder next to the program:\n\n%s\n\n"
             "Any file name ending in .bin will do.",
             folder);
    return NULL;
}

int GameFiles_SelectDisc(const char *path, char *why, size_t why_size)
{
    char saved[PATH_MAX_], temporary[PATH_MAX_];
    FILE *file;
    size_t length = strlen(path);
    int written;
    if (length >= sizeof(found) || !is_the_disc(path)) {
        snprintf(why, why_size, "That file could not be read as a Forbidden Memories (USA, SLUS-01411) disc.\n\n"
                 "Choose the raw .bin file from your .bin/.cue pair (rather than the .cue file), or the "
                 "yfm-disc.txt of a folder extracted from it.");
        return -1;
    }
    Paths_WriteBegin();
    if (Paths_User(saved, sizeof(saved), "disc-path.txt") ||
        Paths_User(temporary, sizeof(temporary), "disc-path.txt.tmp") || !(file = fopen(temporary, "wb"))) {
        char reason[1200];
        snprintf(saved, sizeof(saved), "%s/disc-path.txt", Paths_UserDir());
        snprintf(why, why_size, "Could not save your ROM location to %s", Paths_WriteError(reason, sizeof(reason), saved));
        return -1;
    }
    written = fwrite(path, 1, length, file) == length;
    if (fclose(file)) written = 0;
    if (!written || rename(temporary, saved)) {
        char reason[1200];
        Paths_WriteError(reason, sizeof(reason), saved); /* before remove() changes the reason */
        remove(temporary);
        snprintf(why, why_size, "Could not save your ROM location to %s", reason);
        return -1;
    }
    snprintf(found, sizeof(found), "%s", path);
    return 0;
}

int GameFiles_Setup(char *why, size_t why_size)
{
    char path[PATH_MAX_];
    const char *headless = getenv("MEMORIES_HEADLESS"), *named = getenv("MEMORIES_DISC");
    if (GameFiles_Disc(why, why_size)) return 1;
    if ((headless && *headless && strcmp(headless, "0")) || (named && *named)) return -1;
    for (;;) {
        int result = Platform_SelectDisc(path, sizeof(path), why, why_size);
        if (result <= 0) return result;
        if (!GameFiles_SelectDisc(path, why, why_size)) return 1;
        Platform_ShowError("Unable to use this ROM", why);
    }
}

unsigned char *GameFiles_ReadExecutable(const char *path, size_t *size)
{
    char why[256];
    DiscSource *disc = DiscSource_Open(path, why, sizeof(why));
    unsigned lba, length, at;
    unsigned char *data = NULL;
    if (!disc) return NULL;
    if (find_executable(disc, &lba, &length) && (data = malloc((length + SECTOR - 1) / SECTOR * SECTOR))) {
        for (at = 0; at < length; at += SECTOR) {
            if (!read_source(disc, lba + at / SECTOR, data + at)) {
                free(data);
                data = NULL;
                break;
            }
        }
    }
    DiscSource_Close(disc);
    if (data) *size = length;
    return data;
}
