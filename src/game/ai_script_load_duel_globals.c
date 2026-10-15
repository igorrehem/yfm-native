#include "../types.h"
#include "ai.h"
#include "ai_script_read_byte.h"
#include "ai_script_commands.h"
#define DUEL_TERRAIN_SCALAR_IN_DATA
#include "duel_terrain_boost.h"
#include "ai_opponent_data.h"
#ifdef MEMORIES_PC
#include "pc/free_duel/duelists.h"
#endif

void AiScript_LoadOpponentID(void)
{
    s32 index;
    volatile s32 *values;
    s32 value;

    index = AiScript_ReadByte();
    values = gAiScript_aMemory;
    value = gDuel_bOpponentID;
#ifdef MEMORIES_PC
    /* The base's id, so a duelist a mod added plays by the script the one it
       copies does. The script tests this against ids it has written into it
       -- 8, 15 and 35 to 38 see face-down cards
       (notes/ai-hard-mode-research.md section 5) -- and an added duelist's own
       id matches none of them, so a copy of Heishin would lose the sight that
       makes Heishin play as he does. A negative id is no opponent at all --
       a two-player duel -- and stays as it is. */
    if (value >= 0) value = Duelists_BaseId(value);
#endif
    values[index] = value;
}

void AiScript_LoadTerrain(void)
{
    s32 index = AiScript_ReadByte();
    s32 *values = gAiScript_aMemory;
    u32 value = gDuel_bTerrain;

    values[index] = value;
}
