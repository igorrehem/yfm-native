/* Game > Language (language.h): the text packs in languages/, and the PAL
 * discs they are written from (read too, when a pack is not there). */
#include "pc/compat/fs.h"
#include "language.h"
#include "entry_layout.h"
#include "pal_text.h"
#include "glyphs.h"
#include "pc/debug/log.h"
#include "pc/platform/game_files.h"
#include "pc/platform/paths.h"
#include "pc/platform/settings.h"
#include <ctype.h>
#include <dirent.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SECTOR 2048
#define PATH_SIZE 1024
#define MAX_DISCS 16
/* DATA/WA_MRG.MRG: language n's pack from sector 6498 + 110 n; its text
 * files at these sectors of the pack, each with a u16 id first. */
#define PACK_FIRST 6498u
#define PACK_SECTORS 110u
#define FILE_A_SECTOR 41u
#define FILE_B_SECTOR 71u
#define FILE_C_SECTOR 103u
/* The glyph table in the executable: 0x801D9000 past its 0x800 header. */
#define GLYPH_TABLE_AT (0x801D9000u - 0x80010000u + 0x800u)

/* The PAL discs by serial, SLES-03947 to 03951; each executable's name. */
enum { SERIAL_FIRST = 47, SERIALS = 5 };

typedef struct {
    char path[PATH_SIZE];
    int serial;                 /* 0 Europe (English), 1 France, 2 Germany, 3 Italy, 4 Spain */
    unsigned exe_lba, wa_lba, wa_size;
} Disc;

static Disc discs[MAX_DISCS];
/* scanned: the folders beside the US disc were looked in (its place may
 * not be known yet on the first launch, before the player picks it). */
static int disc_count, scanned, current;

/* Tried in turn for a language: its own disc first, then the Italian and
 * Spanish ones (which carry the final text of all four), then the French and
 * German (an earlier German and Spanish). English only from its own. */
static const int preference[LANGUAGE_COUNT][SERIALS] = {
    {-1}, {0, -1}, {1, 3, 4, 2, -1}, {2, 3, 4, 1, -1}, {3, 4, 1, 2, -1}, {4, 3, 1, 2, -1}};

const char *Language_Label(int language)
{
    static const char *const labels[LANGUAGE_COUNT] = {"English (US)", "English (Europe)", "Français",
                                                       "Deutsch",      "Italiano",         "Español"};
    return language >= 0 && language < LANGUAGE_COUNT ? labels[language] : "";
}

static unsigned le16(const unsigned char *bytes) { return bytes[0] | bytes[1] << 8; }

static int read_bytes(FILE *file, unsigned lba, unsigned char *out, size_t count)
{
    unsigned char sector[SECTOR];
    while (count) {
        size_t n = count < SECTOR ? count : SECTOR;
        if (!GameFiles_ReadSector(file, lba++, sector)) return 0;
        memcpy(out, sector, n);
        out += n;
        count -= n;
    }
    return 1;
}

/* A PAL disc of the game: its serial from SYSTEM.CNF, its executable and
 * the WA_MRG. */
static int identify(const char *path, Disc *disc)
{
    FILE *file = fopen(path, "rb");
    unsigned char cnf[SECTOR + 1];
    unsigned lba, size;
    const char *at;
    char exe[16];
    int ok = 0;
    if (!file) return 0;
    if (GameFiles_FindFile(file, "SYSTEM.CNF", &lba, &size) && size < SECTOR && GameFiles_ReadSector(file, lba, cnf)) {
        cnf[size] = '\0';
        at = strstr((const char *)cnf, "SLES_039.");
        if (at && isdigit((unsigned char)at[9]) && isdigit((unsigned char)at[10])) {
            int serial = (at[9] - '0') * 10 + (at[10] - '0') - SERIAL_FIRST;
            snprintf(exe, sizeof(exe), "SLES_039.%c%c", at[9], at[10]);
            if (serial >= 0 && serial < SERIALS && GameFiles_FindFile(file, exe, &disc->exe_lba, &size) &&
                size > GLYPH_TABLE_AT + PAL_GLYPH_TABLE_SIZE &&
                GameFiles_FindFile(file, "DATA/WA_MRG.MRG", &disc->wa_lba, &disc->wa_size)) {
                disc->serial = serial;
                snprintf(disc->path, sizeof(disc->path), "%s", path);
                ok = 1;
            }
        }
    }
    fclose(file);
    return ok;
}

/* Whether the disc's pack for PAL language `slot` holds that language: its
 * three files' ids (the English disc leaves the others empty). */
static int has_slot(const Disc *disc, int slot)
{
    static const unsigned sectors[3] = {FILE_A_SECTOR, FILE_B_SECTOR, FILE_C_SECTOR};
    FILE *file;
    unsigned pack = disc->wa_lba + PACK_FIRST + PACK_SECTORS * (unsigned)slot;
    int i, ok = (PACK_FIRST + PACK_SECTORS * (unsigned)(slot + 1)) * SECTOR <= disc->wa_size;
    if (!ok || !(file = fopen(disc->path, "rb"))) return 0;
    for (i = 0; i < 3 && ok; i++) {
        unsigned char id[2];
        ok = read_bytes(file, pack + sectors[i], id, 2) && le16(id) == 0x0Fu + 3u * (unsigned)slot + (unsigned)i;
    }
    fclose(file);
    return ok;
}

static int ends_with(const char *name, const char *suffix)
{
    size_t n = strlen(name), m = strlen(suffix), i;
    if (n <= m) return 0;
    for (i = 0; i < m; i++) {
        if (tolower((unsigned char)name[n - m + i]) != suffix[i]) return 0;
    }
    return 1;
}

/* The .bin a .cue names (its first FILE line), beside the .cue. */
static int cue_image(const char *cue, char *out, size_t size)
{
    FILE *file = fopen(cue, "rb");
    char line[512], *name, *end;
    const char *slash;
    int found = 0;
    if (!file) return 0;
    while (!found && fgets(line, sizeof(line), file)) {
        for (name = line; isspace((unsigned char)*name); name++) {}
        if (strncmp(name, "FILE", 4) || !isspace((unsigned char)name[4])) continue;
        for (name += 4; isspace((unsigned char)*name); name++) {}
        if (*name == '"') {
            end = strchr(++name, '"');
        } else {
            for (end = name; *end && !isspace((unsigned char)*end); end++) {}
        }
        if (!end || end == name) break;
        *end = '\0';
        slash = strrchr(cue, '/');
#ifdef _WIN32
        if (!slash || strrchr(cue, '\\') > slash) slash = strrchr(cue, '\\');
#endif
        found = snprintf(out, size, "%.*s%s", slash ? (int)(slash - cue + 1) : 0, cue, name) < (int)size;
    }
    fclose(file);
    return found;
}

static void add_disc(const char *path)
{
    Disc disc;
    int i;
    for (i = 0; i < disc_count; i++) {
        if (!strcmp(discs[i].path, path)) return;
    }
    if (disc_count < MAX_DISCS && identify(path, &disc)) {
        discs[disc_count++] = disc;
        LOG(LOG_MODS, "language: %s is SLES-039%02d", path, SERIAL_FIRST + disc.serial);
    }
}

static void scan_folder(const char *folder)
{
    DIR *directory = opendir(folder);
    struct dirent *entry;
    char path[PATH_SIZE], image[PATH_SIZE];
    if (!directory) return;
    while ((entry = readdir(directory))) {
        if (snprintf(path, sizeof(path), "%s/%s", folder, entry->d_name) >= (int)sizeof(path)) continue;
        if (ends_with(entry->d_name, ".bin")) add_disc(path);
        else if (ends_with(entry->d_name, ".cue") && cue_image(path, image, sizeof(image))) add_disc(image);
    }
    closedir(directory);
}

static void scan(void)
{
    const char *named = getenv("MEMORIES_LANGUAGES_DIR");
    char folder[PATH_SIZE], base[PATH_SIZE], why[256];
    const char *disc, *slash;
    if (scanned) return;
    if (named && *named) {
        scan_folder(named);
        scanned = 1;
        return;
    }
    /* Beside the US disc, then in the usual game folders. */
    if ((disc = GameFiles_Disc(why, sizeof(why)))) {
        slash = strrchr(disc, '/');
#ifdef _WIN32
        if (!slash || strrchr(disc, '\\') > slash) slash = strrchr(disc, '\\');
#endif
        snprintf(base, sizeof(base), "%.*s", slash ? (int)(slash - disc) : 1, slash ? disc : ".");
        snprintf(folder, sizeof(folder), "%s/languages", base);
        scan_folder(folder);
        snprintf(folder, sizeof(folder), "%s/pal", base);
        scan_folder(folder);
        scanned = 1;
    }
    if (!Paths_Program(folder, sizeof(folder), "game/languages")) scan_folder(folder);
    if (!Paths_Program(folder, sizeof(folder), "game/pal")) scan_folder(folder);
    scan_folder("game/languages");
    scan_folder("game/pal");
}

/* The disc to read `language` from, or NULL. */
static const Disc *disc_for(int language)
{
    static signed char found[LANGUAGE_COUNT], asked[LANGUAGE_COUNT];
    int i, j;
    if (language <= LANGUAGE_US || language >= LANGUAGE_COUNT) return NULL;
    if (!asked[language] || (found[language] < 0 && !scanned)) {
        asked[language] = 1;
        found[language] = -1;
        scan();
        for (i = 0; i < SERIALS && preference[language][i] >= 0 && found[language] < 0; i++) {
            for (j = 0; j < disc_count && found[language] < 0; j++) {
                if (discs[j].serial == preference[language][i] && has_slot(&discs[j], language - 1)) {
                    found[language] = (signed char)j;
                }
            }
        }
    }
    return found[language] >= 0 ? &discs[found[language]] : NULL;
}

/* A disc's pack, as a listing (pal_text.h). */
static char *disc_listing(int language, size_t *length, char *origin, size_t origin_size)
{
    const Disc *disc = disc_for(language);
    int slot = language - 1, problems = 0;
    unsigned char *pack;
    unsigned wa_pack;
    char *listing = NULL;
    FILE *file;
    if (!disc) return NULL;
    pack = malloc(PAL_FILE_A_SIZE + PAL_FILE_B_SIZE + PAL_FILE_C_SIZE + PAL_GLYPH_TABLE_SIZE);
    if (!pack || !(file = fopen(disc->path, "rb"))) {
        free(pack);
        return NULL;
    }
    wa_pack = disc->wa_lba + PACK_FIRST + PACK_SECTORS * (unsigned)slot;
    if (read_bytes(file, wa_pack + FILE_A_SECTOR, pack, PAL_FILE_A_SIZE) &&
        read_bytes(file, wa_pack + FILE_B_SECTOR, pack + PAL_FILE_A_SIZE, PAL_FILE_B_SIZE) &&
        read_bytes(file, wa_pack + FILE_C_SECTOR, pack + PAL_FILE_A_SIZE + PAL_FILE_B_SIZE, PAL_FILE_C_SIZE) &&
        read_bytes(file, disc->exe_lba + GLYPH_TABLE_AT / SECTOR,
                   pack + PAL_FILE_A_SIZE + PAL_FILE_B_SIZE + PAL_FILE_C_SIZE, PAL_GLYPH_TABLE_SIZE)) {
        PalTextPack text = {pack, pack + PAL_FILE_A_SIZE, pack + PAL_FILE_A_SIZE + PAL_FILE_B_SIZE,
                            pack + PAL_FILE_A_SIZE + PAL_FILE_B_SIZE + PAL_FILE_C_SIZE};
        listing = PalText_Listing(&text, slot, length, &problems);
    }
    fclose(file);
    free(pack);
    snprintf(origin, origin_size, "%s, %d problems", disc->path, problems);
    return listing;
}

static int disc_available(int language) { return disc_for(language) != NULL; }

/* The text packs: languages/<name>.txt beside the program (or in the
 * working folder, or in MEMORIES_LANGUAGES_DIR), each the listing
 * disc_listing gives for the language, written by
 * tools/pc/export_languages.py. */
static const char *const pack_names[LANGUAGE_COUNT] = {NULL, "en-eu", "fr", "de", "it", "es"};
#define PACK_LIMIT (16u << 20)

static FILE *open_pack(int language, char *path, size_t size)
{
    const char *named = getenv("MEMORIES_LANGUAGES_DIR");
    char relative[64];
    FILE *file;
    if (language <= LANGUAGE_US || language >= LANGUAGE_COUNT) return NULL;
    if (named && *named) {
        snprintf(path, size, "%s/%s.txt", named, pack_names[language]);
        return fopen(path, "rb");
    }
    snprintf(relative, sizeof(relative), "languages/%s.txt", pack_names[language]);
    if (!Paths_Program(path, size, relative) && (file = fopen(path, "rb"))) return file;
    snprintf(path, size, "%s", relative);
    return fopen(path, "rb");
}

static int pack_available(int language)
{
    static signed char found[LANGUAGE_COUNT];
    char path[PATH_SIZE];
    FILE *file;
    if (language <= LANGUAGE_US || language >= LANGUAGE_COUNT) return 0;
    if (!found[language]) {
        file = open_pack(language, path, sizeof(path));
        found[language] = file ? 1 : -1;
        if (file) fclose(file);
    }
    return found[language] > 0;
}

/* A pack's listing as it is, but for carriage returns (an editor's). */
static char *pack_listing(int language, size_t *length, char *origin, size_t origin_size)
{
    char path[PATH_SIZE], *text = NULL;
    FILE *file = open_pack(language, path, sizeof(path));
    long size;
    size_t n = 0, i;
    if (!file) return NULL;
    if (!fseek(file, 0, SEEK_END) && (size = ftell(file)) > 0 && (unsigned long)size < PACK_LIMIT &&
        !fseek(file, 0, SEEK_SET) && (text = malloc((size_t)size + 1)) &&
        fread(text, 1, (size_t)size, file) == (size_t)size) {
        for (i = 0; i < (size_t)size; i++) {
            if (text[i] != '\r') text[n++] = text[i];
        }
        text[n] = '\0';
        *length = n;
        snprintf(origin, origin_size, "%s", path);
    } else {
        free(text);
        text = NULL;
    }
    fclose(file);
    return text;
}

/* Where a language's text can come from, tried in order: the pack, then
 * the disc it is written from. Each says whether it has the language, and
 * gives its listing (malloc'd) and where it came from. */
typedef struct {
    int (*available)(int language);
    char *(*listing)(int language, size_t *length, char *origin, size_t origin_size);
} Source;
static const Source sources[] = {{pack_available, pack_listing}, {disc_available, disc_listing}};
#define SOURCE_COUNT ((int)(sizeof(sources) / sizeof(sources[0])))

/* The listing of `language` from the first source that has it. */
static char *source_listing(int language, size_t *length, char *origin, size_t origin_size)
{
    char *listing = NULL;
    int i;
    for (i = 0; i < SOURCE_COUNT && !listing; i++) {
        if (sources[i].available(language)) listing = sources[i].listing(language, length, origin, origin_size);
    }
    return listing;
}

int Language_Available(int language)
{
    int i;
    if (language == LANGUAGE_US) return 1;
    if (language < 0 || language >= LANGUAGE_COUNT) return 0;
    for (i = 0; i < SOURCE_COUNT; i++) {
        if (sources[i].available(language)) return 1;
    }
    return 0;
}

int Language_Current(void) { return current; }

const char *Language_Code(int language)
{
    if (language == LANGUAGE_US) return "en-us";
    return language > LANGUAGE_US && language < LANGUAGE_COUNT ? pack_names[language] : "";
}

void Language_Drop(void)
{
    current = LANGUAGE_US;
    TextEntries_UseLayout(0);
    Glyphs_SetEuropean(0);
}

/* The port's own words (text.h, TEXT_OWN_*), in the languages that have
 * them written; the rest keep the port's English, which English (EU) says
 * as it is. The deck in the card shop's menu (FE10) is the game's own word
 * for it (CONSTRUIRE JEU, STAPEL ZUSAMMENSTELLEN, CREA MAZZO, CREAR MAZO);
 * the small letters of the card drops' headings draw the accented capitals.
 * The French NEW is cut short with a full stop, as the PAL text cuts words
 * (ESCI DAL NEGO.): past three letters it takes room from the card's name.
 * The card packs' words (FE20-FE39) take the Password screen's own QUIT and
 * END (its EXCHANGE / QUIT and OK / END). */
static const char *const own_words[LANGUAGE_COUNT] = {
    [LANGUAGE_FR] = "\n@bank dialog\n\n"
                    "[FE00]\nNOUV.{end}\n\n"
                    "[FE01]\n%d CARTE DE PLUS{end}\n\n"
                    "[FE02]\n%d CARTES DE PLUS{end}\n\n"
                    "[FE03]\nPAGE %d SUR %d{end}\n\n"
                    "[FE10]\nJEUX{end}\n\n"
                    "[FE20]\nPAQUETS{end}\n\n"
                    "[FE21]\nACHETER{end}\n\n"
                    "[FE22]\nQUITTER{end}\n\n"
                    "[FE23]\nRETOUR{end}\n\n"
                    "[FE24]\nINFO{end}\n\n"
                    "[FE25]\nSUITE{end}\n\n"
                    "[FE26]\nPASSER{end}\n\n"
                    "[FE27]\nOK{end}\n\n"
                    "[FE28]\nFIN{end}\n\n"
                    "[FE29]\nÉPUISÉ{end}\n\n"
                    "[FE2A]\nRESTE %d{end}\n\n"
                    "[FE2B]\n%d CARTES{end}\n\n"
                    "[FE2C]\nVERROUILLÉ{end}\n\n"
                    "[FE2D]\nBATS %s{end}\n\n"
                    "[FE2E]\nBATS %s %d FOIS{end}\n\n"
                    "[FE2F]\nGAGNE %d DUELS{end}\n\n"
                    "[FE30]\nAVANCE L'HISTOIRE{end}\n\n"
                    "[FE31]\nPOSSÈDE %s{end}\n\n"
                    "[FE32]\nPOSSÈDE %d %s{end}\n\n"
                    "[FE33]\nDÉPENSE ENCORE %d{end}\n\n"
                    "[FE34]\nOUVRE ENCORE %d{end}\n\n"
                    "[FE35]\nOUVRE %s x%d{end}\n\n"
                    "[FE36]\nAU MOINS %d %s{end}\n\n"
                    "[FE37]\n%s EN %d PAQUETS{end}\n\n"
                    "[FE38]\n%d CARTE{end}\n\n"
                    "[FE39]\nPLUS RIEN{end}\n",
    [LANGUAGE_DE] = "\n@bank dialog\n\n"
                    "[FE00]\nNEU{end}\n\n"
                    "[FE01]\n%d WEITERE KARTE{end}\n\n"
                    "[FE02]\n%d WEITERE KARTEN{end}\n\n"
                    "[FE03]\nSEITE %d VON %d{end}\n\n"
                    "[FE10]\nSTAPEL{end}\n\n"
                    "[FE20]\nBOOSTER{end}\n\n"
                    "[FE21]\nKAUFEN{end}\n\n"
                    "[FE22]\nBEENDEN{end}\n\n"
                    "[FE23]\nZURÜCK{end}\n\n"
                    "[FE24]\nINFO{end}\n\n"
                    "[FE25]\nWEITER{end}\n\n"
                    "[FE26]\nALLE{end}\n\n"
                    "[FE27]\nOK{end}\n\n"
                    "[FE28]\nEND{end}\n\n"
                    "[FE29]\nAUSVERKAUFT{end}\n\n"
                    "[FE2A]\nNOCH %d{end}\n\n"
                    "[FE2B]\n%d KARTEN{end}\n\n"
                    "[FE2C]\nGESPERRT{end}\n\n"
                    "[FE2D]\nBESIEGE %s{end}\n\n"
                    "[FE2E]\nBESIEGE %s %dx{end}\n\n"
                    "[FE2F]\nGEWINNE %d DUELLE{end}\n\n"
                    "[FE30]\nIN DER STORY WEITER{end}\n\n"
                    "[FE31]\nBESITZE %s{end}\n\n"
                    "[FE32]\nBESITZE %d %s{end}\n\n"
                    "[FE33]\nNOCH %d AUSGEBEN{end}\n\n"
                    "[FE34]\nNOCH %d ÖFFNEN{end}\n\n"
                    "[FE35]\nÖFFNE %s x%d{end}\n\n"
                    "[FE36]\nMINDESTENS %d %s{end}\n\n"
                    "[FE37]\n%s IN %d BOOSTERN{end}\n\n"
                    "[FE38]\n%d KARTE{end}\n\n"
                    "[FE39]\nSCHON ALLE{end}\n",
    [LANGUAGE_IT] = "\n@bank dialog\n\n"
                    "[FE00]\nNUOVA{end}\n\n"
                    "[FE01]\n%d CARTA IN PIÙ{end}\n\n"
                    "[FE02]\n%d CARTE IN PIÙ{end}\n\n"
                    "[FE03]\nPAGINA %d DI %d{end}\n\n"
                    "[FE10]\nMAZZI{end}\n\n"
                    "[FE20]\nBUSTE{end}\n\n"
                    "[FE21]\nCOMPRA{end}\n\n"
                    "[FE22]\nESCI{end}\n\n"
                    "[FE23]\nINDIETRO{end}\n\n"
                    "[FE24]\nINFO{end}\n\n"
                    "[FE25]\nAVANTI{end}\n\n"
                    "[FE26]\nSALTA{end}\n\n"
                    "[FE27]\nOK{end}\n\n"
                    "[FE28]\nEND{end}\n\n"
                    "[FE29]\nESAURITO{end}\n\n"
                    "[FE2A]\nRESTANO %d{end}\n\n"
                    "[FE2B]\n%d CARTE{end}\n\n"
                    "[FE2C]\nBLOCCATO{end}\n\n"
                    "[FE2D]\nBATTI %s{end}\n\n"
                    "[FE2E]\nBATTI %s %d VOLTE{end}\n\n"
                    "[FE2F]\nVINCI %d DUELLI{end}\n\n"
                    "[FE30]\nAVANZA NELLA STORIA{end}\n\n"
                    "[FE31]\nPOSSIEDI %s{end}\n\n"
                    "[FE32]\nPOSSIEDI %d %s{end}\n\n"
                    "[FE33]\nSPENDI ALTRI %d{end}\n\n"
                    "[FE34]\nAPRI ALTRE %d BUSTE{end}\n\n"
                    "[FE35]\nAPRI %s x%d{end}\n\n"
                    "[FE36]\nALMENO %d %s{end}\n\n"
                    "[FE37]\n%s IN %d BUSTE{end}\n\n"
                    "[FE38]\n%d CARTA{end}\n\n"
                    "[FE39]\nGIÀ TUTTE{end}\n",
    [LANGUAGE_ES] = "\n@bank dialog\n\n"
                    "[FE00]\nNUEVA{end}\n\n"
                    "[FE01]\n%d CARTA MÁS{end}\n\n"
                    "[FE02]\n%d CARTAS MÁS{end}\n\n"
                    "[FE03]\nPÁGINA %d DE %d{end}\n\n"
                    "[FE10]\nMAZOS{end}\n\n"
                    "[FE20]\nSOBRES{end}\n\n"
                    "[FE21]\nCOMPRAR{end}\n\n"
                    "[FE22]\nSALIR{end}\n\n"
                    "[FE23]\nVOLVER{end}\n\n"
                    "[FE24]\nINFO{end}\n\n"
                    "[FE25]\nSIGUE{end}\n\n"
                    "[FE26]\nSALTAR{end}\n\n"
                    "[FE27]\nOK{end}\n\n"
                    "[FE28]\nEND{end}\n\n"
                    "[FE29]\nAGOTADO{end}\n\n"
                    "[FE2A]\nQUEDAN %d{end}\n\n"
                    "[FE2B]\n%d CARTAS{end}\n\n"
                    "[FE2C]\nBLOQUEADO{end}\n\n"
                    "[FE2D]\nVENCE A %s{end}\n\n"
                    "[FE2E]\nVENCE A %s x%d{end}\n\n"
                    "[FE2F]\nGANA %d DUELOS{end}\n\n"
                    "[FE30]\nAVANZA LA HISTORIA{end}\n\n"
                    "[FE31]\nTEN %s{end}\n\n"
                    "[FE32]\nTEN %d %s{end}\n\n"
                    "[FE33]\nGASTA %d MÁS{end}\n\n"
                    "[FE34]\nABRE %d SOBRES MÁS{end}\n\n"
                    "[FE35]\nABRE %s x%d{end}\n\n"
                    "[FE36]\nAL MENOS %d %s{end}\n\n"
                    "[FE37]\n%s EN %d SOBRES{end}\n\n"
                    "[FE38]\n%d CARTA{end}\n\n"
                    "[FE39]\nYA TODAS{end}\n",
};

/* The opponents' short names (TEXT_OWN_OPPONENT + id), only where
 * shortening the PAL name (Tables_ShortenName) loses who it is: the French
 * put the name before the title ("Sébek le Gardien" would be "Gardien",
 * like Néku), and Duel Master K would be "Duels" or "K". The rest shorten
 * as the English do. Added after own_words. */
static const char *const own_names[LANGUAGE_COUNT] = {
    [LANGUAGE_FR] = "\n@bank dialog\n\n"
                    "[FE56]\nSekmeton{end}\n\n"
                    "[FE58]\nAnubis{end}\n\n"
                    "[FE5A]\nAtenza{end}\n\n"
                    "[FE5C]\nMarthis{end}\n\n"
                    "[FE5E]\nKépurah{end}\n\n"
                    "[FE61]\nSébek{end}\n\n"
                    "[FE62]\nNéku{end}\n\n"
                    "[FE67]\nMaître K{end}\n",
    [LANGUAGE_IT] = "\n@bank dialog\n\n"
                    "[FE55]\nOceano{end}\n\n"
                    "[FE67]\nMaestro K{end}\n",
    [LANGUAGE_ES] = "\n@bank dialog\n\n"
                    "[FE67]\nMaestro K{end}\n",
};

/* `listing` (`*length` bytes, malloc'd) with `extra` after it, if it can
 * grow. */
static char *append(char *listing, size_t *length, const char *extra)
{
    size_t size;
    char *longer;
    if (!extra) return listing;
    size = strlen(extra);
    longer = realloc(listing, *length + size + 1);
    if (!longer) return listing;
    memcpy(longer + *length, extra, size + 1);
    *length += size;
    return longer;
}

char *Language_Listing(size_t *length)
{
    int language = Settings_Get(SET_LANGUAGE);
    char *listing, origin[PATH_SIZE + 64] = "";
    if (language <= LANGUAGE_US || language >= LANGUAGE_COUNT) return NULL;
    listing = source_listing(language, length, origin, sizeof(origin));
    if (!listing) {
        LOG(LOG_MODS, "language: no text for %s (languages/%s.txt); English (US)", Language_Label(language),
            pack_names[language]);
        return NULL;
    }
    if (own_words[language]) {
        size_t extra = strlen(own_words[language]);
        char *longer = realloc(listing, *length + extra + 1);
        if (longer) {
            memcpy(longer + *length, own_words[language], extra + 1);
            *length += extra;
            listing = longer;
        }
    }
    listing = append(listing, length, own_names[language]);
    current = language;
    TextEntries_UseLayout(1); /* the PAL game's text entries (entry_layout.h) */
    /* Its narrow letters as the PAL font has them (glyphs.h). */
    Glyphs_SetEuropean(1);
    LOG(LOG_MODS, "language: %s from %s", Language_Label(language), origin);
    return listing;
}

int Language_Advance(unsigned flags, int code, int *shift)
{
    *shift = 0;
    /* The small letters (0x100) and the entries of 0x80 are the US code's
     * own paths, which PAL does not space either. */
    if (current == LANGUAGE_US || (flags & 0x180)) return 0;
    return PalText_Advance(Glyphs_Character(code), shift);
}

int Language_PastWidth(unsigned flags, int channel, int count, int step, int cell, int limit)
{
    /* The width each text channel has drawn since its count was last reset
     * (F8 07 and the box's start set it to 0, so the first letter after is
     * count 1). */
    static int width[16];
    if (current == LANGUAGE_US || channel < 0 || channel >= 16) return -1;
    /* Reset first: a small letter can be the first after an F8 07. */
    if (count == 1) width[channel] = 0;
    if (flags & 0x180) return -1;
    return PalText_PastWidth(&width[channel], step, cell, limit);
}

int Language_Export(const char *folder)
{
    int language, missing = 0;
    for (language = LANGUAGE_US + 1; language < LANGUAGE_COUNT; language++) {
        char path[PATH_SIZE], origin[PATH_SIZE + 64] = "";
        size_t length = 0;
        char *listing = source_listing(language, &length, origin, sizeof(origin));
        FILE *file;
        snprintf(path, sizeof(path), "%s/%s.txt", folder, pack_names[language]);
        if (!listing) {
            printf("%s: no pack or PAL disc has it\n", pack_names[language]);
            missing++;
            continue;
        }
        if (!(file = fopen(path, "wb")) || fwrite(listing, 1, length, file) != length) {
            printf("%s: could not write %s\n", pack_names[language], path);
            missing++;
        } else {
            printf("%s: %s\n", pack_names[language], origin);
        }
        if (file) fclose(file);
        free(listing);
    }
    return missing ? 1 : 0;
}
