#ifndef MEMORIES_PC_GUEST_MODEL_RECOMP_H
#define MEMORIES_PC_GUEST_MODEL_RECOMP_H
/* MODEL.MRG's variant control modules translated to C (tools/pc/model_recomp.py
 * writes them into the build folder from the user's disc). The translated
 * code keeps the interpreter's semantics (src/pc/guest/mips.c): the MIPS
 * registers live in a context, guest memory is reached at its own addresses
 * and every call out of a module goes through the interpreter's bridge to
 * native code, on the interpreter's guest stack. A program runs only while
 * the code in guest memory is the bytes it was translated from. */
#include <setjmp.h>
#include <stddef.h>
#include <stdint.h>

#include "pc/compat/gte.h"
#include "pc/guest/image.h"

typedef struct MemoriesRecompContext {
    uint32_t r[32], hi, lo;
    uint32_t delta; /* 0 in slot A, 0x40000 in slot B: where the module's own addresses moved */
    jmp_buf *escape;
} MemoriesRecompContext;

typedef void MemoriesRecompFunction(MemoriesRecompContext *c, uint32_t ra);

typedef struct MemoriesModelProgram {
    uint32_t identifier[2];        /* the module's first word in slot A and in slot B */
    MemoriesRecompFunction *entry; /* the module's entry at +4 */
    const uint32_t *runs;          /* (slot A address, length) of every translated code word */
    unsigned run_count;
    uint8_t sha256[2][32];         /* of those bytes, in slot A and in slot B */
} MemoriesModelProgram;

extern const MemoriesModelProgram Memories_ModelPrograms[];
extern const unsigned Memories_ModelProgramCount;

/* Run the module whose identifier word is at `module` (0x8013B000 or
 * 0x8017B000) with the MIPS arguments `args`: 0 and its v0 in *result,
 * 1 when no translation of the loaded code exists (interpret it), -1 when
 * the translated code failed after printing why. */
int Memories_ModelRecompTry(uint32_t module, const uint32_t *args, unsigned count, uint32_t *result);
/* The loader stored into guest memory (Memories_GuestWritten). Async-signal-safe. */
void Memories_ModelRecompWritten(uintptr_t destination, size_t length);
struct MemoriesState;
/* A loaded state's modules are unproven until checked again. */
void Memories_ModelRecompState(struct MemoriesState *state);

/* The bridges in mips.c. */
uint32_t Memories_RecompNative(MemoriesRecompContext *c, uint32_t target, uint32_t pc);
int Memories_MipsStackBegin(uint32_t *sp, uint32_t *saved);
void Memories_MipsStackEnd(uint32_t saved);
/* A result handed to native code, as the interpreter hands its v0. */
uint32_t Memories_MipsHand(uint32_t value);
_Noreturn void Memories_RecompBadReturn(MemoriesRecompContext *c, uint32_t pc, uint32_t target, uint32_t expected);
_Noreturn void Memories_RecompBadJump(MemoriesRecompContext *c, uint32_t pc, uint32_t target);

#ifdef MEMORIES_RECOMP_GENERATED
/* What the generated code is written in: mips.c's `plain`, word for word. */
#define R(n) (c->r[n])
#define Rc_At(a) ((uintptr_t)MEMORIES_SCRATCHPAD_VIEW((uint32_t)(a)))
static inline uint32_t Rc_L32(uint32_t a) { return *(uint32_t *)Rc_At(a); }
static inline uint16_t Rc_L16(uint32_t a) { return *(uint16_t *)Rc_At(a); }
static inline uint8_t Rc_L8(uint32_t a) { return *(uint8_t *)Rc_At(a); }
static inline void Rc_S32(uint32_t a, uint32_t v) { *(uint32_t *)Rc_At(a) = v; }
static inline void Rc_S16(uint32_t a, uint16_t v) { *(uint16_t *)Rc_At(a) = v; }
static inline void Rc_S8(uint32_t a, uint8_t v) { *(uint8_t *)Rc_At(a) = v; }
static inline uint32_t Rc_Lwl(uint32_t old, uint32_t a)
{
    return (old & (0x00ffffffu >> ((a & 3) * 8))) | (Rc_L32(a & ~3u) << ((3 - (a & 3)) * 8));
}
static inline uint32_t Rc_Lwr(uint32_t old, uint32_t a)
{
    return (old & (0xffffff00u << ((3 - (a & 3)) * 8))) | (Rc_L32(a & ~3u) >> ((a & 3) * 8));
}
static inline void Rc_Swl(uint32_t a, uint32_t v)
{
    uint32_t word = Rc_L32(a & ~3u);
    Rc_S32(a & ~3u, (word & (0xffffff00u << ((a & 3) * 8))) | (v >> ((3 - (a & 3)) * 8)));
}
static inline void Rc_Swr(uint32_t a, uint32_t v)
{
    uint32_t word = Rc_L32(a & ~3u);
    Rc_S32(a & ~3u, (word & (0x00ffffffu >> ((3 - (a & 3)) * 8))) | (v << ((a & 3) * 8)));
}
static inline void Rc_Mult(MemoriesRecompContext *c, uint32_t a, uint32_t b)
{
    int64_t p = (int64_t)(int32_t)a * (int32_t)b;
    c->lo = (uint32_t)p;
    c->hi = (uint32_t)(p >> 32);
}
static inline void Rc_Multu(MemoriesRecompContext *c, uint32_t a, uint32_t b)
{
    uint64_t p = (uint64_t)a * b;
    c->lo = (uint32_t)p;
    c->hi = (uint32_t)(p >> 32);
}
static inline void Rc_Div(MemoriesRecompContext *c, uint32_t a, uint32_t b)
{
    if (b) {
        if (b == 0xffffffffu) { c->lo = (uint32_t)-(int32_t)a; c->hi = 0; }
        else { c->lo = (uint32_t)((int32_t)a / (int32_t)b); c->hi = (uint32_t)((int32_t)a % (int32_t)b); }
    } else {
        c->lo = (int32_t)a < 0 ? 1u : 0xffffffffu;
        c->hi = a;
    }
}
static inline void Rc_Divu(MemoriesRecompContext *c, uint32_t a, uint32_t b)
{
    if (b) { c->lo = a / b; c->hi = a % b; }
    else { c->lo = 0xffffffffu; c->hi = a; }
}
#endif
#endif
