/* Host memory the game is handed, below 4 GB (low_memory.h). Where the
 * game's pointers are native (a 32-bit build, a gcc test) these are malloc
 * and free and nothing here is compiled. */
#define _DEFAULT_SOURCE /* MAP_ANONYMOUS, MAP_FIXED_NOREPLACE */
#include "low_memory.h"
#ifdef MEMORIES_LOW_MEMORY
#include "pc/compat/mman.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/* First fit over a free list kept in address order, so that a freed block
 * joins its free neighbours. Every block starts with its header; sizes are
 * multiples of ALIGN and include it. The blocks are few and small (a glyph
 * of 30 bytes, a name, a unit of text), and the game frees almost none. */
#define ALIGN 16u
typedef struct Block {
    size_t size;
    struct Block *next; /* free blocks only */
} Block;
_Static_assert(sizeof(Block) <= ALIGN, "a block's header fits its alignment");

static Block *free_list;
static unsigned char *region; /* where the region is: MEMORIES_LOW_MEMORY_BASE, or the fallback below */
static int state; /* 0 not tried, 1 mapped, -1 not to be had */

/* Where the fixed address cannot be had, Linux x86-64 can still give 16 MiB
 * below 2 GB (MAP_32BIT): AddressSanitizer keeps its shadow over
 * 0x9E000000, so a test built with it gets the region there. The blocks
 * stay below 4 GB, which is all the game needs of them; only their fixed
 * place is lost (low_memory.h). The game itself holds the fixed range from
 * the start on Windows, where there is no such flag. */
static void *map_below_4gb(void)
{
#if defined(__linux__) && defined(__x86_64__) && defined(MAP_32BIT)
    void *got = mmap(NULL, MEMORIES_LOW_MEMORY_SIZE, PROT_READ | PROT_WRITE, MAP_32BIT | MAP_PRIVATE | MAP_ANONYMOUS,
                     -1, 0);
    if (got != MAP_FAILED && (uintptr_t)got + MEMORIES_LOW_MEMORY_SIZE <= 0x100000000ull) return got;
    if (got != MAP_FAILED) munmap(got, MEMORIES_LOW_MEMORY_SIZE);
#endif
    return NULL;
}

static int map(void)
{
    void *wanted = (void *)(uintptr_t)MEMORIES_LOW_MEMORY_BASE, *got;
    got = Memories_MapFixed(wanted, MEMORIES_LOW_MEMORY_SIZE, PROT_READ | PROT_WRITE,
                            MAP_FIXED_NOREPLACE | MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (got != wanted && (got = map_below_4gb()) != NULL) {
        fprintf(stderr, "memories-pc: the low memory region's address 0x%08x is taken; it is at %p instead\n",
                MEMORIES_LOW_MEMORY_BASE, got);
    } else if (got != wanted) {
        fprintf(stderr, "memories-pc: cannot map the low memory region at 0x%08x; host blocks the game would be "
                        "handed are refused\n", MEMORIES_LOW_MEMORY_BASE);
        return -1;
    }
    region = got;
    free_list = got;
    free_list->size = MEMORIES_LOW_MEMORY_SIZE;
    free_list->next = NULL;
    return 1;
}

void *Memories_LowAlloc(size_t size)
{
    Block **link, *block;
    size_t need;
    if (!state) state = map();
    if (state < 0 || size > MEMORIES_LOW_MEMORY_SIZE) return NULL;
    need = (size + ALIGN + ALIGN - 1) & ~(size_t)(ALIGN - 1);
    for (link = &free_list; (block = *link) != NULL; link = &block->next) {
        if (block->size < need) continue;
        if (block->size - need >= 2 * ALIGN) { /* the rest stays free, where the block was */
            Block *rest = (Block *)((unsigned char *)block + need);
            rest->size = block->size - need;
            rest->next = block->next;
            *link = rest;
            block->size = need;
        } else {
            *link = block->next;
        }
        return (unsigned char *)block + ALIGN;
    }
    {
        static int reported;
        if (!reported++) {
            fprintf(stderr, "memories-pc: the low memory region (%u MiB) is full\n",
                    MEMORIES_LOW_MEMORY_SIZE >> 20);
        }
    }
    return NULL;
}

/* A free the allocator cannot take, the region left as it is: each
 * different one is reported (the same pointer and reason again is not),
 * up to a limit, so a second bug is not hidden behind the first. */
static void refuse_free(const void *pointer, const char *why)
{
    static const void *last_pointer;
    static const char *last_why;
    static int reported;
    if (pointer == last_pointer && why == last_why) return;
    last_pointer = pointer;
    last_why = why;
    if (reported < 16) {
        fprintf(stderr, "memories-pc: Memories_LowFree(%p): %s; not freed%s\n", pointer, why,
                ++reported == 16 ? " (no more of these are reported)" : "");
    }
}

void Memories_LowFree(void *pointer)
{
    const unsigned char *base = region;
    Block *block, **link, *after;
    if (!pointer) return;
    if (state <= 0 || (const unsigned char *)pointer < base + ALIGN ||
        (const unsigned char *)pointer >= base + MEMORIES_LOW_MEMORY_SIZE ||
        ((uintptr_t)pointer - (uintptr_t)base) % ALIGN) {
        refuse_free(pointer, "not a block of the low memory region");
        return;
    }
    block = (Block *)((unsigned char *)pointer - ALIGN);
    for (link = &free_list; *link && *link < block; link = &(*link)->next) {
    }
    after = *link;
    /* Already free: it is a free block, or lies inside the free block
     * before it (merged into it when it was freed). */
    if (after == block) {
        refuse_free(pointer, "already free");
        return;
    }
    if (link != &free_list) {
        const Block *before = (const Block *)((unsigned char *)link - offsetof(Block, next));
        if ((const unsigned char *)before + before->size > (const unsigned char *)block) {
            refuse_free(pointer, "already free");
            return;
        }
    }
    block->next = after;
    *link = block;
    if (after && (unsigned char *)block + block->size == (unsigned char *)after) {
        block->size += after->size;
        block->next = after->next;
    }
    /* The free block before it, if it ends where this one starts. */
    if (link != &free_list) {
        Block *before = (Block *)((unsigned char *)link - offsetof(Block, next));
        if ((unsigned char *)before + before->size == (unsigned char *)block) {
            before->size += block->size;
            before->next = block->next;
        }
    }
}
#else
/* Nothing here: an empty file is not ISO C (-Wpedantic). */
typedef int memories_low_memory_unused;
#endif
