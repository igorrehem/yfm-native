#include "../../types.h"
#include "translated_runtime.h"
#include "state_arm64.h"
#include "state.h"
#include <stdio.h>
#include <stdlib.h>
#define JUMP_LIMIT 32
static struct { void *key; MemoriesArm64Context context; } jumps[JUMP_LIMIT];
void *GuestRuntime_JumpBuffer(void *guest)
{
    void *key = GuestRuntime_ResolveData(guest, 12 * sizeof(s32));
    unsigned i;
    for (i = 0; i < JUMP_LIMIT; ++i) if (jumps[i].key == key) return &jumps[i].context;
    for (i = 0; i < JUMP_LIMIT; ++i) if (!jumps[i].key) {
        jumps[i].key = key;
        return &jumps[i].context;
    }
    fputs("translated runtime: native jump context registry full\n", stderr);
    abort();
}
void *GuestRuntime_JumpBufferForRestore(void *guest)
{
    void *key = GuestRuntime_ResolveData(guest, 12 * sizeof(s32));
    unsigned i;
    for (i = 0; i < JUMP_LIMIT; ++i) if (jumps[i].key == key) return &jumps[i].context;
    fputs("translated runtime: longjmp has no captured native context\n", stderr);
    abort();
}
void GuestRuntime_JumpState(MemoriesState *state)
{
    MemoriesStateField fields[JUMP_LIMIT * 2], floats[JUMP_LIMIT];
    for (unsigned i = 0; i < JUMP_LIMIT; ++i) {
        fields[i * 2] = (MemoriesStateField){&jumps[i].key, sizeof(jumps[i].key)};
        fields[i * 2 + 1] = (MemoriesStateField){&jumps[i].context, 13 * sizeof(uint64_t)};
        floats[i] = (MemoriesStateField){jumps[i].context.d8_d15, sizeof(jumps[i].context.d8_d15)};
    }
    Memories_StateChunk(state, "arm64-jumps", fields, JUMP_LIMIT * 2);
    Memories_StateChunk(state, "arm64-jump-floats", floats, JUMP_LIMIT);
}
