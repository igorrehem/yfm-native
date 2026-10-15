/* Custom monster type icons (src/pc/cards/type_icons.c): a successful load's
 * slot math, a missing or corrupt PNG's diagnostic and cached failure, a
 * lost HD registration's diagnostic (the console-resolution icon still
 * works), and the mark/cell round trip func_80037DA4 and func_80035E20 use
 * to find a type's icon from an entry's otherwise-unused code. */
#include <assert.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/* type_icons.c's own fprintf(stderr, ...) calls, captured without touching
 * the real stream: portable (no platform-specific stderr redirection) and
 * confined to this translation unit. */
static char logged[512];
static int test_fprintf(FILE *stream, const char *format, ...)
{
    va_list args;
    (void)stream;
    va_start(args, format);
    vsnprintf(logged, sizeof(logged), format, args);
    va_end(args);
    return 0;
}
#define fprintf test_fprintf

#include "../../src/pc/cards/type_icons.c"

/* --- stand-ins for type_icons.c's other dependencies -------------------- */

static const char *icon_paths[256];
const char *Cards_TypeIcon(int type)
{
    return type >= 0 && type < 256 ? icon_paths[type] : NULL;
}

static int art_calls, art_fail;
static const char *art_why = "the PNG is not one it could read";
int CardArt_IconFromImage(const char *path, const unsigned short *palette, unsigned char *pixels,
                          unsigned short *clut, char *why, size_t why_size)
{
    int i;
    (void)path;
    (void)palette;
    art_calls++;
    if (art_fail) {
        snprintf(why, why_size, "%s", art_why);
        return 0;
    }
    memset(pixels, 0x11, (size_t)CARD_ICON_SIDE * CARD_ICON_SIDE / 2);
    for (i = 0; i < 16; i++) clut[i] = (unsigned short)(0x8000 | i);
    return 1;
}

/* Rows enough for the bank's palette strip (CLUT_Y 256) plus the highest
 * slot's pixels (type 255 is slot 231, row (231>>4)*16+15 = 239): 512 rows
 * is ample for every id these tests use. */
static uint16_t bank[512 * SOFT_GPU_WIDTH];
static int bank_unavailable;
uint16_t *SoftGpu_Bank(int which)
{
    (void)which;
    return bank_unavailable ? NULL : bank;
}

static int sprite_calls, sprite_fail;
void TexturePack_BankSpritesUseOwner(unsigned owner) { (void)owner; }
void TexturePack_BankSpritesClear(unsigned owner) { (void)owner; }
int TexturePack_AddBankSprite(int bank_, int page_x, int page_y, int depth, int clut_x, int clut_y, int u, int v,
                              int w, int h, const char *file)
{
    (void)bank_;
    (void)page_x;
    (void)page_y;
    (void)depth;
    (void)clut_x;
    (void)clut_y;
    (void)u;
    (void)v;
    (void)w;
    (void)h;
    (void)file;
    sprite_calls++;
    return !sprite_fail;
}

static void reset(void)
{
    memset(made, 0, sizeof(made));
    memset(hd_made, 0, sizeof(hd_made));
    memset(hd_tried, 0, sizeof(hd_tried));
    memset(failed_at, 0, sizeof(failed_at));
    memset(hd_failed_at, 0, sizeof(hd_failed_at));
    retry_clock = 0;
    pending = 0;
    memset(bank, 0, sizeof(bank));
    memset(icon_paths, 0, sizeof(icon_paths));
    art_calls = sprite_calls = 0;
    art_fail = sprite_fail = bank_unavailable = 0;
    logged[0] = 0;
}

/* A valid icon, 24-255: slot math, the (u, v) it lands at, and that
 * different ids never collide. */
static void loaded_cells(void)
{
    static const int ids[] = {24, 31, 32, 127, 255};
    static char paths[sizeof(ids) / sizeof(ids[0])][32];
    int seen_u[sizeof(ids) / sizeof(ids[0])], seen_v[sizeof(ids) / sizeof(ids[0])];
    size_t i, j;
    reset();
    for (i = 0; i < sizeof(ids) / sizeof(ids[0]); i++) {
        int tpage, u, v, clut;
        snprintf(paths[i], sizeof(paths[i]), "icons/%d.png", ids[i]);
        icon_paths[ids[i]] = paths[i];
        assert(TypeIcons_Cell(ids[i], &tpage, &u, &v, &clut));
        assert(tpage == (PAGE | (BANK << 11)));
        assert(u >= 0 && u < 256 && v >= 0 && v < 256);
        assert((clut >> 6) >= CLUT_Y);
        /* duel_ui.c's palettes fill rows 480-511 at x 0-255: no type's
         * palette row reaches them (types 248-255 take a second column). */
        assert((clut >> 6) < 480);
        assert(ids[i] < 248 ? (clut & 0x3F) == CLUT_X >> 4 : (clut & 0x3F) == (CLUT_X + 16) >> 4);
        if (!i) {
            /* Type cells deliberately occupy bank 14's free page at word
             * 64, not bank 13's card-layout frame area or the star cells
             * at word 0.  Their palettes use the matching free x column. */
            assert(bank[0] == 0);
            assert(bank[PAGE * 64] == 0x1111);
            assert(bank[CLUT_Y * SOFT_GPU_WIDTH + CLUT_X] == 0x8000);
        }
        seen_u[i] = u;
        seen_v[i] = v;
        /* The same id again: no re-decode (made[] already 1), same cell. */
        {
            int tpage2, u2, v2, clut2;
            assert(TypeIcons_Cell(ids[i], &tpage2, &u2, &v2, &clut2));
            assert(tpage2 == tpage && u2 == u && v2 == v && clut2 == clut);
        }
    }
    assert(art_calls == (int)(sizeof(ids) / sizeof(ids[0]))); /* decoded once per id */
    for (i = 0; i < sizeof(ids) / sizeof(ids[0]); i++)
        for (j = i + 1; j < sizeof(ids) / sizeof(ids[0]); j++)
            assert(seen_u[i] != seen_u[j] || seen_v[i] != seen_v[j]);
}

/* No "icon" (Cards_TypeIcon NULL), the last retail type (23), a retail
 * type with a path anyway, and one past CARD_TYPE_LIMIT: all decline
 * without touching the decoder, and without crashing. */
static void bounds_and_no_icon(void)
{
    int tpage, u, v, clut;
    reset();
    assert(!TypeIcons_Cell(24, &tpage, &u, &v, &clut)); /* icon_paths[24] still NULL */
    assert(art_calls == 0);
    icon_paths[23] = "icons/equip.png";
    assert(!TypeIcons_Cell(23, &tpage, &u, &v, &clut)); /* a retail id: never a custom icon */
    icon_paths[0] = "icons/dragon.png";
    assert(!TypeIcons_Cell(0, &tpage, &u, &v, &clut));
    assert(!TypeIcons_Cell(256, &tpage, &u, &v, &clut)); /* past CARD_TYPE_LIMIT */
    assert(art_calls == 0);
}

/* A missing or corrupt PNG is throttled rather than decoded and logged on
 * every frame.  A type-bank rebuild drops the cooldown so a newly supplied
 * replacement is available immediately. */
static void failed_decode_retries_after_clear(void)
{
    int tpage, u, v, clut;
    reset();
    icon_paths[24] = "icons/missing.png";
    art_fail = 1;
    art_why = "icons/missing.png is not a PNG it could read";
    assert(!TypeIcons_Cell(24, &tpage, &u, &v, &clut));
    assert(strstr(logged, "type 24") && strstr(logged, "missing.png"));
    assert(art_calls == 1);
    /* Asked again: the cooldown suppresses a second decode and log. */
    logged[0] = 0;
    assert(!TypeIcons_Cell(24, &tpage, &u, &v, &clut));
    assert(art_calls == 1);
    assert(!logged[0]); /* the failure is not re-logged every call */
    art_fail = 0;
    TypeIcons_Clear();
    assert(TypeIcons_Cell(24, &tpage, &u, &v, &clut));
    assert(art_calls == 2);
}

/* The software-GPU bank itself unavailable (not yet started, or the
 * software renderer is off): declines rather than decoding into nothing,
 * and leaves made[] alone to retry once the bank exists. */
static void bank_missing(void)
{
    int tpage, u, v, clut;
    reset();
    icon_paths[24] = "icons/cyberse.png";
    bank_unavailable = 1;
    assert(!TypeIcons_Cell(24, &tpage, &u, &v, &clut));
    assert(art_calls == 0 && made[24] == 0);
    bank_unavailable = 0;
    assert(TypeIcons_Cell(24, &tpage, &u, &v, &clut));
    assert(art_calls == 1);
}

/* A texture-pack HD registration failure: the console-resolution icon
 * (made[] 1, TypeIcons_Cell still succeeds) is unaffected, but it is
 * reported, where silently dropping it would leave an HD pack's player
 * with no sign why the icon never sharpens. */
static void hd_registration_failure_retries_after_clear(void)
{
    int tpage, u, v, clut;
    reset();
    icon_paths[24] = "icons/cyberse.png";
    sprite_fail = 1;
    assert(TypeIcons_Cell(24, &tpage, &u, &v, &clut));
    assert(sprite_calls == 1);
    assert(strstr(logged, "type 24"));
    logged[0] = 0;
    assert(TypeIcons_Cell(24, &tpage, &u, &v, &clut));
    assert(sprite_calls == 1 && !logged[0]);
    sprite_fail = 0;
    TypeIcons_Clear();
    assert(TypeIcons_Cell(24, &tpage, &u, &v, &clut));
    assert(sprite_calls == 2);
}

/* The mark a drawing entry carries (func_80037DA4's TypeIcons_MarkIcon,
 * taken once by DuelEffect_AppendEntry) decodes back to the exact cell
 * TypeIcons_Cell gives that id directly, for the lowest and highest custom
 * ids; a type with no icon, or a retail type, never marks, and the mark
 * is one-shot. */
static void mark_and_cell_round_trip(void)
{
    int tpage, u, v, clut, tpage2, u2, v2, cx2, cy2;
    unsigned code;
    reset();
    icon_paths[24] = "icons/first.png";
    icon_paths[255] = "icons/last.png";

    assert(TypeIcons_Cell(24, &tpage, &u, &v, &clut));
    TypeIcons_MarkIcon(24);
    code = TypeIcons_TakeIconMark();
    assert(code != 0);
    assert(TypeIcons_IconCell(code, &tpage2, &u2, &v2, &cx2, &cy2));
    assert(tpage2 == tpage && u2 == u && v2 == v && cy2 == clut >> 6);

    assert(TypeIcons_Cell(255, &tpage, &u, &v, &clut));
    TypeIcons_MarkIcon(255);
    code = TypeIcons_TakeIconMark();
    assert(code != 0);
    assert(TypeIcons_IconCell(code, &tpage2, &u2, &v2, &cx2, &cy2));
    assert(tpage2 == tpage && u2 == u && v2 == v && cy2 == clut >> 6);

    /* Taking it again (the mark is one-shot) finds nothing. */
    assert(TypeIcons_TakeIconMark() == 0);
    /* A custom type with no icon of its own: marking it leaves no mark, so
     * the drawing keeps the Dragon-compatibility sprite already set up. */
    TypeIcons_MarkIcon(30); /* icon_paths[30] is NULL */
    assert(TypeIcons_TakeIconMark() == 0);
    /* A retail type is never marked, whatever its own icon path. */
    TypeIcons_MarkIcon(0);
    assert(TypeIcons_TakeIconMark() == 0);
    /* A code from nowhere (ordinary glyph text, or a guardian star's own
     * mark, STARS_ICON_CODE | 10): not a type's cell. */
    assert(!TypeIcons_IconCell(0, &tpage2, &u2, &v2, &cx2, &cy2));
    assert(!TypeIcons_IconCell(0xE50Au, &tpage2, &u2, &v2, &cx2, &cy2));
}

/* TypeIcons_Clear (a mod rescan) drops a mark left pending, the same as it
 * drops made[]'s cache: a rebuild mid-mark never leaks a code into the
 * entry that follows it. */
static void clear_drops_pending_mark(void)
{
    reset();
    icon_paths[24] = "icons/cyberse.png";
    TypeIcons_MarkIcon(24);
    TypeIcons_Clear();
    assert(TypeIcons_TakeIconMark() == 0);
}

int main(void)
{
    loaded_cells();
    bounds_and_no_icon();
    failed_decode_retries_after_clear();
    bank_missing();
    hd_registration_failure_retries_after_clear();
    mark_and_cell_round_trip();
    clear_drops_pending_mark();
    return 0;
}
