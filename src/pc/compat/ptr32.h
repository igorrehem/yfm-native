/* Force-included first into every unit of the 64-bit Windows build
 * (tools/pc/build_game32.py --target windows-x64).
 *
 * The game's stored pointers are clang's 4-byte `__ptr32 __uptr` there
 * (G32, src/port_ptr.h). mingw-w64's _mingw.h defines __ptr32 and __ptr64
 * as nothing, for MSVC-style code built by GCC, so a unit that reaches any
 * C library or Windows header after port_ptr.h would silently get 8-byte
 * members and the wrong layout for guest memory. _mingw.h has an include
 * guard: included once here and undone, it never defines them again. */
#ifndef MEMORIES_PC_COMPAT_PTR32_H
#define MEMORIES_PC_COMPAT_PTR32_H
#if defined(__MINGW32__) && defined(__x86_64__) && !defined(__ASSEMBLER__)
#include <_mingw.h>
#undef __ptr32
#undef __ptr64
/* Psy-Q's headers (src/psyq) typedef size_t as unsigned int unless _SIZE_T
 * is defined. The game calls the host C library's qsort and memcpy with it,
 * which take the host's 64-bit size_t, and a unit that sees both typedefs
 * does not compile. No guest record holds a size_t. */
#include <stddef.h>
#define _SIZE_T
#endif
#endif
