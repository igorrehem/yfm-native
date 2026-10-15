/* Exercise the actual packet sorter with Exodia's out-of-range depth. */
#include "types.h"
#include "psyq/libgte.h"
#include "psyq/libgpu.h"
#include "psyq/libgs.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

_Static_assert(sizeof(void *) == 4, "This SDK fixture requires an ILP32 build");
u32 D_800FE240;
short D_800FE0BC, D_800FE0BE;
static unsigned moved;
void Pgxp_AddPrimMoved(const void *packet, int dx, int dy)
{
    (void)packet;
    assert(dx == 0 && dy == 0);
    ++moved;
}

int main(void)
{
    /* Descriptors immediately after the entries reproduce the corruption
     * seen in-game. Guard a larger area too: priority 5690 escaped it. */
    static u32 entries[65536 + 16], packets[128];
    POLY_GT4 polygon;
    GsOT ot = {0};
    const unsigned priorities[] = {0, 4095, 4096, 4117, 5132, 5690, 6319, 65535};
    memset(&polygon, 0, sizeof(polygon));
    polygon.code = 0x3c;
    ot.length = 12;
    ot.org = (GsOT_TAG *)entries;
    for (unsigned i = 0; i < sizeof(priorities) / sizeof(*priorities); ++i) {
        unsigned expected = priorities[i] < 4096 ? priorities[i] : 4095;
        for (unsigned j = 0; j < sizeof(entries) / sizeof(*entries); ++j) entries[j] = 0x123456;
        memset(packets, 0, sizeof(packets));
        D_800FE240 = (u32)(uintptr_t)packets;
        GsSortPoly(&polygon, &ot, (u16)priorities[i]);
        assert(D_800FE240 == (u32)(uintptr_t)(packets + 13));
        assert(packets[0] == 0x0c123456);
        for (unsigned j = 0; j < sizeof(entries) / sizeof(*entries); ++j)
            assert(entries[j] == (j == expected ? ((u32)(uintptr_t)packets & 0xffffff) : 0x123456));
        assert(ot.length == 12 && ot.offset == 0 && ot.point == 0 && !ot.tag);
    }
    /* Nonzero offsets and the one-entry table must be bounded too. */
    ot.length = 0;
    ot.offset = 37;
    entries[0] = entries[1] = 0x123456;
    D_800FE240 = (u32)(uintptr_t)packets;
    GsSortPoly(&polygon, &ot, 0);
    assert(entries[0] == ((u32)(uintptr_t)packets & 0xffffff) && entries[1] == 0x123456);
    D_800FE240 = (u32)(uintptr_t)packets;
    GsSortPoly(&polygon, &ot, 65535);
    assert(entries[1] == 0x123456 && moved == 10);
    puts("LIBGS priorities: valid links, endpoint clamping and adjacent memory passed");
    return 0;
}
