#ifndef YUGIOH_PORT_PTR_H
#define YUGIOH_PORT_PTR_H

/* Guest-width pointer annotations for native 64-bit builds of this source.
 *
 * For the console and the matching-source checks the macros expand to
 * what they replace:
 * G32 to nothing, CALL32(type, f) to f and PSXLONG to long. The
 * preprocessed tokens, and therefore the objects, are unchanged.
 *
 * A native 64-bit port (MEMORIES_PC, clang for x86-64 or AArch64, built
 * with -fms-extensions) keeps the game's data at its retail addresses, so
 * structures and pinned globals must keep their 32-bit layout:
 *
 *   G32     follows the '*' of a pointer the game stores in memory: a
 *           structure or union member, or a global pinned to a retail
 *           address (`u8 *G32 data;`, `void (*G32 callback)(void);`).
 *           With a pointer typedef it follows the typedef name
 *           (`Callback G32 update;`). A local that walks such storage is
 *           `T *G32 *p`. It becomes clang's `__ptr32 __uptr`, a 4-byte
 *           pointer that is zero-extended on load. Pointers the game only
 *           holds in registers, locals and parameters stay plain.
 *   CALL32  wraps the callee of a call through a G32 function pointer:
 *           `CALL32(type, pointer)(args)`, where type is the plain function
 *           pointer type. LLVM cannot lower a call through a 32-bit
 *           pointer, so the port casts it to a native one first.
 *   PSXLONG spells the Psy-Q `long`, which is 32 bits on the console but
 *           64 bits on LP64 hosts (Linux, Android). It is `long` here and
 *           `int` in a native LP64 build.
 */

#if defined(MEMORIES_PC) && defined(__clang__) && \
    (defined(__x86_64__) || defined(__aarch64__))
#define G32 __ptr32 __uptr
#define CALL32(type, pointer) ((type)(pointer))
#else
#define G32
#define CALL32(type, pointer) pointer
#endif

/* MEMORIES_TRANSLATED selects the translated memory model, used in production
 * by macOS ARM64. Portable test harnesses may select it on other hosts.
 * TRANSLATED_G32 is G32 only in the translated build and empty on the
 * fixed-memory 64-bit ones (Windows x64, Android arm64). It fits only a
 * name some declaration in src/ initializes: the port's own table in native
 * .data, which the translated build shares with guest memory. Data of the
 * retail image (a pinned global, such as the text command table
 * D_80090F18), a member, or a local walking either, takes G32;
 * tools/project/check_g32.py rejects TRANSLATED_G32 there. */
#if defined(MEMORIES_TRANSLATED)
#define TRANSLATED_G32 G32
#else
#define TRANSLATED_G32
#endif

#if defined(MEMORIES_PC) && defined(__LP64__)
#define PSXLONG int
#else
#define PSXLONG long
#endif

/* Mach-O cannot express ELF section names. The translated backend places
 * guest globals through its address manifest, rather than host sections. */
#if defined(MEMORIES_TRANSLATED) && defined(__APPLE__)
#define PSX_SECTION(name)
#else
#define PSX_SECTION(name) __attribute__((section(name)))
#endif

/* Guest lists encode their terminator as a word, not an LP64 pointer. */
#ifdef MEMORIES_TRANSLATED
#define PSX_POINTER_END 0xFFFFFFFFu
#else
#define PSX_POINTER_END -1
#endif

#endif
