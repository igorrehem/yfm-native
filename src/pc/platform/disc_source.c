/* The disc's sectors from a raw image or an extracted folder (disc_source.h). */
#include "pc/compat/posix.h"
#include "disc_source.h"
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define RAW DISC_SOURCE_SECTOR
#define DATA 2048
#define USER 24
#define ENTRIES 64
#define LINE 1200

enum { KIND_IMAGE, KIND_DATA, KIND_RAW };

typedef struct Entry {
    int kind, first, count, fd;
    long long offset;  /* KIND_RAW: the first sector's place in its file, in sectors */
    unsigned size;     /* KIND_DATA: the file's bytes */
    unsigned char subheader[4], last[4];
} Entry;

struct DiscSource {
    int sectors, count;
    Entry entries[ENTRIES];
};

/* The standard CD-ROM EDC and ECC (ECMA-130): the generator polynomials'
 * tables, filled once by DiscSource_Open, before any signal can read. */
static unsigned char ecc_f[256], ecc_b[256];
static uint32_t edc_table[256];
static int tables_ready;

static void make_tables(void)
{
    unsigned i, k;
    if (tables_ready) return;
    for (i = 0; i < 256; i++) {
        unsigned j = (i << 1) ^ (i & 0x80 ? 0x11D : 0);
        uint32_t edc = i;
        ecc_f[i] = (unsigned char)j;
        ecc_b[i ^ (j & 0xFF)] = (unsigned char)i;
        for (k = 0; k < 8; k++) edc = (edc >> 1) ^ (edc & 1 ? 0xD8018001u : 0);
        edc_table[i] = edc;
    }
    tables_ready = 1;
}

static void ecc_block(unsigned char *sector, unsigned major_count, unsigned minor_count, unsigned major_mult,
                      unsigned minor_inc, unsigned char *out)
{
    unsigned size = major_count * minor_count, major, minor;
    for (major = 0; major < major_count; major++) {
        unsigned index = (major >> 1) * major_mult + (major & 1);
        unsigned char a = 0, b = 0;
        for (minor = 0; minor < minor_count; minor++) {
            unsigned char t = sector[12 + index];
            index += minor_inc;
            if (index >= size) index -= size;
            a ^= t;
            b ^= t;
            a = ecc_f[a];
        }
        a = ecc_b[ecc_f[a] ^ b];
        out[major] = a;
        out[major + major_count] = a ^ b;
    }
}

/* A MODE2/Form1 sector's EDC and ECC; the address takes no part in the ECC. */
static void form1_tail(unsigned char *sector)
{
    unsigned char address[4];
    uint32_t edc = 0;
    unsigned i;
    for (i = 0x10; i < 0x818; i++) edc = (edc >> 8) ^ edc_table[(edc ^ sector[i]) & 0xFF];
    sector[0x818] = (unsigned char)edc;
    sector[0x819] = (unsigned char)(edc >> 8);
    sector[0x81A] = (unsigned char)(edc >> 16);
    sector[0x81B] = (unsigned char)(edc >> 24);
    memcpy(address, sector + 12, 4);
    memset(sector + 12, 0, 4);
    ecc_block(sector, 86, 24, 2, 86, sector + 0x81C);
    ecc_block(sector, 52, 43, 86, 88, sector + 0x8C8);
    memcpy(sector + 12, address, 4);
}

static unsigned char bcd(int value) { return (unsigned char)(((value / 10) << 4) | (value % 10)); }

static int read_at(int fd, void *out, unsigned length, long long offset)
{
    unsigned char *to = out;
    while (length) {
        long got = (long)pread(fd, to, length, offset);
        if (got <= 0) return 0;
        to += got;
        offset += got;
        length -= (unsigned)got;
    }
    return 1;
}

int DiscSource_Read(DiscSource *source, int lba, unsigned char *out)
{
    const Entry *entry = NULL;
    int lo = 0, hi, index;
    if (!source || lba < 0 || lba >= source->sectors) return 0;
    hi = source->count;
    while (lo < hi) { /* the last entry starting at or before lba */
        int mid = (lo + hi) / 2;
        if (source->entries[mid].first <= lba) lo = mid + 1;
        else hi = mid;
    }
    if (!lo) return 0;
    entry = &source->entries[lo - 1];
    index = lba - entry->first;
    if (index >= entry->count) return 0;
    if (entry->kind == KIND_IMAGE || entry->kind == KIND_RAW) {
        return read_at(entry->fd, out, RAW, (entry->offset + index) * (long long)RAW);
    } else {
        unsigned position = (unsigned)index * DATA, bytes = entry->size - position;
        int position_on_disc = lba + 150;
        if (bytes > DATA) bytes = DATA;
        memset(out, 0, RAW);
        memset(out + 1, 0xFF, 10);
        out[12] = bcd(position_on_disc / 4500);
        out[13] = bcd(position_on_disc / 75 % 60);
        out[14] = bcd(position_on_disc % 75);
        out[15] = 2;
        memcpy(out + 16, index == entry->count - 1 ? entry->last : entry->subheader, 4);
        memcpy(out + 20, out + 16, 4);
        if (!read_at(entry->fd, out + USER, bytes, position)) return 0;
        form1_tail(out);
        return 1;
    }
}

int DiscSource_Sectors(const DiscSource *source)
{
    return source ? source->sectors : 0;
}

void DiscSource_Close(DiscSource *source)
{
    int i;
    if (!source) return;
    for (i = 0; i < source->count; i++) {
        if (source->entries[i].fd >= 0) close(source->entries[i].fd);
    }
    free(source);
}

int DiscSource_IsIndex(const char *path)
{
    size_t length = strlen(path), name = strlen(DISC_SOURCE_INDEX);
    return length >= name && !strcmp(path + length - name, DISC_SOURCE_INDEX) &&
           (length == name || path[length - name - 1] == '/' || path[length - name - 1] == '\\');
}

static int open_file(const char *path)
{
    return open(path, O_RDONLY
#ifdef _WIN32
                | O_BINARY
#endif
    );
}

static long long file_size(int fd)
{
    struct stat info;
    return fstat(fd, &info) ? -1 : (long long)info.st_size;
}

static int hex4(const char *text, unsigned char *out)
{
    unsigned i, value;
    if (strlen(text) != 8) return 0;
    for (i = 0; i < 4; i++) {
        if (sscanf(text + 2 * i, "%2x", &value) != 1) return 0;
        out[i] = (unsigned char)value;
    }
    return 1;
}

static DiscSource *fail(DiscSource *source, char *why, size_t why_size, const char *path, const char *what)
{
    snprintf(why, why_size, "%s: %s", path, what);
    DiscSource_Close(source);
    return NULL;
}

/* Each raw Form1 sector is rebuilt with this file's EDC/ECC and compared:
 * the folder's data sectors depend on that code being the disc's. */
static int self_test(const Entry *entry)
{
    unsigned char sector[RAW], rebuilt[RAW];
    int i;
    for (i = 0; i < entry->count && i < 32; i++) {
        if (!read_at(entry->fd, sector, RAW, (entry->offset + i) * (long long)RAW)) return 0;
        if (sector[15] != 2 || (sector[18] & 0x20)) continue;
        memcpy(rebuilt, sector, RAW);
        form1_tail(rebuilt);
        if (memcmp(rebuilt, sector, RAW)) return 0;
    }
    return 1;
}

static DiscSource *open_index(const char *path, char *why, size_t why_size)
{
    DiscSource *source = calloc(1, sizeof(*source));
    char line[LINE], folder[LINE], file[LINE * 2], kind[16], a[16], b[16], name[LINE];
    const char *slash = strrchr(path, '/');
    FILE *index;
    int next = 0, tested = 0, version = 0;
#ifdef _WIN32
    if (!slash || strrchr(path, '\\') > slash) slash = strrchr(path, '\\');
#endif
    if (!source) return fail(NULL, why, why_size, path, "out of memory");
    snprintf(folder, sizeof(folder), "%.*s", slash ? (int)(slash - path) : 1, slash ? path : ".");
    if (!(index = fopen(path, "rb"))) return fail(source, why, why_size, path, "cannot be read");
    if (!fgets(line, sizeof(line), index) || sscanf(line, "yfm-disc %d", &version) != 1 || version != 1 ||
        !fgets(line, sizeof(line), index) || sscanf(line, "sectors %d", &source->sectors) != 1 ||
        source->sectors <= 0) {
        fclose(index);
        return fail(source, why, why_size, path, "is not a disc index written by tools/pc/extract_disc.py");
    }
    while (fgets(line, sizeof(line), index)) {
        Entry *entry;
        long long first, count, third, have;
        if (!strncmp(line, "source-sha256 ", 14) || line[0] == '\n' || line[0] == '\r') continue;
        if (source->count == ENTRIES) break;
        entry = &source->entries[source->count];
        memset(entry, 0, sizeof(*entry));
        entry->fd = -1;
        if (sscanf(line, "%15s %lld %lld %lld %15s %15s %1199s", kind, &first, &count, &third, a, b, name) == 7 &&
            !strcmp(kind, "data") && hex4(a, entry->subheader) && hex4(b, entry->last)) {
            entry->kind = KIND_DATA;
            entry->size = (unsigned)third;
            if (third <= (count - 1) * DATA || third > count * DATA) break;
        } else if (sscanf(line, "%15s %lld %lld %lld %1199s", kind, &first, &count, &third, name) == 5 &&
                   !strcmp(kind, "raw") && third >= 0) {
            entry->kind = KIND_RAW;
            entry->offset = third;
        } else {
            break;
        }
        if (first != next || count <= 0 || first + count > source->sectors || strstr(name, "..")) break;
        entry->first = (int)first;
        entry->count = (int)count;
        snprintf(file, sizeof(file), "%s/%s", folder, name);
        if ((entry->fd = open_file(file)) < 0) {
            fclose(index);
            source->count++;
            return fail(source, why, why_size, file, "is missing (extract the disc again with tools/pc/extract_disc.py)");
        }
        source->count++;
        have = file_size(entry->fd);
        if (entry->kind == KIND_DATA ? have != entry->size : have < (entry->offset + count) * RAW) {
            fclose(index);
            return fail(source, why, why_size, file, "does not have the size the index gives it");
        }
        if (entry->kind == KIND_RAW && entry->first == 0) {
            make_tables();
            if (!self_test(entry)) {
                fclose(index);
                return fail(source, why, why_size, file, "its sectors do not match the port's EDC/ECC");
            }
            tested = 1;
        }
        next = (int)(first + count);
    }
    fclose(index);
    if (next != source->sectors || !tested) {
        return fail(source, why, why_size, path, "does not account for every sector of the disc");
    }
    make_tables();
    return source;
}

DiscSource *DiscSource_Open(const char *path, char *why, size_t why_size)
{
    DiscSource *source;
    long long size;
    if (!path) return NULL;
    if (DiscSource_IsIndex(path)) return open_index(path, why, why_size);
    if (!(source = calloc(1, sizeof(*source)))) return fail(NULL, why, why_size, path, "out of memory");
    source->count = 1;
    source->entries[0].kind = KIND_IMAGE;
    if ((source->entries[0].fd = open_file(path)) < 0) return fail(source, why, why_size, path, "cannot be read");
    size = file_size(source->entries[0].fd);
    if (size <= 0 || size % RAW || size / RAW > INT32_MAX) {
        return fail(source, why, why_size, path, "is not a raw 2352-byte-sector image");
    }
    source->sectors = (int)(size / RAW);
    source->entries[0].count = source->sectors;
    return source;
}
