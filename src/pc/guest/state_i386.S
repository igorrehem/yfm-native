/* VSync is the save-state boundary (see state.h). The entry records what the
 * game caller expects back -- the callee-saved registers and where its return
 * address is -- and continues in the C implementation on the same frame. */
#ifdef _WIN32
#define SYMBOL(name) _##name
#define FUNCTION(name)
#define END(name)
#else
#define SYMBOL(name) name
#define FUNCTION(name) .type name, @function
#define END(name) .size name, . - name
#endif
    .text
    .globl SYMBOL(VSync)
    FUNCTION(VSync)
SYMBOL(VSync):
#if defined(__PIC__) && defined(__ELF__)
    /* Position-independent (Android's shared object): the entry's address
     * from the GOT, in ECX, which the caller does not keep. */
    call 1f
1:  popl %ecx
    addl $_GLOBAL_OFFSET_TABLE_+(.-1b), %ecx
    movl Memories_StateEntry@GOT(%ecx), %ecx
    movl %ebx, (%ecx)
    movl %esi, 4(%ecx)
    movl %edi, 8(%ecx)
    movl %ebp, 12(%ecx)
    movl %esp, 16(%ecx)
#else
    movl %ebx, SYMBOL(Memories_StateEntry)
    movl %esi, SYMBOL(Memories_StateEntry) + 4
    movl %edi, SYMBOL(Memories_StateEntry) + 8
    movl %ebp, SYMBOL(Memories_StateEntry) + 12
    movl %esp, SYMBOL(Memories_StateEntry) + 16
#endif
    jmp SYMBOL(Memories_VSync)
    END(VSync)

/* void Memories_StateReturn(const MemoriesStateEntry *entry, int value):
 * return `value` from the VSync call that `entry` describes. */
    .globl SYMBOL(Memories_StateReturn)
    FUNCTION(Memories_StateReturn)
SYMBOL(Memories_StateReturn):
    movl 4(%esp), %ecx
    movl 8(%esp), %eax
    movl 0(%ecx), %ebx
    movl 4(%ecx), %esi
    movl 8(%ecx), %edi
    movl 12(%ecx), %ebp
    movl 16(%ecx), %esp
    ret
    END(Memories_StateReturn)

#if defined(_WIN32) || defined(__ANDROID__)
/* void Memories_ContextSwitch(uint32_t *from_esp, const uint32_t *to_esp):
 * the ucontext stand-in (state.c) where the C library has none (Windows,
 * Android's bionic). Keeps the callee-saved registers on the stack being
 * left and resumes the one whose stack pointer `to_esp` holds. */
    .globl SYMBOL(Memories_ContextSwitch)
    FUNCTION(Memories_ContextSwitch)
SYMBOL(Memories_ContextSwitch):
    movl 4(%esp), %eax
    movl 8(%esp), %edx
    pushl %ebp
    pushl %ebx
    pushl %esi
    pushl %edi
    movl %esp, (%eax)
    movl (%edx), %esp
    popl %edi
    popl %esi
    popl %ebx
    popl %ebp
    ret
    END(Memories_ContextSwitch)
#endif
#ifndef _WIN32
    .section .note.GNU-stack, "", @progbits
#endif
