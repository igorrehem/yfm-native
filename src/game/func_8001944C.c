#define GRAPHICS_ACTIVE_BUFFER_IN_DATA
#include "../types.h"
#include "../psyq/libgte.h"
#include "../psyq/libgpu.h"
#include "color_constants.h"
#include "display_object.h"
#include "duel_display.h"
#include "duel_card_staging.h"
#include "func_8001944C.h"
#include "graphics_frame.h"
#ifdef MEMORIES_PC
#include "pc/sdk/display.h"
#endif

#define DUEL_CARD_READBACK_HALFWORDS(buffer) ((u16 *)(buffer))
#define DUEL_CARD_READBACK_WORDS(buffer) ((u32 *)(buffer))

void DuelCard_CaptureRoundedTexture(DisplayObject *o)
{
    u8 *buf;
    u16 *p;
    s32 xoff;

    while (IsIdleGPU(10) != 0) {
        ;
    }

    xoff = 0;
    if (gGraphics_bActiveBuffer == 0) {
        xoff = 0x140;
    }

    buf = D_8015C424;
    D_800E9D70[0].x = o->field_30.h.field_30 + xoff;
    D_800E9D70[0].y = o->field_30.h.field_32;
    D_800E9D70[0].w = DUEL_CARD_READBACK_WIDTH_WORDS;
    D_800E9D70[0].h = DUEL_CARD_READBACK_HEIGHT;
    StoreImage2(&D_800E9D70[0], DUEL_CARD_READBACK_WORDS(buf));
#ifdef MEMORIES_PC
    /* Where the card was read from: the RECT is reused for the load. */
    s32 source_x = D_800E9D70[0].x, source_y = D_800E9D70[0].y;
#endif

    p = DUEL_CARD_READBACK_HALFWORDS(buf);
    xoff = DUEL_CARD_READBACK_WORD_COUNT;
    do {
        *p = *p | COLOR_BGR555_STP_MASK;
        p++;
        xoff--;
    } while (xoff != 0);

    /* The loop above set the STP bit on every pixel; these clear twelve
       corner pixels of the 140x196 readback back to 0 -- (0, 0), (0, 1),
       (1, 0) and the matching three at each other corner -- which rounds
       the card's corners. (0, 0) is the store through D_8015C424 below. */
    p = DUEL_CARD_READBACK_HALFWORDS(D_8015C424);
    p[195 * DUEL_CARD_READBACK_WIDTH_WORDS + 138] = 0;
    p[195 * DUEL_CARD_READBACK_WIDTH_WORDS + 139] = 0;
    p[195 * DUEL_CARD_READBACK_WIDTH_WORDS + 1] = 0;
    p[195 * DUEL_CARD_READBACK_WIDTH_WORDS + 0] = 0;
    p[194 * DUEL_CARD_READBACK_WIDTH_WORDS + 139] = 0;
    p[194 * DUEL_CARD_READBACK_WIDTH_WORDS + 0] = 0;
    p[1 * DUEL_CARD_READBACK_WIDTH_WORDS + 139] = 0;
    p[1 * DUEL_CARD_READBACK_WIDTH_WORDS + 0] = 0;
    p[0 * DUEL_CARD_READBACK_WIDTH_WORDS + 138] = 0;
    p[0 * DUEL_CARD_READBACK_WIDTH_WORDS + 139] = 0;
    p[0 * DUEL_CARD_READBACK_WIDTH_WORDS + 1] = 0;

    DUEL_CARD_READBACK_HALFWORDS(D_8015C424)[0] = 0;
    D_800E9D70[0].x = 0x140;
    D_800E9D70[0].y = 0x100;
    D_800E9D70[0].w = DUEL_CARD_READBACK_WIDTH_WORDS;
    D_800E9D70[0].h = DUEL_CARD_READBACK_HEIGHT;
    LoadImage2(&D_800E9D70[0], DUEL_CARD_READBACK_WORDS(D_8015C424));
#ifdef MEMORIES_PC
    /* The burn draws the card from this copy: the port's scaled picture
     * keeps the card as it was drawn there (a texture pack, HD text), where
     * VRAM only has it at the console's resolution. */
    Memories_PictureCapture(source_x, source_y, D_800E9D70[0].x, D_800E9D70[0].y, DUEL_CARD_READBACK_WIDTH_WORDS,
                            DUEL_CARD_READBACK_HEIGHT);
#endif
}
