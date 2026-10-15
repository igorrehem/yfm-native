/* View > Duel rank's pictures off the disc (rank_art.h). Where each comes
 * from is what the game's own code gives: the packages' loaders place the
 * images and palettes, and the result screen's sprite sheets (its display
 * resource) say which texels, page and palette each piece is. */
#include "rank_art.h"
#include "game/file_constants.h"
#include "game/duel_package.h"
#include <stdio.h>
#include <string.h>

/* The result screen's package, WA sectors 0x1DAB-0x1DCC, as func_80020BE4
 * takes it: 32 sectors of image from VRAM 0, 256; one of palette, a
 * 256 x 4 LoadImage at 0, 248; one of display resource (D_801AF000). */
enum {
    RESULTS_IMAGE_SECTORS = 32, RESULTS_IMAGE_X = 0, RESULTS_IMAGE_Y = 0x100,
    RESULTS_PALETTE_SECTOR = FILE_WA_DUEL_RESULTS_START_SECTOR + RESULTS_IMAGE_SECTORS,
    RESULTS_PALETTE_X = 0, RESULTS_PALETTE_Y = 0xF8, RESULTS_PALETTE_W = 0x100, RESULTS_PALETTE_H = 4,
    RESULTS_RESOURCE_SECTOR = RESULTS_PALETTE_SECTOR + 1, RESOURCE_BYTES = FILE_SECTOR_SIZE
};
/* func_800218F0's two result objects: resource indices 0, 5, is_tec_rank
 * (the badge and plate) and 0, 6, rank_tier (the letter), color word 16
 * (page 16, u and v 0) and texture 8 (palette 0, 248), with flag 0x20, which
 * adds the sheet's own palette step. */
enum { RECORD_BADGE = 5, RECORD_LETTER = 6, OBJECT_PAGE = 16, OBJECT_CLUT_X = 0, OBJECT_CLUT_Y = 0xF8 };
/* Duel_LoadPackageStage, stages 0-2 of a terrain package (all seven hold
 * the same here): 64 sectors of image from 0x300, 0x100, then four of
 * palette as a 256 x 16 LoadImage at 0x100, 0xF0. Duel_DrawCardFrame draws
 * a card's ATK/DEF digits from page 0x1E, v 0x58, u 8 a digit, 8 x 8 in
 * 8-bit color, palette 0x100, 0xF1. */
enum {
    DUEL_IMAGE_SECTORS = 64, DUEL_IMAGE_X = 0x300, DUEL_IMAGE_Y = 0x100,
    DUEL_PALETTE_SECTOR = DUEL_TERRAIN_PACKAGE_FIRST_SECTOR + DUEL_IMAGE_SECTORS,
    DUEL_PALETTE_X = 0x100, DUEL_PALETTE_Y = 0xF0, DUEL_PALETTE_W = 0x100, DUEL_PALETTE_H = 0x10,
    DIGIT_PAGE = 0x1E, DIGIT_V = 0x58, DIGIT_SIZE = 8, DIGIT_CLUT_X = 0x100, DIGIT_CLUT_Y = 0xF1
};
/* The pieces' sizes in the sheets. */
enum { BADGE_W = 24, BADGE_H = 24, PLATE_W = 56, PLATE_H = 48, LETTER_W = 40, LETTER_H = 40 };

static struct {
    int state; /* 0 unread, 1 read, -1 not readable */
    DiscArt badge[2], plate, letter[5], digit[10];
} art;

static int page_x(int page) { return (page & 0xF) * 64; }
static int page_y(int page) { return (page >> 4 & 1) * 256; }

static int u16_at(const unsigned char *bytes, int at)
{
    return at >= 0 && at + 1 < RESOURCE_BYTES ? bytes[at] | bytes[at + 1] << 8 : -1;
}

/* DisplayObject_UpdateCommandStream's three-level offset chain, then the
 * stream's first command as DisplayObjectStream_ReadNextCommand reads it: a
 * frame count and the sheet's offset. -1 if the resource does not have it
 * (or starts with a control command, which the result objects' do not). */
static int sheet_offset(const unsigned char *resource, int record, int variant)
{
    int level1 = u16_at(resource, 0), level2, stream;
    if (level1 < 0) return -1;
    level2 = u16_at(resource, level1 + record * 2);
    if (level2 < 0) return -1;
    stream = u16_at(resource, level2 + variant * 2);
    if (stream < 0 || stream >= RESOURCE_BYTES || resource[stream] >= 0xF0) return -1;
    return u16_at(resource, stream + 1);
}

/* Cuts the sheet's part that is w x h as DisplayObject_RenderSpriteSheet
 * would draw it for the result objects. */
static int cut_part(DiscArt *out, const unsigned char *resource, int sheet, int w, int h)
{
    int count, flags, header_page, header_clut, i;
    if (sheet < 0 || sheet + 4 > RESOURCE_BYTES) return 0;
    count = resource[sheet];
    flags = resource[sheet + 1];
    header_page = resource[sheet + 2];
    header_clut = resource[sheet + 3];
    for (i = 0; i < count && sheet + 4 + i * 6 + 6 <= RESOURCE_BYTES; i++) {
        const unsigned char *part = resource + sheet + 4 + i * 6;
        int cell = part[2] | part[3] << 8, size = part[4] | part[5] << 8;
        int part_w = ((size >> 2) & 0x78) + 8, part_h = ((size >> 6) & 0x78) + 8;
        int page = OBJECT_PAGE + header_page, u = (cell & 0x1F) << 3, v = (cell & 0x3E0) >> 2;
        int clut_x = OBJECT_CLUT_X + ((header_clut & 0xF) << 4), clut_y = OBJECT_CLUT_Y + (header_clut >> 4);
        if (part_w != w || part_h != h) continue;
        if (flags & 0xE0) {
            int value = (clut_x & 0xFF) + ((size & 0xF) << 4);
            page += (cell >> 10) & 7;
            clut_x = (clut_x & 0x300) | (value & 0xFF);
            clut_y += value >> 8;
        }
        page += u >> 8;
        return DiscArt_Cut(out, page_x(page), page_y(page), 4, u & 0xFF, v, w, h, clut_x, clut_y);
    }
    return 0;
}

static int read_art(void)
{
    static unsigned char resource[RESOURCE_BYTES];
    int i;
    if (!DiscArt_LoadImage(FILE_WA_DUEL_RESULTS_START_SECTOR, RESULTS_IMAGE_SECTORS, RESULTS_IMAGE_X,
                           RESULTS_IMAGE_Y) ||
        !DiscArt_LoadRect(RESULTS_PALETTE_SECTOR, 0, RESULTS_PALETTE_X, RESULTS_PALETTE_Y, RESULTS_PALETTE_W,
                          RESULTS_PALETTE_H) ||
        !DiscArt_Read(RESULTS_RESOURCE_SECTOR, resource, RESOURCE_BYTES) ||
        !DiscArt_LoadImage(DUEL_TERRAIN_PACKAGE_FIRST_SECTOR, DUEL_IMAGE_SECTORS, DUEL_IMAGE_X, DUEL_IMAGE_Y) ||
        !DiscArt_LoadRect(DUEL_PALETTE_SECTOR, 0, DUEL_PALETTE_X, DUEL_PALETTE_Y, DUEL_PALETTE_W, DUEL_PALETTE_H))
        return 0;
    for (i = 0; i < 2; i++)
        if (!cut_part(&art.badge[i], resource, sheet_offset(resource, RECORD_BADGE, i), BADGE_W, BADGE_H))
            return 0;
    if (!cut_part(&art.plate, resource, sheet_offset(resource, RECORD_BADGE, 0), PLATE_W, PLATE_H)) return 0;
    for (i = 0; i < 5; i++)
        if (!cut_part(&art.letter[i], resource, sheet_offset(resource, RECORD_LETTER, i), LETTER_W, LETTER_H))
            return 0;
    for (i = 0; i < 10; i++)
        if (!DiscArt_Cut(&art.digit[i], page_x(DIGIT_PAGE), page_y(DIGIT_PAGE), 8, i * DIGIT_SIZE, DIGIT_V,
                         DIGIT_SIZE, DIGIT_SIZE, DIGIT_CLUT_X, DIGIT_CLUT_Y))
            return 0;
    return 1;
}

void RankArt_Reset(void)
{
    int i;
    for (i = 0; i < 2; i++) DiscArt_Free(&art.badge[i]);
    DiscArt_Free(&art.plate);
    for (i = 0; i < 5; i++) DiscArt_Free(&art.letter[i]);
    for (i = 0; i < 10; i++) DiscArt_Free(&art.digit[i]);
    art.state = 0;
}

int RankArt_Ready(void)
{
    if (!art.state) {
        art.state = read_art() ? 1 : -1;
        if (art.state < 0) {
            RankArt_Reset();
            art.state = -1;
            fprintf(stderr, "memories-pc: duel rank: the result screen's pictures are not on this disc\n");
        }
        /* The pieces are cut; the private VRAM is not needed again. */
        DiscArt_Reset();
    }
    return art.state > 0;
}

const DiscArt *RankArt_Badge(int tec) { return art.state > 0 ? &art.badge[tec != 0] : NULL; }
const DiscArt *RankArt_Plate(void) { return art.state > 0 ? &art.plate : NULL; }
const DiscArt *RankArt_Letter(int tier)
{ return art.state > 0 && tier >= 0 && tier < 5 ? &art.letter[tier] : NULL; }
const DiscArt *RankArt_Digit(int digit)
{ return art.state > 0 && digit >= 0 && digit < 10 ? &art.digit[digit] : NULL; }

/* The layout, in game picture pixels from the FIELD box's top right: the
 * plate at half its size, as tall as the box, a step clear of it; the
 * letter at 0.6 on it, against its right edge; the badge at half behind the
 * letter, its corner just above the plate's; the digits at their own size
 * after the plate, centred on it. */
enum {
    GAP = 2, SHRUNK_PLATE_W = PLATE_W / 2, SHRUNK_PLATE_H = PLATE_H / 2, SHRUNK_LETTER = LETTER_W * 3 / 5,
    LETTER_X = SHRUNK_PLATE_W - SHRUNK_LETTER, SHRUNK_BADGE = BADGE_W / 2, BADGE_Y = -1,
    DIGITS_X = SHRUNK_PLATE_W + GAP, DIGITS_Y = (SHRUNK_PLATE_H - DIGIT_SIZE) / 2
};

static int window_x(const RankArtView *view, int x)
{ return view->x + view->w / 2 + (x - 160) * view->w / view->width_2d; }
static int window_y(const RankArtView *view, int y) { return view->y + y * view->h / 240; }

typedef struct { int left, top, right, bottom; } Box;

static void piece(MenuCanvas *canvas, const RankArtView *view, const DiscArt *picture, int x, int y, int w, int h,
                  Box *covered)
{
    int left = window_x(view, x), top = window_y(view, y);
    int right = window_x(view, x + w), bottom = window_y(view, y + h);
    DiscArt_Draw(canvas, picture, left, top, right - left, bottom - top);
    if (left < covered->left) covered->left = left;
    if (top < covered->top) covered->top = top;
    if (right > covered->right) covered->right = right;
    if (bottom > covered->bottom) covered->bottom = bottom;
}

void RankArt_Draw(MenuCanvas *canvas, const RankArtView *view, int right, int top, int tec, int tier, int score,
                  int *x, int *y, int *w, int *h)
{
    Box covered = {0x7FFFFFFF, 0x7FFFFFFF, -0x7FFFFFFF, -0x7FFFFFFF};
    int left = right + GAP;
    *x = *y = *w = *h = 0;
    if (!RankArt_Ready() || view->w <= 0 || view->h <= 0 || view->width_2d <= 0 || tier < 0 || tier > 4) return;
    piece(canvas, view, RankArt_Plate(), left, top, SHRUNK_PLATE_W, SHRUNK_PLATE_H, &covered);
    piece(canvas, view, RankArt_Badge(tec), left, top + BADGE_Y, SHRUNK_BADGE, SHRUNK_BADGE, &covered);
    piece(canvas, view, RankArt_Letter(tier), left + LETTER_X, top, SHRUNK_LETTER, SHRUNK_LETTER, &covered);
    if (score >= 0) {
        if (score > 99) score = 99;
        int at = left + DIGITS_X;
        if (score >= 10) {
            piece(canvas, view, RankArt_Digit(score / 10), at, top + DIGITS_Y, DIGIT_SIZE, DIGIT_SIZE, &covered);
            at += DIGIT_SIZE;
        }
        piece(canvas, view, RankArt_Digit(score % 10), at, top + DIGITS_Y, DIGIT_SIZE, DIGIT_SIZE, &covered);
    }
    if (covered.left < 0) covered.left = 0;
    if (covered.top < 0) covered.top = 0;
    if (covered.right > canvas->width) covered.right = canvas->width;
    if (covered.bottom > canvas->height) covered.bottom = canvas->height;
    if (covered.right <= covered.left || covered.bottom <= covered.top) return;
    *x = covered.left;
    *y = covered.top;
    *w = covered.right - covered.left;
    *h = covered.bottom - covered.top;
}
