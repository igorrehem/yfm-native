/* A Magic card's "card_effects" through the real DuelEffect_StartCardEffect
 * (src/game/duel_magic_effect_dispatch.c): "add" starts its retail (or
 * aliased) effect and queues the list once, on the first of the effect's
 * two handlers; "replace" queues the list and starts no retail effect; a
 * monster's "magic" effect (DuelEffect_StartRetailCardEffect) never queues
 * the card's list. Compile as 32-bit for the game's layouts. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <string.h>
/* Its psyq/stdio.h declares printf and puts. */
#include "../../src/game/duel_magic_effect_dispatch.c"

u8 D_8009B1D5, D_800907D8[40];
u16 gDuel_wCardEffectFlags;
s16 gDuel_sCardEffectIndex, gDuel_wEffectCardID;
DuelCardRecord D_801A7AD8[30];
DuelFieldPosition D_80090800[DUEL_SIDE_COUNT][DUEL_FIELD_SIDE_GRID_SLOT_COUNT];
char D_8009AF40[1];
u8 gDuelEffect_abGroupByEffectId[DUEL_EFFECT_ID_COUNT];
DuelEffectHandler gDuelEffect_apfnGroupHandler[DUEL_EFFECT_GROUP_COUNT * DUEL_CARD_EFFECT_HANDLERS_PER_GROUP];

static int effect_of[1024], card_effect_count[1024], replaces[1024];
static int played_card, played_side, played_count, rituals;
static const MonsterEffect one_effect[1];

int Cards_EffectId(int id) { return effect_of[id] ? effect_of[id] : id; }
int Cards_CardEffects(int id, const MonsterEffect **effects)
{
    *effects = card_effect_count[id] ? one_effect : NULL;
    return card_effect_count[id];
}
int Cards_CardEffectsReplace(int id) { return replaces[id]; }
void MonsterEffects_CardPlayed(int card, int side) { played_card = card; played_side = side; played_count++; }
void MonsterEffects_EffectStarted(int ritual) { rituals += ritual; }
void Mods_Dispatch(MemoriesModEvent *event) { (void)event; }
int DuelEffect_MarkInitialized(void) { assert(0); return 0; }
DuelEffectRequest *DuelEffect_CreateRequest(s32 id) { (void)id; assert(0); return NULL; }
void DuelCard_RemoveFromField(DuelCardRecord *card) { (void)card; assert(0); }

static void reset(void)
{
    memset(effect_of, 0, sizeof(effect_of));
    memset(card_effect_count, 0, sizeof(card_effect_count));
    memset(replaces, 0, sizeof(replaces));
    played_card = played_side = played_count = rituals = 0;
    gDuel_wCardEffectFlags = gDuel_wEffectCardID = 0;
    gDuel_sCardEffectIndex = 0;
    D_8009B1D5 = 1;
}

int main(void)
{
    /* Retail: no list, the card's own effect starts. */
    reset();
    DuelEffect_StartCardEffect(343, 0);
    assert(gDuel_wCardEffectFlags == DUEL_CARD_EFFECT_FLAG_ACTIVE && gDuel_wEffectCardID == 343);
    assert(!played_count);

    /* "add": an aliased retail effect starts, and the card's own list is
     * queued for its player once, not again for the second handler. */
    reset();
    effect_of[900] = 337; card_effect_count[900] = 1;
    DuelEffect_StartCardEffect(900, 0);
    assert(gDuel_wCardEffectFlags == DUEL_CARD_EFFECT_FLAG_ACTIVE && gDuel_wEffectCardID == 337);
    assert(played_count == 1 && played_card == 900 && played_side == 1);
    DuelEffect_StartCardEffect(900, 1);
    assert(gDuel_wCardEffectFlags == (DUEL_CARD_EFFECT_FLAG_ACTIVE | DUEL_CARD_EFFECT_FLAG_SECOND_HANDLER));
    assert(played_count == 1);

    /* "replace": the list is queued, and neither handler starts the retail
     * effect it would otherwise borrow. */
    reset();
    effect_of[901] = 337; card_effect_count[901] = 1; replaces[901] = 1;
    DuelEffect_StartCardEffect(901, 0);
    assert(!gDuel_wCardEffectFlags && played_count == 1 && played_card == 901);
    DuelEffect_StartCardEffect(901, 1);
    assert(!gDuel_wCardEffectFlags && played_count == 1);

    /* A monster's "magic" effect names the retail card whose behavior it
     * wants: that card's own list or replacement does not apply. */
    reset();
    card_effect_count[337] = 1; replaces[337] = 1;
    DuelEffect_StartRetailCardEffect(337, 0);
    assert(gDuel_wCardEffectFlags == DUEL_CARD_EFFECT_FLAG_ACTIVE && gDuel_wEffectCardID == 337);
    assert(!played_count);
    puts("card effects start: add, replace and retail passed");
    return 0;
}
