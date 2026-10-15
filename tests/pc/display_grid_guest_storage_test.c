#include "types.h"
#include "game/display_object.h"
#include "game/menu_record.h"
#include "pc/guest/translated_runtime.h"
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
extern s32 DisplayEffect_BuildResourceObjects(MenuRecord *, DisplayObject *G32 *, s32);
extern void func_8003A440(u8 *G32 *, u32, s32);
extern void func_80039F90(void *G32 *);
static unsigned allocated, released;
static u32 object_address(unsigned i) { return 0x801c0000 + i * 0x100; }
s32 DisplayObject_FindFreeGeneralSlot(void) { return allocated; }
void *DisplayObject_AcquireSlot(s32 index, s32 key) {
    assert(key == 2 && index == (s32)allocated++);
    return (void *)(uintptr_t)object_address(index);
}
void DisplayObject_ConfigureSpriteAtPositionWithResource(DisplayObject *p, s32 x, s32 y,
    s32 a, s32 b, s32 c, s32 d, s32 e, void *r) {
    (void)p; (void)x; (void)y; (void)a; (void)b; (void)c; (void)d; (void)e; (void)r;
}
void DisplayObject_SelectOrderingTable1(DisplayObject *p) { (void)p; }
s32 DisplayObject_SetDepthOffset(DisplayObject *p, s8 depth) {
    DisplayObject *host = GuestRuntime_ResolveData(p, sizeof(*host));
    host->field_16 = depth; return depth;
}
void DisplayObject_ReleaseIfPresent(void *p) {
    assert((uintptr_t)p == object_address(2 - released)); released++;
}
int main(void) {
    MemoriesMemory *memory = calloc(1, sizeof(*memory));
    assert(memory && !GuestRuntime_Bind(memory));
    u32 guest = 0x801b0000;
    u8 *row = Memories_Resolve(memory, guest - 4, 20, 4);
    Memories_WriteLE32(row, 0xdeadbeef); Memories_WriteLE32(row + 16, 0xcafebabe);
    MenuRecord *record = Memories_Resolve(memory, 0x801b0100, sizeof(*record), 4);
    record->field_34 = 104; record->field_36 = 178;
    u8 *resource = Memories_Resolve(memory, 0x801af000, 32, 2);
    /* Three valid part entries: resource[0] -> +2, each part -> +8. */
    for (unsigned i = 0; i < 4; i++) { resource[2*i] = i ? 8 : 2; resource[2*i+1] = 0; }
    resource[8] = 1;
    for (unsigned i = 0; i < 3; i++) assert(Memories_Resolve(memory, object_address(i), sizeof(DisplayObject), 4));
    assert(DisplayEffect_BuildResourceObjects((MenuRecord *)(uintptr_t)0x801b0100,
        (DisplayObject *G32 *)(uintptr_t)guest, 0) == 1);
    assert(allocated == 3);
    for (unsigned i = 0; i < 3; i++) assert(Memories_ReadLE32(row + 4 + 4*i) == object_address(i));
    func_8003A440((u8 *G32 *)(uintptr_t)guest, 0, 7);
    for (unsigned i = 0; i < 3; i++) {
        DisplayObject *obj = Memories_Resolve(memory, object_address(i), sizeof(*obj), 4);
        assert(obj->field_16 == 7 && obj->field_0C == 0x808080);
    }
    func_80039F90((void *G32 *)(uintptr_t)guest);
    assert(released == 3);
    for (unsigned i = 0; i < 3; i++) assert(!Memories_ReadLE32(row + 4 + 4*i));
    assert(Memories_ReadLE32(row) == 0xdeadbeef && Memories_ReadLE32(row + 16) == 0xcafebabe);
    GuestRuntime_Reset(); free(memory);
    puts("Real display grid writer/update/release preserve twelve-byte rows and both sentinels");
}
