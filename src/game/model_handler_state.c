#include "../port_ptr.h"
#include "../types.h"
#include "model_handler_state.h"

u8 D_8009AFE4 PSX_SECTION(".sdata") = 0;
u8 D_8009AFE5 PSX_SECTION(".sdata") = 0;
u16 D_8009AFE6 PSX_SECTION(".sdata") = 0;
u8 D_8009AFE8 PSX_SECTION(".sdata") = 0;
u8 D_8009AFE9 PSX_SECTION(".sdata") = 0;
static u16 sModelHandlerState_PadAFEA
    PSX_SECTION(".sdata") = 0;
u32 D_8009AFEC[2] PSX_SECTION(".sdata") = {
    0x10000000,
    0x00040000,
};
char D_8009AFF4[8] PSX_SECTION(".sdata") = "WHY?\n";
u32 D_8009AFFC[2] PSX_SECTION(".sdata") = {
    0xFA240000,
    0,
};
