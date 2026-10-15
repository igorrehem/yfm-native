/* Shared save-state container; stack/register payloads belong to each ABI. */
#include "state_io.h"
#include <errno.h>
#include <string.h>
#ifdef MEMORIES_TRANSLATED
#include "translated_runtime.h"
#include "translated_state_backend.h"
#endif

int Memories_StateLoading(const MemoriesState *state) { return state && state->loading; }

static uint64_t hash_bytes(uint64_t hash, const uint8_t *bytes, size_t size)
{
    for (size_t i = 0; i < size; ++i) { hash ^= bytes[i]; hash *= 1099511628211ull; }
    return hash;
}
int Memories_StateSeal(MemoriesState *state)
{
    uint8_t buffer[8192];
    uint64_t hash = 14695981039346656037ull;
    size_t count;
    MemoriesStateField field = {&hash, sizeof(hash)};
    if (!state || !state->file || fflush(state->file) || fseek(state->file, 0, SEEK_SET)) return -1;
    while ((count = fread(buffer, 1, sizeof(buffer), state->file))) hash = hash_bytes(hash, buffer, count);
    if (ferror(state->file) || fseek(state->file, 0, SEEK_END)) return -1;
    Memories_StateChunk(state, "state-integrity", &field, 1);
    return ferror(state->file) ? -1 : 0;
}
int Memories_StateIntegrity(const MemoriesState *state)
{
    static const char tag[16] = "state-integrity";
    uint64_t saved;
    uint32_t length;
    size_t at;
    if (!state || !state->image || state->image_size < 44) return 0;
    at = state->image_size - 28;
    if (memcmp(state->image + at, tag, sizeof(tag))) return 0;
    memcpy(&length, state->image + at + 16, sizeof(length));
    memcpy(&saved, state->image + at + 20, sizeof(saved));
    return length == sizeof(saved) && saved == hash_bytes(14695981039346656037ull, state->image, at);
}

void Memories_StateWrite(MemoriesState *state, const void *data, size_t size)
{
    if (size) {
#ifdef MEMORIES_TRANSLATED
        data = GuestRuntime_ResolveData((void *)data, size);
#endif
        fwrite(data, 1, size, state->file);
    }
}

/* Chunk: 16-byte tag, 32-bit size, payload. */
const uint8_t *Memories_StateFindChunk(const MemoriesState *state, const char *tag, size_t *size)
{
    size_t at = 16;
    if (!state || !tag || !size || !state->image || state->image_size < at) return NULL;
    char padded[16];
    size_t tag_length = 0;
    while (tag_length < sizeof(padded) - 1 && tag[tag_length] != '\0') {
        ++tag_length;
    }
    memset(padded, 0, sizeof(padded));
    memcpy(padded, tag, tag_length);
    while (at <= state->image_size && state->image_size - at >= 20) {
        uint32_t length;
        memcpy(&length, state->image + at + 16, 4);
        if (length > state->image_size - at - 20) {
            return NULL;
        }
        if (!memcmp(state->image + at, padded, 16)) {
            *size = length;
            return state->image + at + 20;
        }
        at += 20 + length;
    }
    return NULL;
}

int Memories_StateChunk(MemoriesState *state, const char *tag, const MemoriesStateField *fields, size_t count)
{
    size_t total = 0, i, size;
    const uint8_t *from;
    if (!state || !tag || (count && !fields)) { errno = EINVAL; return 0; }
    for (i = 0; i < count; i++) {
        if ((fields[i].size && !fields[i].data) || fields[i].size > UINT32_MAX - total) {
            errno = EINVAL;
            return 0;
        }
        total += fields[i].size;
    }
    if (!state->loading && !state->file) { errno = EINVAL; return 0; }
    if (!state->loading) {
        char padded[16];
        size_t tag_length = 0;
        while (tag_length < sizeof(padded) - 1 && tag[tag_length] != '\0') {
            ++tag_length;
        }
        uint32_t length = (uint32_t)total;
        memset(padded, 0, sizeof(padded));
        memcpy(padded, tag, tag_length);
        Memories_StateWrite(state, padded, 16);
        Memories_StateWrite(state, &length, 4);
        for (i = 0; i < count; i++) {
            Memories_StateWrite(state, fields[i].data, fields[i].size);
        }
        return 0;
    }
    from = Memories_StateFindChunk(state, tag, &size);
    if (!from) {
        fprintf(stderr, "memories-pc: state: no chunk '%s' (%lu bytes in this build); that part keeps its current state\n",
                tag, (unsigned long)total);
        return 0;
    }
    if (size != total) {
        fprintf(stderr, "memories-pc: state: layout changed for '%s' (%lu bytes in the state, %lu in this build); that part keeps its current state\n",
                tag, (unsigned long)size, (unsigned long)total);
        return 0;
    }
    for (i = 0; i < count; i++) {
        if (fields[i].size) {
            memcpy(fields[i].data, from, fields[i].size);
#ifdef MEMORIES_TRANSLATED
            Memories_NativeStateRelocateField(tag, GuestRuntime_ResolveData(fields[i].data, fields[i].size), fields[i].size);
#endif
        }
        from += fields[i].size;
    }
    return 1;
}
