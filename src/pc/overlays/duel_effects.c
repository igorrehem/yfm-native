#include "pc/compat/fs.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "game/duel_effect_request.h"
#include "pc/guest/mips.h"
#include "pc/guest/retail_image.h"
#include "pc/debug/log.h"
#include "pc/cards/stars.h"

extern unsigned char D_8009B261;
extern unsigned Memories_PresentedFrames(void);

/* The bank's entry, src/overlays/duel_effects/dispatch.c (the decomp names
 * its functions by their PAL addresses; this one is at 0x801462B0 here).
 * The build prefixes every name the module defines (GATED_MODULES). */
extern void duel_effects__func_80146258(int effect, int phase, void *buffer, DuelEffectRequest *context);

enum { MODE_AUTO, MODE_INTERPRETER, MODE_SKIP };

/* The common WA overlay dispatcher at 0x801462B0, the entry of the bank the
 * game's loader places at 0x80146000 with every duel package. It holds all
 * the field and card effects (fusion, battle damage, destruction, magic,
 * trap, ritual, terrain, and the rest: ids 0-24).
 *
 * The decomp matched the whole North American bank, and its C
 * (src/overlays/duel_effects) is linked in: that runs whenever the bytes the
 * disc delivered are the retail bank (src/pc/guest/retail_image.c). A mod or
 * disc patch that changed any of them gets the delivered MIPS run by the
 * interpreter instead, which bridges its resident SDK and game calls to the
 * native port. MEMORIES_TRACE=mods reports which of the two each delivery
 * got.
 *
 * MEMORIES_DUEL_EFFECTS=interpreter interprets the bank even when it is
 * retail (the reference for comparing the two). MEMORIES_DUEL_EFFECTS=skip
 * restores the bring-up behaviour (it was called `native` before the bank
 * ran as native C; `native` now means the default): fusion (1), battle
 * damage (2) and destruction (3) interpreted, everything else reported
 * complete on its first update. An effect the interpreter cannot run is
 * reported once and completed the same way from then on. */
void Memories_DuelEffectControl(short id, short state, int buffer, DuelEffectRequest *request)
{
    static int mode = -1;
    static unsigned failed[8];
    uint32_t args[4], result;
    int native, tpage, u, v, clut;
    unsigned index = (unsigned)(unsigned short)id;

    if (mode < 0) {
        const char *setting = getenv("MEMORIES_DUEL_EFFECTS");
        mode = !setting ? MODE_AUTO
             : strcmp(setting, "interpreter") == 0 ? MODE_INTERPRETER
             : strcmp(setting, "skip") == 0 ? MODE_SKIP
             : MODE_AUTO;
    }
    LOG(LOG_DUEL_EFFECTS, "id=%d state=%d buffer=%08x payload=%d,%d,%d damage=%d",
        id, state, (unsigned)buffer, request->field_00, request->field_02, request->field_04, request->field_12);
    native = mode == MODE_AUTO && RetailImage_Verified(RETAIL_IMAGE_DUEL_EFFECTS);
    /* The battle's guardian star (0xE): its first update gets the star
       less one and picks the icon's cell, u at +0x8C4, v +0x8C6, page
       +0x8C8, palette +0x8CA; past the disc's ten it draws an error cross.
       A star with a mod's icon, or past ten, starts as the first star and
       then takes its own cell (stars.h), native or interpreted. */
    if (id == 0xE && state >= 0 && mode != MODE_SKIP && index < 256 && !(failed[index >> 5] & (1u << (index & 31))) &&
        Stars_EffectCell(state + 1, &tpage, &u, &v, &clut)) {
        uint16_t *cell = (uint16_t *)(uintptr_t)(unsigned)(buffer + 0x8C4);

        if (native) {
            duel_effects__func_80146258(id, 0, (void *)(uintptr_t)(unsigned)buffer, request);
        } else {
            args[0] = index;
            args[1] = 0;
            args[2] = (uint32_t)buffer;
            args[3] = (uint32_t)(uintptr_t)request;
            if (Memories_MipsTry(0x801462B0u, args, 4, &result)) {
                fprintf(stderr, "memories-pc: duel effect %d cannot run; completing it at once from now on\n", id);
                failed[index >> 5] |= 1u << (index & 31);
                D_8009B261 = 1;
                return;
            }
        }
        cell[0] = (uint16_t)u;
        cell[1] = (uint16_t)v;
        cell[2] = (uint16_t)((cell[2] & 0x60) | tpage);
        cell[3] = (uint16_t)clut;
        return;
    }
    if (native) {
        duel_effects__func_80146258(id, state, (void *)(uintptr_t)(unsigned)buffer, request);
        return;
    }
    if ((mode == MODE_SKIP && !(id >= 1 && id <= 3)) || index >= 256 || (failed[index >> 5] & (1u << (index & 31)))) {
        D_8009B261 = 1;
        return;
    }
    args[0] = index;
    args[1] = (uint32_t)(int)state;
    args[2] = (uint32_t)buffer;
    args[3] = (uint32_t)(uintptr_t)request;
    if (Memories_MipsTry(0x801462B0u, args, 4, &result)) {
        fprintf(stderr, "memories-pc: duel effect %d cannot run; completing it at once from now on\n", id);
        failed[index >> 5] |= 1u << (index & 31);
        D_8009B261 = 1;
    }
}
