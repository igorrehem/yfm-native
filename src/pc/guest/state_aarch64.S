/* 64-bit ARM (AArch64) counterpart of state_i386.S and state_x86_64.S: the
 * VSync entry that records what the game caller expects back, the return
 * into that caller, and the stack switch (bionic and the Linux build share
 * it; neither needs ucontext). The build assembles it for AArch64 targets
 * only (tools/pc/build_game32.py). Callee-saved under AAPCS64: X19-X28, the
 * frame pointer X29, SP, and the low halves D8-D15 of V8-V15; X30 (LR) is
 * the caller's return address. Position-independent: the one variable is
 * reached through the GOT, so the same file serves a shared object
 * (Android's libgame.so) and an executable. */
    .text

/* Memories_StateEntry's layout (state.h): X19-X28 at 0, X29 at 80, LR at
 * 88, SP at 96 (the `esp` field: the stack pointer the caller had, as on
 * x86 where it points at the return address), D8-D15 at 104. X16 and X17
 * are free at a call. */
    .globl VSync
    .type VSync, %function
    .p2align 2
VSync:
    adrp x16, :got:Memories_StateEntry
    ldr x16, [x16, #:got_lo12:Memories_StateEntry]
    stp x19, x20, [x16, #0]
    stp x21, x22, [x16, #16]
    stp x23, x24, [x16, #32]
    stp x25, x26, [x16, #48]
    stp x27, x28, [x16, #64]
    stp x29, x30, [x16, #80]
    mov x17, sp
    str x17, [x16, #96]
    stp d8, d9, [x16, #104]
    stp d10, d11, [x16, #120]
    stp d12, d13, [x16, #136]
    stp d14, d15, [x16, #152]
    b Memories_VSync
    .size VSync, . - VSync

/* void Memories_StateReturn(const MemoriesStateEntry *entry, int value):
 * return `value` from the VSync call that `entry` describes. */
    .globl Memories_StateReturn
    .type Memories_StateReturn, %function
    .p2align 2
Memories_StateReturn:
    ldp x19, x20, [x0, #0]
    ldp x21, x22, [x0, #16]
    ldp x23, x24, [x0, #32]
    ldp x25, x26, [x0, #48]
    ldp x27, x28, [x0, #64]
    ldp x29, x30, [x0, #80]
    ldr x16, [x0, #96]
    mov sp, x16
    ldp d8, d9, [x0, #104]
    ldp d10, d11, [x0, #120]
    ldp d12, d13, [x0, #136]
    ldp d14, d15, [x0, #152]
    mov w0, w1
    ret
    .size Memories_StateReturn, . - Memories_StateReturn

/* void Memories_ContextSwitch(uintptr_t *from_sp, const uintptr_t *to_sp):
 * keeps the callee-saved registers on the stack being left and resumes the
 * one whose stack pointer `to_sp` holds. The frame, 176 bytes from the
 * saved stack pointer up: D8-D15 (64), X19-X28 (80), X29, then LR (the
 * resume address). state.c's switch_frame builds a first frame the same
 * way. */
    .globl Memories_ContextSwitch
    .type Memories_ContextSwitch, %function
    .p2align 2
Memories_ContextSwitch:
    sub sp, sp, #176
    stp d8, d9, [sp, #0]
    stp d10, d11, [sp, #16]
    stp d12, d13, [sp, #32]
    stp d14, d15, [sp, #48]
    stp x19, x20, [sp, #64]
    stp x21, x22, [sp, #80]
    stp x23, x24, [sp, #96]
    stp x25, x26, [sp, #112]
    stp x27, x28, [sp, #128]
    stp x29, x30, [sp, #144]
    mov x16, sp
    str x16, [x0]
    ldr x16, [x1]
    mov sp, x16
    ldp d8, d9, [sp, #0]
    ldp d10, d11, [sp, #16]
    ldp d12, d13, [sp, #32]
    ldp d14, d15, [sp, #48]
    ldp x19, x20, [sp, #64]
    ldp x21, x22, [sp, #80]
    ldp x23, x24, [sp, #96]
    ldp x25, x26, [sp, #112]
    ldp x27, x28, [sp, #128]
    ldp x29, x30, [sp, #144]
    add sp, sp, #176
    ret
    .size Memories_ContextSwitch, . - Memories_ContextSwitch

/* void Memories_CallOnStack(void (*function)(void *), void *argument,
 * uintptr_t top): function(argument) with the stack pointer at `top`
 * (16-byte aligned), then back on the stack it was called on. The frame
 * record stays on the caller's stack and x29 points at it, so the frame
 * chain from inside `function` leads back to the caller across the
 * switch. A frame-pointer walk that stops when the chain goes down has to
 * cross it once, from the thread's stack down to the game stack (crash.c's
 * walk does). The call goes through the X16 thunk, as every indirect call
 * here does (build_game32.py's check_arm_branches). */
    .globl Memories_CallOnStack
    .type Memories_CallOnStack, %function
    .p2align 2
Memories_CallOnStack:
    stp x29, x30, [sp, #-32]!
    str x19, [sp, #16]
    mov x29, sp
    mov x19, sp
    and x2, x2, #0xfffffffffffffff0
    mov sp, x2
    mov x16, x0
    mov x0, x1
    bl __llvm_slsblr_thunk_x16
    mov sp, x19
    ldr x19, [sp, #16]
    ldp x29, x30, [sp], #32
    ret
    .size Memories_CallOnStack, . - Memories_CallOnStack
    .section .note.GNU-stack, "", %progbits
