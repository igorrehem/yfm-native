#ifndef MEMORIES_GUEST_FUNCTION_MAP_H
#define MEMORIES_GUEST_FUNCTION_MAP_H
#include "image.h"

/* The generated function map is sorted by guest address. Several overlays
 * can share one address: check residency on every lookup, never cache a
 * target across a module switch. Preserve generated order for equal keys. */
static inline const MemoriesGuestFunction *Memories_FindResidentFunction(unsigned address)
{
    unsigned low = 0, high = Memories_FunctionMapCount;
    while (low < high) {
        unsigned middle = low + (high - low) / 2;
        if (Memories_FunctionMap[middle].guest < address) low = middle + 1;
        else high = middle;
    }
    for (; low < Memories_FunctionMapCount; ++low) {
        const MemoriesGuestFunction *entry = &Memories_FunctionMap[low];
        if (entry->guest != address) break;
        if (Memories_ModuleIsResident(entry->bank, entry->identifier)) return entry;
    }
    return NULL;
}
#endif
