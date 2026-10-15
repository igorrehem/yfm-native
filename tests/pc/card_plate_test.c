/* The title plate a card's name is set on (cards/art.c): what a translated
 * or renamed card shows in place of the retail plate at every scale.
 *
 * Needs a serif face (Times on Windows, fontconfig's "Times" elsewhere);
 * without one it skips (77), as the game leaves the plate alone then.
 * MEMORIES_PLATE_DUMP=1 prints each plate, a digit an ink. */
#include "pc/cards/art.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* The art unit's two outside needs. */
uint32_t Glyphs_NextCharacter(const char **text)
{
    const unsigned char *s = (const unsigned char *)*text;
    uint32_t c = *s++;
    int more = c >= 0xF0 ? 3 : c >= 0xE0 ? 2 : c >= 0xC0 ? 1 : 0;
    if (more) c &= 0x3Fu >> more;
    while (more-- > 0 && (*s & 0xC0) == 0x80) c = c << 6 | (*s++ & 0x3F);
    *text = (const char *)s;
    return c;
}

#ifdef _WIN32
const char *Win32_SerifFontPath(void)
{
    static char path[512];
    const char *windows = getenv("WINDIR");
    FILE *file;
    snprintf(path, sizeof(path), "%s\\Fonts\\times.ttf", windows ? windows : "C:\\Windows");
    file = fopen(path, "rb");
    if (!file) return NULL;
    fclose(file);
    return path;
}
#endif

static int failures;

#define CHECK(condition, ...)                                                                                     \
    do {                                                                                                          \
        if (!(condition)) {                                                                                       \
            fprintf(stderr, "FAIL %s:%d: ", __FILE__, __LINE__);                                                  \
            fprintf(stderr, __VA_ARGS__);                                                                         \
            fputc('\n', stderr);                                                                                  \
            failures++;                                                                                           \
        }                                                                                                         \
    } while (0)

static int ink_at(const unsigned char *plate, int x, int y)
{
    unsigned char byte = plate[y * (CARD_TITLE_WIDTH / 2) + x / 2];
    return x & 1 ? byte >> 4 : byte & 15;
}

typedef struct {
    int left, right, top, bottom, inked, dark, bad;
} Extent;

static Extent measure(const unsigned char *plate)
{
    Extent e = {CARD_TITLE_WIDTH, -1, CARD_TITLE_HEIGHT, -1, 0, 0, 0};
    int x, y;
    for (y = 0; y < CARD_TITLE_HEIGHT; y++) {
        for (x = 0; x < CARD_TITLE_WIDTH; x++) {
            int ink = ink_at(plate, x, y);
            if (ink > 7) e.bad++;
            if (!ink) continue;
            e.inked++;
            if (ink <= 3) e.dark++;
            if (x < e.left) e.left = x;
            if (x > e.right) e.right = x;
            if (y < e.top) e.top = y;
            if (y > e.bottom) e.bottom = y;
        }
    }
    return e;
}

static void dump(const char *name, const unsigned char *plate)
{
    int x, y;
    if (!getenv("MEMORIES_PLATE_DUMP")) return;
    printf("%s\n", name);
    for (y = 0; y < CARD_TITLE_HEIGHT; y++) {
        for (x = 0; x < CARD_TITLE_WIDTH; x++) {
            int ink = ink_at(plate, x, y);
            putchar(ink ? '0' + ink : '.');
        }
        putchar('\n');
    }
}

int main(void)
{
    static const char *const names[] = {"Dancing Elf", "Elfa Dançarina", "Dragão do Trovão de Duas Cabeças",
                                        "Ávila Ção Ênio Úrsula"};
    unsigned char plate[CARD_TITLE_BYTES], wide_plate[CARD_TITLE_BYTES];
    unsigned i;
    memset(plate, 0xEE, sizeof(plate));
    if (!CardArt_TitleFromName("Dancing Elf", plate)) {
        printf("no serif face: skipped\n");
        return 77;
    }
    for (i = 0; i < sizeof(names) / sizeof(*names); i++) {
        Extent e;
        /* Whatever the plate held before, the name is set on a clear one:
         * index 0 lets the card's gold frame through, the retail plates'
         * whole background. */
        memset(plate, 0xEE, sizeof(plate));
        CHECK(CardArt_TitleFromName(names[i], plate), "%s: not set", names[i]);
        dump(names[i], plate);
        e = measure(plate);
        CHECK(!e.bad, "%s: %d texels outside the inks 0-7", names[i], e.bad);
        /* Stems in the dark inks, not a haze of faint ones. */
        CHECK(e.inked > 60 && e.dark > 30, "%s: too little ink (%d, %d dark)", names[i], e.inked, e.dark);
        CHECK(e.left >= 2 && e.right <= 93, "%s: ink in columns %d-%d, past 3-93", names[i], e.left, e.right);
        CHECK(e.top >= 0 && e.bottom <= CARD_TITLE_HEIGHT - 1 && e.bottom >= 9, "%s: ink in rows %d-%d", names[i],
              e.top, e.bottom);
        CHECK(e.inked < CARD_TITLE_WIDTH * CARD_TITLE_HEIGHT / 2, "%s: more ink than clear (%d)", names[i], e.inked);
        /* Clear round the edges, as every retail plate's border is. */
        CHECK(ink_at(plate, 0, 0) == 0 && ink_at(plate, 95, 0) == 0 && ink_at(plate, 95, 13) == 0,
              "%s: a corner inked", names[i]);
    }
    /* A long name is squeezed into the plate, not cut off: it reaches as
     * far right as the room goes, and a short one stops well before. */
    CardArt_TitleFromName("Dragão do Trovão de Duas Cabeças", wide_plate);
    CHECK(measure(wide_plate).right >= 88, "the long name ends at column %d", measure(wide_plate).right);
    CardArt_TitleFromName("Dancing Elf", plate);
    CHECK(measure(plate).right < 80, "the short name runs to column %d", measure(plate).right);
    /* Accents are drawn above the letters, inside the plate. */
    CardArt_TitleFromName("Ávila", plate);
    CardArt_TitleFromName("Avila", wide_plate);
    CHECK(measure(plate).top < measure(wide_plate).top, "Á is no taller than A (rows %d, %d)", measure(plate).top,
          measure(wide_plate).top);
    CHECK(measure(plate).top >= 0, "the accent is cut off");
    /* The same name gives the same plate: a card's plate is made once. */
    CardArt_TitleFromName("Elfa Dançarina", plate);
    CardArt_TitleFromName("Elfa Dançarina", wide_plate);
    CHECK(!memcmp(plate, wide_plate, sizeof(plate)), "the same name set twice differs");
    if (failures) return 1;
    printf("card plates ok\n");
    return 0;
}
