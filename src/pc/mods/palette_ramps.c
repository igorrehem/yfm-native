/* The mods' "palette_ramps" (palette_ramps.h). */
#include "palette_ramps.h"
#include "json.h"
#include "mods.h"
#include "psyq/libgte.h"
#include "psyq/libgpu.h"
#include <stdio.h>
#include <string.h>

enum { RETAIL_RAMPS = 8, RAMP_ENTRIES = 16, RAMP_X = 640, RAMP_Y = 232, NAMED_MAX = 256, NAME_MAX = 64 };

typedef struct {
    char name[NAME_MAX];
    unsigned short ramp[RAMP_ENTRIES];
} NamedRamp;

static NamedRamp named[NAMED_MAX];
static int named_count;

static const NamedRamp *find(const char *name)
{
    int i;
    for (i = 0; name && i < named_count; i++) {
        if (!strcmp(named[i].name, name)) return &named[i];
    }
    return NULL;
}

int PaletteRamps_Ramp(const char *name, unsigned short ramp[16])
{
    const NamedRamp *found = find(name);
    if (!found) return 0;
    memcpy(ramp, found->ramp, sizeof(found->ramp));
    return 1;
}

unsigned short PaletteRamps_Load(const char *name, int x, int y)
{
    const NamedRamp *found = find(name);
    RECT rect;
    if (!found || x < 0 || x > 1024 - RAMP_ENTRIES || x % 16 || y < 0 || y >= 512) return 0;
    rect.x = (short)x;
    rect.y = (short)y;
    rect.w = RAMP_ENTRIES;
    rect.h = 1;
    LoadImage(&rect, (u32 *)found->ramp);
    return (unsigned short)(y << 6 | x >> 4);
}

static int byte(const JsonValue *value, unsigned *out)
{
    long n = Json_Number(value, -1);
    if (Json_TypeOf(value) != JSON_NUMBER || n < 0 || n > 255) return 0;
    *out = (unsigned)n;
    return 1;
}

static int hex(char c)
{
    return c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1;
}

/* "#RRGGBB" or [red, green, blue], 0-255 each. */
static int rgb(const JsonValue *value, unsigned out[3])
{
    const char *text = Json_String(value, NULL);
    int i;
    if (text) {
        if (text[0] != '#' || strlen(text) != 7) return 0;
        for (i = 0; i < 3; i++) {
            int high = hex(text[1 + 2 * i]), low = hex(text[2 + 2 * i]);
            if (high < 0 || low < 0) return 0;
            out[i] = (unsigned)(high << 4 | low);
        }
        return 1;
    }
    return Json_TypeOf(value) == JSON_ARRAY && Json_Count(value) == 3 &&
           byte(Json_At(value, 0), &out[0]) && byte(Json_At(value, 1), &out[1]) && byte(Json_At(value, 2), &out[2]);
}

/* The white ramp's brightness steps in the color: the transparent entry stays
 * transparent, the semi-transparency bit stays as it was, and a step that
 * comes out black stays opaque (0x8000) rather than turning transparent. */
static void make(const unsigned short *base, const unsigned color[3], unsigned short *ramp)
{
    int i;
    for (i = 0; i < RAMP_ENTRIES; i++) {
        unsigned step = base[i] & 31u;
        unsigned short word = (unsigned short)((step * color[2] / 255u) << 10 | (step * color[1] / 255u) << 5 |
                                               step * color[0] / 255u);
        ramp[i] = base[i] ? (unsigned short)(word | (base[i] & 0x8000u)) : 0;
        if (base[i] && !(ramp[i] & 0x7FFF)) ramp[i] |= 0x8000;
    }
}

/* "0" to "7": a retail ramp's row; -1 for a name; -2 for other digits. */
static int retail_slot(const char *key)
{
    const char *c;
    if (!*key) return -1;
    for (c = key; *c; c++) {
        if (*c < '0' || *c > '9') return -1;
    }
    return key[1] == '\0' && key[0] < '0' + RETAIL_RAMPS ? key[0] - '0' : -2;
}

void PaletteRamps_ApplyManifest(const unsigned short *base)
{
    int i, uploaded = 0;
    named_count = 0;
    if (!base) return;
    for (i = 0; i < Mods_LoadedCount(); i++) {
        const int mod = Mods_Loaded(i);
        const JsonValue *section, *entry;
        if (!Mods_Active(mod)) continue;
        section = Json_Member(Mods_Manifest(mod), "palette_ramps");
        if (!section) continue;
        if (Json_TypeOf(section) != JSON_OBJECT) {
            Mods_Note(Mods_Id(mod), "palette_ramps: must be an object of names and colors");
            continue;
        }
        for (entry = Json_At(section, 0); entry; entry = Json_Next(entry)) {
            const char *key = Json_Name(entry);
            unsigned color[3] = {0, 0, 0};
            unsigned short ramp[RAMP_ENTRIES];
            int slot = retail_slot(key);
            if (!rgb(entry, color)) {
                Mods_Note(Mods_Id(mod), "palette_ramps: '%s' must be [red, green, blue] or #RRGGBB", key);
            } else if (slot == -2) {
                Mods_Note(Mods_Id(mod), "palette_ramps: '%s': the game's own ramps are 0 to 7", key);
            } else if (slot >= 0) {
                /* The later mod in load order wins, as it uploads last. */
                RECT rect = {RAMP_X, (short)(RAMP_Y + slot), RAMP_ENTRIES, 1};
                make(base, color, ramp);
                LoadImage(&rect, (u32 *)ramp);
                uploaded = 1;
            } else if (named_count == NAMED_MAX ||
                       snprintf(named[named_count].name, NAME_MAX, "%s:%s", Mods_Id(mod), key) >= NAME_MAX) {
                Mods_Note(Mods_Id(mod), "palette_ramps: cannot add '%s' (%d named ramps at most, %d letters "
                          "with the mod's id)", key, NAMED_MAX, NAME_MAX - 1);
            } else if (find(named[named_count].name)) {
                Mods_Note(Mods_Id(mod), "palette_ramps: '%s' is declared twice; the first is kept", key);
            } else {
                make(base, color, named[named_count].ramp);
                named_count++;
            }
        }
    }
    if (uploaded) DrawSync(0);
}
