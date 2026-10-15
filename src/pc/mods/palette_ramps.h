#ifndef MEMORIES_PC_MODS_PALETTE_RAMPS_H
#define MEMORIES_PC_MODS_PALETTE_RAMPS_H

/* The mods' "palette_ramps" (notes/modding.md, Palette ramps): one RGB value
 * made into the 16-entry brightness ramp of the game's text palettes.
 *
 * `base` is the retail ramps as the boot package uploads them to VRAM
 * (640,232), eight rows of 16. Keys "0" to "7" replace those rows there; any
 * other key is a named ramp, kept here and put in VRAM only by
 * PaletteRamps_Load: no part of VRAM stays free on every screen, so a named
 * ramp goes where the code that draws with it knows there is room. */
void PaletteRamps_ApplyManifest(const unsigned short *base);

/* A named ramp's 16 BGR555 entries, its name qualified as "mod-id:name".
 * Returns 0 (ramp untouched) when no active mod declared it. */
int PaletteRamps_Ramp(const char *name, unsigned short ramp[16]);

/* Uploads a named ramp to VRAM (x, y), x a multiple of 16 below 1024 and y
 * below 512, and returns the CLUT word that selects it there (a primitive's
 * `clut`). Returns 0 when it was not declared or the place is not one. */
unsigned short PaletteRamps_Load(const char *name, int x, int y);

#endif
