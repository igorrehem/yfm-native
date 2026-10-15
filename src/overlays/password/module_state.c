#include "../../port_ptr.h"
#include "../../types.h"
#include "../../ygo_types.h"
#include "module_state.h"

PasswordModuleState gPassword_ModuleState
    PSX_SECTION(".data") = {0};
