/* The game's jmp_buf is the Psy-Q int[12] at a fixed guest address, 48
 * bytes. The AAPCS64 callee-saved state (X19-X28, X29, LR, SP and D8-D15)
 * is 168 bytes, so it is kept in a host slot chosen by the buffer's address
 * (Memories_JumpSlot, state.c), as setjmp_x86_64.S does. Position-
 * independent, and the helper is called with the registers this saves (or
 * has yet to restore) untouched: X19-X28 and D8-D15 are callee-saved, and
 * LR and the arguments are kept on the stack around the call. */
    .text
    .globl Psx_setjmp
    .type Psx_setjmp, %function
    .p2align 2
Psx_setjmp:
    stp x29, x30, [sp, #-16]!
    mov x29, sp
    bl Memories_JumpSlot            /* x0: the buffer; x0: its slot */
    ldp x29, x30, [sp], #16
    stp x19, x20, [x0, #0]
    stp x21, x22, [x0, #16]
    stp x23, x24, [x0, #32]
    stp x25, x26, [x0, #48]
    stp x27, x28, [x0, #64]
    stp x29, x30, [x0, #80]
    mov x16, sp
    str x16, [x0, #96]
    stp d8, d9, [x0, #104]
    stp d10, d11, [x0, #120]
    stp d12, d13, [x0, #136]
    stp d14, d15, [x0, #152]
    mov w0, #0
    ret
    .size Psx_setjmp, . - Psx_setjmp

    .globl Psx_longjmp
    .type Psx_longjmp, %function
    .p2align 2
Psx_longjmp:
    stp x29, x30, [sp, #-32]!
    mov x29, sp
    str w1, [sp, #16]
    bl Memories_JumpSlot            /* x0: the buffer; x0: its slot */
    ldr w1, [sp, #16]
    cmp w1, #0
    csinc w1, w1, wzr, ne           /* longjmp(buf, 0) returns 1 */
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
    .size Psx_longjmp, . - Psx_longjmp
    .section .note.GNU-stack, "", %progbits
