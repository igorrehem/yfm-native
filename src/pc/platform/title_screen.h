#ifndef MEMORIES_PC_PLATFORM_TITLE_SCREEN_H
#define MEMORIES_PC_PLATFORM_TITLE_SCREEN_H
/* The mods' "title" and "menu" keys: what the title screen plays, shows and offers
 * (notes/modding.md, "The title screen"). Every applied mod's "title" is read
 * again each time the title opens, in load order, a later mod's value winning
 * field by field, so applying or removing a mod shows the next time the
 * title opens, with no restart. Without one the title is the retail one. */
#include <stdint.h>

struct MenuCanvas;

/* The song MainMenu_InitFrontendMenu starts (retail 0x000), after reading
 * the mods' "title" again; then TitleScreen_Opened sets the objects up and
 * puts the mods' pictures in VRAM. */
int TitleScreen_Song(void);
void TitleScreen_Opened(void);
/* MainMenu_DestroyFrontendMenu: the title is gone. */
void TitleScreen_Closed(void);
/* Main_RunFrontendLoop and Main_RunMenu call this for
 * MainMenu_UpdateFrontendMenu, which it calls. */
int TitleScreen_Update(void);
/* Main_RunFrontendLoop: 1 to go past the intro movie to the title. */
int TitleScreen_SkipMovie(void);

/* MainMenu_DrawFrontendBackground's colors: the picture's tint (128 each
 * unchanged, as the game's 128), whether the picture and the dark-to-light
 * shade over it are drawn, the solid color drawn under them (0xRRGGBB, or
 * -1 for none), and the menu's dimming level for the game's `level`. */
void TitleScreen_BackgroundTint(unsigned char *r, unsigned char *g, unsigned char *b);
int TitleScreen_ShowPicture(void);
/* The mods' pictures (title_images.h) into the background's ordering table. */
void TitleScreen_DrawImages(void *ot);
int TitleScreen_ShowShade(void);
/* Widescreen with a background that fills it: how far past the game's 320
 * the background goes on either side (TITLE_WIDE_MARGIN), else 0. */
int TitleScreen_BackgroundMargin(void);
/* The menus' items the port draws (title_menu.h), into the entries'
 * ordering table. */
void TitleScreen_DrawMenu(void);
long TitleScreen_BackgroundColour(void);
int TitleScreen_Dim(int level);

/* Save states: whether the title is up, and its idle count and pulse, which
 * live here and not in the game; a state loaded on the title puts the mods'
 * pictures back in VRAM. */
struct MemoriesState;
void TitleScreen_State(struct MemoriesState *state);

/* The "text" lines over the picture (hud.c). */
void TitleScreen_Draw(struct MenuCanvas *canvas, int *x, int *y, int *w, int *h);
unsigned TitleScreen_Signature(void);

#endif
