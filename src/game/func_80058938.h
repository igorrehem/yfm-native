#ifndef MEMORIES_DECOMP_FUNC_80058938_H
#define MEMORIES_DECOMP_FUNC_80058938_H

#include "../types.h"
#include "model.h"

/* Queues a tint ramp for one model slot. `part_mask` selects the model parts
   affected by the request; Model_QueueTintRequestForParts builds it from
   variadic part indices and func_80059AF8 passes 0 for every part. */
void Model_QueueTintRequest(
    s32 slot, s32 selection, ModelTintColor start, ModelTintColor end,
    s32 duration, const u8 *part_mask);
void Model_QueueTintRequestForParts(
    s32 slot, s32 part, ModelTintColor start, ModelTintColor end,
    s32 duration, ...);

/* Compatibility symbols for callers outside the matching C surface. */
void func_80058838(
    s32 slot, s32 part, ModelTintColor start, ModelTintColor end,
    s32 duration, ...);
void func_80058938(
    s32 slot, s32 selection, ModelTintColor start, ModelTintColor end,
    s32 duration, const u8 *part_mask);

#ifdef MEMORIES_PC
/* Model_QueueTintRequestForParts with its part list (ending at the first
   negative word) passed as a pointer and each color as the word a MIPS
   register carries it in: how the interpreter (src/pc/guest/mips.c, which
   cannot include the game's types) bridges the MODEL.MRG modules' calls,
   whose lists outrun the argument words it forwards. */
void Model_QueueTintRequestForPartList(
    s32 slot, s32 part, u32 start, u32 end, s32 duration, const s32 *parts);
#endif

#endif
