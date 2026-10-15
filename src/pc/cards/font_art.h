#ifndef MEMORIES_PC_FONT_ART_H
#define MEMORIES_PC_FONT_ART_H
/* The game's text font off the disc (disc_art.h) for View > Free Duel
 * progress: the 8x12 letters its text boxes are set in, in the text
 * colors the game has (FONT_ART_WHITE, FONT_ART_YELLOW, ...). */
#include "disc_art.h"

/* The text color ramps in the order the boot package holds them, which is
 * the order of gText_abColorSlots' values. */
enum { FONT_ART_WHITE, FONT_ART_YELLOW, FONT_ART_BLUE, FONT_ART_GREEN, FONT_ART_GREY, FONT_ART_ORANGE,
       FONT_ART_RED, FONT_ART_COLORS,
       FONT_ART_COLOURS = FONT_ART_COLORS };   /* the released SDKs' spelling (v0.2.0), for mods built against them */
enum { FONT_ART_W = 8, FONT_ART_H = 12 };

/* Where the game picture is in the window, and the width its 2D is laid
 * out in (320, or 426 in widescreen, where it stays centred). */
typedef struct { int x, y, w, h, width_2d; } FontArtView;

/* Reads the font the first time (a failure is kept, and logged once). 1
 * when it is there. */
int FontArt_Ready(void);
/* A digit, '/' or other retail punctuation in a color; NULL for anything
 * else, or before FontArt_Ready. */
const DiscArt *FontArt_Glyph(char character, int color);
/* Width in game picture pixels, a letter each FONT_ART_W. */
int FontArt_Width(const char *text);
/* `text` with its right edge at `right` and centred on `middle`, in game
 * picture pixels; the bounds covered come back in x, y, w, h (all 0 when
 * nothing was drawn). */
void FontArt_Draw(MenuCanvas *canvas, const FontArtView *view, int right, int middle, const char *text, int color,
                  int *x, int *y, int *w, int *h);
void FontArt_Reset(void);
#endif
