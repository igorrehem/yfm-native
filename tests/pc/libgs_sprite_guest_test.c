/* Real GsSortSprite, with a populated word immediately after its PS1 record. */
#include "types.h"
#include "psyq/libgte.h"
#include "psyq/libgpu.h"
#include "psyq/libgs.h"
#include "pc/guest/translated_runtime.h"
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
_Static_assert(sizeof(GsSPRITE) == 36, "PS1 sprite extent");
_Static_assert(offsetof(GsSPRITE, rotate) == 32, "PS1 angle offset");
static unsigned rotations, projections;
MATRIX *RotMatrix(SVECTOR *angle, MATRIX *matrix)
{
    angle = GuestRuntime_ResolveData(angle, sizeof(*angle));
    assert(angle->vz == 1024); /* Only the explicitly rotated case may call. */
    ++rotations;
    return matrix;
}
MATRIX *ScaleMatrix(MATRIX *matrix, VECTOR *scale) { (void)scale; return matrix; }
void SetRotMatrix(MATRIX *matrix) { (void)matrix; }
void SetTransMatrix(MATRIX *matrix) { (void)matrix; }
PSXLONG ReadGeomScreen(void) { return 320; }
PSXLONG RotTransPers(SVECTOR *vertex, PSXLONG *xy, PSXLONG *p, PSXLONG *flag)
{
    vertex = GuestRuntime_ResolveData(vertex, sizeof(*vertex));
    xy = GuestRuntime_ResolveData(xy, sizeof(*xy));
    p = GuestRuntime_ResolveData(p, sizeof(*p));
    flag = GuestRuntime_ResolveData(flag, sizeof(*flag));
    *xy = (u16)vertex->vx | ((u32)(u16)vertex->vy << 16);
    *p = *flag = 0;
    ++projections;
    return 0;
}
static void put(MemoriesMemory *memory, u32 address, u32 value)
{
    Memories_WriteLE32(Memories_Resolve(memory, address, 4, 4), value);
}
int main(void)
{
    MemoriesMemory *memory = calloc(1, sizeof(*memory));
    GsSPRITE sprite = {0};
    const u32 source = 0x800A0000, descriptor = 0x800A0100, table = 0x800A0200, packet = 0x800A0300;
    const u32 sentinels[] = {0xFFFFFFFFu, 0x12345678u, 0x2C808080u};
    assert(memory && GuestRuntime_Bind(memory) == 0);
    sprite.x = 50; sprite.y = 60; sprite.w = 48; sprite.h = 48;
    sprite.scalex = sprite.scaley = 4096;
    memcpy(Memories_Resolve(memory, source, sizeof(sprite), 4), &sprite, sizeof(sprite));
    put(memory, descriptor + 4, table);
    for (unsigned i = 0; i < sizeof(sentinels) / sizeof(*sentinels); ++i) {
        put(memory, source + 36, sentinels[i]);
        put(memory, 0x800FE240, packet);
        GsSortSprite((GsSPRITE *)(uintptr_t)source, (GsOT *)(uintptr_t)descriptor, 0);
        assert(!rotations && !projections);
        assert((Memories_ReadLE32(Memories_Resolve(memory, packet + 8, 4, 4)) >> 24) == 0x64);
        assert(Memories_ReadLE32(Memories_Resolve(memory, source + 36, 4, 4)) == sentinels[i]);
    }
    put(memory, source + 32, 1024 * 360);
    put(memory, 0x800FE240, packet);
    GsSortSprite((GsSPRITE *)(uintptr_t)source, (GsOT *)(uintptr_t)descriptor, 0);
    assert(rotations == 1 && projections == 4);
    assert((Memories_ReadLE32(Memories_Resolve(memory, packet + 4, 4, 4)) >> 24) == 0x2C);
    GuestRuntime_Reset(); free(memory);
    puts("GsSortSprite: PS1 rotation width, adjacent sentinels, plain and rotated packets passed");
    return 0;
}
