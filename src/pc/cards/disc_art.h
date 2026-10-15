#ifndef MEMORIES_PC_DISC_ART_H
#define MEMORIES_PC_DISC_ART_H
/* The game's own pictures for the host's overlays (View > Duel rank, View >
 * Free Duel progress), read off the player's disc when first wanted: the
 * packages a screen loads are unpacked into a private VRAM the way the
 * game's loaders place them, and sprites are cut from it with the texture
 * page, position and palette the game draws them with. The console's VRAM
 * is never read, so a sprite is there before the screen that loads it has
 * been shown, and nothing of the game is kept in the repository.
 *
 * The packages are not TIM files: an image phase is raw VRAM words, one
 * 2048-byte sector a 64 x 16 block, placed down a column and on to the next
 * 64 words each 256 rows (File_StepActiveTransfer), and a palette phase is
 * one LoadImage rectangle. Offsets are WA_MRG sectors, as the game's
 * requests give them. */
#include "pc/platform/menu.h"
#include <stdint.h>

#define DISC_ART_WA_PATH "\\DATA\\WA_MRG.MRG;1"

typedef struct {
    int width, height;
    uint32_t *pixels; /* 0xAARRGGBB, alpha 0 (the PS1's 0x0000) or 255 */
} DiscArt;

/* An image phase of `sectors` sectors from WA sector `sector`, placed from
 * VRAM x, y (words) as the loader does. 0 if the disc cannot be read. */
int DiscArt_LoadImage(int sector, int sectors, int x, int y);
/* A w x h rectangle of words (a palette upload) that starts `offset` bytes
 * into WA sector `sector`, loaded at x, y. */
int DiscArt_LoadRect(int sector, int offset, int x, int y, int w, int h);
/* `bytes` bytes (up to a few sectors) from WA sector `sector`, for data the
 * game keeps in RAM (a display resource). */
int DiscArt_Read(int sector, void *out, int bytes);

/* w x h texels at u, v of the texture page at page_x (words), page_y, in
 * 4- or 8-bit color through the palette at clut_x, clut_y. 0 if `depth` is
 * neither or memory runs out. Free with DiscArt_Free. */
int DiscArt_Cut(DiscArt *art, int page_x, int page_y, int depth, int u, int v, int w, int h, int clut_x,
                int clut_y);
void DiscArt_Free(DiscArt *art);
/* The private VRAM's word at x, y (0 before anything is loaded there). */
uint16_t DiscArt_Word(int x, int y);
/* Drops the private VRAM (a disc swap or a mod change reloads). */
void DiscArt_Reset(void);

/* Draws `art` over the window rectangle x, y, w, h: each window pixel takes
 * the texel under it when the art is enlarged (sharp, as the game's own 2D),
 * and the average of the texels it covers when it is shrunk. Transparent
 * texels leave the canvas as it is. */
void DiscArt_Draw(MenuCanvas *canvas, const DiscArt *art, int x, int y, int w, int h);
#endif
