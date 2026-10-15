#ifndef MEMORIES_PC_GUEST_SHA256_H
#define MEMORIES_PC_GUEST_SHA256_H
#include <stddef.h>
#include <stdint.h>

/* SHA-256 of `length` bytes (FIPS 180-4). No allocation and no library
 * calls, so it can run anywhere, including on guest memory. */
void Sha256(const void *data, size_t length, uint8_t digest[32]);

#endif
