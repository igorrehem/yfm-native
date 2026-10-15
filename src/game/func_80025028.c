#include "../types.h"
#include "duel_side_state.h"
#include "duel_grid.h"
#include "duel_card.h"
#include "display_object.h"
#include "func_80025028.h"
#ifdef MEMORIES_PC
#include "duel_card_layout.h"
#include "duel_card_record_lifecycle.h"
#include "pc/cards/cards.h"
#include "pc/cards/monster_effects_duel.h"
#endif

/* Defined rather than declared: the assembler only resolves a small global
   gp-relative when the translation unit defines it, and that is what makes the
   store below a single %gp_rel instruction whose load-delay slot needs the
   retail nop. The address itself comes from c_symbols.ld, which overrides this
   common symbol, so no storage is allocated here. */
u8 D_8009B1B8;

/* Searches the acting side's five mapped field slots for an occupied trap
   whose id equals the argument. A hit records the id in D_8009B22A, copies
   the owning object's field_6A slot index to D_8009B1B8 and returns the id; a
   miss leaves D_8009B22A cleared and returns 0. */
s32 Duel_SelectTrapByCardId(s32 arg0)
{
    s32 i;
    s32 base;
    DuelCardRecord *record;
    DisplayObject *object;

    base = D_8009B1D5 * DUEL_FIELD_SIDE_GRID_SLOT_COUNT;
    D_8009B22A = 0;
    for (i = 0; i < DUEL_FIELD_ROW_SIZE; i++) {
        record = &D_801A7AD8[D_800907D8[i + base]];
        if (record->flags & DUEL_CARD_FLAG_OCCUPIED) {
#ifdef MEMORIES_PC
            /* A copy of the trap springs as the trap, a trap whose
               "effect" names it as it (cards.h Cards_TrapId). */
            if (Cards_TrapId((s16)record->card_id) == arg0) {
                if (Cards_CardEffectsReplace(record->card_id)) {
                    /* It springs under the same condition, but its custom
                     * work replaces the retail reaction. Return no retail
                     * trap so the caller keeps its ordinary spell path. */
                    int owner = (int)(record - D_801A7AD8) / DUEL_CARD_SIDE_RECORD_COUNT;
                    MonsterEffects_TrapPlayed(record->card_id, owner);
                    DuelCard_RemoveFromField(record);
                    D_800E9FF0[owner].rank.traps_triggered++;
                    return 0;
                }
#else
            if ((s16) record->card_id == arg0) {
#endif
                object = (DisplayObject *)record->object;
                D_8009B22A = arg0;
                D_8009B1B8 = object->field_6A;
                return arg0;
            }
        }
    }
    return 0;
}
