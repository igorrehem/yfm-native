#ifndef MEMORIES_PC_GUEST_STATE_H
#define MEMORIES_PC_GUEST_STATE_H
/* Save states. A state is taken and resumed at one kind of place only: a
 * VSync(0) call made from game code. What is stored there is
 *
 * - guest RAM and the scratchpad,
 * - the game objects' host variables (game_data/game_bss and each module's
 *   ovl_* sections),
 * - the game stack above the VSync call and the callee-saved registers the
 *   caller expects back,
 * - each native subsystem's state, as a tagged chunk it describes itself.
 *
 * States are meant to outlive a rebuild of the native side, which is the
 * common debugging loop (reach a stub, implement it, come back). For that the
 * build links every game object's code and variables at fixed addresses and
 * the game runs on a stack mapped at a fixed address, so return addresses and
 * pointers held in a state still mean the same thing. Nothing native is
 * stored by address. A state does not survive a change to game sources; the
 * header carries a fingerprint of the game code and a mismatch is reported.
 *
 * Words of game data that the linker relocated (pointers to native
 * functions, for instance) differ between builds. The file keeps the
 * startup image of that data beside the saved one, and a word still at its
 * startup value is taken from the running build instead. */
#include <stddef.h>
#include <stdint.h>

/* The game stack: the fixed range the game's own code runs on (state.c),
 * at one address on every system. 32-bit Windows loads system DLLs around
 * 0x70000000, and an Android app process has ART's boot image there; mods
 * use 0x90000000. */
#define MEMORIES_GAME_STACK_BASE 0xB0000000u
#define MEMORIES_GAME_STACK_SIZE 0x00800000u

typedef struct MemoriesState MemoriesState;
typedef struct MemoriesStateField {
    void *data;
    size_t size;
} MemoriesStateField;

/* Subsystems: save or load one chunk made of these fields, in order. When
 * loading, a missing chunk or one of another size (a layout that changed
 * since) is reported and left alone. Returns 1 if the fields were loaded. */
int Memories_StateChunk(MemoriesState *state, const char *tag, const MemoriesStateField *fields, size_t count);
int Memories_StateLoading(const MemoriesState *state);

/* Before restoring the game image, rebase pointers into a native allocation
 * recreated by a subsystem. Only the saved game memory, variables, stack
 * and entry registers are scanned; native chunks keep their own formats. */
void Memories_StateRemapRange(MemoriesState *state, uint32_t from, uint32_t to, uint32_t size);

/* Registers on entry to VSync, written by the assembly entry (state_i386.S,
 * state_x86_64.S, state_aarch64.S): what the game caller expects back. The
 * stack pointer as the caller left it (MEMORIES_STATE_ENTRY_SP), and where
 * VSync returns to (MEMORIES_STATE_ENTRY_CALLER): on x86 the word the stack
 * pointer points at, on AArch64 the link register. The layout is the
 * "entry" chunk of a state, and a state loads only in a build for the
 * system that saved it. */
#if defined(__x86_64__)
/* state_x86_64.S. The stack pointer keeps the i386 name, so the state code
 * reads one name on both. */
typedef struct MemoriesStateEntry {
    uint64_t rbx, rbp, rdi, rsi, r12, r13, r14, r15, esp; /* esp: rsp, at the return address */
    uint64_t xmm[20]; /* xmm6-xmm15, which Win64 keeps across a call too */
} MemoriesStateEntry;
#define MEMORIES_STATE_ENTRY_SP(entry) ((entry).esp)
#define MEMORIES_STATE_ENTRY_CALLER(entry) (*(const uint64_t *)(uintptr_t)(entry).esp)
#elif defined(__aarch64__)
/* state_aarch64.S. `esp` is SP as the caller left it, as on x86-64. */
typedef struct MemoriesStateEntry {
    uint64_t x19_x28[10];  /* offsets 0..72 */
    uint64_t x29, lr, esp; /* 80, 88, 96 */
    uint64_t d8_d15[8];    /* 104: the low halves of V8-V15 */
} MemoriesStateEntry;
#define MEMORIES_STATE_ENTRY_SP(entry) ((entry).esp)
#define MEMORIES_STATE_ENTRY_CALLER(entry) ((entry).lr)
#else
typedef struct MemoriesStateEntry {
    uint32_t ebx, esi, edi, ebp, esp; /* esp points at the return address */
} MemoriesStateEntry;
#define MEMORIES_STATE_ENTRY_SP(entry) ((entry).esp)
#define MEMORIES_STATE_ENTRY_CALLER(entry) (*(const uint32_t *)(uintptr_t)(entry).esp)
#endif
extern MemoriesStateEntry Memories_StateEntry;

/* main(): run `entry` on the fixed game stack. Does not return. */
int Memories_StateRunGame(int (*entry)(void));
/* function(argument) on the thread's own stack. Android's runtime refuses a
 * Java call (JNI) from a native stack it does not know, as the game stack
 * is: on Android arm64 a call made there runs below the suspended process
 * side of the game thread (the service context) instead. Anywhere else, or
 * off the game stack, a plain call. */
void Memories_OnHostStack(void (*function)(void *), void *argument);
#ifdef __ANDROID__
/* Android: before an SDL call that may reach Java (platform/jni_guard.h).
 * On the game stack it logs `name` once ("... which may call Java, ran on
 * the game stack") and counts it; elsewhere it does nothing. */
void Memories_JniGuard(const char *name);
/* How many such calls ran on the game stack since the start. */
unsigned Memories_JniGuardCount(void);
#ifdef __aarch64__
/* MEMORIES_TEST_HOST_STACK=1: the deepest use, in bytes, of the thread's
 * own stack below the switch point by Memories_OnHostStack's calls since
 * the first; 0 when not measuring. *painted is the span watched, and
 * *stack_size the thread's stack. */
size_t Memories_HostStackUsed(size_t *painted, size_t *stack_size);
#endif
#endif
/* VSync(0), after presenting: act on a pending save or load request. */
void Memories_StatePoint(unsigned presented_frames);
/* 1 save, 2 load; taken up at the next state point. Async-signal-safe. */
void Memories_StateRequest(int what, int slot);
/* The control channel (src/pc/debug/control.c), at the end of VSync(0):
 * save or load a state here. -2 when this VSync was called from native
 * code, where a state means nothing to another build; -1 when it failed
 * (a load's reason in `why`). A load that succeeds does not return: the
 * game resumes in the state's own VSync caller. */
int Memories_StateSaveHere(const char *path);
int Memories_StateLoadHere(const char *path, char *why, size_t why_size);
/* The boot's MEMORIES_LOAD_STATE has been acted on (from presented frame 30). */
int Memories_StateStartupDone(void);
/* The running build's id (the `buildid` file beside the executable). */
uint32_t Memories_StateBuildId(void);
/* Locate the running build's symbol table beside the executable. */
int Memories_SymbolTablePath(char *out, size_t size);
int Memories_LastStateSlot(void);

/* Each subsystem's chunk. */
void Spu_State(MemoriesState *state);
void LibSpu_State(MemoriesState *state);
void LibDs_State(MemoriesState *state);
void LibEtc_State(MemoriesState *state);
/* The rest of the VSync(0) a loaded state resumes in; its return value. */
int LibEtc_StateResumed(void);
void LibGpu_State(MemoriesState *state);
void LibGte_State(MemoriesState *state);
void LibPress_State(MemoriesState *state);
void LibMcrd_State(MemoriesState *state);
void SaveMenu_State(MemoriesState *state);
void DeckMenu_ShopState(MemoriesState *state);
void TitleJump_State(MemoriesState *state);
void Platform_State(MemoriesState *state);
#endif
