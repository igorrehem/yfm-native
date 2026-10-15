#include "../types.h"
#include "duel_effect.h"
#include "duel_effect_entry_ranges.h"
#include "duel_effect_init_entry.h"
#ifdef MEMORIES_PC
#include "pc/text/number_width.h"
#include "pc/cards/card_text_colors.h"
#endif

DuelEffectChannel*DuelEffect_InitEntry(int index,int value,int flags){register int offset=index<<1;DuelEffectChannel*e;unsigned short*range;e=&D_800EB0F8[index];flags|=DUEL_EFFECT_CHANNEL_FLAG_ACTIVE;e->field_5A=8;e->field_5B=12;e->field_53=2;range=(unsigned short*)((unsigned char*)gDuelEffect_awEntryRangeBoundaries+offset);e->index_57=index;e->field_36=value;e->field_54=0;e->flags_34=flags;e->field_38=0;e->field_3A=0;e->field_59=0;e->field_61=0;e->range_start_5C=range[0];e->range_count_5E=range[1]-range[0];
#ifdef MEMORIES_PC
/* A new box: no digits of a number squeezed into the last one are left
   (func_80038148, number_width.h). */
NumberWidth_Reset(index);
CardTextColors_ResetChannel(e);
#endif
return e;}
