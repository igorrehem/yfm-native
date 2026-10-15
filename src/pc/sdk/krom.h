#ifndef MEMORIES_PC_SDK_KROM_H
#define MEMORIES_PC_SDK_KROM_H

#include "port_ptr.h"

/* LIBAPI's kanji ROM lookups, defined in libapi_krom.c. That unit cannot
 * include psyq/libapi.h (its BIOS file calls clash with the host's libc and
 * Windows headers), so libetc.c, which does include it, includes this too:
 * a prototype here that disagreed with the game's would not compile there,
 * and the definitions must agree with this one. */
PSXLONG Krom2RawAdd(unsigned PSXLONG sjis);
PSXLONG Krom2RawAdd2(unsigned short sjis);

#endif
