#include "types.h"
#include "game/duel_card.h"
#include "psyq/libgte.h"
#include "psyq/libgpu.h"
#include "pc/guest/translated_runtime.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
static unsigned captures;
int DuelEffect_MarkInitialized(void) { return 1; }
int StoreImage(RECT *rect, u32 *data) {
    RECT *r = GuestRuntime_ResolveData(rect, sizeof(*r));
    assert(r->x == 156 && r->y == 200 && r->w == 8 && r->h == 88);
    assert((uintptr_t)data == 0x8018c2d8 + 2*1408); captures++; return 0;
}
extern void DuelEffect_ApplyRitual(void);
int main(void) {
    MemoriesMemory *m = calloc(1, sizeof(*m)); assert(m && !GuestRuntime_Bind(m));
    *(u8 *)Memories_Resolve(m, 0x8009b210, 1, 1) = 3;
    *(u8 *)Memories_Resolve(m, 0x8009b19c, 1, 1) = 5;
    *(u16 *)Memories_Resolve(m, 0x8009b1a0, 2, 2) = 364;
    DuelCardRecord *card = Memories_Resolve(m, 0x801a7ad8+5*28, 28, 4);
    card->data = (void *)(uintptr_t)0x801b2200;
    u8 *bytes = (u8 *)card; Memories_WriteLE32(bytes+8, 0xdeadbeef);
    u8 *deck = Memories_Resolve(m, 0x801b2200, 4, 4); deck[3] = 2;
    u16 *rects = Memories_Resolve(m, 0x800ea128, 44, 2);
    rects[20] = 100; rects[21] = 200;
    DuelEffect_ApplyRitual();
    assert(card->card_id == 364 && (deck[0] | deck[1]<<8) == 364);
    assert(Memories_ReadLE32(bytes+4) == 0x801b2200 && Memories_ReadLE32(bytes+8) == 0xdeadbeef);
    assert(captures == 1); GuestRuntime_Reset(); free(m);
    puts("Real ritual publication uses a four-byte data pointer and correct card image block");
}
