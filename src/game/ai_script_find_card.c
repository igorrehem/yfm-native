#include "../types.h"
#include "duel_card_layout.h"
#include "duel_grid.h"
#include "ai_script_read_byte.h"
#include "ai.h"
#include "ai_script_commands.h"
#ifdef MEMORIES_PC
#include "ai_opponent_data.h"   /* gDuel_bOpponentID */
#include "pc/free_duel/duelists.h"
#include "pc/cards/cards.h"
#endif

/* AI script opcode taking two operand bytes: a register that when non-zero
 * makes a face-down opponent card invisible to the scan, and the register to
 * write. It pairs the two fields off strongest against strongest - each round
 * takes the strongest card not yet taken from slots 1..5 and the strongest not
 * yet taken from slots 56..60, marks both taken, and stops as soon as the
 * opponent's pick is not beaten. It answers 1 only if at least one round ran
 * and every round was won, so a losing or empty field answers 0. Slot 0 of
 * gDuel_aActiveCards is the zero entry both searches start from, which is what
 * makes index 0 mean "nothing found" while still comparing cleanly. */
void AiScript_FindDefenseStopper(void)
{
    s32 hide_face_down;
    s32 result;
    s32 answer;
    s32 taken[DUEL_SIDE_COUNT][DUEL_FIELD_ROW_SIZE];
    s32 best;
    s32 other;
    s32 i;
    s32 j;
    AiActiveCard *cards;
    AiActiveCard *others;

    hide_face_down = gAiScript_aMemory[AiScript_ReadByte()];
#ifdef MEMORIES_PC
    /* "sight" in the duelist's "ai" over what the script asked for
       (pc/free_duel/duelists.h); its own answer when it says nothing. */
    hide_face_down = Duelists_HidesFaceDown(gDuel_bOpponentID, hide_face_down);
#endif
    result = AiScript_ReadByte();
    answer = 1;

    for (i = 0; i < DUEL_SIDE_COUNT; i++) {
        for (j = 0; j < DUEL_FIELD_ROW_SIZE; j++) {
            taken[i][j] = 0;
        }
    }

    i = 0;
    do {
        best = AI_SLOT_NONE;
        cards = &gDuel_aActiveCards[AI_SLOT_OWN_MONSTER_FIRST];
        for (j = 0; j < DUEL_FIELD_ROW_SIZE; j++) {
            if (taken[0][j] == 0) {
                if (cards[j].attack > gDuel_aActiveCards[best].attack) {
                    best = j + AI_SLOT_OWN_MONSTER_FIRST;
                }
            }
        }
        if (best != AI_SLOT_NONE) {
            taken[0][best - AI_SLOT_OWN_MONSTER_FIRST] = 1;
        }

        other = AI_SLOT_NONE;
        others = &gDuel_aActiveCards[AI_SLOT_OPPONENT_MONSTER_FIRST];
        for (j = 0; j < DUEL_FIELD_ROW_SIZE; j++) {
            if (taken[1][j] == 0) {
                if (hide_face_down == 0 ||
                    !(others[j].flags & DUEL_CARD_FLAG_FACE_DOWN)) {
                    if (others[j].attack > gDuel_aActiveCards[other].attack) {
                        other = j + AI_SLOT_OPPONENT_MONSTER_FIRST;
                    }
                }
            }
        }
        if (other == AI_SLOT_NONE) {
            break;
        }
        taken[1][other - AI_SLOT_OPPONENT_MONSTER_FIRST] = 1;
        if (gDuel_aActiveCards[best].attack <= gDuel_aActiveCards[other].attack) {
            answer = 0;
            break;
        }
        i++;
    } while (i < DUEL_FIELD_ROW_SIZE);

    if (i == 0) {
        answer = 0;
    }
    gAiScript_aMemory[result] = answer;
}

void AiScript_CountCards(void)
{
    s32 count;
    s32 *table = gAiScript_aMemory;
    s32 type;
    s32 output;
    s32 start;
    s32 end;
    s32 i;

    type = AiScript_ReadByte();
    type = table[type];
    output = AiScript_ReadByte();
    count = 0;

    Ai_GetCardRange(type, &start, &end);

    for (i = start; i <= end; i++) {
        AiActiveCard *entry = &gDuel_aActiveCards[i];
        if (entry->card_id != 0) {
            if (type == 1 || type == 3 || type == 6 || type == 8) {
                if (!(entry->flags & DUEL_CARD_FLAG_USED_THIS_TURN)) {
                    count++;
                }
            } else {
                count++;
            }
        }
    }

    gAiScript_aMemory[output] = count;
}

/* AI script opcode taking three operand bytes: a register holding the wanted
 * slot state, a register holding the zone type, and the register to write.
 * It walks the zone's slot range in order and stops at the first slot whose
 * state matches - 0 for an empty slot, 1 for a face-up card, 2 for a face-down
 * card - writing that slot index, or 0 when the range runs out. In the four
 * zone types that can act, a card already used this turn is passed over.
 * Slot 0 doubles as the not-found answer, which is why the caller's range
 * never starts there. */
void AiScript_FindFirstCard(void)
{
    s32 wanted;
    s32 type;
    s32 result;
    s32 *table = gAiScript_aMemory;
    s32 wanted_idx;
    s32 type_idx;
    s32 start;
    s32 end;
    s32 i;

    wanted_idx = AiScript_ReadByte();
    wanted = table[wanted_idx];
    type_idx = AiScript_ReadByte();
    type = table[type_idx];
    result = AiScript_ReadByte();

    Ai_GetCardRange(type, &start, &end);

    for (i = start; i <= end; i++) {
        if (type == 1 || type == 3 || type == 6 || type == 8) {
            if (gDuel_aActiveCards[i].flags & DUEL_CARD_FLAG_USED_THIS_TURN) {
                continue;
            }
        }
        if (gDuel_aActiveCards[i].card_id != 0) {
            if (gDuel_aActiveCards[i].flags & DUEL_CARD_FLAG_FACE_DOWN) {
                if (wanted == 2) {
                    break;
                }
            } else {
                if (wanted == 1) {
                    break;
                }
            }
        } else {
            if (wanted == 0) {
                break;
            }
        }
    }

    if (end < i) {
        gAiScript_aMemory[result] = 0;
    } else {
        gAiScript_aMemory[result] = i;
    }
}

/* AI script opcode taking four operand bytes: a register holding the card id
 * to look for, a register holding the zone type, a register that when 1 makes
 * a face-down card in a hidden zone (type 5 and up) not count, and the
 * register to write. It walks the zone's slot range in order and stops at the
 * first slot holding that card id, writing the slot index, or 0 when the range
 * runs out. In the four zone types that can act, a card already used this turn
 * is passed over. */
void AiScript_FindCard(void)
{
    s32 wanted;
    s32 type;
    s32 visible_only;
    s32 result;
    s32 *table = gAiScript_aMemory;
    s32 wanted_idx;
    s32 type_idx;
    s32 visible_idx;
    s32 start;
    s32 end;
    s32 i;

    wanted_idx = AiScript_ReadByte();
    wanted = table[wanted_idx];
    type_idx = AiScript_ReadByte();
    type = table[type_idx];
    visible_idx = AiScript_ReadByte();
    visible_only = table[visible_idx];
    result = AiScript_ReadByte();

    Ai_GetCardRange(type, &start, &end);

    for (i = start; i <= end; i++) {
#ifdef MEMORIES_PC
        /* The scripts ask for disc cards by number, and play a found magic
           card straight from the hand with no zone to go to. A card a mod
           replaced with another kind would be played as that card instead,
           and a monster or equip with no zone left the hand cursor waiting
           for a column that does not exist: the turn never ended. */
        if ((gDuel_aActiveCards[i].card_id ? Cards_AiId(gDuel_aActiveCards[i].card_id) : 0) != wanted) {
            continue;
        }
#else
        if (gDuel_aActiveCards[i].card_id != wanted) {
            continue;
        }
#endif
        if (type == 1 || type == 3 || type == 6 || type == 8) {
            if (gDuel_aActiveCards[i].flags & DUEL_CARD_FLAG_USED_THIS_TURN) {
                continue;
            }
        }
        if (visible_only != 1) {
            break;
        }
        if (type < 5) {
            break;
        }
        if (!(gDuel_aActiveCards[i].flags & DUEL_CARD_FLAG_FACE_DOWN)) {
            break;
        }
    }

    if (end < i) {
        gAiScript_aMemory[result] = 0;
    } else {
        gAiScript_aMemory[result] = i;
    }
}
