/* The 64-bit build's compiler gate (tools/pc/build_game32.py --target
 * windows-x64 builds and runs it before the game, at -O0 and -O2).
 *
 * The game's stored pointers are clang's 4-byte `__ptr32 __uptr` there (G32,
 * src/port_ptr.h). clang 12 compiles them silently wrong: sizeof reports 4
 * for an array of such function pointers, but the code indexes it with an
 * 8-byte stride and reads the members after it at the wrong offsets
 * (x64 gate 1, 2026-09-29). clang 21 and 22 were verified. This checks the
 * version and each construct the game relies on, and exits non-zero with the
 * reason when one fails. It must be linked below 4 GB (--image-base
 * 0x40000000), like the game, since it keeps its own function addresses in
 * 4-byte slots. */
#include "types.h"
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#if !defined(__clang__) || __clang_major__ < 21
#error "the 64-bit build needs clang 21 or later (clang 12 miscompiles __ptr32 arrays)"
#endif
#if !defined(__x86_64__)
#error "this gate is for the x86-64 build"
#endif

typedef s32 (*Handler)(s32);

typedef struct Object {
    u8 *G32 text;
    struct Object *G32 next;
    s32 (*G32 handlers[3])(s32);
    s32 after; /* read wrong behind a miscompiled array */
    s16 x, y;
} Object;
_Static_assert(sizeof(Object) == 28, "the retail layout: 4-byte pointers");
_Static_assert(offsetof(Object, after) == 20, "members after a G32 array");

static s32 add_one(s32 value) { return value + 1; }
static s32 twice(s32 value) { return value * 2; }
static s32 negate(s32 value) { return -value; }

static int failures;

static void expect(int ok, const char *what)
{
    if (!ok) {
        printf("x64 compiler gate: %s\n", what);
        failures++;
    }
}

int main(void)
{
    static Object object, other;
    static u8 *G32 table[4];
    volatile int index = 1;
    Object *volatile view = &object;
    u8 *G32 *walk;
    uintptr_t value;
    int i;

    expect((uintptr_t)main < 0x100000000ull, "the gate is not linked below 4 GB (--image-base=0x40000000)");
    object.handlers[0] = add_one;
    object.handlers[1] = twice;
    object.handlers[2] = negate;
    object.after = 0x12345678;
    object.next = &other;
    other.after = 7;
    expect((char *)&view->handlers[index] - (char *)&view->handlers[0] == 4, "G32 function-pointer array stride");
    expect(CALL32(Handler, view->handlers[index])(21) == 42, "call through a G32 array element");
    expect(CALL32(Handler, view->handlers[index + 1])(5) == -5, "call through the next element");
    expect(view->after == 0x12345678, "a member after a G32 function-pointer array");
    expect(view->next->after == 7, "a chained G32 read");

    /* Zero-extension: a KSEG0 address stays 0x80xxxxxx, never 0xffffffff80xxxxxx. */
    object.text = (u8 *)(uintptr_t)0x80012340u;
    value = (uintptr_t)view->text;
    expect(value == 0x80012340u, "G32 loads zero-extend");

    /* A local walking a table of guest pointers steps 4 bytes. */
    for (i = 0; i < 4; i++) table[i] = (u8 *)(uintptr_t)(0x80010000u + 0x100u * (unsigned)i);
    walk = table;
    walk += index;
    expect((uintptr_t)*walk == 0x80010100u && (char *)(walk + 1) - (char *)walk == 4, "T *G32 * walks 4 bytes");
    expect(sizeof(table) == 16, "an array of G32 data pointers is 4 bytes an element");

    if (failures) return 1;
    printf("x64 compiler gate: clang %d.%d passed\n", __clang_major__, __clang_minor__);
    return 0;
}
