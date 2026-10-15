/* View > Free Duel progress's font (src/pc/cards/font_art.c) off the real
 * WA_MRG.MRG under game/DATA (skipped when it is not there): each glyph
 * must be the cell found by hand (notes/pc-build.md) in its color ramp,
 * and a count is drawn through the real path.
 * MEMORIES_FONT_ART_SHEET=<file.ppm> writes counts in each color. */
#include "pc/cards/font_art.h"
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

static uint16_t word_at(long offset)
{
    unsigned char b[2];
    fseek(wa, offset, SEEK_SET);
    assert(fread(b, 1, 2, wa) == 2);
    return (uint16_t)(b[0] | b[1] << 8);
}

/* The hand decode: the font's page is the boot package's first 16 sectors
 * (0x1690), 64 words by 16 rows each, 4-bit; the ramps are the first 0x100
 * bytes of its sector 50, 16 colors a row. */
static uint32_t expected(int u, int v, int ramp)
{
    uint16_t word = word_at(0x1690L * 2048 + (long)(v / 16) * 2048 + ((v % 16) * 64 + u / 4) * 2), c;
    unsigned r, g, b;
    c = word_at((0x1690L + 50) * 2048 + (ramp * 16 + (word >> (u % 4 * 4) & 15)) * 2);
    if (!c) return 0;
    r = c & 31; g = c >> 5 & 31; b = c >> 10 & 31;
    return 0xFF000000u | (r << 3 | r >> 2) << 16 | (g << 3 | g >> 2) << 8 | (b << 3 | b >> 2);
}

static void check(char character, int u, int v, int ramp)
{
    const DiscArt *glyph = FontArt_Glyph(character, ramp);
    int x, y, opaque = 0;
    assert(glyph && glyph->width == 8 && glyph->height == 12);
    for (y = 0; y < 12; y++)
        for (x = 0; x < 8; x++) {
            assert(glyph->pixels[y * 8 + x] == expected(u + x, v + y, ramp));
            opaque += glyph->pixels[y * 8 + x] != 0;
        }
    assert(opaque > 8);
}

static void write_sheet(const char *path)
{
    enum { SHEET_W = 320, SHEET_H = 150 };
    static uint32_t pixels[SHEET_W * SHEET_H];
    static const char *counts[] = {"11/58", "58/58", "0/157", "9/12", "157/157", "3/61", "40/40"};
    MenuCanvas canvas = {pixels, SHEET_W, SHEET_W, SHEET_H, 0};
    FontArtView view = {0, 0, SHEET_W, 240 * SHEET_W / 320, 320};
    FILE *out;
    int i, x, y, w, h;
    for (i = 0; i < SHEET_W * SHEET_H; i++) pixels[i] = 0xFF2A3A34u;
    for (i = 0; i < FONT_ART_COLORS; i++) {
        FontArt_Draw(&canvas, &view, 300, 12 + i * 20, counts[i], i, &x, &y, &w, &h);
        assert(w == FontArt_Width(counts[i]) && h == 12);
    }
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
    const char *sheet = getenv("MEMORIES_FONT_ART_SHEET");
    int i, before, x, y, w, h;

    /* No disc: nothing is drawn, and the failure is kept. */
    assert(!FontArt_Ready() && !FontArt_Glyph('1', FONT_ART_WHITE));
    FontArt_Reset();

    wa = fopen(MEMORIES_SOURCE_DIR "/game/DATA/WA_MRG.MRG", "rb");
    if (!wa) {
        printf("font art: no game/DATA/WA_MRG.MRG, skipped\n");
        return 77;
    }
    fseek(wa, 0, SEEK_END);
    wa_size = ftell(wa);
    assert(FontArt_Ready());
    before = reads;
    assert(FontArt_Ready() && reads == before); /* read once */

    /* '0' ends row 0 after the first fifteen marks, '/' the last of them;
     * '1'-'9' then ':' start row 1. White and yellow ramps 0 and 1. */
    for (i = 0; i < FONT_ART_COLORS; i++) {
        check('0', 120, 0, i);
        check('/', 112, 0, i);
        check('1', 0, 12, i);
        check('9', 64, 12, i);
        check(':', 72, 12, i);
    }
    assert(expected(120 + 3, 5, FONT_ART_WHITE) != expected(120 + 3, 5, FONT_ART_YELLOW) ||
           !expected(120 + 3, 5, FONT_ART_WHITE));
    assert(!FontArt_Glyph('A', FONT_ART_WHITE) && !FontArt_Glyph(' ', FONT_ART_WHITE));
    assert(FontArt_Width("11/58") == 40);
    {
        uint32_t pixel = 0;
        MenuCanvas tiny = {&pixel, 1, 1, 1, 0};
        FontArtView nowhere = {0, 0, 0, 0, 320};
        FontArt_Draw(&tiny, &nowhere, 304, 23, "1/2", FONT_ART_WHITE, &x, &y, &w, &h);
        assert(!w && !h && pixel == 0);
    }
    if (sheet && *sheet) write_sheet(sheet);
    fclose(wa);
    printf("font art: ok\n");
    return 0;
}
