/* Guardian Stars in the duel (stars.h): which star a monster summoned now
 * takes, read off the duel's card records. Kept out of stars.c, which the
 * tests build without the game. */
#include "stars.h"
#include "game/card_constants.h"
#include "game/duel_card.h"
#include "game/duel_card_layout.h"
#include "game/duel_grid.h"

extern unsigned char D_8009B1D5;   /* the side whose turn it is */

static void stars_of(int card_id, int *first, int *second)
{
    unsigned stats = card_id >= 1 ? (unsigned)gDuel_adwCardStats[card_id - 1] : 0;
    *first = (int)((stats >> CARD_STAT_GUARDIAN_STAR_1_SHIFT) & CARD_STAT_GUARDIAN_STAR_MASK);
    *second = (int)((stats >> CARD_STAT_GUARDIAN_STAR_2_SHIFT) & CARD_STAT_GUARDIAN_STAR_MASK);
}

int Stars_PickForCard(int card_id)
{
    int enemy[DUEL_FIELD_ROW_SIZE], count = 0, slot, first, second;
    int side = (D_8009B1D5 & 1) ^ 1;
    stars_of(card_id, &first, &second);
    if (Stars_Single(first, second)) return 0;
    if (Stars_ChoiceMode() == STARS_CHOICE_ASK) return -1;
    /* What the player can see: the opponent's face-up monsters, each with
     * the star it chose. */
    for (slot = 0; slot < DUEL_FIELD_ROW_SIZE; slot++) {
        const DuelCardRecord *record = &D_801A7AD8[side * DUEL_CARD_SIDE_RECORD_COUNT + slot];
        int a, b;
        if (!(record->flags & DUEL_CARD_FLAG_OCCUPIED) || (record->flags & DUEL_CARD_FLAG_FACE_DOWN)) continue;
        stars_of(record->card_id, &a, &b);
        enemy[count++] = (record->flags & DUEL_CARD_FLAG_USE_GUARDIAN_STAR_2) ? b : a;
    }
    return Stars_SummonChoice(first, second, enemy, count);
}

int Stars_CardSingle(int card_id)
{
    int first, second;
    stars_of(card_id, &first, &second);
    return Stars_Single(first, second);
}

int Stars_NoStarCard(int card_id)
{
    unsigned stats;
    if (!Stars_NoStarUsed() || card_id < 1) return 0;
    stats = (unsigned)gDuel_adwCardStats[card_id - 1];
    return (int)((stats >> CARD_STAT_TYPE_SHIFT) & CARD_STAT_TYPE_MASK) < CARD_TYPE_MAGIC &&
           !((stats >> CARD_STAT_GUARDIAN_STAR_1_SHIFT) & CARD_STAT_GUARDIAN_STAR_MASK);
}
