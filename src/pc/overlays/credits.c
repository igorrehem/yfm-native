#include "pc/compat/fs.h"
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "pc/guest/mips.h"
#include "pc/guest/retail_image.h"

/* The credits module, 16 SU sectors the ending (model_intro_controller.c)
 * loads over the main menu at 0x80180000 and enters at three addresses:
 * set-up, the per-frame update (nonzero when the roll is over) and the
 * start of a group of lines. The decomp matched all of it
 * (src/overlays/credits, prefixed credits__ by the build), and that C runs
 * whenever the delivered bytes are the retail module
 * (src/pc/guest/retail_image.c); anything else is interpreted as before.
 * MEMORIES_CREDITS=interpreter interprets it even when it is retail. */
extern void credits__func_801807B0(void);
extern int credits__func_80180A24(void);
extern void credits__func_80181C4C(int group);

static int native(void)
{
    static int forced = -1;
    if (forced < 0) {
        const char *setting = getenv("MEMORIES_CREDITS");
        forced = setting && strcmp(setting, "interpreter") == 0;
    }
    return !forced && RetailImage_Verified(RETAIL_IMAGE_CREDITS);
}

void Memories_CreditsInit(void)
{
    if (native()) {
        credits__func_801807B0();
    } else {
        Memories_MipsCall(0x801807B0u, 0, 0, 0, 0);
    }
}

int Memories_CreditsUpdate(void)
{
    if (native()) {
        return credits__func_80180A24();
    }
    return (int)Memories_MipsCall(0x80180A24u, 0, 0, 0, 0);
}

void Memories_CreditsLines(int group)
{
    if (native()) {
        credits__func_80181C4C(group);
    } else {
        Memories_MipsCall(0x80181C4Cu, (uint32_t)group, 0, 0, 0);
    }
}
