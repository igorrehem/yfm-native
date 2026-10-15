#ifndef MEMORIES_PC_PACK_SHOP_H
#define MEMORIES_PC_PACK_SHOP_H
/* The card packs on the Password screen (notes/card-packs.md).
 *
 * The screen is the game's own, made to sell packs by states of its own
 * machine past the five the game has (Password_UpdateShopScreen, shop.c):
 * the digits' panel becomes the pack's name between the digit cursor's
 * arrows, the big card shows the pack and turns each card of it over, and
 * the message box says the rest, all in the game's letters, boxes, icons and
 * sounds. The game's code asks this module at a handful of places
 * (MEMORIES_PC), and each answers "not mine" at once when no mod declares a
 * pack, so the screen is then the console's.
 *
 * What the screen shows lives here, beside the game, and a save state keeps
 * it in a chunk of its own ("pack-shop"), with the text the game's text boxes
 * point into, whose address the state remaps. */

/* Whether the Password screen sells packs this run. */
int PackShop_Available(void);

/* main_run_password_menu.c, once Password_InitShopScreen has run: the
 * screen's song, and with "packs_only" the list straight away. */
void PackShop_Enter(void);

/* shop.c, state 0, before its own buttons: △ opens the list. 1 when taken. */
int PackShop_Triangle(void);
/* shop.c, state 0: ✕ matched no card; a pack's password? 1 when taken. */
int PackShop_Password(void);
/* shop.c: a state past the game's own five. */
void PackShop_Update(int state);
/* shop.c, Password_UpdateDigitCursorDecoration: while the list shows, the
 * cursor's four arrows are the list's (◄ ► around the name, ▲ ▼ with more
 * than one shop). 1 when this placed `object`. */
int PackShop_Decoration(unsigned char *object);

/* Text_Resolve: the screen's own text by id, and string 226 with △PACKS.
 * NULL for any other. */
const unsigned char *PackShop_Text(int id);
/* Text_Retarget: a jump from the screen's own text (its menu's answer)
 * ends it; NULL for a stream that is not this module's. */
unsigned char *PackShop_Retarget(const unsigned char *cursor);

/* "image_style": "full" (notes/card-packs.md). func_80028B08, which draws the
 * card view's art and plates: while the big card shows such a pack, 1 and
 * its picture, drawn at (x, y) of the card's frame, width x height texels
 * from (u, v) of 8-bit page `tpage` through the palette at VRAM (clut_x,
 * clut_y), in the place of the art, the plates and the icons; 0 for any
 * other card view (`art` is the view's art object). */
typedef struct {
    int x, y, width, height, u, v, tpage, clut_x, clut_y;
} PackShopPicture;
int PackShop_Picture(const void *art, PackShopPicture *picture);
/* DisplayObject_RenderSpriteSheet: 1 when `frame` is that card's frame
 * showing its front, which the picture stands in for (its back is drawn). */
int PackShop_HidesFrame(const void *frame);

/* The running save was loaded (SaveCards_Applied) or written
 * (SaveCards_Saved): what it holds of the packs, beside it. */
void PackShop_SaveLoaded(const void *state);
void PackShop_SaveWritten(const void *state);

/* The chunk of a save state. */
struct MemoriesState;
void PackShop_State(struct MemoriesState *state);

#endif
