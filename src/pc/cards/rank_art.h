#ifndef MEMORIES_PC_RANK_ART_H
#define MEMORIES_PC_RANK_ART_H
/* View > Duel rank's pictures, the game's own off the disc (disc_art.h):
 * the result screen's POW/TEC badge, stone plate and rank letter, and the
 * cards' ATK/DEF digits for the score. */
#include "disc_art.h"

/* Where the game picture is in the window, and the width its 2D is laid
 * out in (320, or 426 in widescreen, where it stays centred). */
typedef struct { int x, y, w, h, width_2d; } RankArtView;

/* Reads the pictures the first time (a failure is kept, and logged once).
 * 1 when they are there. */
int RankArt_Ready(void);
/* The pieces as the result screen has them: the badge (tec 0 POW, 1 TEC),
 * the plate behind the letter, the letter (tier 0 D ... 4 S) and a digit;
 * NULL until RankArt_Ready. */
const DiscArt *RankArt_Badge(int tec);
const DiscArt *RankArt_Plate(void);
const DiscArt *RankArt_Letter(int tier);
const DiscArt *RankArt_Digit(int digit);
/* The rank drawn right of the FIELD box, whose top right corner is at
 * right, top of the game picture: the plate as tall as the box, the letter
 * on it, the badge behind the letter's top left, and the score (0-99; -1
 * for none) in card digits after the plate. The bounds covered come back
 * in x, y, w, h (all 0 when nothing was drawn). */
void RankArt_Draw(MenuCanvas *canvas, const RankArtView *view, int right, int top, int tec, int tier, int score,
                  int *x, int *y, int *w, int *h);
void RankArt_Reset(void);
#endif
