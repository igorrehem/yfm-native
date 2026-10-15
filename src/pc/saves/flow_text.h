#ifndef MEMORIES_PC_SAVES_FLOW_TEXT_H
#define MEMORIES_PC_SAVES_FLOW_TEXT_H
/* For the overlay menus (save_menu.c, deck_menu.c) when the free width is
 * narrower than their text: `text` split where it has a run of three or
 * more spaces (the columns of a slot's details, the hints' clauses) and set
 * left-aligned on as few lines of `w` as hold the pieces, `line_h` apart
 * from the middle `y`. Without a canvas it only counts. Returns the number
 * of lines; *widest (when given) gets the widest piece. */
#include "pc/platform/menu.h"
#include <stdint.h>
#include <string.h>

typedef int (*FlowTextWidth)(const char *text);
typedef void (*FlowTextDraw)(MenuCanvas *canvas, int x, int y, const char *text, uint32_t color);

static inline int FlowText(MenuCanvas *canvas, int x, int w, int y, int line_h, const char *text, uint32_t color,
                           int *widest, FlowTextWidth width, FlowTextDraw draw)
{
    char line[256] = "", piece[200], joined[256];
    int lines = 0;
    if (widest) *widest = 0;
    while (*text) {
        const char *end = strstr(text, "   ");
        size_t n = end ? (size_t)(end - text) : strlen(text), used = strlen(line), gap = used ? 3 : 0;
        int fits;
        if (n >= sizeof(piece)) n = sizeof(piece) - 1;
        memcpy(piece, text, n);
        piece[n] = '\0';
        if (widest && width(piece) > *widest) *widest = width(piece);
        fits = used + gap + n < sizeof(joined);
        if (fits) {
            memcpy(joined, line, used);
            memcpy(joined + used, "   ", gap);
            memcpy(joined + used + gap, piece, n + 1);
        }
        if (used && (!fits || width(joined) > w)) {
            if (canvas) draw(canvas, x, y + lines * line_h, line, color);
            lines++;
            memcpy(line, piece, n + 1);
        } else if (fits) {
            memcpy(line, joined, used + gap + n + 1);
        }
        text += n;
        while (*text == ' ') text++;
    }
    if (line[0]) {
        if (canvas) draw(canvas, x, y + lines * line_h, line, color);
        lines++;
    }
    return lines;
}

#endif
