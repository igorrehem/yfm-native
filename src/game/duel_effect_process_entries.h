#ifndef MEMORIES_DECOMP_DUEL_EFFECT_PROCESS_ENTRIES_H
#define MEMORIES_DECOMP_DUEL_EFFECT_PROCESS_ENTRIES_H

#include "duel_effect.h"

extern void (*G32 D_80090F58[])(DuelEffectEntry *, DuelEffectChannel *);

void DuelEffect_ProcessEntries(DuelEffectChannel *);

#endif
