#include "types.h"
#include "pc/guest/translated_runtime.h"
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
int Psx_setjmp(s32 *env) __attribute__((returns_twice));
void Psx_longjmp(s32 *env, int value) __attribute__((noreturn));
static s32 *at(u32 address) { return (s32 *)(uintptr_t)address; }
int main(void)
{
    MemoriesMemory *memory = calloc(1, sizeof(*memory));
    volatile int changed = 0;
    int result;
    assert(memory && GuestRuntime_Bind(memory) == 0);
    result = Psx_setjmp(at(0x80010000u));
    if (!result) { changed = 7; Psx_longjmp(at(0xa0010000u), 42); }
    assert(result == 42 && changed == 7);
    result = Psx_setjmp(at(0x80010100u));
    if (!result) Psx_longjmp(at(0x10100u), 0);
    assert(result == 1);
    assert(memory->ram[0x10000] == 0 && memory->ram[0x1002f] == 0);
    free(memory);
    GuestRuntime_Reset();
    puts("Native arm64 setjmp/longjmp: caller resume, RAM aliases and zero value passed");
    return 0;
}
