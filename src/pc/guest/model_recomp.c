#include "model_recomp.h"
#include "sha256.h"
#include "state.h"
#include "pc/debug/log.h"
#include <stdio.h>
#include <string.h>

/* Runs the translated MODEL variant modules (model_recomp.h). A slot's
 * program is chosen by the module's first word and checked once per load:
 * the SHA-256 of the code words it was translated from, at that slot's
 * addresses, must match the bytes in guest memory. Anything else, a mod or a
 * patched disc, is left to the interpreter. */

#define SLOT_A 0x8013B000u
#define SLOT_B 0x8017B000u
#define MODULE_SIZE 0x5000u

enum { UNKNOWN, VERIFIED, CHANGED };

typedef struct Slot {
    uint32_t identifier;
    const MemoriesModelProgram *program;
    unsigned char verdict;
} Slot;

static Slot slots[2];
static volatile unsigned char pending[2] = {1, 1};
static uint8_t code[MODULE_SIZE];

static const MemoriesModelProgram *find(int slot, uint32_t identifier)
{
    unsigned i;
    for (i = 0; i < Memories_ModelProgramCount; i++) {
        if (Memories_ModelPrograms[i].entry && Memories_ModelPrograms[i].identifier[slot] == identifier) {
            return &Memories_ModelPrograms[i];
        }
    }
    return NULL;
}

static int verify(const MemoriesModelProgram *program, int slot)
{
    uint32_t delta = slot ? SLOT_B - SLOT_A : 0;
    size_t used = 0;
    uint8_t digest[32];
    unsigned i;
    for (i = 0; i < program->run_count; i++) {
        uint32_t start = program->runs[2 * i] + delta, length = program->runs[2 * i + 1];
        if (used + length > sizeof(code)) {
            return 0;
        }
        memcpy(code + used, (const void *)(uintptr_t)start, length);
        used += length;
    }
    Sha256(code, used, digest);
    return memcmp(digest, program->sha256[slot], sizeof(digest)) == 0;
}

int Memories_ModelRecompTry(uint32_t module, const uint32_t *args, unsigned count, uint32_t *result)
{
    int slot = module == SLOT_B;
    Slot *s = &slots[slot];
    uint32_t identifier, sp, saved;
    MemoriesRecompContext c;
    jmp_buf escape;
    unsigned i;

    if (module != SLOT_A && module != SLOT_B) {
        return 1;
    }
    identifier = *(const uint32_t *)(uintptr_t)module;
    if (pending[slot] || s->verdict == UNKNOWN || s->identifier != identifier) {
        pending[slot] = 0;
        s->identifier = identifier;
        s->program = find(slot, identifier);
        s->verdict = s->program && verify(s->program, slot) ? VERIFIED : CHANGED;
        if (pending[slot]) {
            s->verdict = UNKNOWN; /* a delivery during the check: check again next time */
        }
        LOG(LOG_MODEL, "variant module %u (slot %c): %s", (unsigned)identifier, slot ? 'B' : 'A',
            s->verdict == VERIFIED ? "translated" : s->program ? "changed code: interpreter" : "interpreter");
    }
    if (s->verdict != VERIFIED) {
        return 1;
    }
    if (Memories_MipsStackBegin(&sp, &saved)) {
        return 1;
    }
    memset(&c, 0, sizeof(c));
    c.delta = slot ? SLOT_B - SLOT_A : 0;
    c.escape = &escape;
    c.r[29] = sp;
    for (i = 0; i < count && i < 4; i++) {
        c.r[4 + i] = args[i];
    }
    for (i = 4; i < count; i++) {
        *(uint32_t *)(uintptr_t)MEMORIES_SCRATCHPAD_VIEW(sp + i * 4) = args[i];
    }
    if (setjmp(escape)) {
        Memories_MipsStackEnd(saved);
        s->verdict = CHANGED;
        return -1;
    }
    s->program->entry(&c, 0);
    Memories_MipsStackEnd(saved);
    *result = Memories_MipsHand(c.r[2]);
    return 0;
}

void Memories_ModelRecompWritten(uintptr_t destination, size_t length)
{
    if (destination < SLOT_A + MODULE_SIZE && SLOT_A < destination + length) {
        pending[0] = 1;
    }
    if (destination < SLOT_B + MODULE_SIZE && SLOT_B < destination + length) {
        pending[1] = 1;
    }
}

void Memories_ModelRecompState(MemoriesState *state)
{
    if (Memories_StateLoading(state)) {
        pending[0] = pending[1] = 1;
    }
}
