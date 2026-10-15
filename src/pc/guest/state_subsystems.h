#ifndef MEMORIES_STATE_SUBSYSTEMS_H
#define MEMORIES_STATE_SUBSYSTEMS_H
#include "state.h"
void Memories_StateSubsystems(MemoriesState *state);
#if defined(_WIN32) && defined(__x86_64__) && !defined(MEMORIES_TRANSLATED)
void Memories_StateJumps(MemoriesState *state);
#endif
int Memories_StateCompatibleMods(MemoriesState *state);
int Memories_StateCompatibleLanguage(const MemoriesState *state, const char *path, char *why, size_t why_size);
#endif
