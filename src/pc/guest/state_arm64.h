#ifndef MEMORIES_STATE_ARM64_H
#define MEMORIES_STATE_ARM64_H
#include <stdint.h>

/* AAPCS64 nonvolatile state at a game boundary. x18 belongs to Darwin;
 * floating-point callees preserve the low 64 bits of v8 through v15. */
typedef struct MemoriesArm64Context {
    uint64_t x19_x30[12];
    uint64_t sp;
    uint64_t d8_d15[8];
} MemoriesArm64Context;

int Memories_Arm64Capture(MemoriesArm64Context *context) __attribute__((returns_twice));
void Memories_Arm64Restore(const MemoriesArm64Context *context, int value) __attribute__((noreturn));
#endif
