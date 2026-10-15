#include "../types.h"
#include "duel_side_state.h"
#include "card_constants.h"
#include "duel_card.h"
#include "display_object.h"
#include "duel_card_record_lifecycle.h"
#include "duel_card_staging.h"
#include "duel_action_lock.h"
#include "duel_card_layout.h"
#include "duel_effect.h"
#include "duel_effect_request.h"
#include "duel_grid.h"
#include "sound.h"
#include "view_state.h"
#include "func_80022D94.h"
#include "../unmatched.h"
#include "duel_trap_resolution.h"
#ifdef MEMORIES_PC
#include "pc/cards/cards.h"
#include "pc/cards/monster_effects_duel.h"
#include "pc/cards/tables.h"
#endif

/* Small data at 0x8009AF24, owned here: the attack threshold of each trap
   from House of Adhesive Tape through Widespread Ruin, which
   Duel_SelectAttackTrap
   scales by 100 before comparing. The last entry is the 255 that keeps
   Widespread Ruin unconditional. */
u8 gDuel_abTrapAttackThresholds[DUEL_ATTACK_TRAP_COUNT] = {
    DUEL_HOUSE_OF_ADHESIVE_TAPE_ATTACK_THRESHOLD /
        DUEL_ATTACK_TRAP_THRESHOLD_SCALE,
    DUEL_EATGABOON_ATTACK_THRESHOLD / DUEL_ATTACK_TRAP_THRESHOLD_SCALE,
    DUEL_BEAR_TRAP_ATTACK_THRESHOLD / DUEL_ATTACK_TRAP_THRESHOLD_SCALE,
    DUEL_INVISIBLE_WIRE_ATTACK_THRESHOLD / DUEL_ATTACK_TRAP_THRESHOLD_SCALE,
    DUEL_ACID_TRAP_HOLE_ATTACK_THRESHOLD / DUEL_ATTACK_TRAP_THRESHOLD_SCALE,
    DUEL_WIDESPREAD_RUIN_ATTACK_THRESHOLD / DUEL_ATTACK_TRAP_THRESHOLD_SCALE,
};

#ifdef MEMORIES_PC
/* A replacement trap still uses its inherited/aliased attack threshold to
 * decide whether it springs. Once selected, however, it is consumed and its
 * data-defined effects take over; clearing the retail signal lets battle
 * continue without the old attack-trap behavior. */
static int resolve_replacement_attack_trap(void)
{
    DuelCardRecord *card = &D_801A7AD8[D_8009B1B8];
    int owner = (int)(card - D_801A7AD8) / DUEL_CARD_SIDE_RECORD_COUNT;
    if (!Cards_CardEffectsReplace(card->card_id)) return 1;
    MonsterEffects_AttackTrapPlayed(card->card_id, owner);
    DuelCard_RemoveFromField(card);
    D_800E9FF0[owner].rank.traps_triggered++;
    D_8009B22A = 0;
    D_8009B1B8 = 0;
    return 0;
}

/* Retail groups equal effects into one slot. With per-card thresholds that
 * would let an ineligible copy hide an eligible one. Check each actual card,
 * keeping retail effect priority and the last field slot for equal effects.
 * Leave the retail path untouched when no card has its own threshold. */
static int select_custom_attack_trap(u8 *attacker)
{
    int slot, custom = 0, chosen_effect = 0, chosen_slot = 0, fake_slot = -1;
    int base = D_8009B1D5 * DUEL_FIELD_SIDE_GRID_SLOT_COUNT;
    int attack;
    for (slot = 0; slot < DUEL_FIELD_ROW_SIZE; slot++) {
        DuelCardRecord *card = &D_801A7AD8[D_800907D8[base + slot]];
        if ((card->flags & DUEL_CARD_FLAG_OCCUPIED) && Cards_TrapThreshold(card->card_id, -1) >= 0)
            custom = 1;
    }
    if (!custom) return -1;
    attack = Duel_CalcCardStats(&D_801A7AD8[((DisplayObject *)attacker)->field_6A]) & 0xFFFF;
    for (slot = 0; slot < DUEL_FIELD_ROW_SIZE; slot++) {
        DuelCardRecord *card = &D_801A7AD8[D_800907D8[base + slot]];
        int effect, index, threshold;
        if (!(card->flags & DUEL_CARD_FLAG_OCCUPIED)) continue;
        effect = Cards_TrapId(card->card_id);
        if (effect == DUEL_FAKE_TRAP_CARD_ID && fake_slot < 0)
            fake_slot = ((DisplayObject *)card->object)->field_6A;
        index = effect - DUEL_ATTACK_TRAP_FIRST_CARD_ID;
        if ((unsigned)index >= DUEL_ATTACK_TRAP_COUNT) continue;
        threshold = Tables_TrapThreshold(index, gDuel_abTrapAttackThresholds[index] * DUEL_ATTACK_TRAP_THRESHOLD_SCALE);
        threshold = Cards_TrapThreshold(card->card_id, threshold);
        if (attack <= threshold && (!chosen_effect || effect <= chosen_effect)) {
            chosen_effect = effect;
            chosen_slot = ((DisplayObject *)card->object)->field_6A;
        }
    }
    if (!chosen_effect && fake_slot >= 0) {
        chosen_effect = DUEL_FAKE_TRAP_CARD_ID;
        chosen_slot = fake_slot;
    }
    if (!chosen_effect) return 0;
    D_8009B22A = chosen_effect;
    D_8009B1B8 = chosen_slot;
    return resolve_replacement_attack_trap();
}
#endif

s32 Duel_SelectAttackTrap(u8 *p) {
    s32 i;
    s32 off1;
    u8 *b1;
    s32 n;
    u8 *tbl2;
    u8 *rec2;
    u8 *b2;
    s32 off2;
    s32 h2;
    DuelCardRecord *e;
    s32 id;
    s32 sx;
    s32 sx2;
    s32 th;
    s32 sel;
    s32 off3;
    u8 *b3;
    u8 *q;
    u8 *tb;
    s32 v;
    DisplayObject *w;
    s32 off4;
    u8 *b4;
    s32 j2;
    u8 *tbl3;
    u8 *rec3;
    s32 h3;
    s32 k;

#ifdef MEMORIES_PC
    int custom_result = select_custom_attack_trap(p);
    if (custom_result >= 0) return custom_result;
#endif

    i = 0;
    off1 = 0x18000;
    b1 = D_8015C424;
    for (; i < DUEL_ATTACK_TRAP_COUNT; i++) {
        *(u16 *)(b1 + (u32)&((u16 *)0)[i] + off1 + 0x3C68) = 0;
    }
    n = 0;
    i = n;
    tbl2 = D_800907D8;
    rec2 = (u8 *)D_801A7AD8;
    b2 = D_8015C424;
    off2 = 0x18000;
    h2 = D_8009B1D5 * DUEL_FIELD_SIDE_GRID_SLOT_COUNT;
    for (; i < DUEL_FIELD_ROW_SIZE; i++) {
        e = (DuelCardRecord *G32)(*(u8 *G32)(i + h2 + (s32)tbl2) *
            DUEL_CARD_RECORD_SIZE + (s32)rec2);
        if ((e->flags & DUEL_CARD_FLAG_OCCUPIED) != 0) {
#ifdef MEMORIES_PC
            /* A copy of a trap springs as the trap, a trap whose "effect"
               names one as that one (cards.h Cards_TrapId). */
            id = (u16)Cards_TrapId(e->card_id);
#else
            id = (u16)e->card_id;
#endif
            if ((u32)(id - DUEL_ATTACK_TRAP_FIRST_CARD_ID) <
                DUEL_ATTACK_TRAP_COUNT) {
                sx = (s16)id;
                th = sx - DUEL_ATTACK_TRAP_FIRST_CARD_ID;
                n++;
                *(u16 *)(b2 + (u32)&((u16 *)0)[th] + off2 + 0x3C68) = id;
                sx2 = sx - 0x299;
                *(u16 *)(b2 + (u32)&((u16 *)0)[sx2] + off2 + 0x3C68) =
                    ((DisplayObject *)e->object)->field_6A;
            }
        }
    }
    if (n != 0) {
        do {
            th = Duel_CalcCardStats(
                &D_801A7AD8[p[(u32)&((DisplayObject *)0)->field_6A]]
            ) & 0xFFFF;
        } while (0);
        sel = -1;
        off3 = 0x18000;
        b3 = D_8015C424;
        q = b3 + 0xA;
        i = DUEL_ATTACK_TRAP_COUNT - 1;
        tb = gDuel_abTrapAttackThresholds;
        do {
            if (*(u16 *)(q + off3 + 0x3C68) != 0) {
                v = *(u8 *G32)(i + (s32)tb);
#ifdef MEMORIES_PC
                /* A mod's threshold for this trap (tables.h). */
                if (Tables_TrapThreshold(i, v * DUEL_ATTACK_TRAP_THRESHOLD_SCALE) < th) {
#else
                if (v * DUEL_ATTACK_TRAP_THRESHOLD_SCALE < th) {
#endif
                    break;
                }
                sel = i;
            }
            i--;
            q -= 2;
        } while (i >= 0);
        if (sel >= 0) {
            off4 = 0x18000;
            D_8009B22A = sel + DUEL_ATTACK_TRAP_FIRST_CARD_ID;
            b4 = D_8015C424;
            j2 = sel + 0x10;
            D_8009B1B8 =
                *(u8 *)(b4 + (u32)&((u16 *)0)[j2] + off4 + 0x3C68);
#ifdef MEMORIES_PC
            return resolve_replacement_attack_trap();
#else
            return 1;
#endif
        }
        if (0) {
        hit:
            w = e->object;
            D_8009B22A = v;
            D_8009B1B8 = w->field_6A;
#ifdef MEMORIES_PC
            return resolve_replacement_attack_trap();
#else
            return 1;
#endif
        }
    }
    i = 0;
    tbl3 = D_800907D8;
    rec3 = (u8 *)D_801A7AD8;
    h3 = D_8009B1D5 * DUEL_FIELD_SIDE_GRID_SLOT_COUNT;
    k = DUEL_FAKE_TRAP_CARD_ID;
    for (; i < DUEL_FIELD_ROW_SIZE; i++) {
        e = (DuelCardRecord *G32)(*(u8 *G32)(i + h3 + (s32)tbl3) *
            DUEL_CARD_RECORD_SIZE + (s32)rec3);
        if ((e->flags & DUEL_CARD_FLAG_OCCUPIED) != 0) {
#ifdef MEMORIES_PC
            v = Cards_TrapId(e->card_id);
#else
            v = e->card_id;
#endif
            if (v == k) {
                goto hit;
            }
        }
    }
    return 0;
}

/* Four-state presentation sequencer on the D_8009B210 mode byte: mode 0
 * starts the first screen effect and arms the 0x14-frame counter; mode 1
 * copies the selected card's position into a type-8 effect object, updates
 * the card record and plays the SE when that counter expires; mode 2 starts
 * the second screen effect; mode 3 waits once more, advances the opposing
 * side's state byte at +6 and completes. Returns 1 while busy. */
s32 Duel_UpdateTrapPresentation(void) {
    DuelEffectObject *e;
    DuelCardReplayRecordBlock *g;
    DisplayObject *p;
    DuelSideState *q;
    u8 *r;
    s32 one;
    s32 v;
    u16 t;
    u16 *q34;
    u16 *d;

    if (D_8009B162 != 0) {
        return 1;
    }

    one = 1;
    v = D_8009B210 & 0xF;

    if (v == one) {
        goto m1;
    }
    if (v < 2) {
        if (v == 0) {
            goto m0;
        }
        return 1;
    }
    if (v == 2) {
        goto m2;
    }
    if (v == 3) {
        goto m3;
    }

    return 1;

m0:
    func_80022D94(0x10, 0x208, 0x200, D_800F2848.angle,
                  0xB2 - D_8009B1D5 * 0x164);
    D_8009B162 = 0x10;
    D_8009B210 = one;
    D_8009B1D0 = 0x14;
    do {
    return 1;

m1:
    t = D_8009B1D0 - 1;
    D_8009B1D0 = t;
    if ((s16)t <= 0) {
    r = D_8015C424;
    g = (DuelCardReplayRecordBlock *)(
        (u8 *)&((DuelCardRecord *)r)[D_8009B1B8] +
        DUEL_CARD_STAGING_REPLAY_BASE_OFFSET);
    p = (DisplayObject *)g->record.object;
    e = (DuelEffectObject *)DuelEffect_CreateRequest(8);
    e->x = p->field_30.h.field_30;
    e->y = p->field_30.h.field_32;
    q34 = (u16 *)&p->field_34.h.field_34;
    *(d = &e->field_04) = *q34;
    DuelCard_RemoveFromField(&D_801A7AD8[p->field_6A]);
    SD_SEPlayFull(0x17);
    D_8009B210 = 2;
    }
    return 1;

m2:
    func_80022D94(0x10, 0x258, 0x100, D_800F2848.angle, 0);
    D_8009B162 = 0x10;
    D_8009B210 = 3;
    D_8009B1D0 = 0x14;
    } while (0);
    return 1;

m3:
    t = D_8009B1D0 - 1;
    D_8009B1D0 = t;
    if ((s16)t > 0) {
        return 1;
    }
    q = &D_800E9FF0[D_8009B1D5 ^ 1];
#ifdef MEMORIES_PC
    /* The selected field record is the actual trap, while D_8009B22A is
     * the retail behavior it borrowed.  Queue the former's data-defined
     * actions once its normal trap presentation has completed. */
    MonsterEffects_TrapPresented(D_801A7AD8[D_8009B1B8].card_id, D_8009B1D5 ^ 1);
#endif
    q->rank.traps_triggered = q->rank.traps_triggered + 1;
    return 0;
}
