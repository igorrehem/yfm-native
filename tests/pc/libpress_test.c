/* Synthetic, ROM-free MDEC/IDCT regression. The stream is one 16x16
 * macroblock (Cr, Cb, then four Y blocks) with reproducible DC and AC data. */
#include "psyq/libpress.h"
#include "pc/guest/state.h"
#include <inttypes.h>
#include <stdio.h>
#include <string.h>

int Memories_StateChunk(MemoriesState *state, const char *tag,
                        const MemoriesStateField *fields, size_t count)
{
    (void)state;
    (void)tag;
    (void)fields;
    (void)count;
    return 0;
}

void Memories_MdecService(void);

#define CHECK(condition) do { \
    if (!(condition)) { \
        fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition); \
        return 1; \
    } \
} while (0)

typedef struct BitWriter {
    u16 *words;
    unsigned bit;
} BitWriter;

static void put_bits(BitWriter *writer, unsigned value, unsigned count)
{
    unsigned i;
    for (i = 0; i < count; i++) {
        unsigned shift = count - 1 - i;
        if ((value >> shift) & 1u) {
            writer->words[4 + writer->bit / 16] |= (u16)(1u << (15 - writer->bit % 16));
        }
        writer->bit++;
    }
}

static u32 lcg(u32 *state)
{
    *state = *state * 1664525u + 1013904223u;
    return *state;
}

static void make_stream(u32 *storage)
{
    u16 *header = (u16 *)storage;
    BitWriter writer = {header, 0};
    u32 seed = 0x4d444543u; /* "MDEC" */
    unsigned block;
    memset(storage, 0, 512 * sizeof(*storage));
    header[2] = 8; /* qscale */
    for (block = 0; block < 6; block++) {
        int dc = (int)(lcg(&seed) % 401u) - 200;
        unsigned coefficient;
        put_bits(&writer, (unsigned)dc & 0x3ffu, 10);
        for (coefficient = 0; coefficient < 14; coefficient++) {
            unsigned run = lcg(&seed) % 4u;
            int level = (int)(lcg(&seed) % 81u) - 40;
            /* MPEG escape: six-bit 000001, then run and signed ten-bit level. */
            put_bits(&writer, 1, 6);
            put_bits(&writer, (run << 10) | ((unsigned)level & 0x3ffu), 16);
        }
        put_bits(&writer, 2, 2); /* EOB */
    }
    put_bits(&writer, 0x1ff, 10); /* end of MDEC frame */
}

static int callback_count;

static void completed(void)
{
    callback_count++;
}

static u64 fnv1a(const u8 *bytes, size_t length)
{
    u64 hash = UINT64_C(14695981039346656037);
    size_t i;
    for (i = 0; i < length; i++) {
        hash ^= bytes[i];
        hash *= UINT64_C(1099511628211);
    }
    return hash;
}

static int decode(unsigned depth24, u64 *hash)
{
    u32 stream[512], vlc[1024];
    u8 pixels[16 * 16 * 3];
    size_t byte_count = depth24 ? 16 * 16 * 3 : 16 * 16 * 2;
    unsigned words = (unsigned)(byte_count / sizeof(u32));
    make_stream(stream);
    memset(vlc, 0, sizeof(vlc));
    memset(pixels, 0, sizeof(pixels));
    CHECK(DecDCTvlc2(stream, vlc, NULL) == 0);
    DecDCTin(vlc, (int)depth24);
    DecDCTout((u32 *)pixels, (int)words);
    callback_count = 0;
    CHECK(DecDCToutCallback(completed) == 0);
    Memories_MdecService();
    CHECK(callback_count == 1);
    *hash = fnv1a(pixels, byte_count);
    return 0;
}

int main(void)
{
    u64 rgb24, rgb15;
    CHECK(decode(1, &rgb24) == 0);
    CHECK(decode(0, &rgb15) == 0);
    printf("libpress: RGB24=%016" PRIx64 " RGB15=%016" PRIx64 "\n", rgb24, rgb15);
    /* ARM64 reference pixels, also verified unchanged by Linux i386. */
    CHECK(rgb24 == UINT64_C(0xee7e365dae3d77c7));
    CHECK(rgb15 == UINT64_C(0xbb4351aabef96ea9));
    return 0;
}
