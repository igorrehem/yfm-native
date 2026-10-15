/* The card packs' name box on the Password screen (src/pc/cards/pack_shop.c):
 * text channel 2, where the screen draws its digits, made again with a
 * pack's name in the game's normal letters.
 *
 * A game unit, because the channel's reset (func_8003B6AC) is still the
 * game's own code rather than C, which only game code reaches. It has no
 * variables, so nothing in the game's data moves; it sorts after the other
 * game units all the same. */
#include "types.h"
#include "ygo_types.h"
#include "game/func_8003B6AC.h"
#include "game/text_box_lifecycle.h"
#include "game/text_box_runtime.h"

void PackShop_NameBox(s32 id)
{
    DuelEffectChannel *box;

    func_8003B6AC(2, 1);
    box = (DuelEffectChannel *)TextBox_Create(2, id, 0xA8, 0x68, 0xA0, 0x10);
    if (box) {
        func_80039A14((struct DuelEffectChannel *)box);
    }
}
