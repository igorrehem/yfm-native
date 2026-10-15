/* Renders the Mods and Controls windows to PPM files for review
 * (tools/pc/preview_panels.sh), with the real menu font and the
 * repository's mods/ folder, without booting guest code: their desktop
 * windows at UI scale 1 and 2, and with PREVIEW_TOUCH=1 the panels inside
 * the game's window (panel.h) on phones and tablets, as an Android build
 * lays them out from the screen's size and density.
 *
 * PREVIEW_OUT names the folder the pictures go to (default tmp/pc/panels).
 * The desktop pictures are the ones to compare between two commits: the
 * windows must not change there when the panels do. */
#include "pc/compat/fs.h"
#include "../../src/pc/platform/menu.c"
#include "pc/mods/mods.h"
#include "pc/platform/mods_window.h"
#include "pc/platform/controls_window.h"
#include "pc/platform/settings.h"
#include "pc/debug/symbols.h"
#include "pc/mods/exports.h"
#ifdef PREVIEW_PANELS
#include "pc/platform/panel.h"
#endif
#include <assert.h>
/* The port around the mod system: nothing here activates a mod. */
int Log_Enabled(LogChannel channel) { return (void)channel, 0; }
int Log_Wanted(LogChannel channel) { return (void)channel, 0; }
void Log_Printf(LogChannel channel, const char *format, ...) { (void)channel, (void)format; }
unsigned short Platform_Pad(int port) { return (void)port, 0; }
int Symbols_Add(const SymbolsEntry *entries, size_t count) { return (void)entries, (void)count, 0; }
int Memories_DiscReadSectors(int lba, int sectors, void *out) { return (void)lba, (void)out, sectors; }
int Memories_DiscSectorCount(void) { return 0; }
int Memories_DiscOriginalFileInfo(const char *path, int *lba, unsigned *size)
{
    return (void)path, (void)lba, (void)size, -1;
}
int Memories_DiscFileInfo(const char *path, int *lba, unsigned *size)
{
    return (void)path, (void)lba, (void)size, -1;
}
int Memories_DiscFileStart(const char *path) { return (void)path, -1; }
const MemoriesModExport Memories_ModExports[1];
const unsigned Memories_ModExportCount = 0;
int Platform_OpenFolder(const char *path) { return (void)path, 0; }
int Platform_RestartGame(void) { return 0; }

static const char *out_dir = "tmp/pc/panels";
static void (*draw_target)(MenuCanvas *);
static void save(MenuCanvas *c, const char *name)
{
    char path[1024];
    draw_target(c);
    snprintf(path, sizeof(path), "%s/%s.ppm", out_dir, name);
    FILE *f = fopen(path, "wb");
    assert(f);
    unsigned char *rgb = malloc((size_t)c->width * c->height * 3), *at = rgb;
    assert(rgb);
    fprintf(f, "P6\n%d %d\n255\n", c->width, c->height);
    for (int y = 0; y < c->height; y++)
        for (int x = 0; x < c->width; x++) {
            uint32_t p = c->pixels[y * c->stride + x];
            *at++ = (unsigned char)(p >> 16);
            *at++ = (unsigned char)(p >> 8);
            *at++ = (unsigned char)p;
        }
    assert(fwrite(rgb, 1, (size_t)(at - rgb), f) == (size_t)(at - rgb));
    free(rgb);
    assert(!fclose(f));
}
static MenuCanvas make(int w, int h)
{
    MenuCanvas c = {0};
    c.width = c.stride = w;
    c.height = h;
    c.pixels = calloc((size_t)w * h, 4);
    assert(c.pixels);
    return c;
}
static void mods_send(MenuEventType type, int x, int y, int wheel, MenuKey key)
{
    MenuEvent e = {0};
    e.type = type;
    e.x = x;
    e.y = y;
    e.button = 1;
    e.wheel = wheel;
    e.key = key;
    ModsWindow_Event(&e);
}
static void mods_select(const char *id)
{
    ModsWindow_Init();
    for (int i = 0; i < Mods_Count() && strcmp(Mods_Id(i), id); i++)
        mods_send(MENU_EVENT_KEY_DOWN, 0, 0, 0, MENU_KEY_DOWN);
}
/* The desktop window at its own size, as mods_preview.c drew it. */
static void mods_desktop(int scale)
{
    char name[64];
    int w, h, x, y;
    ui = scale;
    load_font();
    draw_target = ModsWindow_Draw;
    mods_select("ai-hard-mode");
    ModsWindow_Size(&w, &h);
    MenuCanvas c = make(w, h);
    snprintf(name, sizeof(name), "desktop-mods-about-%d", scale);
    save(&c, name);
    x = w * 68 / 100; /* the Settings tab */
    y = 238 * h / 640;
    mods_send(MENU_EVENT_BUTTON_DOWN, x, y, 0, MENU_KEY_OTHER);
    snprintf(name, sizeof(name), "desktop-mods-settings-%d", scale);
    save(&c, name);
    for (int i = 0; i < 8; i++)
        mods_send(MENU_EVENT_WHEEL, x, y + 200, -1, MENU_KEY_OTHER);
    snprintf(name, sizeof(name), "desktop-mods-scrolled-%d", scale);
    save(&c, name);
    mods_send(MENU_EVENT_KEY_DOWN, 0, 0, 0, MENU_KEY_RIGHT); /* enable it: unsaved changes */
    mods_send(MENU_EVENT_BUTTON_DOWN, w * 87 / 100, y, 0, MENU_KEY_OTHER); /* Compatibility */
    snprintf(name, sizeof(name), "desktop-mods-compat-%d", scale);
    save(&c, name);
    mods_send(MENU_EVENT_KEY_DOWN, 0, 0, 0, MENU_KEY_ESCAPE); /* asks to discard */
    snprintf(name, sizeof(name), "desktop-mods-discard-%d", scale);
    save(&c, name);
    free(c.pixels);
    ModsWindow_Resize(620, 480);
    ModsWindow_Size(&w, &h);
    c = make(w, h);
    snprintf(name, sizeof(name), "desktop-mods-small-%d", scale);
    save(&c, name);
    free(c.pixels);
}
static MenuCanvas *controls_frame;
static void controls_key(int code)
{
    ControlsWindow_Key(code, 1, 0, 0);
    ControlsWindow_Key(code, 0, 0, 0);
    ControlsWindow_Draw(controls_frame);
}
static void controls_desktop(int scale)
{
    char name[64];
    int w, h;
    ui = scale;
    load_font();
    draw_target = ControlsWindow_Draw;
    ControlsWindow_Size(&w, &h);
    MenuCanvas c = make(w, h);
    controls_frame = &c;
    ControlsWindow_Init();
    ControlsWindow_Draw(&c);
    snprintf(name, sizeof(name), "desktop-controls-keyboard-%d", scale);
    save(&c, name);
    for (int i = 0; i < 2; i++) {
        ControllerDevice *d = ControlsRuntime_Device(i);
        d->connected = 1;
        d->style = CTRL_ICON_XBOX;
        snprintf(d->identity, sizeof(d->identity), "preview:%d", i);
        snprintf(d->name, sizeof(d->name), "Xbox Wireless Controller %d", i + 1);
    }
    controls_key(CTRL_KEY_TAB);
    controls_key(CTRL_KEY_ENTER); /* the Controller tab */
    controls_key(CTRL_KEY_ARROW_DOWN);
    snprintf(name, sizeof(name), "desktop-controls-controller-%d", scale);
    save(&c, name);
    controls_key(CTRL_KEY_ENTER); /* listening */
    ControlsWindow_Tick();
    snprintf(name, sizeof(name), "desktop-controls-capture-%d", scale);
    save(&c, name);
    controls_key(CTRL_KEY_ESCAPE);
    controls_key(CTRL_KEY_DELETE);
    ControlsWindow_RequestClose();
    snprintf(name, sizeof(name), "desktop-controls-dialog-%d", scale);
    save(&c, name);
    controls_key(CTRL_KEY_ESCAPE);
    for (int i = 0; i < 2; i++)
        ControlsRuntime_Device(i)->connected = 0;
    free(c.pixels);
    ControlsWindow_MinSize(&w, &h);
    c = make(w, h);
    controls_frame = &c;
    ControlsWindow_Init();
    snprintf(name, sizeof(name), "desktop-controls-small-%d", scale);
    save(&c, name);
    free(c.pixels);
}

#ifdef PREVIEW_PANELS
/* The test geometries: a screen's pixels and its density (dpi / 160). */
static const struct {
    const char *name;
    int w, h;
    float density;
} screens[] = {{"phone-2400x1080", 2400, 1080, 2.75f},  {"phone-1280x720", 1280, 720, 2.0f},
               {"phone-3200x1440", 3200, 1440, 3.5f},  {"tablet-2560x1600", 2560, 1600, 2.0f},
               {"tablet-2048x1536", 2048, 1536, 2.0f}, {"tablet-2208x1768", 2208, 1768, 2.625f}};
static MenuCanvas window;
static int wheel_scrolled; /* screens whose Controls page the wheel scrolled */
static void panel_draw(MenuCanvas *c) { Panel_Draw(c); }
static void finger_tap(int x, int y)
{
    MenuEvent e = {0};
    e.type = MENU_EVENT_BUTTON_DOWN;
    e.button = 1;
    e.x = x;
    e.y = y;
    Panel_Pointer(&e, 1);
    e.type = MENU_EVENT_BUTTON_UP;
    Panel_Pointer(&e, 1);
    Panel_Draw(&window); /* the hits are where the last draw put them, as in the game */
}
static void finger_drag(int x, int y, int dy)
{
    MenuEvent e = {0};
    e.type = MENU_EVENT_BUTTON_DOWN;
    e.button = 1;
    e.x = x;
    e.y = y;
    Panel_Pointer(&e, 1);
    for (int i = 1; i <= 8; i++) {
        e.type = MENU_EVENT_MOTION;
        e.y = y + dy * i / 8;
        Panel_Pointer(&e, 1);
    }
    e.type = MENU_EVENT_BUTTON_UP;
    Panel_Pointer(&e, 1);
    Panel_Draw(&window); /* the hits are where the last draw put them, as in the game */
}
static void panel_key(MenuKey k)
{
    MenuEvent e = {0};
    e.type = MENU_EVENT_KEY_DOWN;
    e.key = k;
    int code = k == MENU_KEY_ESCAPE ? CTRL_KEY_ESCAPE
               : k == MENU_KEY_ENTER ? CTRL_KEY_ENTER
               : k == MENU_KEY_TAB   ? CTRL_KEY_TAB
               : k == MENU_KEY_DOWN  ? CTRL_KEY_ARROW_DOWN
                                     : 0;
    Panel_Key(&e, code, 0, 0);
    e.type = MENU_EVENT_KEY_UP;
    Panel_Key(&e, code, 0, 0);
    Panel_Draw(&window);
}
/* Where a Mods widget is: found by looking for its color would be brittle,
 * so the tests tap where the layout puts it (ModsWindow_Locate). */
static void tap_mods(int id)
{
    int x, y;
    if (!ModsWindow_Locate(id, &x, &y)) {
        fprintf(stderr, "mods widget %d is not shown\n", id);
        abort();
    }
    finger_tap(x + Panel_Left(), y + Panel_Top());
}
static void tap_controls(int id)
{
    int x, y;
    if (!ControlsWindow_Locate(id, &x, &y)) {
        fprintf(stderr, "controls widget %d is not shown\n", id);
        abort();
    }
    finger_tap(x + Panel_Left(), y + Panel_Top());
}
static void touch_screens(void)
{
    char name[128];
    for (unsigned s = 0; s < sizeof(screens) / sizeof(screens[0]); s++) {
        int density = screens[s].density >= 4.0f ? 4 : (int)(screens[s].density + 0.5f);
        ui = density;
        touch_row = (int)(48.0f * screens[s].density + 0.5f);
        load_font();
        window = make(screens[s].w, screens[s].h);
        draw_target = panel_draw;
        Panel_Layout(screens[s].w, screens[s].h, 0, 0, screens[s].w, screens[s].h);

        assert(Panel_Open(PANEL_MODS));
        snprintf(name, sizeof(name), "%s-mods-list", screens[s].name);
        save(&window, name);
        for (int i = 0; i < Mods_Count() && strcmp(Mods_Id(i), "ai-hard-mode"); i++)
            panel_key(MENU_KEY_DOWN);
        tap_mods(MODS_UI_ROW_SELECTED);
        snprintf(name, sizeof(name), "%s-mods-about", screens[s].name);
        save(&window, name);
        tap_mods(MODS_UI_TAB + 1);
        snprintf(name, sizeof(name), "%s-mods-settings", screens[s].name);
        save(&window, name);
        finger_drag(screens[s].w / 2, screens[s].h * 3 / 4, -screens[s].h / 3);
        snprintf(name, sizeof(name), "%s-mods-settings-dragged", screens[s].name);
        save(&window, name);
        tap_mods(MODS_UI_TOGGLE);
        tap_mods(MODS_UI_TAB + 2);
        snprintf(name, sizeof(name), "%s-mods-compat", screens[s].name);
        save(&window, name);
        tap_mods(MODS_UI_ORDER + 1);
        tap_mods(MODS_UI_APPLY);
        snprintf(name, sizeof(name), "%s-mods-restart", screens[s].name);
        save(&window, name);
        panel_key(MENU_KEY_ESCAPE); /* the restart question */
        panel_key(MENU_KEY_ESCAPE); /* the list */
        panel_key(MENU_KEY_ESCAPE); /* discard? */
        snprintf(name, sizeof(name), "%s-mods-discard", screens[s].name);
        save(&window, name);
        Panel_Close();

        assert(Panel_Open(PANEL_CONTROLS));
        snprintf(name, sizeof(name), "%s-controls-keyboard", screens[s].name);
        save(&window, name);
        {
            /* A mouse's wheel scrolls the page as a finger's drag does: to
             * the end and back, the first binding shown where the drag
             * puts it. */
            int row = 0, x, y0, y_wheel = -1, y_drag = -1, y_back;
            MenuEvent e = {0};
            while (row < CTRL_ROW_COUNT && !ControlsWindow_Locate(CONTROLS_UI_BINDING + row * 2, &x, &y0))
                row++;
            assert(row < CTRL_ROW_COUNT);
            e.type = MENU_EVENT_WHEEL;
            e.x = screens[s].w / 2;
            e.y = screens[s].h / 2;
            e.wheel = -100;
            Panel_Pointer(&e, 0);
            Panel_Draw(&window);
            ControlsWindow_Locate(CONTROLS_UI_BINDING + row * 2, &x, &y_wheel);
            e.wheel = 100;
            Panel_Pointer(&e, 0);
            Panel_Draw(&window);
            assert(ControlsWindow_Locate(CONTROLS_UI_BINDING + row * 2, &x, &y_back) && y_back == y0);
            finger_drag(screens[s].w / 2, screens[s].h * 2 / 3, -screens[s].h * 20);
            ControlsWindow_Locate(CONTROLS_UI_BINDING + row * 2, &x, &y_drag);
            assert(y_wheel == y_drag);
            wheel_scrolled += y_wheel != y0;
        }
        for (int inset = 1; inset <= 3; inset++) {
            /* A safe area that is no whole number of units wide or tall:
             * every pixel is the panel's, none left see-through. */
            memset(window.pixels, 0, (size_t)window.stride * window.height * 4);
            Panel_Layout(screens[s].w, screens[s].h, inset, 0, screens[s].w - 2 * inset - 1, screens[s].h - inset);
            Panel_Draw(&window);
            for (int i = 0; i < window.stride * window.height; i++)
                assert((window.pixels[i] >> 24) == 0xff);
        }
        Panel_Layout(screens[s].w, screens[s].h, 0, 0, screens[s].w, screens[s].h);
        Panel_Close(); /* the page from its top again, as the pictures below expect */
        assert(Panel_Open(PANEL_CONTROLS));
        Panel_Draw(&window);
        finger_drag(screens[s].w / 2, screens[s].h * 2 / 3, -screens[s].h / 2);
        snprintf(name, sizeof(name), "%s-controls-scrolled", screens[s].name);
        save(&window, name);
        for (int row = 0, x, y; row < CTRL_ROW_COUNT; row++) /* the first binding the page shows */
            if (ControlsWindow_Locate(CONTROLS_UI_BINDING + row * 2, &x, &y)) {
                finger_tap(x + Panel_Left(), y + Panel_Top());
                break;
            }
        tap_controls(CONTROLS_UI_REBIND);
        ControlsWindow_Tick();
        snprintf(name, sizeof(name), "%s-controls-capture", screens[s].name);
        save(&window, name);
        panel_key(MENU_KEY_ESCAPE);
        ControllerDevice *d = ControlsRuntime_Device(0);
        d->connected = 1;
        d->style = CTRL_ICON_PLAYSTATION;
        snprintf(d->identity, sizeof(d->identity), "preview:0");
        snprintf(d->name, sizeof(d->name), "DualSense (preview)");
        tap_controls(CONTROLS_UI_CONTROLLER);
        snprintf(name, sizeof(name), "%s-controls-controller", screens[s].name);
        save(&window, name);
        tap_controls(CONTROLS_UI_DEVICE);
        snprintf(name, sizeof(name), "%s-controls-devices", screens[s].name);
        save(&window, name);
        panel_key(MENU_KEY_ESCAPE);
        tap_controls(CONTROLS_UI_CLEAR);
        tap_controls(CONTROLS_UI_CANCEL);
        snprintf(name, sizeof(name), "%s-controls-dialog", screens[s].name);
        save(&window, name);
        d->connected = 0;
        Panel_Close();
        free(window.pixels);
    }
    touch_row = 0;
    assert(wheel_scrolled); /* a phone's page is longer than its screen */
}
#endif

int main(void)
{
    if (getenv("PREVIEW_OUT"))
        out_dir = getenv("PREVIEW_OUT");
    Settings_Load();
    Mods_Load();
    for (int scale = 1; scale <= 2; scale++) {
        mods_desktop(scale);
        controls_desktop(scale);
    }
#ifdef PREVIEW_PANELS
    if (getenv("PREVIEW_TOUCH") && *getenv("PREVIEW_TOUCH"))
        touch_screens();
#endif
    return 0;
}
