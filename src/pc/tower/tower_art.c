/* A tower's own pictures (tower.h, TowerArt): each PNG a story names made,
 * when the tower is built, into the kind of picture the campaign's
 * machinery draws, so it is drawn by the same code as the disc's.
 *
 *   A scene: 320 x 160 texels at 8 bits through 256 colors (entry 0
 *   clear), as a mode-0 record of ScriptImage_RequestTransfer's is
 *   (zz_tower_storage.c puts it in VRAM in that record's layout).
 *
 *   A character: what one of the display-effect records at WA sector 15182
 *   + id * 50 holds, as func_8003A560 keeps it in its cache slot
 *   (func_8003A560.h): a 384 x 256-texel sheet at 8 bits, two rows of 256
 *   colors (the second the first with the semi-transparency bit, as every
 *   disc record has them), and the parts bank DisplayEffect_BuildResourceObjects
 *   reads: four expressions all of one piece, one frame, one sprite sheet of
 *   parts of at most 128 x 128 (DisplayObject_RenderSpriteSheet), placed as
 *   the disc's are: its middle over the side's anchor and its bottom edge
 *   on it, or, taller than the 178 rows above it, its top at the screen's. The picture is the PNG at its own size, or shrunk to fit
 *   TOWER_CHARACTER_SIDE when it is larger.
 *
 * Above the console's resolution a scene's PNG is drawn at its own (the
 * texture pack's made images, TexturePack_AddMade); a character is drawn at
 * the console's. */
#include "tower.h"
#include "pc/cards/art.h"
#include "pc/mods/mods.h"
#include "pc/render/texture_pack.h"
#include <stdlib.h>
#include <string.h>

#define SCENE_W 320
#define SCENE_H 160
#define SLOT_W 384                    /* texels: the slot's 192 words */
#define SLOT_H 256
#define TOWER_CHARACTER_SIDE 256      /* within one 8-bit page: u stays under 256 */
#define BANK_SIZE 0x800
#define PART 128
/* The side's anchor (func_80039F44: y 0xB2, just under the box's top): a
 * picture stands on it, and one taller than the room above it has its top
 * at the screen's and runs on under the box. */
#define ANCHOR_Y 0xB2

static void put16(unsigned char *at, unsigned value)
{
    at[0] = (unsigned char)value;
    at[1] = (unsigned char)(value >> 8);
}

/* The parts bank of a w x h picture at the sheet's top left. */
static void make_bank(unsigned char *bank, int w, int h)
{
    enum { LEVEL1 = 0x00, LEVEL2 = 0x08, LEVEL3 = 0x0E, STREAM = 0x10, SHEET = 0x14 };
    int c, x, y, count = 0;
    unsigned char *part;
    memset(bank, 0, BANK_SIZE);
    for (c = 0; c < 4; c++) put16(bank + LEVEL1 + c * 2, LEVEL2);   /* every expression the same */
    put16(bank + LEVEL2, LEVEL3);                                    /* piece 0; no eyes, no mouth */
    put16(bank + LEVEL3, STREAM);                                    /* one frame */
    bank[STREAM] = 0;                                                /* shown until it goes */
    put16(bank + STREAM + 1, SHEET);
    bank[SHEET + 1] = 0x10;                                          /* ten-bit offsets */
    part = bank + SHEET + 4;
    for (y = 0; y < h; y += PART) {
        for (x = 0; x < w; x += PART) {
            int pw = w - x < PART ? w - x : PART, ph = h - y < PART ? h - y : PART;
            int dx = x - w / 2, dy = y - (h < ANCHOR_Y ? h : ANCHOR_Y);
            unsigned cell = (unsigned)(x / 8) | (unsigned)(y / 8) << 5 | ((unsigned)(dx >> 8) & 3) << 14;
            unsigned size = (unsigned)(pw / 8 - 1) << 5 | (unsigned)(ph / 8 - 1) << 9 | ((unsigned)(dy >> 8) & 3) << 14;
            part[0] = (unsigned char)dx;
            part[1] = (unsigned char)dy;
            put16(part + 2, cell);
            put16(part + 4, size);
            part += 6;
            count++;
        }
    }
    bank[SHEET] = (unsigned char)count;
}

static int make_scene(const char *mod, TowerArt *art)
{
    char why[256];
    art->texels = malloc(SCENE_W * SCENE_H);
    if (!art->texels) return 0;
    if (!CardArt_IndexedImage(art->path, SCENE_W, SCENE_H, art->texels, art->clut, why, sizeof why)) {
        Mods_Note(mod, "tower: %s", why);
        return 0;
    }
    art->width = SCENE_W;
    art->height = SCENE_H;
    return 1;
}

static int make_character(const char *mod, TowerArt *art)
{
    char why[256];
    int pw, ph, w, h, y, x;
    unsigned char *picture;
    if (!CardArt_ImageSize(art->path, &pw, &ph) || pw < 1 || ph < 1) {
        Mods_Note(mod, "tower: %s is not a PNG it could read", art->path);
        return 0;
    }
    w = pw;
    h = ph;
    if (w > TOWER_CHARACTER_SIDE || h > TOWER_CHARACTER_SIDE) {
        if ((long)w * TOWER_CHARACTER_SIDE >= (long)h * TOWER_CHARACTER_SIDE && w >= h) {
            h = (int)((long)h * TOWER_CHARACTER_SIDE / w);
            w = TOWER_CHARACTER_SIDE;
        } else {
            w = (int)((long)w * TOWER_CHARACTER_SIDE / h);
            h = TOWER_CHARACTER_SIDE;
        }
        if (w < 1) w = 1;
        if (h < 1) h = 1;
    }
    picture = malloc((size_t)w * h);
    art->texels = calloc(SLOT_W * SLOT_H + 2 * 256 * 2, 1);
    art->bank = malloc(BANK_SIZE);
    if (!picture || !art->texels || !art->bank) {
        free(picture);
        return 0;
    }
    if (!CardArt_IndexedImage(art->path, w, h, picture, art->clut, why, sizeof why)) {
        Mods_Note(mod, "tower: %s", why);
        free(picture);
        return 0;
    }
    for (y = 0; y < h; y++) {
        for (x = 0; x < w; x++) art->texels[y * SLOT_W + x] = picture[y * w + (art->flip ? w - 1 - x : x)];
    }
    free(picture);
    art->width = (w + 7) & ~7;
    art->height = (h + 7) & ~7;
    make_bank(art->bank, art->width, art->height);
    {   /* the two rows of colors after the texels: as is, then semi-transparent */
        unsigned short *rows = (unsigned short *)(art->texels + SLOT_W * SLOT_H);
        int k;
        for (k = 0; k < 256; k++) {
            rows[k] = art->clut[k];
            rows[256 + k] = art->clut[k] ? (unsigned short)(art->clut[k] | 0x8000) : 0;
        }
    }
    return 1;
}

void Tower_MakeArt(TowerConfig *config)
{
    int i;
    for (i = 0; i < config->art_count; i++) {
        TowerArt *art = &config->arts[i];
        art->ready = art->kind == TOWER_ART_SCENE ? make_scene(config->mod, art) : make_character(config->mod, art);
        if (!art->ready) {
            free(art->texels);
            free(art->bank);
            art->texels = NULL;
            art->bank = NULL;
            continue;
        }
        if (art->kind == TOWER_ART_SCENE) {
            /* The three rectangles zz_tower_storage.c uploads, each its
             * part of the PNG for the scaled picture. */
            int pw = 0, ph = 0;
            static unsigned char tile[256 * 160], strip[2][64 * 80];
            int y;
            CardArt_ImageSize(art->path, &pw, &ph);
            for (y = 0; y < 160; y++) memcpy(tile + y * 256, art->texels + y * SCENE_W, 256);
            for (y = 0; y < 80; y++) {
                memcpy(strip[0] + y * 64, art->texels + y * SCENE_W + 256, 64);
                memcpy(strip[1] + y * 64, art->texels + (y + 80) * SCENE_W + 256, 64);
            }
            TexturePack_AddMade(tile, 128, 160, 8, art->clut, 256, art->path, 0, 0, pw * 256 / SCENE_W, ph);
            TexturePack_AddMade(strip[0], 32, 80, 8, art->clut, 256, art->path, pw * 256 / SCENE_W, 0,
                                pw - pw * 256 / SCENE_W, ph / 2);
            TexturePack_AddMade(strip[1], 32, 80, 8, art->clut, 256, art->path, pw * 256 / SCENE_W, ph / 2,
                                pw - pw * 256 / SCENE_W, ph - ph / 2);
        }
    }
}

const u8 *Tower_ArtScene(s32 art, const u16 **clut)
{
    const TowerConfig *config = Tower_Config();
    if (!config || art < 0 || art >= config->art_count || !config->arts[art].ready ||
        config->arts[art].kind != TOWER_ART_SCENE)
        return NULL;
    *clut = config->arts[art].clut;
    return config->arts[art].texels;
}

const u8 *Tower_ArtCharacter(s32 art, const u16 **clut, const u8 **bank)
{
    const TowerConfig *config = Tower_Config();
    if (!config || art < 0 || art >= config->art_count || !config->arts[art].ready ||
        config->arts[art].kind != TOWER_ART_CHARACTER)
        return NULL;
    *clut = (const u16 *)(config->arts[art].texels + SLOT_W * SLOT_H);
    *bank = config->arts[art].bank;
    return config->arts[art].texels;
}
