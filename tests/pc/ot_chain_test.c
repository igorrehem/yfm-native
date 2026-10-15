#include "pc/compat/ot_chain.h"
#include <assert.h>
#include <stdio.h>

static uint32_t packets[2];
static uint32_t *resolve(uint32_t guest, void *context)
{
    assert(context == packets);
    if (guest == 0x80020000u) return &packets[0];
    if (guest == 0x80020010u) return &packets[1];
    return NULL;
}
int main(void)
{
    uint32_t tags[] = {0xffffffu, 0x10000u, 0x20000u, 0x20010u};
    MemoriesOtChain chain;
    packets[0] = 0x02010004u; packets[1] = 0x03010008u;
    assert(!Memories_FlattenOtChain(tags, 0x80010000u, 4, 0xffffffu, resolve, packets, &chain));
    assert(chain.first == 0x20010u && chain.last == 0x80020000u && chain.nearest == 2);
    assert(packets[1] == 0x03020000u && packets[0] == 0x02010004u);
    tags[2] = 0x10004u; tags[3] = 0x10008u;
    assert(!Memories_FlattenOtChain(tags, 0x80010000u, 4, 0xffffffu, resolve, packets, &chain));
    assert(chain.first == 0xffffffu && !chain.last && !chain.nearest);
    tags[3] = 0x20010u; packets[1] = 0x20010u;
    assert(Memories_FlattenOtChain(tags, 0x80010000u, 4, 0xffffffu, resolve, packets, &chain) == -2);
    tags[3] = 0x30000u;
    assert(Memories_FlattenOtChain(tags, 0x80010000u, 4, 0xffffffu, resolve, packets, &chain) == -1);
    assert(Memories_FlattenOtChain(tags, 0x80010000u, 0, 0xffffffu, resolve, packets, &chain) == -1);
    puts("Shared OT flattening: depth order, packet lengths, empty table and invalid chains passed");
    return 0;
}
