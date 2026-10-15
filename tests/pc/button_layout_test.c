#include "pc/platform/button_layout.h"
#include <assert.h>
#include <stdio.h>

/* View > Japanese buttons: Cross and Circle exchange, nothing else moves,
 * and the bits the player did not press keep their meaning. */
int main(void)
{
    unsigned bits;
    for (bits = 0; bits <= 0xffffu; bits++) {
        uint16_t b = (uint16_t)bits, jp = ButtonLayout_Apply(b, 0, 1);
        assert(ButtonLayout_Apply(b, 0, 0) == b);
        assert(ButtonLayout_Apply(b, 0xffff, 1) == b);
        assert((jp & 0x9fffu) == (b & 0x9fffu));
        assert(!(jp & 0x2000u) == !(b & 0x4000u) && !(jp & 0x4000u) == !(b & 0x2000u));
        assert(ButtonLayout_Apply(jp, 0, 1) == b);
    }
    assert(ButtonLayout_Apply(0x4000, 0, 1) == 0x2000); /* Cross: back */
    assert(ButtonLayout_Apply(0x2000, 0, 1) == 0x4000); /* Circle: confirm */
    assert(ButtonLayout_Apply(0x8000, 0, 1) == 0x8000); /* Square confirms in both */
    /* Scripted Cross stays Cross beside a pressed Circle, which becomes Cross. */
    assert(ButtonLayout_Apply(0x6000, 0x4000, 1) == 0x4000);
    /* The mouse's right button (Circle) stays back; a pressed Cross turns into Circle too. */
    assert(ButtonLayout_Apply(0x2000, 0x2000, 1) == 0x2000);
    assert(ButtonLayout_Apply(0x6000, 0x2000, 1) == 0x2000);
    puts("button layout: ok");
    return 0;
}
