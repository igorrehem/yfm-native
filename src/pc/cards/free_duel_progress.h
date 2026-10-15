#ifndef MEMORIES_PC_FREE_DUEL_PROGRESS_H
#define MEMORIES_PC_FREE_DUEL_PROGRESS_H
#include "pc/platform/menu.h"
/* View > Free Duel progress (SET_FREE_DUEL_PROGRESS): on the Free Duel grid,
 * "owned/obtainable" for the opponent under the cursor, right of the FREE
 * DUEL title (notes/pc-build.md).
 *
 * Obtainable is every card with a weight in any of the opponent's three drop
 * pools (S/A-POW, B/C/D, S/A-TEC) as the mods have them (Tables_PoolFor),
 * so a mod that edits drops counts. Owned is how many of those the deck and
 * the trunk hold now: the game keeps no record of who gave a card. */

/* The count for opponent `duelist` (1-39): 1 with both numbers, 0 when the
 * disc's drop tables cannot be read. */
int FreeDuelProgress_Count(int duelist, int *owned, int *obtainable);
/* Forget the tables read and the pools worked out (the tests). */
void FreeDuelProgress_Reset(void);

/* The overlay, drawn by the host as the fusion helper is. */
unsigned FreeDuelProgress_Signature(void);
void FreeDuelProgress_Draw(MenuCanvas *, int *x, int *y, int *w, int *h);
#endif
