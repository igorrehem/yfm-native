#include "types.h"
#include "game/duel_card.h"
#include "game/duel_check_ritual.h"
#include "pc/cards/tables.h"
#include "pc/guest/translated_runtime.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int Cards_EffectId(int id) { return id; }
int Cards_BaseId(int id) { return id; }
int Cards_TrapId(int id) { return id >= 681 && id <= 686 ? id : 0; }
int Cards_TrapThreshold(int id, int fallback) { (void)id; return fallback; }
int Cards_CardEffectsReplace(int id) { (void)id; return 0; }
void MonsterEffects_AttackTrapPlayed(int card, int side) { (void)card; (void)side; }
void DuelCard_RemoveFromField(DuelCardRecord *card) { (void)card; abort(); }
int Cards_Type(int id) { (void)id; abort(); }
/* The translated ritual fixture does not load the card-type registry. Its
 * selected retail-rule paths only need the framework's monster predicate. */
int Cards_IsMonsterType(int type) { return type >= 0 && (type < CARD_TYPE_MAGIC || type > CARD_TYPE_EQUIP); }
int Cards_Level(int id) { (void)id; abort(); }
int Cards_InFusionGroup(int id, int group) { (void)id; (void)group; abort(); }
int Tables_HasRitual(int id) { (void)id; return 0; }
int Tables_RitualRequirements(int id, TablesRitualRequirement *req, unsigned short *out) {
    (void)id; (void)req; (void)out; return 0;
}
int Tables_Ritual(int id, unsigned short *out) { (void)id; (void)out; return -1; }
int Tables_RitualRule(int id, TablesRitualRule *rule) { (void)id; (void)rule; return 0; }
int Tables_TrapThreshold(int id, int retail) { (void)id; return retail; }
int Tables_StatCap(int defense) { (void)defense; return 9999; }
extern s32 Duel_SelectAttackTrap(u8 *);
static void *at(u32 addr, size_t size) {
    void *p = Memories_Resolve(GuestRuntime_Memory(), addr, size, 1); assert(p); return p;
}
int main(void) {
    MemoriesMemory *m = calloc(1, sizeof(*m)); assert(m && !GuestRuntime_Bind(m));
    DuelCardRecord *cards = at(0x801a7ad8, 30*sizeof(*cards));
    u16 *recipe = at(0x801799d8, 12);
    u16 values[] = {670,27,38,58,364,0}; memcpy(recipe, values, sizeof(values));
    u8 *side = at(0x8009b1d5, 4);
    u32 *out = at(0x801b0000, 20);
    for (int d = 0; d < 2; d++) {
        *side = d;
        for (int i = 0; i < 3; i++) {
            DuelCardRecord *c = &cards[5+15*d+i];
            c->card_id = values[1+i]; c->flags = 0x8000;
            c->object = (void *)(uintptr_t)(0x801b1000+0x80*i);
        }
        out[4] = 0xfeedcafe;
        assert(Duel_CheckRitual((DuelRitualResult *)(uintptr_t)0x801b0000, 670) == 364);
        assert(out[0] == 0x801b1000 && out[1] == 0x801b1080 && out[2] == 0x801b1100);
        assert(out[3] == 0 && out[4] == 0xfeedcafe);
        cards[7+15*d].flags = 0;
        assert(!Duel_CheckRitual(NULL, 670));
        cards[7+15*d].flags = 0x8000; cards[7+15*d].card_id = 27;
        assert(!Duel_CheckRitual(NULL, 670));
    }
    memset(cards, 0, 30*sizeof(*cards)); *side = 0;
    u8 *grid = at(0x800907d8, 40); for (int i = 0; i < 40; i++) grid[i] = i%30;
    u8 *trap = at(0x801b2000, 0x80), *attacker = at(0x801b2100, 0x80);
    trap[0x6a] = 0; attacker[0x6a] = 20;
    cards[0].flags = 0x8000; cards[0].card_id = 681;
    cards[0].object = (void *)(uintptr_t)0x801b2000;
    u8 thresholds[] = {5,10,15,20,30,255}; memcpy(at(0x8009af24, 8), thresholds, 6);
    cards[20].attack = 500;
    assert(Duel_SelectAttackTrap((u8 *)(uintptr_t)0x801b2100));
    assert(*(s16 *)at(0x8009b22a, 4) == 681);
    cards[20].attack = 501;
    assert(!Duel_SelectAttackTrap((u8 *)(uintptr_t)0x801b2100));
    cards[0].card_id = 686; cards[20].attack = 9999;
    assert(Duel_SelectAttackTrap((u8 *)(uintptr_t)0x801b2100));
    assert(*(s16 *)at(0x8009b22a, 4) == 686);
    GuestRuntime_Reset(); free(m);
    puts("Translated ritual tributes on both sides and attack-trap thresholds passed");
}

/* This isolated rule fixture has no enabled custom monster effects. */
void MonsterEffects_Stats(const void *record, int *attack, int *defense)
{
    (void)record; (void)attack; (void)defense;
}
