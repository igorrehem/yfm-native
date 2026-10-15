/* Runs the original func_80038898 through the structured LLVM compiler.
 * Full game boot, callbacks, invalid command handling and other globals are
 * deliberately outside this proof. */
#include "ygo_types.h"
#include "pc/memory.h"
#ifdef TRANSLATED_GAME_IR
#include "pc/guest/translated_runtime.h"
#endif
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static MemoriesMemory *memory;
extern void func_80038898(DuelEffectChannel *object);
_Static_assert(sizeof(((TextStreamOwner *)0)->streams[0]) == 4, "stored pointer width");
_Static_assert(offsetof(TextStreamOwner, stream_index) == 0x58, "stream layout");
_Static_assert(offsetof(DuelEffectChannel, stream_58) == 0x58, "channel layout");

u8 *TranslatedUnit_Resolve(u32 address, unsigned length)
{
    u8 *host = Memories_Resolve(memory, address, length, 1);
    assert(host != NULL);
    assert((uintptr_t)host > UINT32_MAX);
    return host;
}

int main(void)
{
    const u32 aliases[] = {0x00012000u, 0x80012000u, 0xa0012000u};
    const u32 channel_address = 0x80014000u;
    DuelEffectChannel *channel;
    TextStreamOwner *owner;
    size_t i;
    memory = calloc(1, sizeof(*memory));
    assert(memory != NULL);
#ifdef TRANSLATED_GAME_IR
    assert(GuestRuntime_Bind(memory) == 0);
#endif
    channel = Memories_Resolve(memory, channel_address, sizeof(*channel), 4);
    assert(channel != NULL && (uintptr_t)channel > UINT32_MAX);
    owner = (TextStreamOwner *)channel;
    for (i = 0; i < sizeof(aliases) / sizeof(aliases[0]); ++i) {
        u32 original_address = aliases[i];
        channel->stream_58 = 3;
        owner->streams[3] = (u8 *G32)(uintptr_t)original_address;
        owner->streams[2] = (u8 *G32)(uintptr_t)0x80019900u;
        TranslatedUnit_Resolve(original_address, 2)[0] = (u8)(0x20 + i);
        TranslatedUnit_Resolve(original_address, 2)[1] = (u8)(0x70 + i);
        TranslatedUnit_Resolve(0x8009B26Cu, 1)[0] = 0xff;
        TranslatedUnit_Resolve(0x8009B363u, 1)[0] = 0xff;
        func_80038898(channel);
        assert((uintptr_t)owner->streams[3] == original_address + 1u);
        assert((uintptr_t)owner->streams[2] == 0x80019900u);
        assert(TranslatedUnit_Resolve(0x0009B26Cu, 1)[0] == 5);
        assert(TranslatedUnit_Resolve(0xa009B363u, 1)[0] == 0x20 + i);
        func_80038898(channel);
        assert((uintptr_t)owner->streams[3] == original_address + 2u);
        assert(TranslatedUnit_Resolve(0x8009B363u, 1)[0] == 0x70 + i);
    }
#ifdef TRANSLATED_GAME_IR
    GuestRuntime_Reset();
#endif
    free(memory);
    puts("Real func_80038898: guest stream increment and pinned globals passed (3 aliases)");
    return 0;
}
