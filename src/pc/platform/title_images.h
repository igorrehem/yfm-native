#ifndef MEMORIES_PC_PLATFORM_TITLE_IMAGES_H
#define MEMORIES_PC_PLATFORM_TITLE_IMAGES_H
/* The title's pictures of a mod's own (title_images.c): the background, the
 * logo, copyright and PUSH START BUTTON, each a PNG drawn instead of the
 * game's; the menus' background; the two backgrounds' widescreen pictures,
 * TITLE_WIDE_WIDTH across; and the menus' items drawn by the port, a
 * mod's PNG or a button of words (menu_label.h), each as it is and with the
 * cursor on it; and the pictures a mod adds ("images"). */
#include "title_config.h"

enum { TITLE_IMAGE_BACKGROUND, TITLE_IMAGE_LOGO, TITLE_IMAGE_COPYRIGHT, TITLE_IMAGE_PROMPT,
       TITLE_IMAGE_MENU_BACKGROUND, TITLE_IMAGE_WIDE_BACKGROUND, TITLE_IMAGE_WIDE_MENU_BACKGROUND, TITLE_IMAGE_ITEMS,
       TITLE_IMAGE_PICTURES = TITLE_IMAGE_ITEMS + 2 * TITLE_ITEMS,
       TITLE_IMAGES = TITLE_IMAGE_PICTURES + TITLE_MAX_PICTURES };
/* Item `i`'s picture, as it is or with the cursor on it. */
#define TITLE_IMAGE_ITEM(i, selected) (TITLE_IMAGE_ITEMS + 2 * (i) + ((selected) ? 1 : 0))
/* The title's added picture `i` ("images"). */
#define TITLE_IMAGE_PICTURE(i) (TITLE_IMAGE_PICTURES + (i))

/* Made from `config` and put in VRAM, once the title's own pictures are
 * there (MainMenu_InitFrontendMenu); one that cannot be read, or finds no
 * room, is noted beside its mod and the game's own picture shows (an item:
 * its words, or its name). */
void TitleImages_Prepare(const TitleConfig *config);
/* One of the backgrounds (4:3 or wide, the title's or the menus'). */
int TitleImages_IsBackground(int which);
/* Whether picture `which` is the mod's this time, and the size it is drawn
 * at in the game's pixels (an item's at its "scale"). */
int TitleImages_Ready(int which, int *width, int *height);
/* Draws it at x, y (its top left, in the game's 320 x 240) in color r, g,
 * b (128 each as it is) into ordering table `ot` at `depth`; `blend` 1
 * adds it to what is under it, as the entries' afterimages are. The
 * backgrounds share their VRAM: the one drawn is put there first. */
void TitleImages_Draw(int which, void *ot, int depth, int x, int y, int r, int g, int b, int blend);
#endif
