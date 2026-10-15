/* View > Free Duel progress: "owned/obtainable" right of the FREE DUEL title
 * for the opponent under the grid cursor, drawn by the host over the picture
 * as the fusion helper is, in the game's own font (font_art.c). The numbers
 * come from free_duel_progress.c. */
#include "free_duel_progress.h"
#include "pc/free_duel/duelists.h"
#include "fusion_helper.h"
#include "pc/platform/settings.h"
#include "pc/platform/platform.h"
#include "font_art.h"
#include "game/card_constants.h"
#include "game/main_modes.h"
#include "game/fade.h"
#include "game/file_transfer.h"
#include "overlays/free_duel/free_duel.h"
#include "overlays/free_duel/module_state.h"
#include <stdio.h>

extern unsigned char D_8009B26C; /* main_mode_state.h: the running mode */

/* Main_RunFreeDuelMenu sets 0x40 once it has opened the screen. The screen's
 * own flags: 0x20 while a text box is up (SELECT OPPONENT!, the deck
 * refusal), 0x40 once it is leaving. */
enum { MODE_MASK = 0x1F, MODE_ENTERED = 0x40, SCREEN_DIALOG = 0x20, SCREEN_LEAVING = 0x40 };

static struct { int visible, duelist, owned, obtainable, x, y, w, h; } view;

static void update(void)
{
    int column, row, cell, duelist;
    view.visible = 0;
    if (!Settings_Get(SET_FREE_DUEL_PROGRESS)) return;
    if ((D_8009B26C & MODE_MASK) != MAIN_MODE_FREE_DUEL || !(D_8009B26C & MODE_ENTERED)) return;
    /* Main_InitFreeDuelMenu waits for the module to load before FreeDuel_Init
     * builds the grid, and frames are shown meanwhile: until then the
     * module's state is the last screen's. Then the fade in. */
    if ((D_8009B0F4 & FILE_TRANSFER_REQUEST_BLOCKED_MASK) | D_8009B134) return;
    if (gFade_State.flags & FADE_FLAG_ACTIVE) return;
    if (gFreeDuel_bScreenFlags & (SCREEN_DIALOG | SCREEN_LEAVING)) return;
    /* The pending cell the pad moves at once; the cursor glides after it. The
     * cell is not the duelist: the grid shows a page of forty, so the duelist
     * it stands for is the page's (Duelists_AtCell, free_duel/duelists.h), and
     * on a page past the first even cell 0 is somebody to duel. */
    column = gFreeDuel_bTargetColumn;
    row = gFreeDuel_bTargetRow;
    if (column < 0 || column >= FREE_DUEL_GRID_COLUMN_COUNT || row < 0 || row >= FREE_DUEL_GRID_ROW_COUNT) return;
    cell = row * FREE_DUEL_GRID_COLUMN_COUNT + column;
    duelist = Duelists_AtCell(cell);
    if (duelist < FREE_DUEL_STORY_OPPONENT_FIRST_INDEX || !Duelists_Available(duelist)) return;
    if (!FreeDuelProgress_Count(duelist, &view.owned, &view.obtainable)) return;
    view.duelist = duelist;
    view.visible = 1;
}

unsigned FreeDuelProgress_Signature(void)
{
    int x, y, w, h;
    update();
    if (!view.visible) return 0;
    FusionHelper_GetViewport(&x, &y, &w, &h);
    return ((((unsigned)view.duelist * 1031u + (unsigned)view.owned) * 1031u + (unsigned)view.obtainable) * 331u +
            (unsigned)x * 17u + (unsigned)y) * 31u + (unsigned)w * 7u + (unsigned)h + 1u;
}

/* The title banner's middle row and the right edge of the text, in picture
 * pixels: over the eye right of the banner, clear of the grid's frame. */
enum { TITLE_MIDDLE = 23, TEXT_RIGHT = 304 };

/* "12/157" in the game's own text font and colors (font_art.h), white, or
 * yellow once every card is owned, laid on the picture in its pixels, so it
 * grows with the window and keeps its place in widescreen. */
void FreeDuelProgress_Draw(MenuCanvas *canvas, int *x, int *y, int *w, int *h)
{
    char text[24];
    FontArtView picture;
    *x = *y = *w = *h = 0;
    update();
    FusionHelper_GetViewport(&view.x, &view.y, &view.w, &view.h);
    if (!view.visible || view.w <= 0 || view.h <= 0) return;
    snprintf(text, sizeof(text), "%d/%d", view.owned, view.obtainable);
    picture.x = view.x;
    picture.y = view.y;
    picture.w = view.w;
    picture.h = view.h;
    picture.width_2d = Platform_Widescreen() ? 426 : 320;
    FontArt_Draw(canvas, &picture, TEXT_RIGHT, TITLE_MIDDLE, text,
                 view.obtainable && view.owned == view.obtainable ? FONT_ART_YELLOW : FONT_ART_WHITE, x, y, w, h);
}
