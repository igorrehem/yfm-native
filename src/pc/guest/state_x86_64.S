/* The 64-bit Windows build's VSync entry and stack switch (state_i386.S
 * is the 32-bit one). Win64 keeps rbx, rbp, rdi, rsi, r12-r15 and
 * xmm6-xmm15 across a call. */
    .text

/* VSync is the save-state boundary (see state.h). The entry records the
 * callee-saved registers and where the caller's return address is, and
 * continues in the C implementation on the same frame, its argument still
 * in rcx. */
    .globl VSync
VSync:
    movq %rbx, Memories_StateEntry(%rip)
    movq %rbp, Memories_StateEntry+8(%rip)
    movq %rdi, Memories_StateEntry+16(%rip)
    movq %rsi, Memories_StateEntry+24(%rip)
    movq %r12, Memories_StateEntry+32(%rip)
    movq %r13, Memories_StateEntry+40(%rip)
    movq %r14, Memories_StateEntry+48(%rip)
    movq %r15, Memories_StateEntry+56(%rip)
    movq %rsp, Memories_StateEntry+64(%rip)
    movdqu %xmm6, Memories_StateEntry+72(%rip)
    movdqu %xmm7, Memories_StateEntry+88(%rip)
    movdqu %xmm8, Memories_StateEntry+104(%rip)
    movdqu %xmm9, Memories_StateEntry+120(%rip)
    movdqu %xmm10, Memories_StateEntry+136(%rip)
    movdqu %xmm11, Memories_StateEntry+152(%rip)
    movdqu %xmm12, Memories_StateEntry+168(%rip)
    movdqu %xmm13, Memories_StateEntry+184(%rip)
    movdqu %xmm14, Memories_StateEntry+200(%rip)
    movdqu %xmm15, Memories_StateEntry+216(%rip)
    jmp Memories_VSync

/* void Memories_StateReturn(const MemoriesStateEntry *entry, int value):
 * return `value` from the VSync call that `entry` describes, with the
 * registers it recorded, xmm6-xmm15 included. */
    .globl Memories_StateReturn
Memories_StateReturn:
    movl %edx, %eax
    movq 0(%rcx), %rbx
    movq 8(%rcx), %rbp
    movq 16(%rcx), %rdi
    movq 24(%rcx), %rsi
    movq 32(%rcx), %r12
    movq 40(%rcx), %r13
    movq 48(%rcx), %r14
    movq 56(%rcx), %r15
    movdqu 72(%rcx), %xmm6
    movdqu 88(%rcx), %xmm7
    movdqu 104(%rcx), %xmm8
    movdqu 120(%rcx), %xmm9
    movdqu 136(%rcx), %xmm10
    movdqu 152(%rcx), %xmm11
    movdqu 168(%rcx), %xmm12
    movdqu 184(%rcx), %xmm13
    movdqu 200(%rcx), %xmm14
    movdqu 216(%rcx), %xmm15
    movq 64(%rcx), %rsp
    ret

/* void Memories_ContextSwitch(uintptr_t *from_sp, const uintptr_t *to_sp):
 * the ucontext stand-in (state.c). Keeps the callee-saved registers on the
 * stack being left and resumes the one whose stack pointer `to_sp` holds.
 * The frame, from the saved stack pointer up: xmm6-xmm15 (160 bytes), then
 * r15, r14, r13, r12, rdi, rsi, rbx, rbp and the return address. */
    .globl Memories_ContextSwitch
Memories_ContextSwitch:
    pushq %rbp
    pushq %rbx
    pushq %rsi
    pushq %rdi
    pushq %r12
    pushq %r13
    pushq %r14
    pushq %r15
    subq $160, %rsp
    movdqu %xmm6, 0(%rsp)
    movdqu %xmm7, 16(%rsp)
    movdqu %xmm8, 32(%rsp)
    movdqu %xmm9, 48(%rsp)
    movdqu %xmm10, 64(%rsp)
    movdqu %xmm11, 80(%rsp)
    movdqu %xmm12, 96(%rsp)
    movdqu %xmm13, 112(%rsp)
    movdqu %xmm14, 128(%rsp)
    movdqu %xmm15, 144(%rsp)
    movq %rsp, (%rcx)
    movq (%rdx), %rsp
    movdqu 0(%rsp), %xmm6
    movdqu 16(%rsp), %xmm7
    movdqu 32(%rsp), %xmm8
    movdqu 48(%rsp), %xmm9
    movdqu 64(%rsp), %xmm10
    movdqu 80(%rsp), %xmm11
    movdqu 96(%rsp), %xmm12
    movdqu 112(%rsp), %xmm13
    movdqu 128(%rsp), %xmm14
    movdqu 144(%rsp), %xmm15
    addq $160, %rsp
    popq %r15
    popq %r14
    popq %r13
    popq %r12
    popq %rdi
    popq %rsi
    popq %rbx
    popq %rbp
    ret
