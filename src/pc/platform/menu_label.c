/* A menu button of words (menu_label.h). The frames' colors are the retail
 * entries' own, read off the title at the console's resolution
 * (2026-09-30): LOAD's dark rim, olive border (96, 96, 8), fill about
 * (40, 32, 32) and grey lines (128, 120, 120) five rows in; NEW GAME's red,
 * orange and red border (168, 16, 16 / 232, 136, 0), blue-white-blue lines
 * and green letters with white hearts. Both are 28 rows tall. */
#include "menu_label.h"
#include "paths.h"
#include "pc/cards/art.h"
#include "pc/compat/fs.h"
#include "pc/text/glyphs.h"
#include <ft2build.h>
#include FT_FREETYPE_H
#include <png.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { H = MENU_LABEL_HEIGHT, PAD = 14, MIN_WIDTH = 64, MAX_WIDTH = 240, TEXT_PX = 17 };
/* How many times the drawn size the PNG is made: MENU_LABEL_FACTOR, more
 * for a button drawn bigger (MenuLabel_Make's `factor`). */
static int F = MENU_LABEL_FACTOR;
/* Bumped when the drawing changes, so an old file is not used. */
enum { STYLE = 1 };

typedef struct { unsigned char r, g, b; } Color;

static void fill(unsigned char *rgba, int width, int x0, int y0, int x1, int y1, Color c)
{
    int x, y;
    for (y = y0 * F; y < y1 * F; y++) {
        for (x = x0 * F; x < x1 * F; x++) {
            unsigned char *p = rgba + ((size_t)y * width * F + x) * 4;
            p[0] = c.r;
            p[1] = c.g;
            p[2] = c.b;
            p[3] = 255;
        }
    }
}

/* The ink over what is there at coverage `cover`. */
static void blend(unsigned char *p, Color c, int cover)
{
    p[0] = (unsigned char)((p[0] * (255 - cover) + c.r * cover) / 255);
    p[1] = (unsigned char)((p[1] * (255 - cover) + c.g * cover) / 255);
    p[2] = (unsigned char)((p[2] * (255 - cover) + c.b * cover) / 255);
}

/* The words' coverage at F times the size, from the left edge, into
 * `cover` (`wide` across and H * F down; NULL only measures): their width
 * in pixels at F, or -1 without a serif face. */
/* The face the words are set in: the serif the card names are (Times),
 * else the port's own letters' (a system sans), else none. */
static FT_Face label_face(void)
{
    FT_Face face = (FT_Face)CardArt_SerifFace();
    return face ? face : (FT_Face)Glyphs_Face('A');
}

static int set_words(const char *text, unsigned char *cover, int wide)
{
    FT_Face face = label_face();
    int pen = 0, x, y, baseline = (H * F) / 2 + (TEXT_PX * F * 36) / 100;
    FT_UInt previous = 0;
    if (!face || FT_Set_Pixel_Sizes(face, 0, TEXT_PX * F)) return -1;
    while (*text) {
        FT_UInt index = FT_Get_Char_Index(face, (FT_ULong)Glyphs_NextCharacter(&text));
        FT_Bitmap *bitmap;
        if (!index) continue; /* a letter the face lacks is left out */
        if (previous && FT_HAS_KERNING(face)) {
            FT_Vector kern;
            if (!FT_Get_Kerning(face, previous, index, FT_KERNING_DEFAULT, &kern)) pen += (int)((kern.x + 32) >> 6);
        }
        previous = index;
        if (FT_Load_Glyph(face, index, FT_LOAD_RENDER | FT_LOAD_NO_HINTING | FT_LOAD_NO_BITMAP)) continue;
        bitmap = &face->glyph->bitmap;
        for (y = 0; cover && y < (int)bitmap->rows; y++) {
            int ty = baseline - face->glyph->bitmap_top + y;
            if (ty < 0 || ty >= H * F) continue;
            for (x = 0; x < (int)bitmap->width; x++) {
                int tx = pen + face->glyph->bitmap_left + x;
                unsigned char v = bitmap->buffer[y * bitmap->pitch + x];
                if (tx >= 0 && tx < wide && v > cover[(size_t)ty * wide + tx]) cover[(size_t)ty * wide + tx] = v;
            }
        }
        pen += (int)((face->glyph->advance.x + 32) >> 6);
    }
    return pen;
}

/* The words drawn centred into `cover`, `wide` pixels across. */
static void place_words(const char *text, unsigned char *cover, int wide, int words)
{
    unsigned char *line = calloc((size_t)wide * H * F, 1);
    int x, y, shift = (wide - words) / 2;
    if (!line) return;
    set_words(text, line, wide);
    for (y = 0; y < H * F; y++) {
        for (x = 0; x < wide; x++) {
            int from = x - shift;
            cover[(size_t)y * wide + x] = from >= 0 && from < wide ? line[(size_t)y * wide + from] : 0;
        }
    }
    free(line);
}

/* The most of `cover` within `r` pixels: a glow or an outline. */
static void spread(const unsigned char *cover, unsigned char *out, int wide, int high, int r)
{
    int x, y, dx, dy;
    for (y = 0; y < high; y++) {
        for (x = 0; x < wide; x++) {
            int most = 0;
            for (dy = -r; dy <= r; dy++) {
                for (dx = -r; dx <= r; dx++) {
                    int sx = x + dx, sy = y + dy;
                    if (sx < 0 || sy < 0 || sx >= wide || sy >= high || dx * dx + dy * dy > r * r) continue;
                    if (cover[(size_t)sy * wide + sx] > most) most = cover[(size_t)sy * wide + sx];
                }
            }
            out[(size_t)y * wide + x] = (unsigned char)most;
        }
    }
}

static void draw(const char *text, int selected, int width, int words, unsigned char *rgba)
{
    const Color rim = {16, 8, 16}, olive = {96, 96, 8}, body = {40, 32, 32}, grey_line = {128, 120, 120};
    const Color red = {168, 16, 16}, orange = {232, 136, 0}, dark = {40, 24, 24};
    const Color blue_a = {104, 96, 200}, white_line = {224, 224, 248}, blue_b = {48, 64, 184};
    const Color grey = {176, 176, 176}, shadow = {8, 0, 8}, green = {56, 144, 48}, heart = {224, 248, 216};
    int wide = width * F, high = H * F, i;
    unsigned char *cover = calloc((size_t)wide * high, 1), *around = calloc((size_t)wide * high, 1);
    if (!cover || !around) {
        free(cover);
        free(around);
        return;
    }
    if (selected) {
        fill(rgba, width, 0, 0, width, H, red);
        fill(rgba, width, 1, 1, width - 1, H - 1, orange);
        fill(rgba, width, 2, 2, width - 2, H - 2, red);
        fill(rgba, width, 3, 3, width - 3, H - 3, dark);
        fill(rgba, width, 5, 4, width - 5, 5, blue_a);
        fill(rgba, width, 5, 5, width - 5, 6, white_line);
        fill(rgba, width, 5, 6, width - 5, 7, blue_b);
        fill(rgba, width, 5, H - 7, width - 5, H - 6, blue_a);
        fill(rgba, width, 5, H - 6, width - 5, H - 5, white_line);
        fill(rgba, width, 5, H - 5, width - 5, H - 4, blue_b);
    } else {
        fill(rgba, width, 0, 0, width, H, rim);
        fill(rgba, width, 1, 1, width - 1, H - 1, olive);
        fill(rgba, width, 2, 2, width - 2, H - 2, body);
        fill(rgba, width, 6, 5, width - 6, 6, grey_line);
        fill(rgba, width, 6, H - 6, width - 6, H - 5, grey_line);
    }
    place_words(text, cover, wide, words);
    if (selected) {
        spread(cover, around, wide, high, F);
        for (i = 0; i < wide * high; i++) {
            blend(rgba + (size_t)i * 4, green, around[i]);
            blend(rgba + (size_t)i * 4, heart, cover[i] * 3 / 4);
        }
    } else {
        for (i = 0; i < wide * high; i++) {
            int x = i % wide, y = i / wide, sx = x - F, sy = y - F;
            if (sx >= 0 && sy >= 0) blend(rgba + (size_t)i * 4, shadow, cover[(size_t)sy * wide + sx]);
        }
        for (i = 0; i < wide * high; i++) blend(rgba + (size_t)i * 4, grey, cover[i]);
    }
    free(cover);
    free(around);
}

static uint32_t fnv(const char *text, uint32_t hash)
{
    for (; *text; text++) hash = (hash ^ (unsigned char)*text) * 16777619u;
    return hash;
}

int MenuLabel_Make(const char *text, int selected, int factor, char *path, size_t size, int *width, int *height,
                   char *why, size_t why_size)
{
    char relative[96], larger[16] = "";
    int words, w;
    unsigned char *rgba;
    png_image image;
    FILE *file;
    FT_Face face = label_face();
    /* Its width as at 100, whatever size it is made at: measured at
     * MENU_LABEL_FACTOR, then the words set again at `factor`. */
    F = MENU_LABEL_FACTOR;
    words = set_words(text, NULL, 0);
    /* No face at all: the frame alone, so the button is still there. */
    if (words < 0) {
        fprintf(stderr, "memories-pc: menu: no font for the label \"%s\"; its frame is drawn empty\n", text);
        words = 0;
    }
    w = words / F + 2 * PAD;
    if (factor > MENU_LABEL_FACTOR && words > 0) {
        F = factor;
        words = set_words(text, NULL, 0);
    }
    if (w < MIN_WIDTH) w = MIN_WIDTH;
    if (w > MAX_WIDTH) w = MAX_WIDTH;
    w = (w + 1) & ~1;
    *width = w;
    *height = H;
    /* Named by the words, the face and the style: another face (a serif
     * installed since) makes another file. */
    if (F != MENU_LABEL_FACTOR) snprintf(larger, sizeof(larger), "-x%d", F);
    snprintf(relative, sizeof(relative), "cache/menu-labels/%08x-%d-%d%s.png",
             (unsigned)fnv(text, fnv(face && face->family_name ? face->family_name : "-", 2166136261u + STYLE)),
             selected ? 1 : 0, w, larger);
    if (Paths_User(path, size, relative) != 0) {
        snprintf(why, why_size, "the user directory's path is too long");
        return 0;
    }
    file = fopen(path, "rb");
    if (file) {
        fclose(file);
        return 1;
    }
    rgba = calloc((size_t)w * F * H * F, 4);
    if (!rgba) {
        snprintf(why, why_size, "out of memory");
        return 0;
    }
    draw(words ? text : "", selected, w, words > w * F ? w * F : words, rgba);
    memset(&image, 0, sizeof(image));
    image.version = PNG_IMAGE_VERSION;
    image.width = (png_uint_32)(w * F);
    image.height = (png_uint_32)(H * F);
    image.format = PNG_FORMAT_RGBA;
    file = fopen(path, "wb");
    if (!file || !png_image_write_to_stdio(&image, file, 0, rgba, 0, NULL)) {
        snprintf(why, why_size, "cannot write %s", path);
        if (file) fclose(file);
        free(rgba);
        return 0;
    }
    fclose(file);
    free(rgba);
    return 1;
}
