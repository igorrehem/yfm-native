/* Pgxp_MaybeVertexWord (pc/compat/pgxp.h): DrawOTag's cheap pre-filter
 * before a PGXP table lookup. A stored word packs two int16_t screen
 * coordinates; the GTE never projects past -1024..1023, and LIBGS adds at
 * most a screen's offset (well under 1024 more), so a real vertex's x and y
 * both stay within +-2048. Color, texture and OT command words routinely do
 * not. This is the boundary itself, checked directly rather than only
 * through DrawOTag's own behaviour. */
#include "pc/compat/pgxp.h"
#include <assert.h>

static uint32_t word(int16_t x, int16_t y)
{
    return ((uint32_t)(uint16_t)x) | (((uint32_t)(uint16_t)y) << 16);
}

int main(void)
{
    /* Comfortably inside: both halves accepted. */
    assert(Pgxp_MaybeVertexWord(word(0, 0)));
    assert(Pgxp_MaybeVertexWord(word(-1024, 1023)));
    assert(Pgxp_MaybeVertexWord(word(2047, -2048)));

    /* The boundary itself, on each side, on x and on y independently. */
    assert(Pgxp_MaybeVertexWord(word(2047, 0)));
    assert(!Pgxp_MaybeVertexWord(word(2048, 0)));
    assert(Pgxp_MaybeVertexWord(word(-2048, 0)));
    assert(!Pgxp_MaybeVertexWord(word(-2049, 0)));
    assert(Pgxp_MaybeVertexWord(word(0, 2047)));
    assert(!Pgxp_MaybeVertexWord(word(0, 2048)));
    assert(Pgxp_MaybeVertexWord(word(0, -2048)));
    assert(!Pgxp_MaybeVertexWord(word(0, -2049)));

    /* One half out is enough to reject the whole word. */
    assert(!Pgxp_MaybeVertexWord(word(2048, -2048)));
    assert(!Pgxp_MaybeVertexWord(word(-2048, 2048)));

    /* Realistic non-vertex words: a POLY_FT4's color word and its
     * tpage/clut word, both far outside on at least one half. Checked by
     * hand against the same halves Pgxp_MaybeVertexWord decodes, not
     * assumed: an OT link/count word was tried here first and turned out to
     * decode inside the window on both halves for some values, which would
     * have made this test wrong instead of the code -- worth remembering
     * next time a "surely this is never a vertex" word is picked by eye. */
    assert(!Pgxp_MaybeVertexWord(0x00808080u)); /* r0/g0/b0 = 0x80 each, code byte 0 */
    assert(!Pgxp_MaybeVertexWord(0x0d00a000u)); /* tpage 0xa0, clut selector high byte 0x0d */
    return 0;
}
