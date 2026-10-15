#ifdef MEMORIES_PC
#include "pc/mods/mods.h"
#endif
#include "../types.h"
#include "card_constants.h"
#include "duel_card_checks.h"
#ifdef MEMORIES_PC
#include "pc/cards/cards.h"
#include "pc/cards/tables.h"
#include "pc/cards/rules.h"
#include "pc/tower/tower.h"
#endif

#define FUSION_TABLE_BYTES(table) ((u8 *)(table))
#define FUSION_TABLE_OFFSETS(table) ((u16 *)(table))

#ifdef MEMORIES_PC
/* The equip and fusion tables are the disc's, of retail cards: a card past
   the disc's is looked up as its base (cards.h). Duel_CheckEquip follows. */
static s32 Duel_CheckEquipRetail(s32 arg0, s32 arg1)
#else
s32 Duel_CheckEquip(s32 arg0, s32 arg1)
#endif
{
    u16 *p = gDuel_awEquipTable;

    while (1) {
        s32 key = p[0];
        s32 n;

        if (key == 0) {
            return 0;
        }
        n = p[1];
        p += 2;
        if (key == arg0) {
            do {
                if (arg1 == *p) {
                    return arg1;
                }
                n--;
                p++;
            } while (n != 0);
            return 0;
        }
        p += n;
    }
}

#ifdef MEMORIES_PC
/* An equip answers with the monster it was asked about, so a copy stays
   itself. The mods' rules come before the disc's table (tables.h). The
   disc's is of the cards as they were: a replaced card made another kind
   (cards.h) is out of it, or an equip card made a monster would still
   equip, taking a monster off the field for the one it is played on. An
   equip card whose "effect" is a disc equip fits what that one fits, though
   it was a monster on the disc. */
int CardRules_Equip(int a, int b)
{
    int ruled, as;
    if (!Cards_Valid(a) || !Cards_Valid(b)) return 0;
    ruled = Tables_Equip(a, b);
    as = Cards_Type(a) == CARD_TYPE_EQUIP && Cards_RetailType(Cards_EffectId(a)) == CARD_TYPE_EQUIP
             ? Cards_EffectId(a) : 0;
    if (ruled < 0)
        ruled = (as || !Cards_KindChanged(a)) && !Cards_KindChanged(b) &&
                Duel_CheckEquipRetail(as ? as : Cards_BaseId(a), Cards_BaseId(b)) != 0;
    /* A tower floor with "no_equips" (tower.h): nothing equips, for the
       player, the CPU and the fusion helper alike. */
    if (ruled && Tower_Refuses(TOWER_RULE_NO_EQUIPS, a, b, b)) return 0;
    return ruled ? b : 0;
}

s32 Duel_CheckEquip(s32 arg0, s32 arg1)
{
    MemoriesModEvent event = {MEMORIES_EVENT_EQUIP, MEMORIES_BEFORE, arg0, arg1, 0, 0, 0};
    Mods_Dispatch(&event);
    if (!event.handled) event.result = CardRules_Equip(event.a, event.b) != 0;
    /* The floor's rule stands over a code mod's answer too. */
    if (event.result && Tower_Refuses(TOWER_RULE_NO_EQUIPS, event.a, event.b, event.b)) event.result = 0;
    event.phase = MEMORIES_AFTER; Mods_Dispatch(&event);
    return event.result ? arg1 : 0;
}
#endif

#ifdef MEMORIES_PC
static s32 Duel_CheckFusionRetail(s32 arg0, s32 arg1)
#else
s32 Duel_CheckFusion(s32 arg0, s32 arg1)
#endif
{
    u8 *base = FUSION_TABLE_BYTES(gDuel_aFusionTable);
    u8 *p;
    s32 off;
    s32 n;
    s32 b;

#ifdef MEMORIES_PC
    arg0 = Cards_BaseId(arg0);
    arg1 = Cards_BaseId(arg1);
#endif
    if (arg1 < arg0) {
        s32 t = arg1;
        arg1 = arg0;
        arg0 = t;
    }
    off = FUSION_TABLE_OFFSETS(base)[arg0];
    if (off == 0) {
        return 0;
    }
    p = base + off;
    n = p[0];
    if (n == 0) {
        n = FUSION_TABLE_EXTENDED_COUNT_BASE - p[1];
        p++;
    }
    p++;
    do {
        b = p[0];
        if ((((b << FUSION_TABLE_FIRST_PARTNER_SHIFT) &
              FUSION_TABLE_CARD_ID_HIGH_MASK) | p[1]) == arg1) {
            return ((b << FUSION_TABLE_FIRST_RESULT_SHIFT) &
                    FUSION_TABLE_CARD_ID_HIGH_MASK) | p[2];
        }
        if ((((b << FUSION_TABLE_SECOND_PARTNER_SHIFT) &
              FUSION_TABLE_CARD_ID_HIGH_MASK) | p[3]) == arg1) {
            return ((b << FUSION_TABLE_SECOND_RESULT_SHIFT) &
                    FUSION_TABLE_CARD_ID_HIGH_MASK) | p[4];
        }
        p += FUSION_TABLE_ENTRY_SIZE;
        n -= FUSION_TABLE_PAIRS_PER_ENTRY;
    } while (n > 0);
    return 0;
}

#ifdef MEMORIES_PC
/* The disc's table is of the cards as they were, so a replaced card made
   another kind (cards.h) neither fuses by it nor comes out of it: the CPU
   would fuse a monster with what is now a magic card, which the game plays
   as a magic card, and lose it. The mods' rules still name any card. */
int CardRules_Fusion(int a, int b)
{
    int result = 0;
    if (!Tables_Fusion(a, b, &result) && !Cards_Fusion(a, b, &result)) {
        if (Cards_Valid(a) && Cards_Valid(b) && !Cards_KindChanged(a) && !Cards_KindChanged(b))
            result = Tables_FilterFusion(Duel_CheckFusionRetail(a, b));
        if (result && Cards_KindChanged(result)) result = 0;
    }
    /* A tower floor with "no_fusions" (tower.h): nothing fuses, for the
       player, the CPU and the fusion helper alike. */
    if (Cards_Valid(result) && Tower_Refuses(TOWER_RULE_NO_FUSIONS, a, b, result)) return 0;
    return Cards_Valid(result) ? result : 0;
}

s32 Duel_CheckFusion(s32 a, s32 b)
{
    MemoriesModEvent event = {MEMORIES_EVENT_FUSION, MEMORIES_BEFORE, a, b, 0, 0, 0};
    Mods_Dispatch(&event);
    if (!event.handled) event.result = CardRules_Fusion(event.a, event.b);
    if (event.result && !Cards_Valid(event.result)) event.result = 0;
    /* The floor's rule stands over a code mod's answer too. */
    if (event.result && Tower_Refuses(TOWER_RULE_NO_FUSIONS, event.a, event.b, event.result)) event.result = 0;
    event.phase = MEMORIES_AFTER; Mods_Dispatch(&event);
    return event.result;
}
#endif
