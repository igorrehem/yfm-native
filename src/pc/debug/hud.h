#ifndef MEMORIES_PC_DEBUG_HUD_H
#define MEMORIES_PC_DEBUG_HUD_H
#include "pc/platform/menu.h"

/* The statistics and, when it is open, the save slot menu (pc/saves). */
void Hud_Draw(MenuCanvas *canvas);
/* The mods' overlays (MemoriesMod.overlay) on their own, for a window that
 * draws something of its own over them (the touch pad): the next Hud_Draw,
 * which must follow in the same composition, leaves them out, and its
 * bounds still cover them. */
void Hud_DrawMods(MenuCanvas *canvas);
void Hud_Bounds(int *x, int *y, int *w, int *h);
/* Changes whenever what the HUD would draw changes; the full statistics
 * level changes every frame. */
unsigned Hud_Signature(void);

#endif
