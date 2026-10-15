/* The European narrow letters (src/pc/text/serif.c): the serifs on a stem
 * drawn here, and, when game/DATA/WA_MRG.MRG is there, on the US font's own
 * i and l (the font's 4-bit page at sector 5776, as glyphs.c finds its
 * cells). MEMORIES_SERIF_PRINT=1 prints the disc's letters before and
 * after. */
#include "pc/text/serif.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef MEMORIES_SOURCE_DIR
#define MEMORIES_SOURCE_DIR "."
#endif

static int failures;

#define CHECK(condition)                                                                                               \
    do {                                                                                                               \
        if (!(condition)) {                                                                                            \
            fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition);                                            \
            failures++;                                                                                                \
        }                                                                                                              \
    } while (0)

typedef struct {
    unsigned char pixels[16][16];
    int width, height;
} Cell;

/* A bare stem with a dot over it, shaded as the US letters are: columns
 * `left` and `left` + 1, the left one darker, dark edges either side, the
 * outline (1) round it all. */
static void draw_stem(Cell *cell, int width, int height, int left, int dot, int top, int bottom)
{
    int x, y;
    memset(cell, 0, sizeof(*cell));
    cell->width = width;
    cell->height = height;
    for (y = top; y <= bottom; y++) {
        cell->pixels[y][left - 1] = 2;
        cell->pixels[y][left] = 10;
        cell->pixels[y][left + 1] = 15;
        cell->pixels[y][left + 2] = 2;
    }
    for (x = left - 1; x <= left + 2; x++) cell->pixels[top - 1][x] = cell->pixels[bottom + 1][x] = 1;
    if (dot >= 0) {
        for (x = left - 1; x <= left + 2; x++) cell->pixels[dot - 1][x] = cell->pixels[dot + 1][x] = 1;
        cell->pixels[dot][left] = 9;
        cell->pixels[dot][left + 1] = 12;
        cell->pixels[dot][left - 1] = cell->pixels[dot][left + 2] = 1;
    }
}

/* Every body pixel has something on all eight sides: the outline is closed. */
static int closed(const Cell *cell)
{
    int x, y, dx, dy;
    for (y = 0; y < cell->height; y++) {
        for (x = 0; x < cell->width; x++) {
            if (cell->pixels[y][x] < SERIF_BODY) continue;
            for (dy = -1; dy <= 1; dy++) {
                for (dx = -1; dx <= 1; dx++) {
                    int nx = x + dx, ny = y + dy;
                    if (nx < 0 || ny < 0 || nx >= cell->width || ny >= cell->height || !cell->pixels[ny][nx]) return 0;
                }
            }
        }
    }
    return 1;
}

static int body_run(const Cell *cell, int y, int *from)
{
    int x, count = 0;
    *from = -1;
    for (x = 0; x < cell->width; x++) {
        if (cell->pixels[y][x] >= SERIF_BODY) {
            if (*from < 0) *from = x;
            count++;
        }
    }
    return count;
}

static void synthetic(void)
{
    Cell cell, before, again;
    SerifStem stem;
    int x, y, from, changed = 0;

    /* The small font's i: a dot on row 1, the stem rows 4-9 in columns 3-4. */
    draw_stem(&cell, 8, 12, 3, 1, 4, 9);
    before = cell;
    CHECK(Serif_Stem(&cell.pixels[0][0], 16, 8, 12, &stem));
    CHECK(stem.left == 3 && stem.right == 4 && stem.top == 4 && stem.bottom == 9);
    CHECK(Serif_Add(&cell.pixels[0][0], 16, 8, 12, SERIF_REACH(0), 1));
    /* The foot: a pixel either side, in the row's brightest shade. */
    CHECK(body_run(&cell, 9, &from) == 4 && from == 2);
    CHECK(cell.pixels[9][2] == 15 && cell.pixels[9][5] == 15 && cell.pixels[9][3] == 10);
    /* The serif: a pixel left of the stem's first row, none on its right. */
    CHECK(body_run(&cell, 4, &from) == 3 && from == 2);
    CHECK(cell.pixels[4][2] == 15 && cell.pixels[4][5] == 2);
    /* The rows between and the dot are as they were. */
    for (y = 6; y <= 7; y++) CHECK(!memcmp(cell.pixels[y], before.pixels[y], sizeof(cell.pixels[y])));
    CHECK(!memcmp(cell.pixels[1], before.pixels[1], sizeof(cell.pixels[1])));
    CHECK(closed(&cell));
    /* Only the three pixels and outline: nothing that was ink is gone. */
    for (y = 0; y < 12; y++) {
        for (x = 0; x < 8; x++) {
            if (cell.pixels[y][x] == before.pixels[y][x]) continue;
            changed++;
            CHECK(cell.pixels[y][x] >= SERIF_BODY || (cell.pixels[y][x] == 1 && !before.pixels[y][x]));
        }
    }
    CHECK(changed > 3);
    /* Twice is once. */
    again = cell;
    CHECK(Serif_Add(&again.pixels[0][0], 16, 8, 12, SERIF_REACH(0), 1));
    CHECK(!memcmp(&again, &cell, sizeof(cell)));

    /* The small font's l: no dot, the stem from row 1 (the outline on 0). */
    draw_stem(&cell, 8, 12, 3, -1, 1, 9);
    CHECK(Serif_Add(&cell.pixels[0][0], 16, 8, 12, SERIF_REACH(0), 1));
    CHECK(cell.pixels[1][2] == 15 && body_run(&cell, 1, &from) == 3);
    CHECK(body_run(&cell, 9, &from) == 4 && from == 2);
    CHECK(cell.pixels[0][1] == 1 && closed(&cell));

    /* The large font's: two pixels either side of the foot, two left at the top. */
    draw_stem(&cell, 16, 16, 6, 2, 5, 12);
    CHECK(Serif_Add(&cell.pixels[0][0], 16, 16, 16, SERIF_REACH(1), 1));
    CHECK(body_run(&cell, 12, &from) == 6 && from == 4);
    CHECK(body_run(&cell, 5, &from) == 4 && from == 4);
    CHECK(closed(&cell));

    /* No room, or no stem: the cell stays as it was. */
    draw_stem(&cell, 8, 12, 1, -1, 1, 9);
    before = cell;
    CHECK(!Serif_Add(&cell.pixels[0][0], 16, 8, 12, SERIF_REACH(0), 1));
    CHECK(!memcmp(&cell, &before, sizeof(cell)));
    memset(&cell, 0, sizeof(cell));
    CHECK(!Serif_Stem(&cell.pixels[0][0], 16, 8, 12, &stem));
    CHECK(!Serif_Add(&cell.pixels[0][0], 16, 8, 12, 1, 1));
}

static void print(const Cell *a, const Cell *b)
{
    static const char hex[] = ".123456789ABCDEF";
    int x, y;
    for (y = 0; y < a->height; y++) {
        for (x = 0; x < a->width; x++) putchar(hex[a->pixels[y][x]]);
        printf("  ");
        for (x = 0; x < b->width; x++) putchar(hex[b->pixels[y][x]]);
        putchar('\n');
    }
    putchar('\n');
}

/* The US font's letters: letters by their Shift-JIS (a is 0x8281), small
 * cells 8x12 at u (sjis & 15) * 8, v (sjis - 0x8240) >> 4 rows of 12; large
 * 16x16 at v 0x48 on (glyphs.c, retail_cell). */
static void disc(void)
{
    static const char letters[] = "il";
    unsigned char page[0x6000];
    FILE *file = fopen(MEMORIES_SOURCE_DIR "/game/DATA/WA_MRG.MRG", "rb");
    int i, large, x, y, show = getenv("MEMORIES_SERIF_PRINT") != NULL;
    if (!file) {
        printf("serif: no game/DATA/WA_MRG.MRG, the US letters not checked\n");
        return;
    }
    if (fseek(file, 5776L * 2048, SEEK_SET) || fread(page, 1, sizeof(page), file) != sizeof(page)) {
        fclose(file);
        printf("serif: WA_MRG.MRG too short, the US letters not checked\n");
        return;
    }
    fclose(file);
    for (i = 0; letters[i]; i++) {
        unsigned sjis = 0x8281u + (unsigned)(letters[i] - 'a');
        for (large = 0; large < 2; large++) {
            Cell cell, before;
            SerifStem stem;
            int u = (int)(sjis & 15) * (large ? 16 : 8);
            int v = large ? (int)((sjis - 0x8240) >> 4) * 16 + 0x48 : (int)((sjis - 0x8240) >> 4) * 12, from;
            memset(&cell, 0, sizeof(cell));
            cell.width = large ? 16 : 8;
            cell.height = large ? 16 : 12;
            for (y = 0; y < cell.height; y++) {
                for (x = 0; x < cell.width; x++) {
                    unsigned char byte = page[(v + y) * 128 + (u + x) / 2];
                    cell.pixels[y][x] = (unsigned char)((u + x) & 1 ? byte >> 4 : byte & 15);
                }
            }
            before = cell;
            CHECK(Serif_Stem(&cell.pixels[0][0], 16, cell.width, cell.height, &stem));
            /* A two-pixel stem, as the letters were measured to have. */
            CHECK(stem.right - stem.left == 1);
            CHECK(Serif_Add(&cell.pixels[0][0], 16, cell.width, cell.height, SERIF_REACH(large), 1));
            CHECK(body_run(&cell, stem.bottom, &from) == 2 + 2 * SERIF_REACH(large) &&
                  from == stem.left - SERIF_REACH(large));
            CHECK(body_run(&cell, stem.top, &from) >= 2 + SERIF_REACH(large) && from == stem.left - SERIF_REACH(large));
            CHECK(closed(&cell) || !closed(&before));
            if (show) {
                printf("%c %s: stem columns %d-%d, rows %d-%d\n", letters[i], large ? "large" : "small", stem.left,
                       stem.right, stem.top, stem.bottom);
                print(&before, &cell);
            }
        }
    }
}

int main(void)
{
    synthetic();
    disc();
    if (failures) fprintf(stderr, "serif: %d failures\n", failures);
    else printf("serif: ok\n");
    return failures != 0;
}
