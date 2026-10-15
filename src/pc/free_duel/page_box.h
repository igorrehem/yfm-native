#ifndef MEMORIES_PC_FREE_DUEL_PAGE_BOX_H
#define MEMORIES_PC_FREE_DUEL_PAGE_BOX_H
/* The Free Duel grid's page indicator (notes/more-duelists.md).
 *
 * The grid shows forty duelists at a time and L1 and R1 turn the page, which
 * wants saying on the screen. It is said in the game's own letters, through
 * the game's own text box, so it reads as part of the screen and scales with
 * the picture -- the way the results screen's added pages do (cards/drops.h),
 * and not as something drawn over the top.
 *
 * The string is composed here and answered for one reserved id, which
 * Text_Resolve asks about. The words in the middle are the port's own string
 * TEXT_OWN_FREE_DUEL_PAGE (text.h), so a translation writes them as it writes
 * the rest; "L1" and "R1" are the buttons' own names and stay as they are.
 */
#include "types.h"

/* The composed string ids are handed out from the top down, one per screen
 * that makes a line of its own: 0xFFFF the results screen's added pages
 * (cards/drops.h), 0xFFFE the Password screen's label (cards/passwords.h),
 * and this. */
#define FREE_DUEL_PAGE_TEXT_ID 0xFFFD
#define FREE_DUEL_PAGE_TEXT_SIZE 96

/* The box spans the picture, 4 in from each edge, so that the page can be
 * centred on the picture from the box's own left edge. A glyph steps the box
 * eight along, which the size command in the string settles, and the centring
 * measures the string with the same eight. */
#define FREE_DUEL_PAGE_BOX_X 0x04
#define FREE_DUEL_PAGE_BOX_WIDTH 0x138
#define FREE_DUEL_PAGE_ADVANCE 8

/* Compose the line: the L1 hint, "PAGE n/m" centred, the R1 hint. Nothing is
 * shown for a single page. */
void FreeDuelPage_Compose(int page, int pages);
/* Forget it: the screen has gone. */
void FreeDuelPage_Clear(void);
/* Text_Resolve's question: the composed line for FREE_DUEL_PAGE_TEXT_ID. */
const unsigned char *FreeDuelPage_Text(int id);

#endif
