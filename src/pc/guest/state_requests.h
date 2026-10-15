#ifndef MEMORIES_STATE_REQUESTS_H
#define MEMORIES_STATE_REQUESTS_H
/* Runtime-only bookkeeping. Mod SDK headers cannot use the host signal API. */
#ifndef MEMORIES_MOD
#include <signal.h>
#include <stddef.h>

/* Host bookkeeping stays outside the serialized game stack and payloads. */
typedef struct MemoriesStateRequests {
    volatile sig_atomic_t requested, slot;
    int startup_done, scripted_done, autosave_read;
    unsigned scripted_frame, autosave_every, autosave_frame, autosave_index;
    const char *scripted_path;
} MemoriesStateRequests;
#define MEMORIES_STATE_REQUESTS_INIT {.slot = 1}

typedef struct MemoriesStateActions {
    int (*save)(const char *path, int tell);
    void (*load)(const char *path, int slot);
} MemoriesStateActions;

void Memories_StateQueue(MemoriesStateRequests *requests, int what, int slot);
/* Called only after the backend has verified its own VSync boundary. A
 * successful load need not return; bookkeeping is advanced before callbacks. */
void Memories_StateProcess(MemoriesStateRequests *requests, unsigned frames,
                           const MemoriesStateActions *actions);
/* Recognize only positive, representable slotN.state basenames. */
int Memories_StateSlotFromPath(const char *path);
int Memories_StateSaveFailure(const char *path, int tell);
#endif /* !MEMORIES_MOD */
#endif
