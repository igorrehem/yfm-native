/* What tools/pc/build_mod.py force-includes first into every unit of a
 * 64-bit mod (--target x86_64-windows or aarch64), the mods' counterpart of
 * src/pc/compat/ptr32.h. Not for the 32-bit target, whose pointers are the
 * guest's width already.
 *
 * Psy-Q's headers (src/psyq) typedef size_t as unsigned int unless _SIZE_T
 * is defined, and the C library the host lends takes the host's 64-bit
 * size_t: the compiler's stddef.h comes first, and Psy-Q's is kept away.
 *
 * Then the gate: the game's own declarations of the guest tables mods reach
 * most, with their stored pointers 4 bytes wide (G32, src/port_ptr.h). A
 * mod that declares one of them itself without G32 would compile, read
 * 8-byte entries out of a table of 4-byte ones and fail at run time; with
 * these first it is a compile error ("redeclaration of 'D_800E9D90' with a
 * different type"). Include the header instead of declaring the table. The
 * three tables ordering_tables.h names with views (D_800E9D94, D_800E9D98,
 * D_800E9D9C) are its scalar ones here: index D_800E9D90 instead. */
#ifndef MEMORIES_PC_MODS_PRELUDE64_H
#define MEMORIES_PC_MODS_PRELUDE64_H
#include <stddef.h>
#define _SIZE_T
#include "game/ordering_tables.h"   /* D_800E9D90..D_800E9D9C: the frame's ordering tables */
#include "game/main_services.h"     /* D_800E9DB0: the frame service callbacks */
#endif
