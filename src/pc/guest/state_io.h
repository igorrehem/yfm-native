#ifndef MEMORIES_STATE_IO_H
#define MEMORIES_STATE_IO_H
#include "state.h"
#include <stdio.h>

struct MemoriesState {
    int loading;
    FILE *file;              /* saving to a file */
    const uint8_t *image;    /* loading: the whole file */
    size_t image_size;
};

/* Architecture-independent YFMSTATE tagged chunks. The first 16 bytes
 * belong to the header; both backends validate their version themselves. */
void Memories_StateWrite(MemoriesState *state, const void *data, size_t size);
const uint8_t *Memories_StateFindChunk(const MemoriesState *state, const char *tag, size_t *size);
/* Optional integrity footer for new backends; legacy files stay unchanged. */
int Memories_StateSeal(MemoriesState *state);
int Memories_StateIntegrity(const MemoriesState *state);
#endif
