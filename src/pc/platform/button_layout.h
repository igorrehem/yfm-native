#ifndef MEMORIES_PC_BUTTON_LAYOUT_H
#define MEMORIES_PC_BUTTON_LAYOUT_H

#include <stdint.h>

/* View > Japanese buttons (SET_JP_BUTTONS, `jp_buttons`). The port runs the
 * USA release, which confirms with Cross (or Square) and cancels with
 * Circle. The Japanese release confirms with Circle (or Square) and cancels
 * with Cross: on every screen matched in both, its button checks are the
 * USA's with Cross and Circle exchanged (the card viewer's close button is
 * the one exception that is not a plain exchange). So exchanging the two
 * bits of the pad state the game reads gives the Japanese layout on every
 * screen, the ones not yet matched included, with no change to the game.
 *
 * libetc.c's run_vblank applies it once per pad and VBlank, to both pads, to
 * what the player's own keyboard and controllers press. `fixed` are bits
 * that keep their meaning: scripted input (MEMORIES_INPUT, MEMORIES_INPUT2),
 * written in the USA layout, and the mouse, whose right button is "back".
 * Bits are in the controller's order, as Platform_Pad reports them. */
#define BUTTON_LAYOUT_CIRCLE 0x2000u
#define BUTTON_LAYOUT_CROSS 0x4000u

static inline uint16_t ButtonLayout_Apply(uint16_t bits, uint16_t fixed, int japanese)
{
    unsigned own = (unsigned)bits & ~(unsigned)fixed;
    if (!japanese) return bits;
    own = (own & ~(BUTTON_LAYOUT_CIRCLE | BUTTON_LAYOUT_CROSS)) | (own & BUTTON_LAYOUT_CIRCLE) << 1 |
          (own & BUTTON_LAYOUT_CROSS) >> 1;
    return (uint16_t)(own | ((unsigned)bits & fixed));
}

#endif
