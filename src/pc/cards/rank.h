#ifndef MEMORIES_PC_RANK_H
#define MEMORIES_PC_RANK_H
#include "game/duel_side_state.h"

/* The duel rank the game gives at the end (Duel_CalcRankScore and
 * DuelScene_UpdateResultRewards), worked out from one side record at any
 * moment without writing anything. Duel_CalcRankScore itself stays as it
 * is: it also fills the result display and the statistics pages. */

/* RANK_SCORE_UNKNOWN when a row of gDuel_awRankScoreChange has no threshold
 * above the counter anywhere up to the table's end (no duel table loaded):
 * the game's own lookup would walk on past it. */
#define RANK_SCORE_UNKNOWN (-0x7FFF)

/* 50 + adjustment + Duel_CalcRankScoreChange of each counter, in the order
 * and with the reads Duel_CalcRankScore uses. The record's own
 * rank.result_adjustment is not added; the caller passes the one it wants. */
int Rank_Score(const DuelSideState *side, int adjustment);

/* The letter the result screen shows for a score: below 50 is TEC (tec = 1)
 * and mirrored as 99 - score (from 0), 100 and up count as 99, and
 * (score - 50) / 10 is the tier, 0 D to 4 S. */
void Rank_Grade(int score, int *tec, int *tier);

#endif
