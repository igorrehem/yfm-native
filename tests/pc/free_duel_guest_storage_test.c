#include "types.h"
#include "game/display_object.h"
#include "pc/guest/translated_runtime.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
extern DisplayObject *G32 *FreeDuel_GetSparkleSlot(void);
extern void FreeDuel_UpdateSparkle(void);
extern void FreeDuel_UpdateScrollbar(void);
static unsigned releases;
void DisplayObject_ReleaseIfPresent(void *p) {
    assert((uintptr_t)p == 0x801b0000); releases++;
}
int main(void) {
    MemoriesMemory *m = calloc(1, sizeof(*m)); assert(m && !GuestRuntime_Bind(m));
    u32 *pool = Memories_Resolve(m, 0x80169060, 64, 4);
    assert((uintptr_t)FreeDuel_GetSparkleSlot() == 0x8016909c);
    for (unsigned i = 0; i < 16; i++) pool[i] = 0x801b1000;
    pool[4] = 0; assert((uintptr_t)FreeDuel_GetSparkleSlot() == 0x80169070);
    pool[4] = 0x801b1000; assert(!FreeDuel_GetSparkleSlot());
    for (unsigned i = 0; i < 16; i++) pool[i] = 0;
    pool[0] = 0x801b0000;
    DisplayObject *sparkle = Memories_Resolve(m, 0x801b0000, sizeof(*sparkle), 4);
    sparkle->field_6C = 1;
    u32 *cursor_words = Memories_Resolve(m, 0x801690a0, 8, 4);
    cursor_words[0] = 0x801b2000; cursor_words[1] = 0x40;
    *(u32 *)Memories_Resolve(m, 0x80169058, 4, 4) = 0x801b2100;
    DisplayObject *cursor = Memories_Resolve(m, 0x801b2000, sizeof(*cursor), 4);
    DisplayObject *thumb = Memories_Resolve(m, 0x801b2100, sizeof(*thumb), 4);
    cursor->field_30.h.field_32 = 404;
    FreeDuel_UpdateScrollbar();
    assert(*(s16 *)Memories_Resolve(m, 0x8009b148, 2, 2) == 260);
    assert(thumb->field_30.h.field_32 == 79);
    for (unsigned i = 0; i < 16; i++) FreeDuel_UpdateSparkle();
    assert(releases == 1 && pool[0] == 0);
    assert(cursor_words[0] == 0x801b2000 && cursor_words[1] == 0x40);
    GuestRuntime_Reset(); free(m);
    puts("Real Free Duel cursor, scrollbar and sixteen-entry sparkle pool preserve guest layout");
}
