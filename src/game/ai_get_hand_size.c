#include "../types.h"
#include "ai.h"
#include "ai_opponent_data.h"
#ifdef MEMORIES_PC
#include "pc/free_duel/duelists.h"
#endif

s8 Ai_GetHandSize(void)
{
#ifdef MEMORIES_PC
    /* The duelist's own row when a mod gave it one ("search"), its base's
       otherwise (duelists.h). The disc's table has a row per duelist it
       has, and an added duelist is past the end of it. */
    return Duelists_AiRow(gDuel_bOpponentID)[0];
#else
    return gDuel_aOpponentData[gDuel_bOpponentID].values[0];
#endif
}
