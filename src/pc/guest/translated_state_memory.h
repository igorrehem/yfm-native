#ifndef MEMORIES_TRANSLATED_STATE_MEMORY_H
#define MEMORIES_TRANSLATED_STATE_MEMORY_H
#include "state.h"
typedef struct MemoriesNativeMemoryState MemoriesNativeMemoryState;
int Memories_NativeMemorySave(MemoriesState *state);
MemoriesNativeMemoryState *Memories_NativeMemoryPrepare(MemoriesState *state, char *why, size_t size);
int Memories_NativeMemoryApply(MemoriesNativeMemoryState *pending);
void Memories_NativeMemoryRelocate(MemoriesNativeMemoryState *pending, void *data, size_t size,
                                  uintptr_t old_image, uintptr_t new_image, size_t image_size);
void Memories_NativeMemoryFree(MemoriesNativeMemoryState *pending);
void Memories_NativeMemoryRestorePayloads(MemoriesNativeMemoryState *pending,
                                         uintptr_t old_image, uintptr_t new_image, size_t image_size);
void Memories_NativeMemoryRemapGuests(MemoriesNativeMemoryState *pending, uint32_t from, uint32_t to, uint32_t size);
#endif
