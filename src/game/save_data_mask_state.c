#include "../port_ptr.h"
#include "../types.h"
#include "save_data.h"

u32 gSaveData_dwMaskStateLow PSX_SECTION(".sdata") = 0x55555555;
u32 gSaveData_dwMaskStateHigh PSX_SECTION(".sdata") = 0x55555555;
