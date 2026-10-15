#ifndef MEMORIES_TRANSLATED_STATE_BACKEND_H
#define MEMORIES_TRANSLATED_STATE_BACKEND_H
#include "state.h"
#include <stdint.h>
int Memories_NativeStateStackRange(uintptr_t *low, uintptr_t *high);
int Memories_NativeStateRunGame(int (*entry)(void));
void Memories_NativeStatePoint(unsigned frames);
void Memories_NativeStateRequest(int what, int slot);
int Memories_NativeStateSave(const char *path);
int Memories_NativeStateLoad(const char *path, char *why, size_t size);
int Memories_NativeStateStartupDone(void);
int Memories_NativeStateLastSlot(void);
void Memories_NativeStateRemapRange(MemoriesState *state, uint32_t from, uint32_t to, uint32_t size);
void Memories_NativeStateRelocateField(const char *tag, void *data, size_t size);
#endif
