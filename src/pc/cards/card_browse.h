#ifndef MEMORIES_PC_CARD_BROWSE_H
#define MEMORIES_PC_CARD_BROWSE_H
/* Game > Browse cards with Up/Down: in the card viewer triangle opens
 * (DuelEffect_UpdateCardViewerState, src/game/func_800283F4.c), Up and Down
 * show the previous and next card of the list it was opened from, in place,
 * without closing it; the list's cursor follows, and at either end the game's
 * "cannot" sounds. Build Deck's two lists. Off by default, as the retail
 * game has it; the retail viewer reads neither button, so turning it on
 * takes nothing away. */

/* Called by the viewer while it shows a card; nonzero when it has shown
 * another, so the viewer does nothing more this frame. */
int CardBrowse_Poll(void);

#endif
