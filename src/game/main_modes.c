#include "../types.h"
#include "main_modes.h"
#ifdef MEMORIES_PC
#include "pc/cards/passwords.h"
#endif

/* Initialized data at 0x80090B64: the mode dispatch table Main_Loop indexes
   with the low five bits of the frontend state byte. */
MainModeRunner TRANSLATED_G32 gMain_apfnModeRunner[MAIN_MODE_COUNT] = {
    Main_RunDebugMenu,
    Main_RunAnimatedBattle,
    Main_RunCampaign,
    Main_RunDuel,
#ifdef MEMORIES_PC
    CardPassword_RunLibraryMenu, /* the Library, then View > Card passwords (passwords.h) */
#else
    Main_RunLibraryMenu,
#endif
    Main_RunCampaignMap,
    Main_RunFreeDuelMenu,
    Main_RunBuildDeckMenu,
    Main_RunMenu,
    Main_RunNameEntry,
    Main_RunPasswordMenu,
    Main_RunOptionsMenu,
    Main_RunGameOver,
    Main_RunUnusedDeveloperMode,
    Main_RunTrade,
    Main_RunCredits,
    Main_RunTwoPlayerDuelSetup,
};
