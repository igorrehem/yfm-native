/* The game's jmp_buf is the Psy-Q int[12] at a fixed guest address, 48
 * bytes. The Win64 callee-saved state (rbx, rbp, rdi, rsi, r12-r15, the
 * stack pointer, the return address and xmm6-xmm15) is 240 bytes, so it is
 * kept in a host slot chosen by the buffer's address (Memories_JumpSlot,
 * state.c); setjmp_i386.S is the 32-bit version, which fits. Each helper
 * call is made on a 16-byte aligned stack with its shadow space, and keeps
 * the callee-saved registers this saves or has yet to restore. */
    .text
    .globl Psx_setjmp
Psx_setjmp:
    subq $40, %rsp
    call Memories_JumpSlot          /* rcx: the buffer; rax: its slot */
    addq $40, %rsp
    movq %rbx, 0(%rax)
    movq %rbp, 8(%rax)
    movq %rdi, 16(%rax)
    movq %rsi, 24(%rax)
    movq %r12, 32(%rax)
    movq %r13, 40(%rax)
    movq %r14, 48(%rax)
    movq %r15, 56(%rax)
    leaq 8(%rsp), %rcx
    movq %rcx, 64(%rax)
    movq (%rsp), %rcx
    movq %rcx, 72(%rax)
    movdqu %xmm6, 80(%rax)
    movdqu %xmm7, 96(%rax)
    movdqu %xmm8, 112(%rax)
    movdqu %xmm9, 128(%rax)
    movdqu %xmm10, 144(%rax)
    movdqu %xmm11, 160(%rax)
    movdqu %xmm12, 176(%rax)
    movdqu %xmm13, 192(%rax)
    movdqu %xmm14, 208(%rax)
    movdqu %xmm15, 224(%rax)
    xorl %eax, %eax
    ret

    .globl Psx_longjmp
Psx_longjmp:
    subq $40, %rsp
    movl %edx, 32(%rsp)
    call Memories_JumpSlot          /* rcx: the buffer; rax: its slot */
    movl 32(%rsp), %edx
    testl %edx, %edx
    jnz 1f
    incl %edx
1:  movq 0(%rax), %rbx
    movq 8(%rax), %rbp
    movq 16(%rax), %rdi
    movq 24(%rax), %rsi
    movq 32(%rax), %r12
    movq 40(%rax), %r13
    movq 48(%rax), %r14
    movq 56(%rax), %r15
    movdqu 80(%rax), %xmm6
    movdqu 96(%rax), %xmm7
    movdqu 112(%rax), %xmm8
    movdqu 128(%rax), %xmm9
    movdqu 144(%rax), %xmm10
    movdqu 160(%rax), %xmm11
    movdqu 176(%rax), %xmm12
    movdqu 192(%rax), %xmm13
    movdqu 208(%rax), %xmm14
    movdqu 224(%rax), %xmm15
    movq 64(%rax), %rsp
    movq 72(%rax), %rcx
    movl %edx, %eax
    jmp *%rcx
