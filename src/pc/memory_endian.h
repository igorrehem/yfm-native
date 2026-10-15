#ifndef MEMORIES_MEMORY_ENDIAN_H
#define MEMORIES_MEMORY_ENDIAN_H
#include <stdint.h>

/* Shared byte access, independent of host alignment and endian order. */
static inline uint32_t Memories_LoadLE32(const uint8_t *bytes)
{
    return (uint32_t)bytes[0] | ((uint32_t)bytes[1] << 8) |
           ((uint32_t)bytes[2] << 16) | ((uint32_t)bytes[3] << 24);
}
static inline void Memories_StoreLE32(uint8_t *bytes, uint32_t value)
{
    bytes[0] = (uint8_t)value;
    bytes[1] = (uint8_t)(value >> 8);
    bytes[2] = (uint8_t)(value >> 16);
    bytes[3] = (uint8_t)(value >> 24);
}
#endif
