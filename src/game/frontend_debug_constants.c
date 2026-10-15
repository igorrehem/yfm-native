#include "../port_ptr.h"
#include "../types.h"
#include "frontend_debug_constants.h"

/* GCC 2.8.1 aligns arrays to four bytes, so keep this retail block scalar. */
u16 D_8009AF44 PSX_SECTION(".sdata") = 0x0500;
u16 D_8009AF46 PSX_SECTION(".sdata") = 1;
static u16 sFrontendDebugValue48 PSX_SECTION(".sdata") = 0;
static u16 sFrontendDebugValue4A PSX_SECTION(".sdata") = 1;
u16 D_8009AF4C PSX_SECTION(".sdata") = 0x000F;
static u16 sFrontendDebugValue4E PSX_SECTION(".sdata") = 0x00F0;
static u16 sFrontendDebugValue50 PSX_SECTION(".sdata") = 0x0F00;
static u16 sFrontendDebugValue52 PSX_SECTION(".sdata") = 0xF000;
