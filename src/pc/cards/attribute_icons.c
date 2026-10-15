/* Attribute-bank icons.  Every bank 0-15 already belongs to someone (see
 * star_icons.c's own note; card_layout_art.c's FRAME_BANK is 13, glyphs are
 * 15, 1-12 are the 3D Monsters mod, 0 is real VRAM) -- tpage only has four
 * bits to name one (bits 11-14; bit 15 is HD_TEXT_MARK), so a sixteenth
 * bank was never available to carve out. These share bank 14 with
 * star_icons.c, in the rows its own layout (pixels 0-15, CLUT 250 and
 * 257-271) leaves alone.
 *
 * A made icon gets one 16x16 pixel cell and one dedicated CLUT row of its
 * own (as type_icons.c's bank does) -- that is what makes the original PNG
 * available to TexturePack_AddBankSprite above 1x; packing several CLUTs
 * into one VRAM row (as this file once did) is not enough above 1x. A
 * dedicated row per *declared* id (ATTRIBUTES_MAX is 255) would not fit
 * this bank at all, so cells are handed out lazily, one per icon actually
 * decoded, capped at what the shared rows hold -- ample for any real mod,
 * which declares a handful of custom attributes, not the full id space. */
#include "attributes.h"
#include "art.h"
#include "pc/render/soft_gpu.h"
#include "pc/render/texture_pack.h"
#include <stdio.h>
#include <string.h>

#define ICON_BANK 14
#define ICON_COLS 16
/* Star icons keep rows 0-15 (pixels) and 250, 257-271 (CLUT): stay clear of
 * both with a margin, rather than interleaving around their exact rows. */
#define ICON_Y 16
#define CLUT_Y 272
/* The CLUT rows stop at 479: duel_ui.c's pictures keep their palettes in
 * rows 480-511 of this bank, across x 0-255. */
#define CELL_LIMIT 208   /* 480 - CLUT_Y */
static unsigned char made[ATTRIBUTES_MAX + 1];   /* 0 not yet, 1 made */
static unsigned char has_cell[ATTRIBUTES_MAX + 1];
static short cell_for[ATTRIBUTES_MAX + 1];
static int cells_used;
static int exhaustion_reported;

void Attributes_IconsClear(void)
{
    memset(made, 0, sizeof(made));
    memset(has_cell, 0, sizeof(has_cell));
    memset(cell_for, 0, sizeof(cell_for));
    cells_used = 0;
    exhaustion_reported = 0;
    TexturePack_BankSpritesClear(TEXTURE_BANK_OWNER_ATTRIBUTE_ICONS);
}

/* The cell already handed to this id, or a freshly handed-out one, -1 past
 * CELL_LIMIT. Every caller must check for -1 before touching the bank with
 * it: unlike `made`, this does not remember a first failure, so a mod that
 * frees up room (never happens today, but Attributes_Clear would) gets a
 * cell on its next call rather than staying stuck on one no row backs. */
static int cell_of(int id)
{
    if (!has_cell[id]) {
        if (cells_used >= CELL_LIMIT) {
            if (!exhaustion_reported++)
                fprintf(stderr, "memories-pc: attribute icons: no room for attribute %d; the shared bank holds %d icons\n", id, CELL_LIMIT);
            return -1;
        }
        has_cell[id] = 1;
        cell_for[id] = (short)cells_used++;
    }
    return cell_for[id];
}

static void store(uint16_t *bank, int cell, const unsigned char *pixels)
{
    int x0 = (cell % ICON_COLS) * 4, y0 = ICON_Y + (cell / ICON_COLS) * CARD_ICON_SIDE;
    for (int y = 0; y < CARD_ICON_SIDE; y++)
        for (int x = 0; x < CARD_ICON_SIDE / 4; x++) {
            const unsigned char *p = &pixels[y * CARD_ICON_SIDE / 2 + x * 2];
            bank[(y0 + y) * SOFT_GPU_WIDTH + x0 + x] = (uint16_t)(p[0] | (p[1] << 8));
        }
}

static int make(int id, int cell, uint16_t *bank)
{
    unsigned char pixels[CARD_ICON_SIDE * CARD_ICON_SIDE / 2] = {0};
    unsigned short clut[16] = {0};
    char why[256];
    const char *icon = Attributes_Icon(id);
    int decoded = icon && CardArt_IconFromImage(icon, NULL, pixels, clut, why, sizeof(why));
    if (!decoded) {
        if (icon) fprintf(stderr, "memories-pc: attribute %d: %s\n", id, why);
        /* A visible neutral fallback for a declared attribute without a PNG.
         * Unreachable for a retail id (0-5): Attributes_IconCell only calls
         * make() for one once it already found that id its own icon. */
        clut[1] = 0x7fff;
        for (int y = 2; y < 14; y++) for (int x = 2; x < 14; x++)
            pixels[(y * CARD_ICON_SIDE + x) / 2] |= (unsigned char)(1 << ((x & 1) * 4));
    }
    store(bank, cell, pixels);
    memcpy(&bank[(CLUT_Y + cell) * SOFT_GPU_WIDTH], clut, sizeof(clut));
    /* The HD texture must describe the same picture written to the console
     * bank. An undecodable PNG has the neutral fallback above, not an HD
     * replacement that might decode differently in the texture pack. */
    if (decoded) {
        TexturePack_BankSpritesUseOwner(TEXTURE_BANK_OWNER_ATTRIBUTE_ICONS);
        if (!TexturePack_AddBankSprite(ICON_BANK, 0, 0, 0, 0, CLUT_Y + cell,
                                       (cell % ICON_COLS) * CARD_ICON_SIDE,
                                       ICON_Y + (cell / ICON_COLS) * CARD_ICON_SIDE,
                                       CARD_ICON_SIDE, CARD_ICON_SIDE, icon))
            fprintf(stderr, "memories-pc: attribute %d: its icon has no HD replacement (the console-resolution one still applies)\n", id);
    }
    return 1;
}

int Attributes_IconCell(int attribute, int *tpage, int *u, int *v, int *clut_x, int *clut_y)
{
    uint16_t *bank;
    int cell;
    if (attribute < 0 || attribute > ATTRIBUTES_MAX) return 0;
    if (attribute < ATTRIBUTES_RETAIL) {
        /* A renamed retail attribute (0-5) only switches to this bank when
         * a mod also gave it an icon -- otherwise the card-detail renderer's
         * own retail path (func_80028B08.c) keeps drawing it, unchanged. */
        if (!Attributes_Icon(attribute)) return 0;
    } else if (!Attributes_Declared(attribute)) {
        return 0;
    }
    if (!(bank = SoftGpu_Bank(ICON_BANK))) return 0;
    if ((cell = cell_of(attribute)) < 0) return 0;
    if (!made[attribute]) made[attribute] = make(attribute, cell, bank);
    *tpage = ICON_BANK << 11;
    *u = (cell % ICON_COLS) * CARD_ICON_SIDE;
    *v = ICON_Y + (cell / ICON_COLS) * CARD_ICON_SIDE;
    *clut_x = 0;
    *clut_y = CLUT_Y + cell;
    return 1;
}
