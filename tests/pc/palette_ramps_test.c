/* The mods' "palette_ramps" key (src/pc/mods/palette_ramps.c): real
 * manifests through the real JSON reader, VRAM uploads caught. Checked:
 * ramps 0-7 replace their retail row and the later mod wins; a named ramp
 * goes into VRAM only when PaletteRamps_Load asks, where it is asked to;
 * the transparent entry, the semi-transparency bit and black steps; and
 * bad keys and values being noted, not applied. */
/* The Psy-Q headers do not build under the tests' warnings (clang): what
 * palette_ramps.c takes from them, here. */
#define _LIBGTE_H_
#define _LIBGPU_H_
#include "types.h"
typedef struct {
    short x, y;
    short w, h;
} RECT;
int LoadImage(RECT *rect, u32 *p);
int DrawSync(int mode);
#include "../../src/pc/mods/palette_ramps.c"
#include <stdarg.h>
#include <stdlib.h>

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition);     \
            exit(1);                                                           \
        }                                                                       \
    } while (0)

static int notes;
static char note[512];
void Mods_Note(const char *id, const char *format, ...)
{
    va_list arguments;
    (void)id;
    notes++;
    va_start(arguments, format);
    vsnprintf(note, sizeof(note), format, arguments);
    va_end(arguments);
}

#define MAX_MODS 3
static struct {
    const char *id;
    JsonDocument *document;
    int active;
} fake_mods[MAX_MODS];
static int fake_mod_count;

int Mods_LoadedCount(void) { return fake_mod_count; }
int Mods_Loaded(int index) { return index; }
int Mods_Active(int mod) { return fake_mods[mod].active; }
const char *Mods_Id(int mod) { return fake_mods[mod].id; }
const JsonValue *Mods_Manifest(int mod) { return Json_Root(fake_mods[mod].document); }

/* VRAM as far as these uploads reach. */
static unsigned short vram[512][1024];
static int uploads, syncs;
int LoadImage(RECT *rect, u32 *p)
{
    const unsigned short *words = (const unsigned short *)p;
    int x, y;
    uploads++;
    for (y = 0; y < rect->h; y++) {
        for (x = 0; x < rect->w; x++) vram[rect->y + y][rect->x + x] = words[y * rect->w + x];
    }
    return 0;
}
int DrawSync(int mode) { (void)mode; syncs++; return 0; }

/* The retail white ramp's shape: transparent, an opaque black outline, a
 * semi-transparent step, then brighter greys. */
static unsigned short base[8 * 16];

static void add(const char *id, const char *json, int active)
{
    char error[128];
    fake_mods[fake_mod_count].id = id;
    fake_mods[fake_mod_count].document = Json_Parse(json, error, sizeof(error));
    CHECK(fake_mods[fake_mod_count].document);
    fake_mods[fake_mod_count].active = active;
    fake_mod_count++;
}

static void reset(void)
{
    int i;
    for (i = 0; i < fake_mod_count; i++) Json_Free(fake_mods[i].document);
    fake_mod_count = 0;
    notes = uploads = syncs = 0;
    note[0] = '\0';
    memset(vram, 0, sizeof(vram));
}

static unsigned short grey(int step) { return (unsigned short)(step << 10 | step << 5 | step); }

int main(void)
{
    unsigned short ramp[16];
    int i;

    base[0] = 0;
    base[1] = 0x8000;
    base[2] = (unsigned short)(0x8000 | grey(8));
    for (i = 3; i < 16; i++) base[i] = grey(2 * i);

    /* Nothing declared: VRAM untouched, no named ramps. */
    add("plain", "{\"id\": \"plain\"}", 1);
    PaletteRamps_ApplyManifest(base);
    CHECK(uploads == 0 && syncs == 0 && notes == 0);
    CHECK(!PaletteRamps_Ramp("plain:x", ramp) && PaletteRamps_Load("plain:x", 0, 0) == 0);
    reset();

    /* "0" red: its row only, built from the white ramp. Named ramps are
     * kept, not uploaded. */
    add("a", "{\"palette_ramps\": {\"0\": \"#FF0000\", \"rare\": [0, 255, 0], \"3\": \"#ffffff\"}}", 1);
    PaletteRamps_ApplyManifest(base);
    CHECK(notes == 0 && uploads == 2 && syncs == 1);
    CHECK(vram[232][640] == 0);                         /* transparent stays transparent */
    CHECK(vram[232][641] == 0x8000);                    /* the black outline stays opaque */
    CHECK(vram[232][642] == (0x8000 | 8));              /* red, semi-transparency kept */
    CHECK(vram[232][655] == 30);                        /* grey 30 as red */
    CHECK(vram[235][655] == grey(30));                  /* white: the base itself */
    CHECK(vram[233][655] == 0);                         /* rows not named: untouched */
    for (i = 240; i < 512; i++) CHECK(vram[i][640] == 0);
    CHECK(PaletteRamps_Ramp("a:rare", ramp) && ramp[0] == 0 && ramp[1] == 0x8000 && ramp[15] == (30 << 5));
    CHECK(!PaletteRamps_Ramp("rare", ramp) && !PaletteRamps_Ramp("b:rare", ramp));

    /* PaletteRamps_Load: where it is asked, its CLUT word; not elsewhere. */
    uploads = 0;
    CHECK(PaletteRamps_Load("a:rare", 992, 400) == (400 << 6 | 992 >> 4));
    CHECK(uploads == 1 && vram[400][992 + 15] == (30 << 5) && vram[400][991] == 0);
    CHECK(PaletteRamps_Load("a:rare", 1000, 400) == 0);          /* not a multiple of 16 */
    CHECK(PaletteRamps_Load("a:rare", 1024, 0) == 0 && PaletteRamps_Load("a:rare", 0, 512) == 0);
    CHECK(PaletteRamps_Load("a:rare", -16, 0) == 0 && PaletteRamps_Load("a:nope", 0, 0) == 0);
    CHECK(PaletteRamps_Load(NULL, 0, 0) == 0 && uploads == 1);
    /* Row 0 of VRAM is a place too; the CLUT word for it is still not zero. */
    CHECK(PaletteRamps_Load("a:rare", 16, 0) == 1);
    reset();

    /* The later mod wins a retail row; an inactive mod counts for nothing. */
    add("first", "{\"palette_ramps\": {\"1\": [0, 0, 255]}}", 1);
    add("second", "{\"palette_ramps\": {\"1\": [255, 0, 0]}}", 1);
    add("off", "{\"palette_ramps\": {\"1\": [0, 255, 0], \"named\": \"#00FF00\"}}", 0);
    PaletteRamps_ApplyManifest(base);
    CHECK(vram[233][655] == 30 && notes == 0);
    CHECK(!PaletteRamps_Ramp("off:named", ramp));
    reset();

    /* Bad keys and values: noted, nothing applied. An empty key is a name,
     * not ramp 0. */
    add("bad", "{\"palette_ramps\": {\"8\": \"#FFFFFF\", \"01\": \"#FFFFFF\", \"x\": \"#12345\", "
               "\"y\": \"#12345G\", \"z\": [1, 2], \"w\": [0, 256, 0], \"v\": \"red\", \"\": \"#FFFFFF\"}}", 1);
    PaletteRamps_ApplyManifest(base);
    CHECK(notes == 7 && uploads == 0);
    CHECK(PaletteRamps_Ramp("bad:", ramp));
    reset();
    add("list", "{\"palette_ramps\": [\"#FFFFFF\"]}", 1);
    PaletteRamps_ApplyManifest(base);
    CHECK(notes == 1 && strstr(note, "object") && uploads == 0);
    reset();

    /* The same name twice in a mod: the first kept. Two mods may share a
     * name: their ids tell them apart. */
    add("m", "{\"palette_ramps\": {\"gold\": [255, 0, 0], \"gold\": [0, 0, 255]}}", 1);
    add("n", "{\"palette_ramps\": {\"gold\": [0, 0, 255]}}", 1);
    PaletteRamps_ApplyManifest(base);
    CHECK(notes == 1 && strstr(note, "twice"));
    CHECK(PaletteRamps_Ramp("m:gold", ramp) && ramp[15] == 30);
    CHECK(PaletteRamps_Ramp("n:gold", ramp) && ramp[15] == (30 << 10));
    reset();

    /* A name too long with the mod's id is refused. */
    add("long", "{\"palette_ramps\": {\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\": [1, 2, 3]}}", 1);
    PaletteRamps_ApplyManifest(base);
    CHECK(notes == 1 && strstr(note, "cannot add"));
    reset();

    /* A second start (the boot stage again) starts from no named ramps. */
    add("again", "{\"palette_ramps\": {\"once\": [1, 2, 3]}}", 1);
    PaletteRamps_ApplyManifest(base);
    reset();
    PaletteRamps_ApplyManifest(base);
    CHECK(!PaletteRamps_Ramp("again:once", ramp));

    puts("palette ramps ok");
    return 0;
}
