/* The game's own pictures off the disc for the host's overlays (disc_art.h). */
#include "disc_art.h"
#include "pc/sdk/disc.h"
#include "pc/text/overlay_text.h"
#include <stdlib.h>
#include <string.h>

enum { VRAM_W = 1024, VRAM_H = 512, SECTOR = 2048, BLOCK_W = 64, BLOCK_H = 16 };

static uint16_t *vram;

void DiscArt_Reset(void)
{
    free(vram);
    vram = NULL;
}

uint16_t DiscArt_Word(int x, int y)
{
    return vram && x >= 0 && y >= 0 && x < VRAM_W && y < VRAM_H ? vram[y * VRAM_W + x] : 0;
}

/* `sectors` sectors of WA_MRG from `sector`, if the file has them. */
static unsigned char *read_sectors(int sector, int sectors)
{
    unsigned char *bytes;
    unsigned size;
    int lba;
    if (sector < 0 || sectors <= 0 || Memories_DiscFileInfo(DISC_ART_WA_PATH, &lba, &size) != 0 || lba < 0 ||
        (unsigned)(sector + sectors) * SECTOR > size)
        return NULL;
    bytes = malloc((size_t)sectors * SECTOR);
    if (bytes && Memories_DiscReadSectors(lba + sector, sectors, bytes) != sectors) {
        free(bytes);
        bytes = NULL;
    }
    return bytes;
}

static int have_vram(void)
{
    if (!vram) vram = calloc((size_t)VRAM_W * VRAM_H, sizeof(*vram));
    return vram != NULL;
}

static void put(int x, int y, const unsigned char *words, int w, int h)
{
    int i, j;
    for (j = 0; j < h; j++)
        for (i = 0; i < w; i++) {
            const unsigned char *at = words + ((size_t)j * w + i) * 2;
            vram[((y + j) & (VRAM_H - 1)) * VRAM_W + ((x + i) & (VRAM_W - 1))] = (uint16_t)(at[0] | at[1] << 8);
        }
}

int DiscArt_LoadImage(int sector, int sectors, int x, int y)
{
    unsigned char *bytes;
    int i;
    if (!have_vram() || !(bytes = read_sectors(sector, sectors))) return 0;
    /* File_StepActiveTransfer: 16 rows further down each sector; past a
     * 256-row boundary, back to the top of that half and 64 words right. */
    for (i = 0; i < sectors; i++) {
        put(x, y, bytes + (size_t)i * SECTOR, BLOCK_W, BLOCK_H);
        y += BLOCK_H;
        if ((y & 0xFF) == 0) {
            y = (y ^ 0x100) & 0x100;
            x += BLOCK_W;
        }
    }
    free(bytes);
    return 1;
}

int DiscArt_LoadRect(int sector, int offset, int x, int y, int w, int h)
{
    unsigned char *bytes;
    int sectors;
    if (offset < 0 || w <= 0 || h <= 0 || !have_vram()) return 0;
    sectors = (offset + w * h * 2 + SECTOR - 1) / SECTOR;
    if (!(bytes = read_sectors(sector, sectors))) return 0;
    put(x, y, bytes + offset, w, h);
    free(bytes);
    return 1;
}

int DiscArt_Read(int sector, void *out, int bytes)
{
    unsigned char *data;
    if (bytes <= 0 || !(data = read_sectors(sector, (bytes + SECTOR - 1) / SECTOR))) return 0;
    memcpy(out, data, (size_t)bytes);
    free(data);
    return 1;
}

static uint32_t color(uint16_t word)
{
    unsigned r = word & 31, g = word >> 5 & 31, b = word >> 10 & 31;
    /* 0x0000 is the one transparent color; 0x8000 is opaque black. */
    if (!word) return 0;
    return 0xFF000000u | (r << 3 | r >> 2) << 16 | (g << 3 | g >> 2) << 8 | (b << 3 | b >> 2);
}

int DiscArt_Cut(DiscArt *art, int page_x, int page_y, int depth, int u, int v, int w, int h, int clut_x,
                int clut_y)
{
    int x, y;
    memset(art, 0, sizeof(*art));
    if ((depth != 4 && depth != 8) || w <= 0 || h <= 0 || !vram) return 0;
    art->pixels = malloc((size_t)w * h * sizeof(*art->pixels));
    if (!art->pixels) return 0;
    art->width = w;
    art->height = h;
    for (y = 0; y < h; y++) {
        for (x = 0; x < w; x++) {
            int tu = u + x, index;
            uint16_t word;
            if (depth == 4) {
                word = DiscArt_Word(page_x + tu / 4, page_y + v + y);
                index = word >> (tu % 4 * 4) & 0xF;
            } else {
                word = DiscArt_Word(page_x + tu / 2, page_y + v + y);
                index = word >> (tu % 2 * 8) & 0xFF;
            }
            art->pixels[y * w + x] = color(DiscArt_Word(clut_x + index, clut_y));
        }
    }
    return 1;
}

void DiscArt_Free(DiscArt *art)
{
    free(art->pixels);
    memset(art, 0, sizeof(*art));
}

/* The texels window column (or row) i of n covers, of a source of s: the one
 * under its centre when enlarged, all it spans when shrunk. */
static void span(int i, int n, int s, int *first, int *last)
{
    if (n >= s) {
        *first = *last = (int)(((2 * (long long)i + 1) * s) / (2 * (long long)n));
        return;
    }
    *first = (int)((long long)i * s / n);
    *last = (int)((long long)(i + 1) * s / n) - 1;
    if (*last < *first) *last = *first;
}

void DiscArt_Draw(MenuCanvas *canvas, const DiscArt *art, int x, int y, int w, int h)
{
    int i, j;
    if (!art || !art->pixels || w <= 0 || h <= 0) return;
    for (j = 0; j < h; j++) {
        int top, bottom;
        if (y + j < 0 || y + j >= canvas->height) continue;
        span(j, h, art->height, &top, &bottom);
        for (i = 0; i < w; i++) {
            int left, right, sx, sy;
            unsigned r = 0, g = 0, b = 0, opaque = 0, total = 0;
            if (x + i < 0 || x + i >= canvas->width) continue;
            span(i, w, art->width, &left, &right);
            for (sy = top; sy <= bottom; sy++) {
                for (sx = left; sx <= right; sx++) {
                    uint32_t texel = art->pixels[sy * art->width + sx];
                    total++;
                    if (!(texel >> 24)) continue;
                    opaque++;
                    r += texel >> 16 & 255;
                    g += texel >> 8 & 255;
                    b += texel & 255;
                }
            }
            if (!opaque) continue;
            OverlayText_Blend(canvas, x + i, y + j, (r / opaque) << 16 | (g / opaque) << 8 | b / opaque,
                              opaque * 255 / total);
        }
    }
}
