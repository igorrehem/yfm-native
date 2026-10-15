/* View > Duel rank's pictures (src/pc/cards/rank_art.c) off the real
 * WA_MRG.MRG under game/DATA (skipped when it is not there): the pieces the
 * result screen's sprite sheets name must be the texels found by hand
 * (notes/pc-build.md), and every rank is drawn through the real path.
 * MEMORIES_RANK_ART_SHEET=<file.ppm> writes the ten ranks and the digits. */
#include "pc/cards/rank_art.h"
#include "pc/sdk/disc.h"
#include "pc/text/overlay_text.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef MEMORIES_SOURCE_DIR
#define MEMORIES_SOURCE_DIR "."
#endif
#define FAKE_LBA 5000

static FILE *wa;
static long wa_size;
static int reads;

int Memories_DiscFileInfo(const char *path, int *lba, unsigned *size)
{
    if (!wa || strcmp(path, DISC_ART_WA_PATH)) return -1;
    *lba = FAKE_LBA;
    *size = (unsigned)wa_size;
    return 0;
}

int Memories_DiscReadSectors(int lba, int sectors, void *out)
{
    reads++;
    if (fseek(wa, (long)(lba - FAKE_LBA) * 2048, SEEK_SET)) return 0;
    return (int)(fread(out, 2048, (size_t)sectors, wa));
}

/* The opaque canvas's blend of overlay_text.c. */
void OverlayText_Blend(const MenuCanvas *canvas, int x, int y, uint32_t color, unsigned alpha)
{
    uint32_t *at, under;
    if (x < 0 || y < 0 || x >= canvas->width || y >= canvas->height || !alpha) return;
    at = canvas->pixels + (size_t)y * (size_t)canvas->stride + (size_t)x;
    under = *at;
#define MIX(shift) ((((color >> shift) & 255) * alpha + ((under >> shift) & 255) * (255 - alpha)) / 255)
    *at = 0xFF000000u | MIX(16) << 16 | MIX(8) << 8 | MIX(0);
#undef MIX
}

/* The hand decode: the image 4- or 8-bit at VRAM word x, row y of the
 * package phase that starts at `sector` and was placed from x0, y0, through
 * the palette at clut_x, clut_y of the 256-wide upload at palette_x0,
 * palette_y0 that palette_sector holds. */
static uint16_t word_at(long offset)
{
    unsigned char b[2];
    fseek(wa, offset, SEEK_SET);
    assert(fread(b, 1, 2, wa) == 2);
    return (uint16_t)(b[0] | b[1] << 8);
}
static uint16_t image_word(int sector, int x0, int y0, int x, int y)
{
    int column = (x - x0) / 64, row = y - y0, block = column * 16 + row / 16;
    return word_at((long)sector * 2048 + (long)block * 2048 + ((row % 16) * 64 + (x - x0) % 64) * 2);
}
static uint32_t expected(int sector, int x0, int y0, int depth, int page_x, int page_y, int u, int v,
                         int palette_sector, int palette_x0, int palette_y0, int clut_x, int clut_y)
{
    uint16_t word, c;
    int index;
    unsigned r, g, b;
    if (depth == 4) {
        word = image_word(sector, x0, y0, page_x + u / 4, page_y + v);
        index = word >> (u % 4 * 4) & 15;
    } else {
        word = image_word(sector, x0, y0, page_x + u / 2, page_y + v);
        index = word >> (u % 2 * 8) & 255;
    }
    c = word_at((long)palette_sector * 2048 + ((clut_y - palette_y0) * 256 + clut_x - palette_x0 + index) * 2);
    if (!c) return 0;
    r = c & 31; g = c >> 5 & 31; b = c >> 10 & 31;
    return 0xFF000000u | (r << 3 | r >> 2) << 16 | (g << 3 | g >> 2) << 8 | (b << 3 | b >> 2);
}

static void check_results(const DiscArt *art, int w, int h, int tu, int tv, int clut_x)
{
    int x, y, opaque = 0;
    assert(art && art->width == w && art->height == h);
    for (y = 0; y < h; y++)
        for (x = 0; x < w; x++) {
            uint32_t want = expected(0x1DAB, 0, 256, 4, 0, 256, tu + x, tv + y, 0x1DAB + 32, 0, 248, clut_x, 248);
            if (art->pixels[y * w + x] != want)
                fprintf(stderr, "%dx%d at %d,%d: %08x, not %08x\n", w, h, x, y, (unsigned)art->pixels[y * w + x],
                        (unsigned)want);
            assert(art->pixels[y * w + x] == want);
            opaque += want != 0;
        }
    assert(opaque > w * h / 4);
}

static void check_digit(int digit)
{
    const DiscArt *art = RankArt_Digit(digit);
    int x, y;
    assert(art && art->width == 8 && art->height == 8);
    for (y = 0; y < 8; y++)
        for (x = 0; x < 8; x++)
            assert(art->pixels[y * 8 + x] ==
                   expected(0x16C6, 768, 256, 8, 896, 256, digit * 8 + x, 88 + y, 0x16C6 + 64, 256, 240, 256, 241));
}

static void write_sheet(const char *path)
{
    enum { CELL_W = 200, CELL_H = 120, SHEET_W = CELL_W * 5 + 60, SHEET_H = CELL_H * 2 + 60 };
    static uint32_t pixels[SHEET_W * SHEET_H];
    MenuCanvas canvas = {pixels, SHEET_W, SHEET_W, SHEET_H, 0};
    FILE *out;
    int i, x, y, w, h;
    for (i = 0; i < SHEET_W * SHEET_H; i++) pixels[i] = 0xFF101418u;
    for (i = 0; i < 10; i++) {
        /* A 320x240 picture scaled 4x from the cell, the box at 12, 24 as at rest. */
        RankArtView view = {(i % 5) * CELL_W - 4 * 60, (i / 5) * CELL_H - 4 * 20, 1280, 960, 320};
        RankArt_Draw(&canvas, &view, 67, 24, i / 5, i % 5, i % 5 * 20 + 9, &x, &y, &w, &h);
        assert(w > 0 && h > 0);
    }
    for (i = 0; i < 10; i++) DiscArt_Draw(&canvas, RankArt_Digit(i), 10 + i * 40, CELL_H * 2 + 10, 32, 32);
    out = fopen(path, "wb");
    assert(out);
    fprintf(out, "P6\n%d %d\n255\n", SHEET_W, SHEET_H);
    for (y = 0; y < SHEET_H; y++)
        for (x = 0; x < SHEET_W; x++) {
            unsigned char rgb[3] = {(unsigned char)(pixels[y * SHEET_W + x] >> 16),
                                    (unsigned char)(pixels[y * SHEET_W + x] >> 8),
                                    (unsigned char)pixels[y * SHEET_W + x]};
            fwrite(rgb, 1, 3, out);
        }
    fclose(out);
}

int main(void)
{
    static const int letters[5][2] = {{40, 168}, {0, 168}, {80, 128}, {40, 128}, {0, 128}}; /* D C B A S */
    const char *sheet = getenv("MEMORIES_RANK_ART_SHEET");
    int i, before, x, y, w, h;
    uint32_t pixel = 0;
    MenuCanvas tiny = {&pixel, 1, 1, 1, 0};
    RankArtView nowhere = {0, 0, 0, 0, 320};

    /* No disc: nothing is drawn, and the failure is kept. */
    assert(!RankArt_Ready() && !RankArt_Badge(0));
    RankArt_Reset();

    wa = fopen(MEMORIES_SOURCE_DIR "/game/DATA/WA_MRG.MRG", "rb");
    if (!wa) {
        printf("rank art: no game/DATA/WA_MRG.MRG, skipped\n");
        return 77;
    }
    fseek(wa, 0, SEEK_END);
    wa_size = ftell(wa);
    assert(RankArt_Ready());
    before = reads;
    assert(RankArt_Ready() && reads == before); /* read once */

    /* Badge (POW at 184, 312 through palette 112; TEC at 184, 288, 96), the
     * stone plate (128, 288, palette 16) and the letters, each in its own
     * palette (D 208 ... S 144), all on page 0, 256 of the result package. */
    check_results(RankArt_Badge(0), 24, 24, 184, 56, 112);
    check_results(RankArt_Badge(1), 24, 24, 184, 32, 96);
    check_results(RankArt_Plate(), 56, 48, 128, 32, 16);
    for (i = 0; i < 5; i++) check_results(RankArt_Letter(i), 40, 40, letters[i][0], letters[i][1], 208 - i * 16);
    for (i = 0; i < 10; i++) check_digit(i);

    /* A picture with no size draws nothing. */
    RankArt_Draw(&tiny, &nowhere, 67, 24, 0, 4, 50, &x, &y, &w, &h);
    assert(!w && !h && pixel == 0);
    if (sheet && *sheet) write_sheet(sheet);
    fclose(wa);
    printf("rank art: ok\n");
    return 0;
}
