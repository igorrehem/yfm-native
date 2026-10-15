#include "types.h"
#include "game/sound.h"
#include "pc/guest/translated_runtime.h"
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
extern void SD_ArmBusyCallback(void);
extern void SD_ResetMusicTrackBuffer(void);
extern void func_8004ADE8(s32, s32, s32);
/* Empty instrument program must return before calling voice dependencies. */
s32 SD_FindLowestPrioritySecondaryObject(s32 a) { (void)a; abort(); }
s32 SD_SelectSecondaryObject(s32 a,s32 b) { (void)a;(void)b;abort(); }
void SD_SpatializeSecondaryObject(void *a,void *b) { (void)a;(void)b;abort(); }
s32 SD_CalcPitchBend(void *a,s32 b) { (void)a;(void)b;abort(); }
s32 func_80049FB4(s32 a,s32 b,s32 c,s32 d) { (void)a;(void)b;(void)c;(void)d;abort(); }
void SpuSetKeyOnWithAttr(SpuVoiceAttr *a) { (void)a;abort(); }
unsigned PSXLONG SpuSetReverbVoice(PSXLONG a,unsigned PSXLONG b) { (void)a;(void)b;abort(); }
unsigned PSXLONG SpuGetReverbVoice(void) { abort(); }
static int reset_calls;
/* Observing doubles: these two real commands' dependencies are not under test. */
void SD_ClearBusyFlag(void) {}
void SD_ResetMusicState(void) { ++reset_calls; }
int main(void)
{
    MemoriesMemory *memory = calloc(1, sizeof(*memory));
    const u32 state_address = 0x801e1618u;
    SDValue *state;
    u8 *global, *callback, *music;
    assert(memory && GuestRuntime_Bind(memory) == 0);
    state = Memories_Resolve(memory, state_address, sizeof(*state), 4);
    global = Memories_Resolve(memory, 0x8009b45cu, 8, 4);
    callback = Memories_Resolve(memory, 0x8009b128u, 8, 4);
    assert(state && global && callback);
    Memories_WriteLE32(global, state_address);
    Memories_WriteLE32(global + 4, 0x801e1650u);
    Memories_WriteLE32(callback, 0);
    Memories_WriteLE32(callback + 4, 0xdecafbad);
    assert(GuestRuntime_RegisterFunction(0x8004544cu, SD_ClearBusyFlag) == 0);
    SD_ArmBusyCallback();
    assert(state->busy == 1);
    assert(Memories_ReadLE32(global) == state_address);
    assert(Memories_ReadLE32(global + 4) == 0x801e1650u);
    assert(Memories_ReadLE32(callback) == 0x8004544cu);
    assert(Memories_ReadLE32(callback + 4) == 0xdecafbadu);
    music = Memories_Resolve(memory, state_address + offsetof(SDValue, music_track), 8, 4);
    assert(music);
    Memories_WriteLE32(music + 4, 0xaabbccddu);
    SD_ResetMusicTrackBuffer();
    assert(reset_calls == 1);
    assert(Memories_ReadLE32(music) == 0x801ea800u);
    assert(Memories_ReadLE32(music + 4) == 0xaabbccddu);
    assert(*(u16 *)Memories_Resolve(memory, 0x801ea800u, 2, 2) == 0xffffu);
    /* Recreate the observed 0x1620_801ea870 concatenation in the header slot. */
    u8 *secondary = Memories_Resolve(memory, 0x801e3000u, 0x4b0, 4);
    u8 *secondary_global = Memories_Resolve(memory, 0x8009b458u, 4, 4);
    u8 *header = Memories_Resolve(memory, 0x801ea870u, 0x30, 4);
    assert(secondary && secondary_global && header);
    Memories_WriteLE32(secondary_global, 0x801e3000u);
    Memories_WriteLE32(secondary + 0x4a8, 0x801ea870u);
    Memories_WriteLE32(secondary + 0x4ac, 0x1620u);
    header[0x20] = 0;
    func_8004ADE8(0, 60, 127);
    assert(Memories_ReadLE32(secondary + 0x4ac) == 0x1620u);
    GuestRuntime_Reset(); free(memory);
    puts("Real sound commands: four-byte absolute/member pointer accesses preserve adjacent words");
    return 0;
}
