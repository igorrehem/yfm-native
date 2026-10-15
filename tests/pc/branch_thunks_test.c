/* The indirect-branch thunks (src/pc/guest/branch_thunks.c): for each of the
 * seven registers a compiler may call through, a target in guest memory
 * reaches what the resolver names and a host target is jumped to as it is,
 * with every register (the target register too) and the stack as the caller
 * left them; the same through the entry of the stubs the build writes for
 * module functions called by name. Then calls from C, which this file is
 * compiled to route through the thunks: arguments and results pass, and the
 * resolver runs on an aligned stack. Last, tail jmps through the thunks and
 * to a stub.
 * Nothing here maps guest memory: the guest addresses must never be jumped
 * to, or the test faults. */
#include "pc/guest/image.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#if defined(__i386__)
#ifdef _WIN32
#define SYMBOL(name) "_" #name
#else
#define SYMBOL(name) #name
#endif

#define GUEST_RECORD 0x80001000u
#define GUEST_ADD 0x80002004u
#define GUEST_PHYSICAL 0x00012340u
#define GUEST_KSEG1 0xa0002004u

/* What record_registers saw: eax, ecx, edx, ebx, esp, ebp, esi, edi. */
uint32_t seen[8];
uint32_t esp_before;
/* Resolutions of the test's guest addresses, and of anything else: a host
 * address whose bits 21-28 and 30 are clear takes the slow path too, which
 * an address-randomized test executable can be loaded at. */
static unsigned resolved, others, misaligned;
void record_registers(void);
__asm__(".text\n"
        ".globl " SYMBOL(record_registers) "\n"
        SYMBOL(record_registers) ":\n"
        "    movl %eax, " SYMBOL(seen) "\n"
        "    movl %ecx, " SYMBOL(seen) "+4\n"
        "    movl %edx, " SYMBOL(seen) "+8\n"
        "    movl %ebx, " SYMBOL(seen) "+12\n"
        "    movl %esp, " SYMBOL(seen) "+16\n"
        "    movl %ebp, " SYMBOL(seen) "+20\n"
        "    movl %esi, " SYMBOL(seen) "+24\n"
        "    movl %edi, " SYMBOL(seen) "+28\n"
        "    ret\n");

/* call_through_<reg>(target): every register but esp set to a known value,
 * <reg> to `target`, then a call through that register's thunk. */
#define DRIVER(reg)                                                               \
    void call_through_##reg(uint32_t target);                                     \
    __asm__(".text\n"                                                             \
            ".globl " SYMBOL(call_through_##reg) "\n"                             \
            SYMBOL(call_through_##reg) ":\n"                                      \
            "    movl 4(%esp), %eax\n"                                            \
            "    pushal\n"                                                        \
            "    pushl %eax\n"                                                    \
            "    movl $0x11111111, %eax\n"                                        \
            "    movl $0x22222222, %ecx\n"                                        \
            "    movl $0x33333333, %edx\n"                                        \
            "    movl $0x44444444, %ebx\n"                                        \
            "    movl $0x66666666, %ebp\n"                                        \
            "    movl $0x77777777, %esi\n"                                        \
            "    movl $0x88888888, %edi\n"                                        \
            "    popl %" #reg "\n"                                                \
            "    movl %esp, " SYMBOL(esp_before) "\n"                             \
            "    call " SYMBOL(__x86_indirect_thunk_##reg) "\n"                   \
            "1:  cmpl %esp, " SYMBOL(esp_before) "\n"                             \
            "    je 2f\n"                                                         \
            "    movl $0, " SYMBOL(esp_before) "\n"                               \
            "2:  popal\n"                                                         \
            "    ret\n");
DRIVER(eax)
DRIVER(ecx)
DRIVER(edx)
DRIVER(ebx)
DRIVER(esi)
DRIVER(edi)
DRIVER(ebp)

/* A module function the C calls by name, as build_game32.py writes its host
 * stub (guest_branches.c), and a driver that calls it directly with every
 * register set to its known value (the argument is not used). */
__asm__(".text\n"
        "direct_record:\n"
        "    pushl $0x80001000\n"
        "    jmp " SYMBOL(Memories_GuestBranchDirect) "\n"
        ".globl " SYMBOL(call_direct) "\n"
        SYMBOL(call_direct) ":\n"
        "    pushal\n"
        "    movl $0x11111111, %eax\n"
        "    movl $0x22222222, %ecx\n"
        "    movl $0x33333333, %edx\n"
        "    movl $0x44444444, %ebx\n"
        "    movl $0x66666666, %ebp\n"
        "    movl $0x77777777, %esi\n"
        "    movl $0x88888888, %edi\n"
        "    movl %esp, " SYMBOL(esp_before) "\n"
        "    call direct_record\n"
        "    cmpl %esp, " SYMBOL(esp_before) "\n"
        "    je 1f\n"
        "    movl $0, " SYMBOL(esp_before) "\n"
        "1:  popal\n"
        "    ret\n");
void call_direct(uint32_t unused);

/* tail_<reg>(a, b, c): a sibling call as a compiler emits one, the target
 * (tail_target) in <reg> and a jmp through that register's thunk, with the
 * caller's return address on top of the stack and the arguments above it;
 * tail_direct, a jmp to a build-style stub. */
uint32_t tail_target;
#define TAIL(reg)                                                                 \
    int tail_##reg(int a, int b, int c);                                          \
    __asm__(".text\n"                                                             \
            ".globl " SYMBOL(tail_##reg) "\n"                                     \
            SYMBOL(tail_##reg) ":\n"                                              \
            "    movl " SYMBOL(tail_target) ", %" #reg "\n"                       \
            "    jmp " SYMBOL(__x86_indirect_thunk_##reg) "\n");
TAIL(eax)
TAIL(ecx)
TAIL(edx)
int tail_direct(int a, int b, int c);
__asm__(".text\n"
        "direct_add:\n"
        "    pushl $0x80002004\n"
        "    jmp " SYMBOL(Memories_GuestBranchDirect) "\n"
        ".globl " SYMBOL(tail_direct) "\n"
        SYMBOL(tail_direct) ":\n"
        "    jmp direct_add\n");

static int add3(int a, int b, int c) { return a + b + c; }

static void *resolve(unsigned address)
{
    /* The thunk aligns the stack to 16 before the call, so this frame's
     * base (below the return address and the saved ebp) is 8 past it. */
    if (((uintptr_t)__builtin_frame_address(0) & 15) != 8) misaligned++;
    if (address == GUEST_RECORD || address == GUEST_ADD || address == GUEST_KSEG1 || address == GUEST_PHYSICAL) {
        resolved++;
    } else {
        others++;
    }
    if (address == GUEST_RECORD) return (void *)(uintptr_t)record_registers;
    if (address == GUEST_ADD || address == GUEST_KSEG1 || address == GUEST_PHYSICAL) return (void *)(uintptr_t)add3;
    return (void *)(uintptr_t)address;
}

static int check_registers(const char *name, void (*driver)(uint32_t), int slot, uint32_t target)
{
    static const uint32_t magic[8] = {0x11111111, 0x22222222, 0x33333333, 0x44444444, 0, 0x66666666, 0x77777777,
                                      0x88888888};
    int i, failures = 0;
    memset(seen, 0, sizeof(seen));
    driver(target);
    for (i = 0; i < 8; i++) {
        uint32_t expected = i == slot ? target : magic[i];
        if (i == 4) continue;
        if (seen[i] != expected) {
            printf("FAIL %s -> 0x%08x: register %d is 0x%08x, not 0x%08x\n", name, target, i, seen[i], expected);
            failures++;
        }
    }
    if (!esp_before || seen[4] != esp_before - 4) {
        printf("FAIL %s -> 0x%08x: the stack moved\n", name, target);
        failures++;
    }
    return failures;
}

typedef int (*Add)(int, int, int);

static int __attribute__((noinline)) call_from_c(Add function, int x)
{
    return function(x, 1, 2);   /* what the compiler makes of it: a call or a jmp through a thunk */
}

int main(void)
{
    static const struct { const char *name; void (*driver)(uint32_t); int slot; } drivers[] = {
        {"eax", call_through_eax, 0}, {"ecx", call_through_ecx, 1}, {"edx", call_through_edx, 2},
        {"ebx", call_through_ebx, 3}, {"ebp", call_through_ebp, 5}, {"esi", call_through_esi, 6},
        {"edi", call_through_edi, 7}};
    volatile Add through;
    unsigned i, before;
    int failures = 0;
    if (!((uintptr_t)record_registers & 0x5fe00000u) || !((uintptr_t)add3 & 0x5fe00000u)) {
        /* The checks below tell a host target by its taking the fast path. */
        printf("FAIL the test's code at 0x%08x lies where the thunks' fast path takes it for guest memory; "
               "link it at a fixed base (--disable-dynamicbase)\n", (unsigned)(uintptr_t)record_registers);
        return 1;
    }
    Memories_GuestBranchResolver = resolve;
    for (i = 0; i < sizeof(drivers) / sizeof(drivers[0]); i++) {
        before = resolved;
        failures += check_registers(drivers[i].name, drivers[i].driver, drivers[i].slot, GUEST_RECORD);
        if (resolved != before + 1) {
            printf("FAIL %s: the guest target was not resolved\n", drivers[i].name);
            failures++;
        }
        before = resolved;
        failures += check_registers(drivers[i].name, drivers[i].driver, drivers[i].slot,
                                    (uint32_t)(uintptr_t)record_registers);
        if (resolved != before) {
            printf("FAIL %s: a host target was resolved as a guest one\n", drivers[i].name);
            failures++;
        }
    }
    before = resolved;
    failures += check_registers("direct call", call_direct, -1, GUEST_RECORD);
    if (resolved != before + 1) failures++, printf("FAIL direct call: the guest address was not resolved\n");
    through = (Add)(uintptr_t)GUEST_ADD;
    if (through(1, 2, 3) != 6) failures++, printf("FAIL call to a KSEG0 guest address\n");
    through = (Add)(uintptr_t)GUEST_KSEG1;
    if (through(10, 20, 30) != 60) failures++, printf("FAIL call to a KSEG1 guest address\n");
    through = (Add)(uintptr_t)GUEST_PHYSICAL;
    if (through(5, 5, 5) != 15) failures++, printf("FAIL call to a physical guest address\n");
    if (call_from_c((Add)(uintptr_t)GUEST_ADD, 4) != 7) failures++, printf("FAIL call to a guest address from C\n");
    {
        static const struct { const char *name; int (*tail)(int, int, int); } tails[] = {
            {"eax", tail_eax}, {"ecx", tail_ecx}, {"edx", tail_edx}};
        for (i = 0; i < sizeof(tails) / sizeof(tails[0]); i++) {
            tail_target = GUEST_ADD;
            before = resolved;
            if (tails[i].tail(1, 2, 3) != 6 || resolved != before + 1) {
                failures++, printf("FAIL tail jmp through %s to a guest address\n", tails[i].name);
            }
            tail_target = (uint32_t)(uintptr_t)add3;
            before = resolved;
            if (tails[i].tail(4, 5, 6) != 15 || resolved != before) {
                failures++, printf("FAIL tail jmp through %s to a host function\n", tails[i].name);
            }
        }
        if (tail_direct(7, 8, 9) != 24) failures++, printf("FAIL tail jmp to a direct-call stub\n");
    }
    through = add3;
    before = resolved;
    if (through(1, 1, 1) != 3 || resolved != before) failures++, printf("FAIL call to a host function\n");
    if (misaligned) failures++, printf("FAIL the resolver ran on a misaligned stack %u times\n", misaligned);
    if (others && ((uintptr_t)record_registers & 0x5fe00000u) && ((uintptr_t)add3 & 0x5fe00000u) &&
        ((uintptr_t)main & 0x5fe00000u)) {
        failures++, printf("FAIL host targets went to the resolver %u times\n", others);
    }
    printf("%s\n", failures ? "branch thunks: FAILED" : "branch thunks: ok");
    return failures != 0;
}
#elif defined(__aarch64__)
/* 64-bit ARM (AArch64): the thunks clang's -mharden-sls=blr calls
 * (__llvm_slsblr_thunk_x0..x29 but x18), the same checks, and the fast path
 * for a host target above 4 GB. With NDK clang, e.g.
 *   clang --target=aarch64-linux-android24 -static -O2 -Isrc
 *         -mharden-sls=blr -fno-optimize-sibling-calls -fno-jump-tables
 *         -Wl,--image-base=0x40000000
 *         tests/pc/branch_thunks_test.c src/pc/guest/branch_thunks.c
 * and run under qemu-aarch64 (user mode) or on a device. */
#include <sys/mman.h>
#define GUEST_RECORD 0x80001000u
#define GUEST_ADD 0x80002004u
#define GUEST_PHYSICAL 0x00012340u
#define GUEST_KSEG1 0xa0002004u

/* What record_registers saw: X0-X30, SP, then Q0 and Q7 (low halves). */
uint64_t seen[34];
uint64_t sp_before, lr_expected, driver_target, tail_target;
const uint64_t vfp_magic[2] = {0x0123456789abcdefull, 0xfedcba9876543210ull};
static unsigned resolved, others, misaligned;
void record_registers(void);
__asm__(".text\n"
        ".globl record_registers\n"
        "record_registers:\n"
        "    str x16, [sp, #-16]!\n"
        "    adrp x16, seen\n"
        "    add x16, x16, :lo12:seen\n"
        "    stp x0, x1, [x16, #0]\n    stp x2, x3, [x16, #16]\n    stp x4, x5, [x16, #32]\n"
        "    stp x6, x7, [x16, #48]\n    stp x8, x9, [x16, #64]\n    stp x10, x11, [x16, #80]\n"
        "    stp x12, x13, [x16, #96]\n  stp x14, x15, [x16, #112]\n"
        "    ldr x0, [sp], #16\n"
        "    stp x0, x17, [x16, #128]\n  stp x18, x19, [x16, #144]\n stp x20, x21, [x16, #160]\n"
        "    stp x22, x23, [x16, #176]\n stp x24, x25, [x16, #192]\n stp x26, x27, [x16, #208]\n"
        "    stp x28, x29, [x16, #224]\n str x30, [x16, #240]\n"
        "    mov x0, sp\n    str x0, [x16, #248]\n"
        "    str d0, [x16, #256]\n    str d7, [x16, #264]\n"
        "    ret\n");

/* call_through_xN(target): X0-X15 and X19-X28 set to 0x0101010101010101 *
 * (number + 1), D0 and D7 to vfp_magic, XN to `target`, then a call
 * through XN's thunk. */
#define SET(r, v) "    ldr x" #r ", =" #v "\n"
#define DRIVER(n)                                                                   \
    void call_through_x##n(uint64_t target);                                        \
    __asm__(".text\n"                                                               \
            ".globl call_through_x" #n "\n"                                         \
            "call_through_x" #n ":\n"                                               \
            "    stp x29, x30, [sp, #-96]!\n"                                       \
            "    stp x19, x20, [sp, #16]\n stp x21, x22, [sp, #32]\n"               \
            "    stp x23, x24, [sp, #48]\n stp x25, x26, [sp, #64]\n"               \
            "    stp x27, x28, [sp, #80]\n"                                         \
            "    ldr x1, =driver_target\n    str x0, [x1]\n"                        \
            "    ldr x1, =vfp_magic\n    ldr d0, [x1]\n    ldr d7, [x1, #8]\n"      \
            "    ldr x1, =lr_expected\n    adr x2, 1f\n    str x2, [x1]\n"          \
            "    ldr x1, =sp_before\n    mov x2, sp\n    str x2, [x1]\n"            \
            SET(0, 0x0101010101010101) SET(1, 0x0202020202020202)                   \
            SET(2, 0x0303030303030303) SET(3, 0x0404040404040404)                   \
            SET(4, 0x0505050505050505) SET(5, 0x0606060606060606)                   \
            SET(6, 0x0707070707070707) SET(7, 0x0808080808080808)                   \
            SET(8, 0x0909090909090909) SET(9, 0x0a0a0a0a0a0a0a0a)                   \
            SET(10, 0x0b0b0b0b0b0b0b0b) SET(11, 0x0c0c0c0c0c0c0c0c)                 \
            SET(12, 0x0d0d0d0d0d0d0d0d) SET(13, 0x0e0e0e0e0e0e0e0e)                 \
            SET(14, 0x0f0f0f0f0f0f0f0f) SET(15, 0x1010101010101010)                 \
            SET(19, 0x1414141414141414) SET(20, 0x1515151515151515)                 \
            SET(21, 0x1616161616161616) SET(22, 0x1717171717171717)                 \
            SET(23, 0x1818181818181818) SET(24, 0x1919191919191919)                 \
            SET(25, 0x1a1a1a1a1a1a1a1a) SET(26, 0x1b1b1b1b1b1b1b1b)                 \
            SET(27, 0x1c1c1c1c1c1c1c1c) SET(28, 0x1d1d1d1d1d1d1d1d)                 \
            "    ldr x" #n ", =driver_target\n"                                     \
            "    ldr x" #n ", [x" #n "]\n"                                          \
            "    bl __llvm_slsblr_thunk_x" #n "\n"                                  \
            "1:  ldp x19, x20, [sp, #16]\n ldp x21, x22, [sp, #32]\n"               \
            "    ldp x23, x24, [sp, #48]\n ldp x25, x26, [sp, #64]\n"               \
            "    ldp x27, x28, [sp, #80]\n"                                         \
            "    ldp x29, x30, [sp], #96\n"                                         \
            "    ret\n"                                                             \
            ".ltorg\n");
DRIVER(0) DRIVER(1) DRIVER(2) DRIVER(3) DRIVER(4) DRIVER(5) DRIVER(6) DRIVER(7) DRIVER(8) DRIVER(9)
DRIVER(10) DRIVER(11) DRIVER(12) DRIVER(13) DRIVER(14) DRIVER(15) DRIVER(16) DRIVER(17)
DRIVER(19) DRIVER(20) DRIVER(21) DRIVER(22) DRIVER(23) DRIVER(24) DRIVER(25) DRIVER(26) DRIVER(27) DRIVER(28)

/* A module function the C calls by name, as build_game32.py writes its host
 * stub: the address in X16, a branch to Memories_GuestBranchDirect. */
__asm__(".text\n"
        "direct_add:\n"
        "    movz x16, #0x2004\n"
        "    movk x16, #0x8000, lsl #16\n"
        "    b Memories_GuestBranchDirect\n"
        ".globl tail_x3\n"
        "tail_x3:\n"
        "    ldr x3, =tail_target\n    ldr x3, [x3]\n"
        "    b __llvm_slsblr_thunk_x3\n"
        ".globl tail_x17\n"
        "tail_x17:\n"
        "    ldr x17, =tail_target\n    ldr x17, [x17]\n"
        "    b __llvm_slsblr_thunk_x17\n"
        ".globl tail_x16\n"
        "tail_x16:\n"
        "    ldr x16, =tail_target\n    ldr x16, [x16]\n"
        "    b __llvm_slsblr_thunk_x16\n"
        ".globl tail_direct\n"
        "tail_direct:\n"
        "    b direct_add\n"
        ".ltorg\n");
int tail_x3(int a, int b, int c);
int tail_x16(int a, int b, int c);
int tail_x17(int a, int b, int c);
int tail_direct(int a, int b, int c);

static int add3(int a, int b, int c) { return a + b + c; }

static void *resolve(unsigned address)
{
    uintptr_t sp;
    __asm__ volatile("mov %0, sp" : "=r"(sp));
    if (sp & 15) misaligned++; /* AAPCS64: 16-byte aligned */
    if (address == GUEST_RECORD || address == GUEST_ADD || address == GUEST_KSEG1 || address == GUEST_PHYSICAL) {
        resolved++;
    } else {
        others++;
    }
    if (address == GUEST_RECORD) return (void *)(uintptr_t)record_registers;
    if (address == GUEST_ADD || address == GUEST_KSEG1 || address == GUEST_PHYSICAL) return (void *)(uintptr_t)add3;
    return (void *)(uintptr_t)address;
}

/* `slot`: the register that held the target, -1 for none. X16 and X17 are
 * the registers a thunk may change; on the slow path (`slow`) X9-X15 too,
 * which a call does not keep under AAPCS64. */
static int check_registers(const char *name, void (*driver)(uint64_t), int slot, uint64_t target, int slow)
{
    int i, failures = 0;
    memset(seen, 0, sizeof(seen));
    driver(target);
    for (i = 0; i < 29; i++) {
        uint64_t expected = i == slot ? target : 0x0101010101010101ull * (uint64_t)(i + 1);
        if (i == 16 || i == 17 || i == 18) continue;
        if (slow && i >= 9 && i <= 15) continue; /* caller-saved temporaries: the resolver's */
        if (i == slot && (target >> 32 || (target & 0x5fe00000u))) expected = target; /* fast path: as it was */
        if (seen[i] != expected && !(i == slot && seen[i] == (uint64_t)(uintptr_t)record_registers)) {
            printf("FAIL %s -> 0x%llx: x%d is 0x%llx, not 0x%llx\n", name, (unsigned long long)target, i,
                   (unsigned long long)seen[i], (unsigned long long)expected);
            failures++;
        }
    }
    if (seen[31] != sp_before) failures++, printf("FAIL %s -> 0x%llx: the stack moved\n", name, (unsigned long long)target);
    if (seen[30] != lr_expected) failures++, printf("FAIL %s: lr is not the return address\n", name);
    if (seen[32] != vfp_magic[0] || seen[33] != vfp_magic[1]) failures++, printf("FAIL %s: d0 or d7 changed\n", name);
    return failures;
}

typedef int (*Add)(int, int, int);

static int __attribute__((noinline)) call_from_c(Add function, int x)
{
    return function(x, 1, 2) + 0; /* a call through a thunk: sibling calls are off */
}

int main(void)
{
    static void (*const drivers[])(uint64_t) = {
        call_through_x0, call_through_x1, call_through_x2, call_through_x3, call_through_x4, call_through_x5,
        call_through_x6, call_through_x7, call_through_x8, call_through_x9, call_through_x10, call_through_x11,
        call_through_x12, call_through_x13, call_through_x14, call_through_x15, call_through_x16,
        call_through_x17, NULL, call_through_x19, call_through_x20, call_through_x21, call_through_x22,
        call_through_x23, call_through_x24, call_through_x25, call_through_x26, call_through_x27,
        call_through_x28};
    volatile Add through;
    unsigned i, before;
    int failures = 0;
    char name[8];
    void *high;
    if (!((uintptr_t)record_registers & 0x5fe00000u) || (uintptr_t)record_registers >> 32) {
        printf("FAIL the test's code at %p is not where the thunks' fast path lets it through; link it at "
               "0x40000000\n", (void *)record_registers);
        return 1;
    }
    Memories_GuestBranchResolver = resolve;
    for (i = 0; i < sizeof(drivers) / sizeof(drivers[0]); i++) {
        if (!drivers[i]) continue;
        snprintf(name, sizeof(name), "x%u", i);
        before = resolved;
        failures += check_registers(name, drivers[i], (int)i, GUEST_RECORD, 1);
        if (resolved != before + 1) failures++, printf("FAIL %s: the guest target was not resolved\n", name);
        before = resolved;
        failures += check_registers(name, drivers[i], (int)i, (uint64_t)(uintptr_t)record_registers, 0);
        if (resolved != before) failures++, printf("FAIL %s: a host target was resolved as a guest one\n", name);
    }
    /* A host target above 4 GB (a system library's): a copy of
     * record_registers' code in a page mapped high goes straight through. */
    high = mmap((void *)0x7f0000000000ull, 4096, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (high != MAP_FAILED && (uintptr_t)high >> 32) {
        /* adrp is position-dependent: a tiny function that only returns
         * 42 instead (mov w0, #42; ret). */
        static const uint32_t code[] = {0x52800540u, 0xd65f03c0u};
        memcpy(high, code, sizeof(code));
        mprotect(high, 4096, PROT_READ | PROT_EXEC);
        __builtin___clear_cache((char *)high, (char *)high + sizeof(code));
        before = others;
        through = (Add)high;
        if (through(0, 0, 0) != 42 || others != before) failures++, printf("FAIL call to a host function above 4 GB\n");
    } else {
        printf("note: no page above 4 GB to test the upper-half fast path\n");
    }
    through = (Add)(uintptr_t)GUEST_ADD;
    if (through(1, 2, 3) != 6) failures++, printf("FAIL call to a KSEG0 guest address\n");
    through = (Add)(uintptr_t)GUEST_KSEG1;
    if (through(10, 20, 30) != 60) failures++, printf("FAIL call to a KSEG1 guest address\n");
    through = (Add)(uintptr_t)GUEST_PHYSICAL;
    if (through(5, 5, 5) != 15) failures++, printf("FAIL call to a physical guest address\n");
    if (call_from_c((Add)(uintptr_t)GUEST_ADD, 4) != 7) failures++, printf("FAIL call to a guest address from C\n");
    {
        static const struct { const char *name; int (*tail)(int, int, int); } tails[] = {
            {"x3", tail_x3}, {"x16", tail_x16}, {"x17", tail_x17}};
        for (i = 0; i < sizeof(tails) / sizeof(tails[0]); i++) {
            tail_target = GUEST_ADD;
            before = resolved;
            if (tails[i].tail(1, 2, 3) != 6 || resolved != before + 1) {
                failures++, printf("FAIL tail branch through %s to a guest address\n", tails[i].name);
            }
            tail_target = (uint64_t)(uintptr_t)add3;
            before = resolved;
            if (tails[i].tail(4, 5, 6) != 15 || resolved != before) {
                failures++, printf("FAIL tail branch through %s to a host function\n", tails[i].name);
            }
        }
        if (tail_direct(7, 8, 9) != 24) failures++, printf("FAIL tail branch to a direct-call stub\n");
    }
    through = add3;
    before = resolved;
    if (through(1, 1, 1) != 3 || resolved != before) failures++, printf("FAIL call to a host function\n");
    if (misaligned) failures++, printf("FAIL the resolver ran on a misaligned stack %u times\n", misaligned);
    if (others) failures++, printf("FAIL host targets went to the resolver %u times\n", others);
    printf("%s\n", failures ? "branch thunks: FAILED" : "branch thunks: ok");
    return failures != 0;
}
#else
int main(void)
{
    puts("branch thunks: x86 and AArch64 only");
    return 0;
}
#endif
