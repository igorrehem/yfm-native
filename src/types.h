#ifndef YUGIOH_TYPES_H
#define YUGIOH_TYPES_H

#include "port_ptr.h"

typedef signed char s8;
typedef unsigned char u8;
typedef signed short s16;
typedef unsigned short u16;
typedef signed int s32;
typedef unsigned int u32;
#if defined(MEMORIES_PC) && defined(__i386__)
/* 32-bit x86 Linux aligns a 64-bit integer to 4 inside a structure; the
 * retail layout (MIPS) and 32-bit Windows align it to 8. This makes all three
 * agree, which the game's memory image and a mod built once for both systems
 * rely on (tools/pc/check_layouts.py). */
typedef signed long long s64 __attribute__((aligned(8)));
typedef unsigned long long u64 __attribute__((aligned(8)));
#else
typedef signed long long s64;
typedef unsigned long long u64;
#endif

/* A scratchpad address, written with its retail value (0x1F800000 to
 * 0x1F8003FF, the 1 KiB of data cache the game uses as fast RAM). The
 * console shows the same RAM at 0x9F800000 too (KSEG0), and that is where
 * the native port maps it: an Android app process has its Java heap at
 * 0x1F800000 (notes/pc-build.md, "Android"). For the console build the
 * macro is the literal itself, token for token, so the matching build is
 * unchanged. */
#ifdef MEMORIES_PC
#define SCRATCHPAD_ADDR(address) ((address) | 0x80000000u)
#else
#define SCRATCHPAD_ADDR(address) address
#endif

#endif
