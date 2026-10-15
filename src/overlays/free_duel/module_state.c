#include "../../port_ptr.h"
#include "../../types.h"
#include "../../game/display_object.h"
#include "module_state.h"

u8 gFreeDuel_abGridAvailable[FREE_DUEL_GRID_STATE_CAPACITY]
    PSX_SECTION(".data") = {0};
DisplayObject *TRANSLATED_G32 gFreeDuel_pThumbWidget
    PSX_SECTION(".data") = 0;
static u32 sFreeDuel_dwUnknown105C
    PSX_SECTION(".data") = 0;
DisplayObject *TRANSLATED_G32 gFreeDuel_apSparklePool[FREE_DUEL_SPARKLE_POOL_CAPACITY]
    PSX_SECTION(".data") = {0};
DisplayObject *TRANSLATED_G32 gFreeDuel_pCursorWidget
    PSX_SECTION(".data") = 0;
u32 gFreeDuel_dwScreenFlagsStorage
    asm("gFreeDuel_bScreenFlags")
    PSX_SECTION(".data") = 0;
