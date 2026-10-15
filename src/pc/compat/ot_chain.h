#ifndef MEMORIES_OT_CHAIN_H
#define MEMORIES_OT_CHAIN_H
#include <stdint.h>
#include <stddef.h>

typedef struct MemoriesOtChain {
    uint32_t first, last;
    unsigned nearest;
} MemoriesOtChain;

/* One packet-chain algorithm for fixed pointers and translated tokens. Only
 * word resolution varies. Constant resolver callbacks can inline at O2. */
static inline int Memories_FlattenOtChain(const uint32_t *tags, uint32_t base,
    unsigned count, uint32_t end, uint32_t *(*resolve)(uint32_t, void *),
    void *context, MemoriesOtChain *out)
{
    const uint32_t mask = 0xffffffu;
    unsigned hops = 0x20000u;
    uint32_t *last = NULL;
    MemoriesOtChain chain = {mask, 0, 0};
    if (!tags || !resolve || !out || !count || count > 0x4000u) return -1;
    for (unsigned i = count; i-- > 0;) {
        uint32_t link = tags[i] & mask;
        uint32_t stop = i ? (base + 4 * (i - 1)) & mask : end;
        while (link != stop) {
            uint32_t guest = 0x80000000u | link;
            uint32_t *packet;
            if (!hops--) return -2;
            packet = resolve(guest, context);
            if (!packet) return -1;
            if (last) *last = (*last & ~mask) | link;
            else chain.first = link;
            last = packet;
            chain.last = guest;
            chain.nearest = i;
            link = *packet & mask;
        }
    }
    *out = chain;
    return 0;
}
#endif
