/* The Free Duel screen's state for duelists past the disc's
 * (src/pc/free_duel/duelists.h).
 *
 * A game unit, like card_storage.c and drops.c, so these are in the game's
 * data: at fixed addresses, and inside every save state. Game units link in
 * name order; this one sorts after both of those, so no existing variable
 * moves, which would keep states from earlier builds from loading.
 *
 * Nothing the disc laid out moves: gFreeDuel_abGridAvailable stays in the
 * overlay's module_state.c at its forty entries and the records stay at 0x51C
 * in the save block. What an added duelist needs sits beside them, which is
 * what is here.
 */
#include "types.h"
#include "game/card_constants.h"

/* What the running save holds of the duelists past the grid's forty: their
 * win and loss counts, as SaveDataDuelistRecord holds the first forty in the
 * save block itself. */
u16 gFreeDuel_aExtraRecords[DUELIST_TABLE_COUNT][2] = {{0}};
/* Whether the grid shows an added duelist, as gFreeDuel_abGridAvailable says
 * for the first forty. */
u8 gFreeDuel_abExtraAvailable[DUELIST_TABLE_COUNT] = {0};
/* Whose the records are: the duelist code of the save they belong to. */
int gFreeDuel_nExtraOwner = 0;
/* Which page of forty the Free Duel grid is showing: 0 is the disc's own. */
int gFreeDuel_nPage = 0;
/* The grid's forty cell sprites, so a page can be turned without building
 * them again -- a cell's texture slot and palette are fixed by the cell, so
 * only the texels in them change. DisplayObject *, held as void * because
 * this unit has no business with the type. */
void *gFreeDuel_apCells[FREE_DUEL_GRID_ENTRY_COUNT] = {0};
/* The forty portrait records the screen was opened with, to take a page's
 * portraits from. */
void *gFreeDuel_pPortraits = 0;
/* The text box saying which page the grid shows, remade as it turns, and the
 * red arrow beside each of its two buttons. */
void *gFreeDuel_pPageBox = 0;
void *gFreeDuel_apPageArrows[2] = {0};
