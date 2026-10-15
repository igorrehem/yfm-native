#ifndef MEMORIES_PC_STARCHIP_PRIZE_H
#define MEMORIES_PC_STARCHIP_PRIZE_H
/* A won duel's starchips on RESULTS OF DUEL's SPOILS page, past the row's
 * eight (notes/gameplay-tables.md, "Values").
 *
 * The disc draws one starchip picture for each starchip a win gives, from
 * x 160 in steps of 20, and its record has room for eight of them. A mod's
 * "starchip_prize" (tables.h) may give up to 1000: up to eight are drawn as
 * the disc draws them, and past eight the row is a single picture with
 * "xN" beside it, in the game's own letters through the game's own text
 * box -- the way the added card drops pages (drops.h) and the Free Duel
 * page line (free_duel/page_box.h) are written -- so it scales with the
 * picture and HD text sets it like the rest of the page.
 *
 * The string is composed from the results record itself (D_8009B1E8)
 * whenever the box asks for it, so a state saved on the results screen
 * shows the same. */
#include "types.h"

#define STARCHIP_PRIZE_ROW 8            /* the pictures the disc's row draws */
/* The composed string ids are handed out from the top down (page_box.h):
 * 0xFFFF card drops, 0xFFFE card passwords, 0xFFFD the Free Duel page. */
#define STARCHIP_PRIZE_TEXT_ID 0xFFFC
/* The page's own text is channel 0. The duel's messages on 1 are over by
 * the results, and 2 and 3 stay free for the quit prompt and the screens
 * after it. */
#define STARCHIP_PRIZE_CHANNEL 1
/* Just right of the one picture and level with it; "x1000" is five
 * glyphs of eight. */
#define STARCHIP_PRIZE_BOX_X 170
#define STARCHIP_PRIZE_BOX_Y 184
#define STARCHIP_PRIZE_BOX_WIDTH 0x30
#define STARCHIP_PRIZE_BOX_HEIGHT 0x10
#define STARCHIP_PRIZE_TEXT_SIZE 32

/* How many pictures the row draws for `prize`: the prize itself up to
 * eight, else one. */
int StarchipPrize_Pictures(int prize);
/* Whether the row shows "xN" for `prize`: only past eight, so a win the
 * disc's row can draw looks as it does on the disc. */
int StarchipPrize_Counted(int prize);
/* "xN" in the game's text codes, or NULL when `prize` is not counted. */
const unsigned char *StarchipPrize_Compose(int prize);
/* Text_Resolve's question: the count for STARCHIP_PRIZE_TEXT_ID, from the
 * results record. */
const unsigned char *StarchipPrize_Text(int id);
#endif
