#include "types.h"
#include "game/duel_card_record_lifecycle.h"
#include "game/duel_card_staging.h"
#include "pc/guest/translated_runtime.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>

static unsigned calls;
u8 *Duel_SetupCardRecord(s32 slot, s32 id) {
    assert((slot == 2 || slot == 0x82) && id == 77);
    return (u8 *)(uintptr_t)0x801a7b10;
}
DuelCardDisplayObject *func_80024C1C(s32 id, s32 x, s32 y) {
    assert(id == 123 && x == -40 && y == 82); calls++;
    return (DuelCardDisplayObject *)(uintptr_t)0x801b1000;
}
extern void func_80024D34(s32, s32);
int main(void) {
    MemoriesMemory *m = calloc(1, sizeof(*m)); assert(m && !GuestRuntime_Bind(m));
    u8 *slot = Memories_Resolve(m, 0x801a7b10, 28, 4);
    DuelCardDisplayObject *obj = Memories_Resolve(m, 0x801b1000, sizeof(*obj), 4);
    u8 *data = Memories_Resolve(m, 0x801b2000, 4, 4); data[0] = 123;
    for (int side = 0; side < 2; side++) {
        unsigned index = 2 + side*15;
        u8 *replay = Memories_Resolve(m, 0x8015c424 + 0x4b6b4 + 28*index, 28, 4);
        Memories_WriteLE32(replay+4, 0x801b2000);
        s16 *position = Memories_Resolve(m, 0x800908a0 + 4*index, 4, 2);
        position[0] = -40; position[1] = 82;
        Memories_WriteLE32(slot+4, 0x801b2000);
        func_80024D34(side ? 0x82 : 2, 77);
        assert(Memories_ReadLE32(slot) == 0x801b1000);
        assert(Memories_ReadLE32(slot+4) == 0x801b2000);
        assert(obj->card_index == index);
    }
    assert(calls == 2); GuestRuntime_Reset(); free(m);
    puts("Real card reconstruction preserves the adjacent data pointer on both sides");
}
