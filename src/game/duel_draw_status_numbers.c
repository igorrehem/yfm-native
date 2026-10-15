#include "../types.h"
#include "text_encode_decimal_digits.h"
#include "../psyq/libgte.h"
#include "../psyq/libgpu.h"
#include "../psyq/libgs.h"
#include "duel_side_state.h"
#include "../ygo_types.h"
#include "duel_draw_status_numbers.h"
#include "card_constants.h"
#include "duel_display.h"
#include "duel_grid.h"
#include "ordering_tables.h"
#ifdef MEMORIES_PC
#include "display_object.h"
#include "display_object_layout.h"
#include "display_object_packet_submit.h"
#include "display_object_render_sprite_sheet.h"
#include "pc/cards/duel_ui.h"
#endif

/* The duel screen's life-point and deck-count readout: func_80016D2C sorts
   one row of digit sprites, Duel_UpdateLifePointDisplay steps the drawn
   life-point counter a frame towards the real total, and
   Duel_DrawLifePointsAndDeckCounts calls both for each side. The first two
   were recorded at gcc_2_8_1_g0_split and gcc_2_8_1_g8 and compile to
   identical objects at this unit's gcc_2_8_1_g8_split. */

void func_80016D2C(
    DisplayObject *style,
    GsSPRITE *digit,
    int source,
    int count
) {
    u8 temp[8];
    int i;

    Text_EncodeDecimalDigits(source, count, temp);
    for (i = count - 1; i >= 0; i--) {
        digit->u = temp[i] << 3;
        GsSortFastSprite(
            digit,
            D_800E9D90[style->ot_index],
            style->field_14
        );
        digit->x += 8;
    }
}

/* Steps the drawn life-point counter one frame towards the real total. The
 * step grows with the distance left, which is what makes the readout race
 * for a large swing and crawl for a small one.
 */
void Duel_UpdateLifePointDisplay(DuelSideState *side)
{
    s32 difference =
        side->displayed_life_points - side->life_points.signed_value;
    /* This order and the builtin preserve the target a1/a2 register roles. */
    s32 step;
    s32 magnitude;

    if (difference == 0) {
        return;
    }
    magnitude = __builtin_abs(difference);
    step = 9;
    if (magnitude >= 300) {
        step = 19;
    }
    if (magnitude >= 1000) {
        step = 47;
    }
    if (magnitude >= 3000) {
        step = 97;
    }
    if (difference > 0) {
        difference -= step;
        if (difference < 0) {
            difference = 0;
        }
    } else {
        difference += step;
        if (difference > 0) {
            difference = 0;
        }
    }
    side->displayed_life_points =
        side->life_points.unsigned_value + difference;
}

/* Draws the paired digit-sprite readout for both players' D_800E9FF0 slots.
   D_8009B1D5 selects which side (0 or 1) currently renders in the "active"
   grey shade (0x808080) vs the dim shade (0x404040); the other side always
   gets the opposite shade. Each side draws two digit groups (4-digit then
   2-digit) offset from the display object arg0->field_50 points at. The values
   are displayed life points and DECK_SIZE minus the signed deck_draw_cursor
   of the corresponding D_800E9FF0 entry. */

#define GS_SPRITE_VIEW(sprite) ((GsSPRITE *)(sprite))
#define SCRATCH ((DuelStatusDigitPacket *)SCRATCHPAD_ADDR(0x1F800320))

#ifdef MEMORIES_PC
/* Life points past 9999: a mod's "limits" (pc/cards/tables.h) may start a
   duel with more or let healing go further. Either side's record says so
   (its start, its healing cap, or what it holds now), and then the panel
   is drawn a digit wider for the whole duel, the fifth digit on the left.
   Without such a mod every value stays under 10000 and nothing here draws. */
#define LIFE_POINT_DIGIT_WIDTH 8
/* The panel's columns from here to its right edge are the boxes' insides
   and right borders, right of every label (LP, COM, YOU). */
#define LIFE_POINT_PANEL_SPLIT 32

static s32 Duel_LifePointDigits(void)
{
    s32 i;

    for (i = 0; i < DUEL_SIDE_COUNT; i++) {
        if (D_800E9FF0[i].max_life_points >= 10000 || D_800E9FF0[i].life_points.signed_value >= 10000 ||
            D_800E9FF0[i].displayed_life_points >= 10000) {
            return 5;
        }
    }
    return 4;
}

/* The panel a digit wider, from its own picture: a one-part sprite sheet
   (DisplayObject_RenderSpriteSheet). Its sprite is worked out by letting the
   sheet renderer place it far off screen, where nothing shows (a
   screen-space sheet culls it), and read back from the scratchpad. Then,
   after the digits, so that the ordering table draws them the other way
   round: the panel's right part where it is, and the whole panel again one
   digit to the left. The copy covers the one the display list drew,
   labels and the opponent's name over COM with it (a whole panel is what
   the HD text and the name look for), and the right part put back over the
   copy's right edge makes the boxes one digit longer. Only the plain case:
   a panel flipped, clip-tested or of more parts is left as it is. */
#define LIFE_POINT_PANEL_PROBE 1024

static void Duel_DrawWideLifePointPanel(DisplayObject *panel)
{
    SpritePrim *sprite = (SpritePrim *)SCRATCHPAD_ADDR(0x1F800320);
    SpritePrim part;
    s32 ot = (s32)D_800E9D90[panel->ot_index];
    s32 depth = (s16)panel->field_14;
    s16 x = panel->field_30.h.field_30;
    s32 left;
    s32 top;

    if (((SpriteSheetHeader *G32)panel->field_4C)->count != 1 ||
        (panel->flags & DISPLAY_OBJECT_FLAG_CLIP_TEST) || (panel->attribute & 0x800000)) {
        return;
    }
    panel->field_30.h.field_30 = x + LIFE_POINT_PANEL_PROBE;
    DisplayObject_RenderSpriteSheet(panel, ot, depth);
    panel->field_30.h.field_30 = x;
    part = *sprite;
    /* Its top left corner, back from the pivot a sheet off screen space is
       placed by. */
    left = (s16)part.xy.h.x - LIFE_POINT_PANEL_PROBE;
    top = (s16)part.xy.h.y;
    if ((panel->attribute & 0x08000000) == 0) {
        left -= (s16)part.mxmy.h.x;
        top -= (s16)part.mxmy.h.y;
    }
    part.mxmy.word = 0;
    part.rotate = 0;

    *sprite = part;
    sprite->xy.h.x = left + LIFE_POINT_PANEL_SPLIT;
    sprite->xy.h.y = top;
    sprite->uv.b.lo += LIFE_POINT_PANEL_SPLIT;
    sprite->extent.wh.w.word -= LIFE_POINT_PANEL_SPLIT;
    DisplayObject_SubmitPacket(sprite, 0, ot, (u16)depth | 0x10000, 0);

    *sprite = part;
    sprite->xy.h.x = left - LIFE_POINT_DIGIT_WIDTH;
    sprite->xy.h.y = top;
    DisplayObject_SubmitPacket(sprite, 0, ot, (u16)depth | 0x10000, 0);
}
#endif

void Duel_DrawLifePointsAndDeckCounts(DisplayObject *arg0)
{
    DisplayObject *pos;
    DuelStatusDigitPacket *scratch;
    u32 tmp10;
#ifdef MEMORIES_PC
    s32 digits;
    s32 own;
#endif

    Duel_UpdateLifePointDisplay(&D_800E9FF0[0]);
    Duel_UpdateLifePointDisplay(&D_800E9FF0[1]);
    pos = (DisplayObject *G32)arg0->field_50.word;
#ifdef MEMORIES_PC
    digits = Duel_LifePointDigits();
    /* A mod's "ui" moving the panel's halves draws their digits with them
       (pc/cards/duel_ui.h), and widens them itself for a fifth. */
    own = DuelUi_PanelDrawn(digits);
#endif

    scratch = SCRATCH;
    scratch->field_00 = 0x09000000;
    tmp10 = 0xF10100;
    scratch->field_10 = tmp10;
    scratch->field_0C = 0x1E;
    scratch->field_0E = 0x5800;
    scratch->field_08 = 0x80008;
    scratch->field_14 = DUEL_DISPLAY_COLOR_NORMAL;
    if (D_8009B1D5 == 0) {
        scratch->field_14 = DUEL_DISPLAY_COLOR_DIMMED;
    }

    scratch->field_04 = pos->field_30.h.field_30 - 3;
    scratch->field_06 = pos->field_30.h.field_32 - 0xD;
#ifdef MEMORIES_PC
    scratch->field_04 -= (digits - 4) * LIFE_POINT_DIGIT_WIDTH;
    if (!own || !DuelUi_DrawDigits(1, pos, scratch, D_800E9FF0[1].displayed_life_points, digits))
        func_80016D2C(pos, GS_SPRITE_VIEW(scratch), D_800E9FF0[1].displayed_life_points, digits);
#else
    func_80016D2C(
        pos,
        GS_SPRITE_VIEW(scratch),
        D_800E9FF0[1].displayed_life_points,
        4
    );
#endif

    scratch->field_04 = pos->field_30.h.field_30 + 0xE;
    scratch->field_06 = pos->field_30.h.field_32 - 5;
#ifdef MEMORIES_PC
    if (!own || !DuelUi_DrawDigits(1, pos, scratch, DECK_SIZE - D_800E9FF0[1].deck_draw_cursor, 2))
#endif
    func_80016D2C(
        pos,
        GS_SPRITE_VIEW(scratch),
        DECK_SIZE - D_800E9FF0[1].deck_draw_cursor,
        2
    );

    scratch->field_14 = DUEL_DISPLAY_COLOR_NORMAL;
    if (D_8009B1D5 != 0) {
        scratch->field_14 = DUEL_DISPLAY_COLOR_DIMMED;
    }

    scratch->field_04 = pos->field_30.h.field_30 - 3;
    scratch->field_06 = pos->field_30.h.field_32 + 0xD;
#ifdef MEMORIES_PC
    scratch->field_04 -= (digits - 4) * LIFE_POINT_DIGIT_WIDTH;
    if (!own || !DuelUi_DrawDigits(0, pos, scratch, D_800E9FF0[0].displayed_life_points, digits))
        func_80016D2C(pos, GS_SPRITE_VIEW(scratch), D_800E9FF0[0].displayed_life_points, digits);
#else
    func_80016D2C(
        pos,
        GS_SPRITE_VIEW(scratch),
        D_800E9FF0[0].displayed_life_points,
        4
    );
#endif

    scratch->field_04 = pos->field_30.h.field_30 + 0xE;
    scratch->field_06 = pos->field_30.h.field_32 + 5;
#ifdef MEMORIES_PC
    if (!own || !DuelUi_DrawDigits(0, pos, scratch, DECK_SIZE - D_800E9FF0[0].deck_draw_cursor, 2))
#endif
    func_80016D2C(
        pos,
        GS_SPRITE_VIEW(scratch),
        DECK_SIZE - D_800E9FF0[0].deck_draw_cursor,
        2
    );
#ifdef MEMORIES_PC
    if (digits > 4 && !own) {
        Duel_DrawWideLifePointPanel(pos);
    }
#endif
}
