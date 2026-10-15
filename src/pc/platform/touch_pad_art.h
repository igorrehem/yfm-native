#ifndef MEMORIES_PC_TOUCH_PAD_ART_H
#define MEMORIES_PC_TOUCH_PAD_ART_H
/* The on-screen controller's pictures (touch_pad.h): the game's own button
 * sprites, cut off the disc (disc_art.h) from the boot package the game
 * keeps in VRAM, where its screens take their round Cross, Circle, Triangle
 * and Square, START, the L1/L2/R1/R2 tabs and the boxed arrows; SELECT is
 * set in the game's text font. Nothing of the game is kept in the
 * repository. Main thread only. */
#include "menu.h"

/* Draws the pad where touch_pad.c has laid it out (nothing while hidden),
 * and gives the bounds it covered (all 0 when nothing). */
void TouchPadArt_Draw(MenuCanvas *canvas, int *x, int *y, int *w, int *h);
/* Drops the pictures (a disc swap reloads them). */
void TouchPadArt_Reset(void);

#endif
