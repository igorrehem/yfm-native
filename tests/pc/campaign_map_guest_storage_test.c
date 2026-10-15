#include "types.h"
#include "pc/guest/translated_runtime.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
extern void CampaignMap_ClearLocationObjects(void);
static unsigned releases;
void DisplayObject_ReleaseIfPresent(void *p) {
    assert((uintptr_t)p == 0x801c0000 + 0x100 * releases); releases++;
}
int main(void) {
    MemoriesMemory *memory = calloc(1, sizeof(*memory)); assert(memory && !GuestRuntime_Bind(memory));
    u8 *table = Memories_Resolve(memory, 0x801695f4, 24, 4); assert(table);
    Memories_WriteLE32(table, 0xdeadbeef); Memories_WriteLE32(table + 20, 0xcafebabe);
    for (unsigned i = 0; i < 4; i++) Memories_WriteLE32(table + 4 + 4*i, 0x801c0000 + 0x100*i);
    CampaignMap_ClearLocationObjects(); assert(releases == 4);
    for (unsigned i = 0; i < 4; i++) assert(!Memories_ReadLE32(table + 4 + 4*i));
    assert(Memories_ReadLE32(table) == 0xdeadbeef && Memories_ReadLE32(table + 20) == 0xcafebabe);
    GuestRuntime_Reset(); free(memory); puts("Real campaign map cleanup preserves four guest pointers and neighboring state");
}
