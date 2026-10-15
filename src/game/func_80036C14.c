#include "../types.h"
#include "duel_effect.h"
#include "func_80036C14.h"
#include "../unmatched.h"
#ifdef MEMORIES_PC
#include "pc/text/glyphs.h"
#include "pc/cards/stars.h"
#include "pc/cards/duel_ui.h"
#include "pc/cards/type_icons.h"
#endif

/* D_801D9174: a lookup table of 0x1E-byte records, each prefixed by a
   big-endian u16 id (id field for record i lives 2 bytes apart, but the
   record itself is 0x1E bytes -- id and record strides differ, so this is
   NOT `struct { u16 id; ... } records[]`; it is a compact id table walked
   in lockstep with the 0x1E-byte record table). Terminated by an id of 0.
   Returns a pointer to the matching record, or NULL if not found / list
   ends first. */

s32 Text_FindRecordById(s32 id) {
    u8 *rec;
    u8 *key;
    s32 v;

    rec = D_801D9174;
    key = D_801D9174_b;

loop_check:
    v = key[0] << 8;
    v |= key[1];
    if (v == 0) {
        return 0;
    }
    if (v == id) {
        return (s32) rec;
    }
    key += 2;
    rec += 0x1E;
    goto loop_check;
}

void DuelEffect_AppendEntry(DuelEffectChannel *p, s32 a)
{
    DuelEffectEntry *q;
    s16 *r;
    u16 f;
    s32 v;
    s32 b;
    s32 c;
#ifdef MEMORIES_PC
    /* The guardian star or the card type func_80037DA4 said this icon
       stands for, taken now so it never passes to a later entry (stars.h,
       type_icons.h). The two are never both marked for the same entry. */
    u16 star_icon = Stars_TakeIconMark();
    u16 type_icon = (u16)TypeIcons_TakeIconMark();
#endif

    q = p->entry_end_20;
#ifdef MEMORIES_PC
    /* The channel's slice of D_800EB288 (range_count_5E entries from
       range_start_5C: 255, 160, 160 and 45; with a PAL language 280, 220,
       220 and 80, as on the PAL console) holds the page's entries and the
       one after the last, whose cleared flags end the list. The console's
       own text always fits; a translation's page may not, and the entries
       past the slice are the next channel's, and past the last channel's
       whatever follows the table. What does not fit is left out. */
    if (p->range_count_5E != 0 &&
        q >= &D_800EB288[p->range_start_5C + p->range_count_5E - 1]) {
        return;
    }
    if (q >= &D_800EB288[DUEL_EFFECT_ENTRY_TOTAL - 1]) {
        return;
    }
#endif
    q->field_12 = p->index_57 + 1;
    q->field_13 = 1;
    q->field_15 = 0;
    r = D_801DA000;
    f = p->flags_34;
    if (f & 0x80) {
        q->field_10 = a;
        b = p->field_62;
        q->flags_11 = 0xA0;
        q->field_17 = b;
#ifdef MEMORIES_PC
        /* Retail leaves an icon's code as the entry had it; func_80035E20
           reads a star's or a type's there, so every icon says whether it
           is one. */
        q->code_00 = star_icon ? star_icon : type_icon;
#endif
    } else if (f & 0x100) {
#ifdef MEMORIES_PC
        /* The 8x8 font: an added letter and ':' are the port's to draw
           (glyphs.h), and func_80035E20 knows them by the Shift-JIS, which
           the retail entry leaves as it was. */
        v = Glyphs_TinyIndex(a);
#else
        v = (a >> 20) & 0xFF;
#endif
        if (v == 0) {
            return;
        }
#ifdef MEMORIES_PC
        q->code_00 = (u16)a;
#endif
        q->field_10 = v;
        q->flags_11 = 0xC0;
        c = p->field_54;
        q->field_13 = 0;
        q->field_16 = c;
    } else {
        a &= 0x8000FFFF;
        if (a == 0) {
            return;
        }
        if (f & 0x200) {
            r = (s16 *)(p->field_60 * 0x88 + (u8 *)r);
        }
        q->field_10 = 0;
        b = p->field_54;
        q->flags_11 = 0x80;
        *(s32 *)q = a;
        q->field_16 = b;
        r[0] = 0x280;
        r[2] = 4;
        r[1] = 0;
        r[3] = 0x10;
    }
    if (p->flags_34 & 0x1C00) {
        q->field_13 = 0;
    }
    q->x_0C = p->field_38;
    q->y_0E = p->field_3A;
#ifdef MEMORIES_PC
    /* Which of the card bar's parts it is, for a mod's "ui" (duel_ui.h). */
    DuelUi_TagEntry(p, q);
#endif
    q++;
    q->flags_11 = 0;
    p->entry_end_20 = q;
}
