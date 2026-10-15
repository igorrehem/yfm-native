/* The real retail and per-card trap selectors, including their field-slot
 * outputs. Compile as 32-bit for the game's display-object layout. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <stdio.h>
#include <stddef.h>
#include <string.h>
#include "../../src/game/duel_trap_resolution.c"

u8 D_8009B1D5, D_8009B1B8, D_800907D8[40], D_8015C424[0x20000];
s16 D_8009B22A;
/* PE retains references from the unused presentation function. These must
 * never run: the disc-backed runtime test covers presentation separately. */
u16 D_8009B162, D_8009B1D0, D_8009B210;
DuelSideState D_800E9FF0[2];
ViewState D_800F2848;
void func_80022D94(s32 frames, s32 x, s32 z, s32 y, s32 value)
{ (void)frames; (void)x; (void)z; (void)y; (void)value; assert(0); }
DuelEffectRequest *DuelEffect_CreateRequest(s32 id) { (void)id; assert(0); return NULL; }
void DuelCard_RemoveFromField(DuelCardRecord *card) { card->flags = 0; card->object = NULL; }
void SD_SEPlayFull(u32 sound) { (void)sound; assert(0); }
DuelCardRecord D_801A7AD8[30];
static DisplayObject objects[30];
static int effects[1024], thresholds[1024], attack, replace_id, played_card, played_side;
int Cards_TrapId(int id) { return effects[id]; }
int Cards_TrapThreshold(int id, int fallback) { return thresholds[id] >= 0 ? thresholds[id] : fallback; }
int Cards_CardEffectsReplace(int id) { return id == replace_id; }
void MonsterEffects_CardPlayed(int card, int side) { (void)card; (void)side; }
void MonsterEffects_TrapPlayed(int card, int side) { (void)card; (void)side; }
void MonsterEffects_TrapPresented(int card, int side) { (void)card; (void)side; }
void MonsterEffects_AttackTrapPlayed(int card, int side) { played_card = card; played_side = side; }
void MonsterEffects_TrackBattleParticipants(int attacker, int defender) { (void)attacker; (void)defender; }
/* gMonsterEffects is in every save state (src/pc/game/trigger_state.c): the
 * fields earlier builds had keep their offsets, new ones go at the end. */
_Static_assert(sizeof(MonsterTrigger) == 4, "a queued trigger's save-state size");
_Static_assert(offsetof(MonsterEffectsState, count) == 8, "save-state layout");
_Static_assert(offsetof(MonsterEffectsState, trap_pending) == 9, "the old pad byte");
_Static_assert(offsetof(MonsterEffectsState, queue) == 272, "save-state layout");
_Static_assert(offsetof(MonsterEffectsState, battle_life) == 486, "save-state layout");
_Static_assert(offsetof(MonsterEffectsState, battle_abort) == 494, "appended after the old layout");
_Static_assert(offsetof(MonsterEffectsState, trap_battle_record) == 496, "appended after the old layout");
int Tables_TrapThreshold(int index, int retail) { (void)index; return retail; }
s32 Duel_CalcCardStats(DuelCardRecord *card) { (void)card; return attack; }

static void reset(void)
{
    int i;
    memset(D_801A7AD8, 0, sizeof(D_801A7AD8));
    memset(D_800E9FF0, 0, sizeof(D_800E9FF0));
    memset(effects, 0, sizeof(effects));
    for (i = 0; i < 1024; i++) thresholds[i] = -1;
    for (i = 0; i < 30; i++) objects[i].field_6A = i;
    for (i = 0; i < 5; i++) D_800907D8[i] = i;
    replace_id = played_card = played_side = 0;
    D_8009B1D5 = 0;
}
static void put(int slot, int id, int effect, int threshold)
{
    D_801A7AD8[slot].flags = DUEL_CARD_FLAG_OCCUPIED;
    D_801A7AD8[slot].card_id = id;
    D_801A7AD8[slot].object = &objects[slot];
    effects[id] = effect;
    thresholds[id] = threshold;
}
static int select_trap(void)
{
    D_8009B22A = 0;
    D_8009B1B8 = 255;
    return Duel_SelectAttackTrap((u8 *)&objects[29]);
}
int main(void)
{
    static const int attacks[] = {0, 499, 500, 501, 999, 1000, 1001, 1499, 1500, 1501,
                                 1999, 2000, 2001, 2999, 3000, 3001, 25499, 25500, 25501, 65535};
    int omitted, mask, a, slot, e, result, effect, selected;
    /* Every subset of five of the six retail effects at all boundaries.
     * Adding an override equal to retail must not change selection. */
    for (omitted = 0; omitted < 6; omitted++) for (mask = 1; mask < 32; mask++) {
        for (a = 0; a < (int)(sizeof(attacks) / sizeof(attacks[0])); a++) {
            reset();
            for (slot = e = 0; e < 6; e++) {
                if (e == omitted) continue;
                if (mask & (1 << slot)) put(slot, 681 + e, 681 + e, -1);
                slot++;
            }
            attack = attacks[a];
            result = select_trap(); effect = D_8009B22A; selected = D_8009B1B8;
            for (slot = 0; slot < 5; slot++) {
                int id = D_801A7AD8[slot].card_id;
                if (!id) continue;
                thresholds[id] = gDuel_abTrapAttackThresholds[id - 681] * 100;
                assert(select_trap() == result && D_8009B22A == effect && D_8009B1B8 == selected);
                thresholds[id] = -1;
            }
        }
    }
    reset();
    put(0, 1, 681, 1500); put(1, 723, 681, 1000);
    attack = 1500;
    assert(select_trap() && D_8009B1B8 == 0); /* later ineligible copy cannot hide this one */
    attack = 1000;
    assert(select_trap() && D_8009B1B8 == 1); /* retail's last-slot tie */
    attack = 1501;
    assert(!select_trap());
    put(2, 2, 682, 2000);
    assert(select_trap() && D_8009B22A == 682 && D_8009B1B8 == 2);
    put(3, 3, 690, -1); attack = 2001;
    assert(select_trap() && D_8009B22A == 690 && D_8009B1B8 == 3);
    effects[3] = 0; /* a former trap converted to a monster never springs */
    assert(!select_trap());
    thresholds[1] = 0; attack = 0;
    assert(select_trap() && D_8009B22A == 681);
    thresholds[1] = 65535; attack = 65535;
    assert(select_trap() && D_8009B1B8 == 0);
    /* A per-card replacement springs under its inherited threshold but does
     * not select the retail attack-trap handler. It is consumed and queued
     * for the actual field owner. */
    reset();
    put(0, 900, 681, 1500); attack = 1500; replace_id = 900;
    assert(!select_trap());
    assert(played_card == 900 && played_side == 0);
    assert(!(D_801A7AD8[0].flags & DUEL_CARD_FLAG_OCCUPIED));
    assert(D_800E9FF0[0].rank.traps_triggered == 1);
    puts("trap selection: retail parity, inclusive thresholds, copies and Fake Trap passed");
    return 0;
}
