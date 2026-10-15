/* A number wider than its field drawn in the field's width
 * (src/pc/text/number_width.c). */
#include "pc/text/number_width.h"
#include <assert.h>
#include <stdio.h>

static int steps(int channel, int digits, int advance, int *each)
{
    int i, total = 0;
    for (i = 0; i < digits; i++) {
        each[i] = advance - NumberWidth_Take(channel);
        total += each[i];
    }
    return total;
}

int main(void)
{
    int each[8];
    /* Nothing squeezed: every glyph steps its advance. */
    assert(NumberWidth_Take(0) == 0 && NumberWidth_Take(3) == 0);
    /* Five digits in four cells of 8: 6, 6, 6, 7, 7, the field's 32 in all,
     * and the glyph after them steps its own 8. */
    NumberWidth_Squeeze(1, 5, 4, 8);
    assert(steps(1, 5, 8, each) == 32);
    assert(each[0] == 6 && each[1] == 6 && each[2] == 6 && each[3] == 7 && each[4] == 7);
    assert(NumberWidth_Take(1) == 0);
    /* Eight in six cells of 16 (the Password screen's starchips). */
    NumberWidth_Squeeze(2, 8, 6, 16);
    assert(steps(2, 8, 16, each) == 96 && each[0] == 12 && each[7] == 12);
    /* Channels apart; a new box forgets what was left. */
    NumberWidth_Squeeze(0, 7, 6, 8);
    assert(NumberWidth_Take(3) == 0);
    NumberWidth_Reset(0);
    assert(NumberWidth_Take(0) == 0);
    /* A number that fits, and channels out of range, change nothing. */
    NumberWidth_Squeeze(0, 4, 4, 8);
    NumberWidth_Squeeze(9, 5, 4, 8);
    NumberWidth_Squeeze(-1, 5, 4, 8);
    assert(NumberWidth_Take(0) == 0 && NumberWidth_Take(9) == 0 && NumberWidth_Take(-1) == 0);
    puts("number_width: ok");
    return 0;
}
