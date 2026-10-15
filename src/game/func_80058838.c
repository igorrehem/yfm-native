#include "../types.h"
#include "func_80058938.h"
#include "model.h"

#ifdef MEMORIES_PC
#include "../psyq/stdarg.h"

/* The part list ends at the first negative word. The console walks it up its
 * own stack from &a4, which on the PC holds only what the host call pushed:
 * the MODEL.MRG variant modules (run by src/pc/guest/mips.c) pass up to 18
 * parts, and the bridge forwards twelve argument words, so the walk ran off
 * the end after the seventh part. Here a native caller's list is read with
 * va_arg and the interpreter's straight from the guest stack, through
 * Model_QueueTintRequestForPartList. A part past the eight-byte mask (64 and
 * up, which no constant list in MODEL.MRG has) would write outside it and
 * is left out. */
static void mark_part(u8 *bits, s32 value)
{
    if (value < 64)
        bits[value >> 3] |= 1 << (value & 7);
}

void Model_QueueTintRequestForPartList(
    s32 a0, s32 a1, u32 start, u32 end, s32 a4, const s32 *parts)
{
    ModelTintColor a2;
    ModelTintColor a3;
    u8 bits[8] = {0};

    a2.b0 = start; a2.b1 = start >> 8; a2.b2 = start >> 16; a2.b3 = start >> 24;
    a3.b0 = end; a3.b1 = end >> 8; a3.b2 = end >> 16; a3.b3 = end >> 24;
    while (*parts >= 0)
        mark_part(bits, *parts++);
    a2.b3 = a1 & 127;
    Model_QueueTintRequest(a0, a1 & 128, a2, a3, a4, bits);
}

void Model_QueueTintRequestForParts(
    s32 a0, s32 a1, ModelTintColor a2, ModelTintColor a3, s32 a4, ...)
{
    u8 bits[8] = {0};
    va_list parts;
    s32 value;

    va_start(parts, a4);
    while ((value = va_arg(parts, s32)) >= 0)
        mark_part(bits, value);
    va_end(parts);
    a2.b3 = a1 & 127;
    Model_QueueTintRequest(a0, a1 & 128, a2, a3, a4, bits);
}
#else
void Model_QueueTintRequestForParts(
    s32 a0, s32 a1, ModelTintColor a2, ModelTintColor a3, s32 a4, ...)
{
    u8 bits[8];
    u8 *arguments;
    s32 value;
    s32 byte_index;
    s32 i;
    u8 *cursor;

    i = 7;
    cursor = bits + 7;
    for (; i >= 0; i--)
        *cursor-- = 0;
    arguments = (u8 *)&a4 + 4;
    while (1) {
        arguments += 4;
        value = *(s32 *)(arguments - 4);
        if (value < 0)
            break;
        byte_index = value >> 3;
        bits[byte_index] |= 1 << (value - byte_index * 8);
    }
    a2.b3 = a1 & 127;
    Model_QueueTintRequest(a0, a1 & 128, a2, a3, a4, bits);
}
#endif
