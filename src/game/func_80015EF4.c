/* Draws one 3D duel card. The display object's Euler bytes and position build
 * a local matrix in the scratchpad, four card corners are rotated, lit with
 * RotColorDpq into the POLY_GT4 and sorted at their mean depth, and the same
 * corners flattened to y = 0 are projected with RTPS into the POLY_FT4 that
 * is sorted at the back as the card's ground sprite.
 *
 * What the retail listing fixes about the source:
 * - The scale test reads the 16-bit flags word against GsROTOFF (1 << 27).
 *   cse cannot see that the mask misses every bit of a halfword; combine can,
 *   but only after the test is its own instruction, so retail keeps a literal
 *   zero, a branch that never goes, and the dead temporary's stack slot.
 * - The matrix, the first corner, the scale, the light normal, the rotation
 *   and the depth words are pointers set once after the guard, in address
 *   order. Corners 1-3 and copies 1-3 get their own pointers where they are
 *   first used; copy 0 is rot[4].
 * - Each chained store writes the right-hand corner first.
 * - The RTPS inputs are literal scratchpad addresses, which reload
 *   materialises in $t0-$t3.
 * - u0 and v0 are both read back before either is biased, and setPolyGT4
 *   follows the clut store.
 *
 * The GTE words come from the official Psy-Q inline_c.h macros; the profile
 * expands Psy-Q's RTPS placeholder to the real COP2 opcode. */
#include "../types.h"
#include "../ygo_types.h"
#include "../psyq/libgte.h"
#include "../psyq/libgpu.h"
#include "../psyq/libgs.h"
#include "../psyq/inline_c.h"
#include "display_object.h"
#include "screen_projection.h"
#include "ordering_tables.h"
#include "func_80015EF4.h"
#ifdef MEMORIES_PC
#include "duel_card.h"
#include "duel_card_layout.h"
#include "pc/cards/card_layout_art.h"
#include "pc/cards/cards.h"
#endif

#define CVECTOR_VIEW(color) ((CVECTOR *)(color))
#define DISPLAY_OBJECT_BYTES(object) ((u8 *)(object))

void func_80015EF4(void *record, POLY_GT4 *prim, POLY_FT4 *sprite, s32 *color)
{
    DuelCardRenderHolder *holder = record;
    GsOT *G32 *tab;
    DisplayObject *obj;
    s32 a;
    s32 c;
    s32 d;
    s32 y;
    MATRIX *lm;
    SVECTOR *q;
    VECTOR *scale;
    SVECTOR *up;
    SVECTOR *rot;
    s32 *depth;
    SVECTOR *q1;
    SVECTOR *q2;
    SVECTOR *q3;
    SVECTOR *c1;
    SVECTOR *c2;
    SVECTOR *c3;

    obj = (DisplayObject *)holder->model;
    if ((obj->flags & 0x40) == 0) {
        return;
    }

    lm = (MATRIX *)SCRATCHPAD_ADDR(0x1F8002C0);
    q = (SVECTOR *)SCRATCHPAD_ADDR(0x1F800300);
    scale = (VECTOR *)SCRATCHPAD_ADDR(0x1F800320);
    up = (SVECTOR *)SCRATCHPAD_ADDR(0x1F800380);
    rot = (SVECTOR *)SCRATCHPAD_ADDR(0x1F8003A0);
    depth = (s32 *)SCRATCHPAD_ADDR(0x1F8003E0);
    up->vx = 0;
    up->vy = 0x1000;
    up->vz = 0;
    *color = obj->field_0C;
    rot[0].vx = obj->field_20.b.field_20 << 4;
    y = obj->field_20.b.field_21 << 4;
    rot[0].vy = y;
    rot[0].vz = obj->field_20.b.field_22 << 4;
    if (holder->field_18 >= 0xF) {
        rot[0].vy = y + 0x800;
    }
    lm->t[0] = *(s16 *)(DISPLAY_OBJECT_BYTES(obj) + 0x30);
    a = *(s16 *)(DISPLAY_OBJECT_BYTES(obj) + 0x32);
    lm->t[1] = a;
    d = *(s16 *)(DISPLAY_OBJECT_BYTES(obj) + 0x34);
    lm->t[2] = d;
    a += 0xFF;
    if (a < 0) {
        a = 0;
    }
    sprite->b0 = a;
    sprite->g0 = a;
    sprite->r0 = a;
    RotMatrixZYX_gte(rot, lm);
    if ((obj->flags & GsROTOFF) == 0) {
        scale->vx = obj->field_44.h.field_44;
        scale->vy = 0x1000;
        scale->vz = obj->field_44.h.field_46;
        ScaleMatrix(lm, scale);
    }

    q2 = (SVECTOR *)SCRATCHPAD_ADDR(0x1F800310);
    q3 = (SVECTOR *)SCRATCHPAD_ADDR(0x1F800318);
    q1 = (SVECTOR *)SCRATCHPAD_ADDR(0x1F800308);
    q[0].vx = q2->vx = -0x19;
    q[1].vx = q3->vx = 0x1A;
    q[0].vz = q1->vz = 0x1D;
    q[2].vz = q3->vz = -0x1E;
    q[0].vy = q1->vy = q2->vy = q3->vy = 0;
    GsSetLsMatrix(lm);

    RotTransSV(&q[0], &rot[0], (PSXLONG *)depth);
    RotTransSV(&q[1], &rot[1], (PSXLONG *)depth);
    RotTransSV(&q[2], &rot[2], (PSXLONG *)depth);
    RotTransSV(&q[3], &rot[3], (PSXLONG *)depth);

    c1 = (SVECTOR *)SCRATCHPAD_ADDR(0x1F8003C8);
    c2 = (SVECTOR *)SCRATCHPAD_ADDR(0x1F8003D0);
    c3 = (SVECTOR *)SCRATCHPAD_ADDR(0x1F8003D8);
    *(Bytes8 *)&rot[4] = *(Bytes8 *)&rot[0];
    *(Bytes8 *)c1 = *(Bytes8 *)&rot[1];
    *(Bytes8 *)c2 = *(Bytes8 *)&rot[2];
    *(Bytes8 *)c3 = *(Bytes8 *)&rot[3];

    GsSetLightMatrix(lm);
    GsSetLsMatrix(&D_800FE148);

    depth[4] = RotColorDpq(&rot[0], up, CVECTOR_VIEW(color),
                (PSXLONG *)&prim->x0, CVECTOR_VIEW(&prim->r0),
                (PSXLONG *)&depth[0]);
    depth[5] = RotColorDpq(&rot[1], up, CVECTOR_VIEW(color),
                (PSXLONG *)&prim->x1, CVECTOR_VIEW(&prim->r1),
                (PSXLONG *)&depth[1]);
    depth[6] = RotColorDpq(&rot[2], up, CVECTOR_VIEW(color),
                (PSXLONG *)&prim->x2, CVECTOR_VIEW(&prim->r2),
                (PSXLONG *)&depth[2]);
    depth[7] = RotColorDpq(&rot[3], up, CVECTOR_VIEW(color),
                (PSXLONG *)&prim->x3, CVECTOR_VIEW(&prim->r3),
                (PSXLONG *)&depth[3]);

    if ((depth[0] | depth[1] | depth[2]
         | depth[3]) < 0) {
        return;
    }

    prim->u0 = prim->u2 = DISPLAY_OBJECT_BYTES(obj)[0x5C];
    prim->v0 = prim->v1 = DISPLAY_OBJECT_BYTES(obj)[0x5D];
    if (NormalClip(*(PSXLONG *)&prim->x0, *(PSXLONG *)&prim->x1,
                   *(PSXLONG *)&prim->x2) <= 0) {
        prim->u2 = 0x38;
        prim->u0 = 0x38;
        prim->v1 = 0x80;
        prim->v0 = 0x80;
    }
    c = prim->u0;
    d = prim->v0;
    c += 0x34;
    d += 0x3C;
    prim->u3 = c;
    prim->u1 = c;
    prim->v3 = d;
    prim->v2 = d;
    prim->clut = (((u16)obj->field_40.h.field_42 + 0xF1) << 6) | 0x10;
    setPolyGT4(prim);
    SetSemiTrans(prim, 0);
    prim->tpage = prim->tpage & 0xFF9F;
    prim->tpage = prim->tpage | ((obj->attribute >> 23) & 0x60);
    if ((obj->attribute & GsALON) != 0) {
        SetSemiTrans(prim, 1);
        sprite->r0 = DISPLAY_OBJECT_BYTES(obj)[0xC];
        sprite->g0 = DISPLAY_OBJECT_BYTES(obj)[0xD];
        sprite->b0 = DISPLAY_OBJECT_BYTES(obj)[0xE];
    }

#ifdef MEMORIES_PC
    /* A style's own field texture (card_layout_art.h's
     * CardLayoutArt_FieldFrameCell/FieldBackCell) replaces retail's
     * Cards_FrameColor palette-row pick above outright: tpage/clut/u/v only,
     * so the corners' already-rotated xy and already-lit rgb (RotColorDpq
     * above) stay exactly what retail computed, and the custom texture
     * rotates with them like any other face of this quad.
     *
     * The face is the one retail's own uv pick above shows: the back when
     * the quad faces away (NormalClip), which a face-down card does (it is
     * turned over) and a face-up one does for half of a turn. The style's
     * field_back_image there, else retail's own back. */
    {
        int field_tpage, field_u, field_v, field_clut, field_w, field_h;
        int card_id = ((DuelCardRecord *)record)->card_id;
        /* The face the quad shows, as retail's uv pick above: its back
         * (u 0x38, v 0x80) when it faces away -- face down, or a face-up
         * card mid-turn. */
        int face_down = NormalClip(*(PSXLONG *)&prim->x0, *(PSXLONG *)&prim->x1, *(PSXLONG *)&prim->x2) <= 0;
        int got = face_down
            ? CardLayoutArt_FieldBackCell(card_id, &field_tpage, &field_u, &field_v, &field_clut, &field_w,
                                          &field_h)
            : CardLayoutArt_FieldFrameCell(card_id, &field_tpage, &field_u, &field_v, &field_clut, &field_w,
                                           &field_h);
        if (got) {
            prim->tpage = (u16)(field_tpage | ((obj->attribute >> 23) & 0x60));   /* the blend, as retail's */
            prim->clut = (u16)field_clut;
            prim->u0 = prim->u2 = (u8)field_u;
            prim->u1 = prim->u3 = (u8)(field_u + field_w);
            prim->v0 = prim->v1 = (u8)field_v;
            prim->v2 = prim->v3 = (u8)(field_v + field_h);
        } else {
            /* Neither cell applies to this card (no style at all, or a
             * face-down card with no field_back_image): prim->tpage must be
             * put back to Duel_DrawFieldCards' own known base
             * (func_800164FC.c's p3->tpage = 0x9E), not left as whatever
             * this scratchpad currently holds. It is the same POLY_GT4
             * reused for every field card drawn this frame, reset only
             * there, once, before the whole loop -- retail's own tpage line
             * two above only ever touches its bits 5-6, never its bank bits
             * (11-14), because retail itself never needs to: real VRAM is
             * always bank 0. A style's own full tpage above is the first
             * thing that ever puts a different bank there, and with
             * nothing to reset it, an unrelated plain card drawn right
             * after would go on sampling that same bank (confirmed live: a
             * stray green tint on a plain card, but only once a styled card
             * had drawn earlier in the same frame -- not on its own). */
            prim->tpage = (0x9E & 0xFF9F) | ((obj->attribute >> 23) & 0x60);
            if (face_down && Cards_FrameColor(card_id) >= 0) {
                /* No style back_image to fall back to and face down: retail's
                 * own monster/magic/trap/ritual rows (0-3) read the same bytes
                 * at this mirrored-back uv regardless of row, but
                 * Cards_FrameColor's own extra rows (func_80024C1C.c, 4+ for a
                 * style's own hand_color) are a PC-port addition, baked into
                 * obj->icon_variant once at creation and never revisited for
                 * face state -- that row's own palette is only ever meant to be
                 * seen face up, so whatever happens to sit at this mirrored uv
                 * there (confirmed live: a wrong color, not retail's own grey)
                 * is not a real asset to preserve. Row 0 (plain monster) is
                 * retail's own neutral face-down look, with no accent to leak
                 * the card's styled identity through its back. */
                prim->clut = (0xF1 << 6) | 0x10;
            }
        }
    }
#endif
    depth[0] = (depth[4] + depth[5]
                          + depth[6] + depth[7]) / 4 >> 2;
    tab = D_800E9D90;
    GsSortPoly(prim, tab[2], *(u16 *)depth);

    c3->vy = 0;
    c2->vy = 0;
    c1->vy = 0;
    rot[4].vy = 0;
    gte_ldv0((SVECTOR *)SCRATCHPAD_ADDR(0x1F8003C0));
    gte_rtps();
    gte_stsxy(&sprite->x0);
    gte_ldv0((SVECTOR *)SCRATCHPAD_ADDR(0x1F8003C8));
    gte_rtps();
    gte_stsxy(&sprite->x1);
    gte_ldv0((SVECTOR *)SCRATCHPAD_ADDR(0x1F8003D0));
    gte_rtps();
    gte_stsxy(&sprite->x2);
    gte_ldv0((SVECTOR *)SCRATCHPAD_ADDR(0x1F8003D8));
    gte_rtps();
    gte_stsxy(&sprite->x3);
    GsSortPoly(sprite, tab[2], 0xFFF);
}
