/* Exercise the gameplay and preview entry points on packed retail bytes and
 * mod rules. The event counter proves previews never dispatch game events. */
#include "pc/cards/rules.h"
#include "pc/cards/cards.h"
#include "pc/cards/tables.h"
#include "pc/mods/mod_types.h"
#include "game/duel_card_checks.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

unsigned short gDuel_awEquipTable[0x2100 / 2];
unsigned short gDuel_aFusionTable[0x10000 / 2];
static int event_count, mod_result = -1, equip_rule = -1, removed, changed;
int Cards_Valid(int id) { return id > 0 && id <= 800; }
int Cards_KindChanged(int id) { return id == changed; }
int Cards_BaseId(int id) { return id > 722 ? id - 722 : id; }
/* Card `effect_card` is an equip whose "effect" is `effect_as`. */
static int effect_card, effect_as;
int Cards_EffectId(int id) { return id == effect_card ? effect_as : Cards_BaseId(id); }
int Cards_Type(int id) { return id == effect_card || (Cards_BaseId(id) == 301 && id != changed) ? 23 : 0; }
int Cards_RetailType(int id) { return id == 301 ? 23 : 0; }
int Tables_Fusion(int a, int b, int *result)
{
    if (mod_result < 0 || !((a == 1 && b == 2) || (a == 2 && b == 1))) return 0;
    *result = mod_result; return 1;
}
int Cards_Fusion(int a, int b, int *result)
{
    if (a == 799 || b == 799) { *result = 800; return 1; }
    return 0;
}
int Tables_FilterFusion(int result) { return result == removed ? 0 : result; }
int Tables_Equip(int e, int m) { (void)e; (void)m; return equip_rule; }
/* A code mod that answers the fusion and equip events itself (mod_answers
 * >= 0), and a tower floor's rules (pc/tower/tower.h, TOWER_RULE_*). */
static int mod_answers = -1, tower_rules;
void Mods_Dispatch(MemoriesModEvent *event)
{
    event_count++;
    if (mod_answers >= 0 && event->phase == MEMORIES_BEFORE &&
        (event->type == MEMORIES_EVENT_FUSION || event->type == MEMORIES_EVENT_EQUIP)) {
        event->handled = 1;
        event->result = mod_answers;
    }
}
int Tower_Refuses(int rule, int a, int b, int result)
{
    (void)a; (void)b; (void)result;
    return (tower_rules & rule) != 0;
}

int main(void)
{
    unsigned char *bytes = (unsigned char *)gDuel_aFusionTable;
    int a, b;
    /* Odd count's second half is still examined by retail (glitch fusion). */
    gDuel_aFusionTable[1] = 1500;
    bytes[1500] = 1; bytes[1501] = 0; bytes[1502] = 2; bytes[1503] = 3;
    bytes[1504] = 4; bytes[1505] = 5;
    gDuel_awEquipTable[0] = 301; gDuel_awEquipTable[1] = 1; gDuel_awEquipTable[2] = 1;
    assert(CardRules_Fusion(1, 2) == 3 && CardRules_Fusion(2, 1) == 3);
    assert(CardRules_Fusion(1, 4) == 5);
    assert(CardRules_Fusion(723, 724) == 3);
    assert(CardRules_Equip(301, 723) == 723 && !CardRules_Equip(723, 301));
    assert(!event_count);
    for (a = 1; a <= 800; a++) for (b = a; b <= 800; b++)
        assert(CardRules_Fusion(a, b) == Duel_CheckFusion(a, b));
    event_count = 0;
    mod_result = 750;
    assert(CardRules_Fusion(1, 2) == 750);
    mod_result = 0; assert(!CardRules_Fusion(1, 2));
    mod_result = 900; assert(!CardRules_Fusion(1, 2));
    mod_result = -1; removed = 3; assert(!CardRules_Fusion(1, 2));
    assert(CardRules_Fusion(799, 2) == 800);
    equip_rule = 0; assert(!CardRules_Equip(301, 1));
    equip_rule = 1; assert(CardRules_Equip(301, 724) == 724);
    assert(!CardRules_Equip(301, 0) && !CardRules_Fusion(0, 1));
    /* A card a "replace" made another kind is out of the disc's tables, as
     * material, as result, as equip and as the monster equipped; the mods'
     * own rules still name it. */
    equip_rule = -1; removed = 0;
    changed = 2; assert(!CardRules_Fusion(1, 2) && !CardRules_Fusion(2, 1) && CardRules_Fusion(1, 4) == 5);
    changed = 3; assert(!CardRules_Fusion(1, 2));
    changed = 2; mod_result = 750; assert(CardRules_Fusion(1, 2) == 750); mod_result = -1;
    changed = 301; assert(!CardRules_Equip(301, 1));
    changed = 1; assert(!CardRules_Equip(301, 1));
    equip_rule = 1; assert(CardRules_Equip(301, 1) == 1); equip_rule = -1;
    changed = 0; assert(CardRules_Fusion(1, 2) == 3 && CardRules_Equip(301, 1) == 1);
    /* An equip whose "effect" is a disc equip fits what that one does: a
     * monster the "replace" made one, and a copy of another equip. */
    effect_card = changed = 5; effect_as = 301;
    assert(CardRules_Equip(5, 1) == 1 && !CardRules_Equip(5, 2));
    effect_card = 760; changed = 0; assert(CardRules_Equip(760, 1) == 1);
    effect_as = 2; assert(!CardRules_Equip(760, 1));     /* a monster's effect is no equip's */
    effect_card = 0;
    /* A tower floor's "no_fusions" and "no_equips": nothing fuses, nothing
     * equips -- through CardRules (the fusion helper) and through
     * Duel_CheckFusion / Duel_CheckEquip, which the player's placement and
     * the CPU's planning (ai_fusion.c, ai_turn_action.c) both ask -- even
     * where a code mod answered the event itself. The other kind stays. */
    tower_rules = 1;   /* TOWER_RULE_NO_FUSIONS */
    assert(!CardRules_Fusion(1, 2) && !Duel_CheckFusion(1, 2) && !Duel_CheckFusion(799, 2));
    assert(CardRules_Equip(301, 1) == 1 && Duel_CheckEquip(301, 1) == 1);
    mod_answers = 3;
    assert(!Duel_CheckFusion(1, 2) && Duel_CheckEquip(301, 1) == 1);
    mod_answers = -1;
    tower_rules = 2;   /* TOWER_RULE_NO_EQUIPS */
    assert(CardRules_Fusion(1, 2) == 3 && Duel_CheckFusion(1, 2) == 3);
    assert(!CardRules_Equip(301, 1) && !Duel_CheckEquip(301, 1));
    mod_answers = 1;
    assert(!Duel_CheckEquip(301, 1));
    mod_answers = -1;
    tower_rules = 3;
    for (a = 1; a <= 800; a++) for (b = a; b <= 800; b++)
        assert(!Duel_CheckFusion(a, b) && !CardRules_Fusion(a, b));
    tower_rules = 0;
    assert(CardRules_Fusion(1, 2) == 3 && Duel_CheckEquip(301, 1) == 1);
    event_count = 0;
    assert(!CardRules_Fusion(0, 1) && !event_count);   /* the preview still dispatches nothing */
    assert(!event_count);
    puts("fusion rules: gameplay parity, mod rules and side-effect-free preview passed");
    return 0;
}
