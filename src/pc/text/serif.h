#ifndef MEMORIES_PC_SERIF_H
#define MEMORIES_PC_SERIF_H
/* The European releases' narrow letters, drawn from the US font's (with a
 * PAL language on, glyphs.h): the PAL font is a slab serif whose i and l
 * fill the six pixels the PAL gives them, where the US i and l are a bare
 * two-pixel stem, so "li" and "il" leave a gap wider than any other pair.
 * The US stem gets the PAL's serifs, measured on the PAL font's own i and l
 * (research only; nothing of either font is kept in the source):
 *
 *   - a foot: the stem's last row reaches `reach` pixels further on either
 *     side (the PAL's small i and l, 8x16: one; its large ones, 12x16: two);
 *   - a serif at the top left: the stem's first row (under the i's dot, the
 *     top of the l) reaches `reach` pixels further left;
 *
 * each new pixel in the brightest index of the stem on its row (the US
 * letters shade a stroke across by its row), the dark outline round it.
 * The rest of the letter is left as it is. Pure: a cell of 4-bit indices
 * in, the same cell out, so a test can check it without the game. */

/* Indices from here up are a letter's body; below, its dark edges and
 * outline (the US font's small and large cells). */
#define SERIF_BODY 6

typedef struct {
    int left, right;   /* the stem's body columns */
    int top, bottom;   /* its first and last rows */
} SerifStem;

/* How far a serif reaches past the stem: the small font's one pixel, the
 * large's two. */
#define SERIF_REACH(large) ((large) ? 2 : 1)

/* The stem of a narrow letter in a `width` x `height` cell (`pitch` bytes a
 * row): its columns from the body on the row above its last (a foot, once
 * it has one, is wider), its rows from its last up to where the body stops
 * (the gap under the i's dot or its mark). 0 when the cell has none. */
int Serif_Stem(const unsigned char *cell, int pitch, int width, int height, SerifStem *stem);

/* The serifs onto the narrow letter in `cell`, `outline` the index round
 * the letters. 0 when it has no stem, or the serifs would not fit in the
 * cell (the cell is then unchanged). */
int Serif_Add(unsigned char *cell, int pitch, int width, int height, int reach, int outline);

#endif
