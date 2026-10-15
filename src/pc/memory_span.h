#ifndef MEMORIES_PC_MEMORY_SPAN_H
#define MEMORIES_PC_MEMORY_SPAN_H
#include "memory.h"

/* Checked RAM/scratchpad resolution for a known memory context.
 * Sharing this implementation lets the runtime inline its common path without
 * weakening alias, alignment or final-byte bounds checks. */
static inline void *Memories_ResolveSpan(MemoriesMemory *memory, uint32_t address,
                                        size_t length, size_t alignment)
{
    uint8_t *base;
    uint32_t physical;
    size_t offset, capacity;
    if (!memory || !alignment || alignment > 16 ||
        (alignment & (alignment - 1)) || (address & (alignment - 1))) {
        return NULL;
    }
    /* Accept physical, KSEG0 and KSEG1; reject mapped/privileged segments. */
    if (address < MEMORIES_GUEST_PHYSICAL_END) {
        physical = address;
    } else if (address >= MEMORIES_GUEST_RAM && address < MEMORIES_GUEST_DIRECT_END) {
        physical = address & MEMORIES_GUEST_PHYSICAL_MASK;
    } else {
        return NULL;
    }
    if (physical < MEMORIES_RAM_SIZE) {
        base = memory->ram;
        capacity = MEMORIES_RAM_SIZE;
        offset = physical;
    } else if (physical >= MEMORIES_GUEST_SCRATCHPAD_RETAIL && physical < (MEMORIES_GUEST_SCRATCHPAD_RETAIL + MEMORIES_SCRATCHPAD_SIZE) &&
               address < MEMORIES_GUEST_RAM_UNCACHED) {
        base = memory->scratchpad;
        capacity = MEMORIES_SCRATCHPAD_SIZE;
        offset = physical - MEMORIES_GUEST_SCRATCHPAD_RETAIL;
    } else {
        return NULL;
    }
    if (length > capacity - offset) {
        return NULL;
    }
    return base + offset;
}

#endif
