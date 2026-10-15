#include "pc/guest/state_arm64.h"
#include <assert.h>
#include <stddef.h>
#include <stdio.h>

_Static_assert(offsetof(MemoriesArm64Context, sp) == 96, "assembly SP offset");
_Static_assert(offsetof(MemoriesArm64Context, d8_d15) == 104, "assembly SIMD offset");
_Static_assert(sizeof(MemoriesArm64Context) == 168, "complete ARM64 context");

static MemoriesArm64Context context;
static volatile unsigned restored;

static void restore_from_nested_call(int value)
{
    volatile unsigned guard[128];
    for (unsigned i = 0; i < 128; ++i) guard[i] = i * 3;
    assert(guard[127] == 381);
    __asm__ volatile("fmov d8, xzr\n\tfmov d15, xzr" ::: "d8", "d15");
    ++restored;
    Memories_Arm64Restore(&context, value);
}

static void round_trip(int value)
{
    volatile uint64_t caller_data = 0x123456789abcdef0ull;
    unsigned before = restored;
    uint64_t marker = 0x40f23456789abcdeull, restored_d8, restored_d15;
    __asm__ volatile("fmov d8, %0\n\tfmov d15, %0" :: "r"(marker) : "d8", "d15");
    int result = Memories_Arm64Capture(&context);
    if (!result) {
        assert(context.sp && !(context.sp & 15));
        assert(context.x19_x30[11]);
        assert(context.d8_d15[0] == marker && context.d8_d15[7] == marker);
        restore_from_nested_call(value);
    }
    assert(result == (value ? value : 1));
    assert(restored == before + 1);
    assert(caller_data == 0x123456789abcdef0ull);
    __asm__ volatile("fmov %0, d8\n\tfmov %1, d15" : "=r"(restored_d8), "=r"(restored_d15));
    assert(restored_d8 == marker && restored_d15 == marker);
}

int main(void)
{
    round_trip(263);
    round_trip(0);
    round_trip(-7);
    puts("ARM64 context: nested capture/restore, continuation, stack alignment and values passed");
    return 0;
}
