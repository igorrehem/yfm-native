#ifndef MEMORIES_PC_RANK_METER_H
#define MEMORIES_PC_RANK_METER_H
#include "pc/platform/menu.h"
/* View > Duel rank (SET_RANK_METER): the rank the duel would end with, by
 * the FIELD box, while a duel against the computer is played. 0 draws
 * nothing, 1 the rank (S-POW ... S-TEC), 2 the rank and the score. */
unsigned RankMeter_Signature(void);
void RankMeter_Draw(MenuCanvas *, int *x, int *y, int *w, int *h);
#endif
