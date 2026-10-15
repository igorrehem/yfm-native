#include "types.h"
#include "pc/guest/translated_runtime.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
extern void GsDrawOt(void *descriptor);
static unsigned draws, mod_calls;
/* Observe the real descriptor reader without running the unrelated renderer. */
void Mods_DrawFrame(void) { ++mod_calls; }
void DrawOTag(u32 *list)
{
    assert((uintptr_t)list == 0x800a0614u);
    ++draws;
}
int main(void)
{
    MemoriesMemory *memory = calloc(1, sizeof(*memory));
    u8 *descriptor;
    assert(memory && GuestRuntime_Bind(memory) == 0);
    descriptor = Memories_Resolve(memory, 0x800a0000u, 24, 4);
    assert(descriptor && (uintptr_t)descriptor > UINT32_MAX);
    Memories_WriteLE32(descriptor + 16, 0x800a0614u);
    Memories_WriteLE32(descriptor + 20, 6);
    GsDrawOt((void *)(uintptr_t)0x800a0000u);
    GsDrawOt((void *)(uintptr_t)0xa00a0000u);
    GsDrawOt(descriptor);
    assert(draws == 3 && mod_calls == 3);
    assert(Memories_ReadLE32(descriptor + 20) == 6);
    GuestRuntime_Reset();free(memory);
    puts("Real GsDrawOt: four-byte tag pointer, adjacent word and RAM aliases passed");
    return 0;
}
