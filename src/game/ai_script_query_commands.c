#include "../types.h"
#include "duel_get_base_card_stat.h"
#include "ai.h"
#include "card_constants.h"
#include "ai_script_read_byte.h"
#include "ai_script_commands.h"
#include "duel_card.h"
#include "duel_card_layout.h"
#include "duel_side_state.h"
#ifdef MEMORIES_PC
#include "pc/cards/cards.h"
#endif

void AiScript_TestHighStat(void)
{
    register s32 *values = gAiScript_aMemory;
    s32 value = values[AiScript_ReadByte()];
    s32 dest = AiScript_ReadByte();
    s32 result;

    if (((gDuel_adwCardStats[value - 1] >> CARD_STAT_TYPE_SHIFT) &
         CARD_STAT_TYPE_MASK) < CARD_TYPE_MAGIC) {
        s32 attack = Duel_GetBaseCardStat(value, 0);
        s32 defense = Duel_GetBaseCardStat(value, 1);
        result = !(defense < attack);
    } else {
        result = 0;
    }
    gAiScript_aMemory[dest] = result;
}

void AiScript_LoadCardType(void)
{
    s32 *memory = gAiScript_aMemory;
    s32 index = memory[AiScript_ReadByte()] - 1;

    memory[AiScript_ReadByte()] =
        (gDuel_adwCardStats[index] >> CARD_STAT_TYPE_SHIFT) &
        CARD_STAT_TYPE_MASK;
}

void AiScript_LoadCardID(void)
{
    s32 *memory = gAiScript_aMemory;
    s32 index = memory[AiScript_ReadByte()];

#ifdef MEMORIES_PC
    /* The field script finds a magic or trap card by the disc card it plays
       as (ai_script_find_card.c), then reloads its number to choose what to
       do with it: a mod's Umi or Stain Storm was taken for Forest or Dragon
       Capture Jar. A magic or trap card reads as the disc card whose effect
       it has. Equips, rituals and monsters stay themselves: their number
       goes on to their own equip rules, recipes and stats. */
    {
        s32 id = gDuel_aActiveCards[index].card_id;
        s32 type = id ? Cards_Type(id) : 0;
        /* One with no retail analogue (Cards_AiId -1: a card_effects
           replacement without "ai_effect") keeps its own number: a script
           may go on to AiScript_LoadCardType, which must not see 0, and
           the lookups that value or find a card by number already go
           through Cards_AiId. */
        if ((type == CARD_TYPE_MAGIC || type == CARD_TYPE_TRAP) && Cards_AiId(id) > 0) id = Cards_AiId(id);
        memory[AiScript_ReadByte()] = id;
        return;
    }
#endif
    memory[AiScript_ReadByte()] = gDuel_aActiveCards[index].card_id;
}

/* Looks up gDuel_aActiveCards[gAiScript_aMemory[idx1]] and classifies it: 0 if
   field0 is zero, 2 if the card is face-down, else 1. Stores the result at
   gAiScript_aMemory[idx2]. */
void AiScript_SetFaceDown(void) {
    s32 *table = gAiScript_aMemory;
    s32 idx1 = AiScript_ReadByte();
    s32 val1 = table[idx1];
    s32 idx2 = AiScript_ReadByte();
    s32 flagval;

    if (gDuel_aActiveCards[val1].card_id == 0) {
        flagval = 0;
    } else if (gDuel_aActiveCards[val1].flags & DUEL_CARD_FLAG_FACE_DOWN) {
        flagval = 2;
    } else {
        flagval = 1;
    }

    gAiScript_aMemory[idx2] = flagval;
}

void AiScript_LoadLifePoint(void) {
    s32 *p = gAiScript_aMemory;
    s32 i = p[AiScript_ReadByte()];
    p[AiScript_ReadByte()] = D_800E9FF0[1 - i].life_points.signed_value;
}
