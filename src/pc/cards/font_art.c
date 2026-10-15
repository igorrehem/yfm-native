/* The game's text font off the disc (font_art.h). */
#include "font_art.h"
#include <stdio.h>
#include <string.h>

/* Main_RunBootSequence's package, WA sectors 0x1690-0x16C5, as
 * Main_LoadBootPackageStage places it: 48 sectors of image from VRAM
 * 0x280, 0 (the font is on the first column's page, its first 16 sectors),
 * and at 0x280, 0xE8 the 16 x 8 text color ramps, the first 0x100 bytes of
 * the package's 51st sector. The small font is 4-bit on that page, 8 x 12 a
 * cell (glyphs.c, retail_cell, has where func_80035E20 finds each). */
enum {
    BOOT_SECTOR = 0x1690, FONT_PAGE_SECTORS = 16, FONT_X = 0x280, FONT_Y = 0,
    RAMP_SECTOR = BOOT_SECTOR + 50, RAMP_X = 0x280, RAMP_Y = 0xE8, RAMP_W = 16, RAMP_H = 8
};

/* The retail punctuation by its Shift-JIS order in the font: the first 15
 * fill row 0 before '0', the rest follow '9' on row 1. */
static const char punctuation[] = "!\"#$%&'()*+,-./:;<=>?";

static struct {
    int state; /* 0 unread, 1 read, -1 not readable */
    DiscArt digit[FONT_ART_COLORS][10], mark[FONT_ART_COLORS][sizeof(punctuation) - 1];
} art;

/* A digit's or a listed mark's cell (the caller passes nothing else). */
static void cell(char character, int *u, int *v)
{
    int mark;
    if (character == '0') {
        *u = 15 * FONT_ART_W;
        *v = 0;
    } else if (character >= '1' && character <= '9') {
        *u = (character - '1') * FONT_ART_W;
        *v = FONT_ART_H;
    } else {
        mark = (int)(strchr(punctuation, character) - punctuation);
        *u = mark < 15 ? mark * FONT_ART_W : mark * FONT_ART_W - 0x30;
        *v = mark < 15 ? 0 : FONT_ART_H;
    }
}

static int read_art(void)
{
    int color, i, u, v;
    if (!DiscArt_LoadImage(BOOT_SECTOR, FONT_PAGE_SECTORS, FONT_X, FONT_Y) ||
        !DiscArt_LoadRect(RAMP_SECTOR, 0, RAMP_X, RAMP_Y, RAMP_W, RAMP_H))
        return 0;
    for (color = 0; color < FONT_ART_COLORS; color++) {
        for (i = 0; i < 10; i++) {
            cell((char)('0' + i), &u, &v);
            if (!DiscArt_Cut(&art.digit[color][i], FONT_X, FONT_Y, 4, u, v, FONT_ART_W, FONT_ART_H, RAMP_X,
                             RAMP_Y + color))
                return 0;
        }
        for (i = 0; punctuation[i]; i++) {
            cell(punctuation[i], &u, &v);
            if (!DiscArt_Cut(&art.mark[color][i], FONT_X, FONT_Y, 4, u, v, FONT_ART_W, FONT_ART_H, RAMP_X,
                             RAMP_Y + color))
                return 0;
        }
    }
    return 1;
}

void FontArt_Reset(void)
{
    int color, i;
    for (color = 0; color < FONT_ART_COLORS; color++) {
        for (i = 0; i < 10; i++) DiscArt_Free(&art.digit[color][i]);
        for (i = 0; punctuation[i]; i++) DiscArt_Free(&art.mark[color][i]);
    }
    art.state = 0;
}

int FontArt_Ready(void)
{
    if (!art.state) {
        if (!read_art()) {
            FontArt_Reset();
            art.state = -1;
            fprintf(stderr, "memories-pc: free duel progress: the game's font is not on this disc\n");
        } else {
            art.state = 1;
        }
        /* The glyphs are cut; the private VRAM is not needed again. */
        DiscArt_Reset();
    }
    return art.state > 0;
}

const DiscArt *FontArt_Glyph(char character, int color)
{
    const char *mark;
    if (art.state <= 0 || color < 0 || color >= FONT_ART_COLORS || !character) return NULL;
    if (character >= '0' && character <= '9') return &art.digit[color][character - '0'];
    mark = strchr(punctuation, character);
    return mark ? &art.mark[color][mark - punctuation] : NULL;
}

int FontArt_Width(const char *text) { return (int)strlen(text) * FONT_ART_W; }

static int window_x(const FontArtView *view, int x)
{ return view->x + view->w / 2 + (x - 160) * view->w / view->width_2d; }
static int window_y(const FontArtView *view, int y) { return view->y + y * view->h / 240; }

void FontArt_Draw(MenuCanvas *canvas, const FontArtView *view, int right, int middle, const char *text, int color,
                  int *x, int *y, int *w, int *h)
{
    int left = right - FontArt_Width(text), top = middle - FONT_ART_H / 2, i, x0, y0, x1, y1;
    *x = *y = *w = *h = 0;
    if (!FontArt_Ready() || view->w <= 0 || view->h <= 0 || view->width_2d <= 0 || !*text) return;
    for (i = 0; text[i]; i++) {
        int from = window_x(view, left + i * FONT_ART_W), to = window_x(view, left + (i + 1) * FONT_ART_W);
        DiscArt_Draw(canvas, FontArt_Glyph(text[i], color), from, window_y(view, top), to - from,
                     window_y(view, top + FONT_ART_H) - window_y(view, top));
    }
    x0 = window_x(view, left);
    y0 = window_y(view, top);
    x1 = window_x(view, right);
    y1 = window_y(view, top + FONT_ART_H);
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 > canvas->width) x1 = canvas->width;
    if (y1 > canvas->height) y1 = canvas->height;
    if (x1 <= x0 || y1 <= y0) return;
    *x = x0;
    *y = y0;
    *w = x1 - x0;
    *h = y1 - y0;
}
