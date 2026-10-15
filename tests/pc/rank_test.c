/* View > Duel rank's sum (src/pc/cards/rank.c) against the game's own
 * Duel_CalcRankScore (src/game/duel_result_runtime.c, linked unchanged):
 * the same score for both sides over random records and tables, with the
 * record and the result display left as they were. The rest of the game
 * unit's references are rank_test_stubs.c. */
#include "pc/cards/rank.h"
#include "game/duel_rank.h"
#include "game/duel_result_display.h"
#include "game/duel_rewards.h"
#include "game/text_staging.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

DuelSideState D_800E9FF0[DUEL_SIDE_COUNT];
DuelRankScoreChangeEntry gDuel_awRankScoreChange[10][DUEL_RANK_SCORE_THRESHOLD_COUNT];
DuelResultDisplayState *D_8009B1E8;
TextStagingValues D_801D5608[1];
u8 gDuel_bWinnerSide;
static DuelResultDisplayState display;

/* The retail rows (notes/research/the-game.md §6.1); the last threshold of
 * each row stands for "and above". */
static const DuelRankScoreChangeEntry retail[10][DUEL_RANK_SCORE_THRESHOLD_COUNT] = {
    {{5, 12}, {9, 8}, {29, 0}, {33, -8}, {0x7FFF, -12}},
    {{2, 4}, {4, 2}, {10, 0}, {20, -2}, {0x7FFF, -4}},
    {{2, 0}, {6, -10}, {10, -20}, {15, -30}, {0x7FFF, -40}},
    {{1, 0}, {11, -2}, {21, -4}, {31, -6}, {0x7FFF, -8}},
    {{1, 2}, {4, -4}, {7, -8}, {10, -12}, {0x7FFF, -16}},
    {{1, 2}, {3, -8}, {5, -16}, {7, -24}, {0x7FFF, -32}},
    {{9, 15}, {13, 12}, {33, 0}, {37, -5}, {0x7FFF, -7}},
    {{100, -7}, {1000, -5}, {7000, 0}, {8000, 4}, {0x7FFF, 6}},
    {{1, 4}, {5, 0}, {10, -4}, {15, -8}, {0x7FFF, -12}},
    {{1, 4}, {5, 0}, {10, -4}, {15, -8}, {0x7FFF, -12}},
};

static unsigned seed = 12345;
static int next(int n) { seed = seed * 1103515245u + 12345u; return (int)((seed >> 8) % (unsigned)n); }

static void random_table(void)
{
    int row, i, threshold;
    for (row = 0; row < 10; row++) {
        threshold = -300 + next(200);
        for (i = 0; i < DUEL_RANK_SCORE_THRESHOLD_COUNT; i++) {
            threshold += 1 + next(i == 0 ? 50 : 3000);
            gDuel_awRankScoreChange[row][i].threshold = (s16)(threshold > 0x7FFF ? 0x7FFF : threshold);
            gDuel_awRankScoreChange[row][i].score_change = (s16)(next(81) - 40);
        }
        /* Mostly an "and above" end like retail's; sometimes the walk has
         * to carry on into the next row, which the game's lookup also does. */
        if (next(4)) gDuel_awRankScoreChange[row][4].threshold = 0x7FFF;
    }
    gDuel_awRankScoreChange[9][4].threshold = 0x7FFF;
}

static void random_side(DuelSideState *side)
{
    static const int adjustments[] = {0, 2, -40, 40, 0};
    unsigned char *bytes = (unsigned char *)side;
    size_t i;
    for (i = 0; i < sizeof(*side); i++) bytes[i] = (unsigned char)next(256);
    side->rank.result_adjustment = (s8)(next(6) == 5 ? next(256) - 128 : adjustments[next(5)]);
    switch (next(4)) {
    case 0: side->life_points.signed_value = (s16)(next(3) ? 8000 : next(2) ? 0 : 99); break;
    case 1: side->life_points.signed_value = (s16)(next(20000) - 10000); break;
    default: side->life_points.signed_value = (s16)next(9000); break;
    }
    if (next(2)) side->deck_draw_cursor = (s8)next(41);
}

/* The game's sum for both sides against ours, and ours writes nothing. */
static void compare(void)
{
    DuelSideState before[DUEL_SIDE_COUNT];
    DuelResultDisplayState display_before;
    int i, ours;
    gDuel_bWinnerSide = (u8)next(2);
    D_8009B1E8 = &display;
    memcpy(before, D_800E9FF0, sizeof(before));
    Duel_CalcRankScore();
    assert(!memcmp(before, D_800E9FF0, sizeof(before)));
    memcpy(&display_before, &display, sizeof(display));
    for (i = 0; i < DUEL_SIDE_COUNT; i++) {
        ours = Rank_Score(&D_800E9FF0[i], D_800E9FF0[i].rank.result_adjustment);
        if (ours != display.side_scores[i]) {
            fprintf(stderr, "side %d: ours %d, the game's %d\n", i, ours, (int)display.side_scores[i]);
            assert(0);
        }
    }
    assert(!memcmp(before, D_800E9FF0, sizeof(before)));
    assert(!memcmp(&display_before, &display, sizeof(display)));
}

static void grade(int score, const char *expected)
{
    static const char letters[] = "DCBAS";
    char got[8];
    int tec, tier;
    Rank_Grade(score, &tec, &tier);
    assert(tier >= 0 && tier <= 4);
    snprintf(got, sizeof(got), "%c-%s", letters[tier], tec ? "TEC" : "POW");
    if (strcmp(got, expected)) {
        fprintf(stderr, "score %d: %s, expected %s\n", score, got, expected);
        assert(0);
    }
}

int main(void)
{
    int round;
    /* A duel's first turn: no turns, full LP, five cards drawn, and the
     * +2 of an LP win: 101, S-POW (what the meter shows in game). */
    memcpy(gDuel_awRankScoreChange, retail, sizeof(retail));
    memset(D_800E9FF0, 0, sizeof(D_800E9FF0));
    D_800E9FF0[0].life_points.signed_value = 8000;
    D_800E9FF0[0].deck_draw_cursor = 5;
    assert(Rank_Score(&D_800E9FF0[0], 2) == 101);
    /* A deck-out win with everything else neutral. */
    D_800E9FF0[0].rank.turns_taken = 20;
    D_800E9FF0[0].rank.effective_attacks = 5;
    D_800E9FF0[0].rank.face_down_plays = 10;
    D_800E9FF0[0].rank.pure_magic_used = 5;
    D_800E9FF0[0].rank.traps_triggered = 2;
    D_800E9FF0[0].rank.fusions_initiated = 3;
    D_800E9FF0[0].rank.equips_used = 3;
    D_800E9FF0[0].deck_draw_cursor = 40;
    D_800E9FF0[0].life_points.signed_value = 3000;
    D_800E9FF0[0].rank.result_adjustment = -40;
    compare();
    assert(Rank_Score(&D_800E9FF0[0], -40) == 50 - 40 + 0 + 0 - 2 - 8 - 8 - 7 + 0 + 0 + 0);
    for (round = 0; round < 20000; round++) {
        if (round % 50 == 0) {
            if (round % 100) random_table();
            else memcpy(gDuel_awRankScoreChange, retail, sizeof(retail));
        }
        random_side(&D_800E9FF0[0]);
        random_side(&D_800E9FF0[1]);
        compare();
    }
    /* No threshold above the value anywhere up to the table's end: the
     * game's lookup would walk past it, ours stops. */
    memset(gDuel_awRankScoreChange, 0, sizeof(gDuel_awRankScoreChange));
    assert(Rank_Score(&D_800E9FF0[0], 0) == RANK_SCORE_UNKNOWN);

    /* DuelScene_UpdateResultRewards's ten ranks. */
    grade(-140, "S-TEC"); grade(0, "S-TEC"); grade(9, "S-TEC"); grade(10, "A-TEC"); grade(19, "A-TEC");
    grade(20, "B-TEC"); grade(29, "B-TEC"); grade(30, "C-TEC"); grade(39, "C-TEC"); grade(40, "D-TEC");
    grade(49, "D-TEC"); grade(50, "D-POW"); grade(59, "D-POW"); grade(60, "C-POW"); grade(69, "C-POW");
    grade(70, "B-POW"); grade(79, "B-POW"); grade(80, "A-POW"); grade(89, "A-POW"); grade(90, "S-POW");
    grade(99, "S-POW"); grade(101, "S-POW"); grade(139, "S-POW");
    puts("rank: ok");
    return 0;
}
