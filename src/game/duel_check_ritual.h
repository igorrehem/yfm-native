#ifndef MEMORIES_DECOMP_DUEL_CHECK_RITUAL_H
#define MEMORIES_DECOMP_DUEL_CHECK_RITUAL_H

#include "../types.h"
#include "card_constants.h"

/* Optional ritual-match output: the three matched tribute display objects,
 * followed by a word the function clears. */
typedef struct DuelRitualResult {
    void *G32 tribute_objects[DUEL_RITUAL_TRIBUTE_COUNT];
    s32 field_0C;
} DuelRitualResult;

typedef char DuelRitualResult_size_must_be_0x10[
    sizeof(DuelRitualResult) == 0x10 ? 1 : -1
];
typedef char DuelRitualResult_clear_word_offset_must_be_0x0C[
    (u32)&((DuelRitualResult *)0)->field_0C == 0x0C ? 1 : -1
];

/* The recipe table that Duel_CheckRitual walks.
 * Duel_LoadPackageStage's case 4 fills it, handing the address to a transfer
 * as both value_08 and value_0C with mode 0x800, the same way its case 3 fills
 * gDuel_aFusionTable. Duel_CheckRitual then scans it as fixed-size records --
 * id first, stepping by DUEL_RITUAL_RECIPE_HALFWORD_COUNT -- and stops on a
 * zero id, so the loaded data is self-terminating.
 *
 * The same memory is also borrowed as scratch once the duel is over:
 * DuelScene_UpdateResultOutro casts it to DuelResultSpriteSlot * for the outro, which
 * duel_result_outro.h documents as "the gDuel_awRitualData scratch". That reuse is
 * why the array stays unsized here -- the two consumers disagree about the
 * element type, and only the halfword view belongs to this header.
 *
 * DuelScene_UpdateResultRewards reuses the same backing for a complete
 * 0x40-byte result display record after recipe processing has ended. Its guarded view
 * below describes that bounded record, not a new allocation. */
#ifdef DUEL_RITUAL_DATA_RESULT_VIEW
#include "duel_result_display.h"
extern DuelResultDisplayState gDuel_awRitualData;
#else
extern u16 gDuel_awRitualData[];
#endif

s32 Duel_CheckRitual(DuelRitualResult *out, s32 ritual_id);

#ifdef MEMORIES_PC
/* The ritual card a played ritual's effect checks: a card played with
 * another's effect (a copy past the disc's, or a card whose "effect" names a
 * ritual) leaves that card in gDuel_wEffectCardID, and its own recipe, when
 * a mod gave it one, is the one it summons by. */
s32 Duel_RitualPlayed(void);

/* Every tribute of the last ritual Duel_CheckRitual matched. A mod's
 * ritual may take one to five monsters, from the field, the hand or both
 * (tables.h, Tables_RitualRule); `out` holds only three display objects,
 * and a hand card has none, so the ritual effect reads them all here. */
#define DUEL_RITUAL_TRIBUTE_MAX 5
typedef struct {
    s32 count;                          /* tributes; 0: no match */
    s32 extended;                       /* not the disc's three from the field */
    s16 record[DUEL_RITUAL_TRIBUTE_MAX];   /* each one's D_801A7AD8 index */
    s8 hand_slot[DUEL_RITUAL_TRIBUTE_MAX]; /* its hand slot, or -1 on the field */
    s16 zone;                           /* the record the result goes to */
    s16 result;
} DuelRitualMatch;

/* DuelEffect_ApplyRitual's ritual, from its own Duel_CheckRitual to the
 * tributes leaving: Begin takes the match that call made. While one is
 * under way, a check with an output other than the effect's work slots
 * (the 3D effect's, func_8014A8E4, native or interpreted) is answered with
 * it, whatever card it names: the effect names the disc ritual whose
 * effect was played, not a copy with its own recipe. */
void Duel_RitualBegin(void);
const DuelRitualMatch *Duel_RitualActive(void);
/* The ritual under way's tributes on the field, in recipe order, at most
 * DUEL_RITUAL_TRIBUTE_MAX; -1 with none under way. */
s32 Duel_RitualFieldObjects(void *G32 *objects);
/* An extended ritual's tributes leave: the field's records are emptied,
 * the hand's slots cleared. Returns the record its result goes to and
 * ends the ritual. */
s32 Duel_RitualSpend(void);
void Duel_RitualEnd(void);

/* The 3D effect's cards: every field tribute, and the motion of a fourth
 * and fifth, for which its work area has no room. Kept here because the
 * effects bank, swapped in and out with its overlay, may have no variables
 * of its own (tools/pc/build_game32.py, GATED_MODULES). */
#include "../psyq/libgte.h"
typedef struct {
    void *G32 cards[DUEL_RITUAL_TRIBUTE_MAX];
    s32 count;
    SVECTOR velocities[DUEL_RITUAL_TRIBUTE_MAX - DUEL_RITUAL_TRIBUTE_COUNT];
    SVECTOR rotations[DUEL_RITUAL_TRIBUTE_MAX - DUEL_RITUAL_TRIBUTE_COUNT];
    u16 states[DUEL_RITUAL_TRIBUTE_MAX - DUEL_RITUAL_TRIBUTE_COUNT];
} DuelRitualFlight;
DuelRitualFlight *Duel_RitualFlight(void);

/* Duel_CheckRitual's search over the tributes of a ritual with its own rule
 * (duel_check_ritual.c, extended_match). */
#include "duel_grid.h"
#include "../pc/cards/tables.h"
typedef struct {
    TablesRitualRule rule;          /* a copy: no pointer in it (check_g32) */
    s16 record[2 * DUEL_FIELD_ROW_SIZE];
    s8 hand_slot[2 * DUEL_FIELD_ROW_SIZE];
    s32 candidates;
    s32 order[DUEL_RITUAL_TRIBUTE_MAX];
    s32 pick[DUEL_RITUAL_TRIBUTE_MAX];
    s32 best[DUEL_RITUAL_TRIBUTE_MAX];
    s32 found, free_zone, prefer_defense;
} RitualSearch;
#endif

#endif
