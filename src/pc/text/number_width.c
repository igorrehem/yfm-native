#include "number_width.h"

#define CHANNELS 4

static struct {
    int left;     /* glyphs of the number still to step */
    int digits;   /* how many it has */
    int total;    /* pixels to take off their steps, all together */
} squeezes[CHANNELS];

void NumberWidth_Squeeze(int channel, int digits, int field, int advance)
{
    if (channel < 0 || channel >= CHANNELS || digits <= field || field <= 0 || advance <= 0) return;
    squeezes[channel].left = digits;
    squeezes[channel].digits = digits;
    squeezes[channel].total = (digits - field) * advance;
}

void NumberWidth_Reset(int channel)
{
    if (channel >= 0 && channel < CHANNELS) squeezes[channel].left = 0;
}

int NumberWidth_Take(int channel)
{
    int i;
    if (channel < 0 || channel >= CHANNELS || squeezes[channel].left <= 0) return 0;
    /* The i-th glyph of the number: the pixels shared out, the first glyphs
     * taking the one left over each (5 in 4 cells of 8: 2, 2, 2, 1, 1). */
    i = squeezes[channel].digits - squeezes[channel].left--;
    return squeezes[channel].total / squeezes[channel].digits +
           (i < squeezes[channel].total % squeezes[channel].digits ? 1 : 0);
}
