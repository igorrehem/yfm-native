/* View > Duel rank's numbers (rank.h): Duel_CalcRankScore's sum, read-only. */
#include "rank.h"
#include "game/duel_rank.h"
#include "tables.h"

#define RANK_RULE_COUNT 10

/* Duel_CalcRankScoreChange walks from its row's first pair until a
 * threshold is above the value, into the next rows if it must. Only let it
 * run when that happens inside the ten rows. */
static int change(int rule, int value, int *known)
{
    const DuelRankScoreChangeEntry *entry = &gDuel_awRankScoreChange[rule][0];
    const DuelRankScoreChangeEntry *end = &gDuel_awRankScoreChange[RANK_RULE_COUNT - 1][DUEL_RANK_SCORE_THRESHOLD_COUNT];
    for (; entry < end; entry++)
        if (value < entry->threshold) return Duel_CalcRankScoreChange(rule, value);
    *known = 0;
    return 0;
}

int Rank_Score(const DuelSideState *side, int adjustment)
{
    /* The start and the end's points as Duel_CalcRankScore takes them,
     * a mod's "rank_score" included (tables.h). */
    int known = 1,
        score = (int)Tables_Value(TABLES_VALUE_RANK_START, DUEL_RANK_SCORE_INITIAL) + Tables_RankAdjustment(adjustment);
    score += change(DUEL_RANK_RULE_CARDS_USED, side->deck_draw_cursor, &known);
    score += change(DUEL_RANK_RULE_REMAINING_LP, side->life_points.signed_value, &known);
    score += change(DUEL_RANK_RULE_EFFECTIVE_ATTACKS, side->rank.effective_attacks, &known);
    score += change(DUEL_RANK_RULE_DEFENSIVE_WINS, side->rank.defensive_wins, &known);
    score += change(DUEL_RANK_RULE_FACE_DOWN_PLAYS, side->rank.face_down_plays, &known);
    score += change(DUEL_RANK_RULE_INITIATE_FUSION, side->rank.fusions_initiated, &known);
    score += change(DUEL_RANK_RULE_EQUIP_MAGIC, side->rank.equips_used, &known);
    score += change(DUEL_RANK_RULE_PURE_MAGIC, side->rank.pure_magic_used, &known);
    score += change(DUEL_RANK_RULE_TRAPS_TRIGGERED, side->rank.traps_triggered, &known);
    score += change(DUEL_RANK_RULE_TURNS, side->rank.turns_taken, &known);
    return known ? score : RANK_SCORE_UNKNOWN;
}

void Rank_Grade(int score, int *tec, int *tier)
{
    *tec = 0;
    if (score < 50) {
        *tec = 1;
        if (score < 0) score = 0;
        score = 99 - score;
    }
    if (score >= 100) score = 99;
    *tier = (score - 50) / 10;
}
