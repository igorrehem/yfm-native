/* Compare bulk clears with VRAM's cell-by-cell wrapping contract, on native
 * 32/64-bit hosts without the translated runtime. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "pc/render/texture_dump.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

#define WORDS (SOFT_GPU_WIDTH * SOFT_GPU_HEIGHT)
static uint32_t tags[WORDS + 2];
static uint16_t shadow[WORDS * 4 + 2];
static unsigned char cleared[WORDS];
static int forget_calls, expected_x, expected_y, expected_w, expected_h;

const uint16_t *SoftGpu_Vram(void) { return NULL; }

static void forget(int x, int y, int w, int h)
{
    assert(x == expected_x && y == expected_y);
    assert(w == expected_w && h == expected_h);
    forget_calls++;
}

static void check_clear(int x, int y, int w, int h, int with_shadow)
{
    size_t i;
    TextureDump_Tags = tags + 1;
    TextureDump_Shadow = with_shadow ? shadow + 1 : NULL;
    for (i = 0; i < WORDS + 2; i++) tags[i] = 11;
    for (i = 0; i < WORDS * 4 + 2; i++) shadow[i] = 17;
    memset(cleared, 0, sizeof(cleared));
    for (int row = 0; row < h; row++) {
        for (int column = 0; column < w; column++) {
            unsigned cx = (unsigned)(x + column) % SOFT_GPU_WIDTH;
            unsigned cy = (unsigned)(y + row) % SOFT_GPU_HEIGHT;
            cleared[cy * SOFT_GPU_WIDTH + cx] = 1;
        }
    }
    expected_x = x; expected_y = y; expected_w = w; expected_h = h;
    forget_calls = 0;
    TextureDump_Cleared(x, y, w, h);
    assert(forget_calls == 1);
    assert(tags[0] == 11 && tags[WORDS + 1] == 11);
    assert(shadow[0] == 17 && shadow[WORDS * 4 + 1] == 17);
    for (i = 0; i < WORDS; i++) {
        assert(tags[i + 1] == (cleared[i] ? 0u : 11u));
        for (size_t sub = 0; sub < 4; sub++)
            assert(shadow[1 + i * 4 + sub] ==
                   (with_shadow && cleared[i] ? 0 : 17));
    }
}

int main(void)
{
    TextureDump_Forget = forget;
    for (int with_shadow = 0; with_shadow <= 1; with_shadow++) {
        check_clear(20, 30, 8, 8, with_shadow);
        check_clear(SOFT_GPU_WIDTH - 2, SOFT_GPU_HEIGHT - 1, 4, 2, with_shadow);
        check_clear(-3, -2, 7, 5, with_shadow);
        check_clear(9, 11, SOFT_GPU_WIDTH * 2 + 3, 2, with_shadow);
        check_clear(0, 0, 3, SOFT_GPU_HEIGHT + 2, with_shadow);
        check_clear(0, 0, SOFT_GPU_WIDTH, SOFT_GPU_HEIGHT, with_shadow);
        check_clear(0, 0, 0, 2, with_shadow);
        check_clear(0, 0, 2, 0, with_shadow);
    }
    TextureDump_Tags = NULL;
    forget_calls = 0;
    TextureDump_Cleared(0, 0, 1, 1);
    assert(forget_calls == 0);
    puts("Texture clears: native wrapping, shadow, adjacent cells and callback contract agree");
    return 0;
}
