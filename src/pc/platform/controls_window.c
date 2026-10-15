/* The Controls window: a header with the player and the Keyboard/Controller
 * tabs, the device picker, a PlayStation pad picture beside the binding
 * table, and the Restore/Cancel/Apply/OK footer.
 *
 * Drawing and hit-testing are one pass: every widget paints itself and
 * registers its rectangle, so the two can never disagree. Coordinates are
 * logical units multiplied by `scale`, which drops towards 1 when the window
 * is too small for the chosen menu scale; the window is resizable, so the
 * layout also reflows (the picture drops out, the table scrolls) rather than
 * assuming its default size. Colors follow menu.c so the game menu, the Mods
 * window and this one look like one piece of UI.
 *
 * With a finger (Menu_TouchTarget: a panel inside the game's window on a
 * phone or tablet, panel.h) the scale stays the menu's (the density), rows
 * and buttons are a finger's target tall, and the window is one page that
 * a drag scrolls (ControlsWindow_Drag) between a fixed header (the tabs and
 * the players) and a fixed footer (Clear, Rebind, Cancel, Apply, OK, over a
 * message line): the device, the pad picture, both lists at full length,
 * the fixed keys and Restore defaults, one above the other.
 *
 * The table lists the 16 PlayStation pad destinations in a reading order
 * (D-pad, face buttons, shoulders, stick clicks, system) with group headings;
 * the port's own actions (Exit game, save states, the other shortcuts) are a
 * second list, Game, under the pad picture, with the keys that cannot be
 * bound listed below it for reference. The order is presentation only: row
 * indices, the stored file and every id below still use the wire-bit order
 * of Controls_Actions, host actions (CTRL_HOST_*) after it.
 * Main thread only. */
#include "pc/compat/fs.h"
#include "controls_window.h"
#include "controls_art.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Short names for the public widget ids (controls_window.h). */
enum {
    PLAYER = CONTROLS_UI_PLAYER_1,
    PLAYER_2 = CONTROLS_UI_PLAYER_2,
    DEVICE = CONTROLS_UI_DEVICE,
    KEYBOARD = CONTROLS_UI_KEYBOARD,
    CONTROLLER = CONTROLS_UI_CONTROLLER,
    REBIND = CONTROLS_UI_REBIND,
    CLEAR = CONTROLS_UI_CLEAR,
    DEFAULTS = CONTROLS_UI_DEFAULTS,
    CANCEL = CONTROLS_UI_CANCEL,
    APPLY = CONTROLS_UI_APPLY,
    OK = CONTROLS_UI_OK,
    YES = CONTROLS_UI_YES,
    NO = CONTROLS_UI_NO,
    KEEP = CONTROLS_UI_KEEP,
    ROW = CONTROLS_UI_BINDING,  /* ROW + row * 2 + slot */
    DIAGRAM = CONTROLS_UI_PAD,  /* DIAGRAM + destination */
    CHOICE = CONTROLS_UI_CHOICE /* CHOICE + device-list entry */
};

/* Logical metrics (before `scale`). */
enum {
    PAD = 18,
    GAP = 16,
    HEADER_H = 74,
    ROW_H_MOUSE = 22,
    HEAD_H = 24,
    BTN_H_MOUSE = 30,
    FOOTER_H = 54,
    NAME_W = 106,
    SLOT_W = 172,
    KEY_W = 224,
    POPUP_ROW_MOUSE = 26,
    POPUP_ROWS = 8,
    DIAGRAM_MIN = 250,
    DIAGRAM_MAX = 520,
    MIN_W = 560,
    MIN_H = 440,
    SIZE_W = 940,
    SIZE_H = 900,
    FIXED_LINES = 3 /* the fixed keys' text, under its heading */
};

/* Rows, buttons and the device list's entries: a finger's target tall with
 * a finger (touch, in pixels; 0 with a mouse), else the sizes above. */
static int touch, row_h = ROW_H_MOUSE, btn_h = BTN_H_MOUSE, popup_row = POPUP_ROW_MOUSE;
#define ROW_H row_h
#define BTN_H btn_h
#define POPUP_ROW popup_row

/* Status severity: picks the color of the message line. */
enum { SAY_INFO, SAY_DONE, SAY_WARN, SAY_BUSY };

typedef struct {
    int x, y, w, h;
} Rect;
typedef struct {
    int x, y, w, h, id;
} Hit;

static struct {
    ControlsConfig draft;
    int player, tab, row, slot, scroll, scroll_max, lines_shown, focus, hover, close, modal, popup,
        popup_scroll, popup_max, width, height;
    int host_scroll, host_scroll_max, host_lines_shown, pointer_x, pointer_y; /* the Game list's view */
    int count, mods, selected_device, draw_scale, say;
    int click_id, click_x, click_y;
    uint64_t click_time;
    /* With a finger: the page's scroll, its most, and the view it shows
     * (header to message line); reveal: bring the selected row into it. */
    int page_scroll, page_max, view_top, view_bottom, reveal, drag_rest;
    int keyed; /* with a finger: a key moved the focus last, so its ring shows */
    Hit hits[320];
    ControlCapture capture;
    ControlsEvaluator preview;
    char status[1200];
} ui;
static MenuCanvas *canvas;
static int scale;
/* While the page is drawn with a finger: its offset on the canvas, and the
 * rows a hit may take (the view between the header and the message line);
 * 0 and none otherwise. */
static int offset_y, clip_top, clip_bottom;
/* The top of each row's line on the page, from the last draw (reveal). */
static int row_page_y[CTRL_ROW_COUNT];
/* Where the last draw put each pad button (the drawn shape, not its larger
 * mouse target); ControlsWindow_Locate reports these for the picture. */
static Rect pad_rect[CTRL_DEST_COUNT];
static Rect list_rect[2]; /* where the last draw put the pad list and the Game list */
static Rect device_drop; /* set while drawing; the device list hangs off it */

static const uint32_t bg = 0xff1e1f22, panel = 0xff27282c, raised = 0xff34363b, hot = 0xff42454d,
                      sunken = 0xff232427, edge = 0xff4a4d55, edge_off = 0xff2f3136, text = 0xffe8e8ea,
                      dim = 0xff9a9ca3, faint = 0xff6c6e76, off = 0xff55575e,
                      accent = 0xff3b82f6, accent_hot = 0xff5a97f8, on_accent = 0xffffffff,
                      held = 0xff2f7d55, held_cell = 0xff26603f, on_held = 0xffeafff3,
                      good = 0xff4cc38a, warn = 0xfff5b642,
                      /* The pad picture's selection ring: bright grey-green,
                       * clear of both the cyan artwork and the pressed fill. */
                      marker = 0xff8ccda0;

/* ------------------------------------------------------------------ */
/*  Reading order for the table                                        */
/* ------------------------------------------------------------------ */

typedef struct {
    const char *title;
    int first, count;
} Group;
typedef struct {
    const char *title; /* the name column's heading */
    const int *order;
    const Group *groups;
    int group_count, row_count;
} List;
static const int pad_order[CTRL_DEST_COUNT] = {4,  6,  7,  5,  /* Up Down Left Right */
                                               12, 13, 14, 15, /* Triangle Circle Cross Square */
                                               10, 11, 8,  9,  /* L1 R1 L2 R2 */
                                               1,  2,          /* L3 R3 */
                                               3,  0};         /* Start Select */
static const Group pad_groups[] = {{"D-pad", 0, 4},
                                   {"Face buttons", 4, 4},
                                   {"Shoulders and triggers", 8, 4},
                                   {"Stick clicks", 12, 2},
                                   {"System", 14, 2}};
#define H(action) (CTRL_DEST_COUNT + CTRL_HOST_##action)
static const int host_order[CTRL_HOST_COUNT] = {H(EXIT),       H(FULLSCREEN), H(SCREENSHOT), H(MUTE),
                                                H(VOLUME_UP),  H(VOLUME_DOWN), H(SAVE_STATE), H(LOAD_STATE),
                                                H(SLOT_1),     H(SLOT_2),     H(SLOT_3),     H(SLOT_4),
                                                H(PAUSE),      H(FRAME_STEP), H(TURBO),      H(HUD),
                                                H(DECK_SLOTS)};
#undef H
static const Group host_groups[] = {{"Program", 0, 6}, {"Save states", 6, 6}, {"Speed", 12, 3}, {"Tools", 15, 2}};
static const List lists[2] = {{"PS1 BUTTON", pad_order, pad_groups, 5, CTRL_DEST_COUNT},
                              {"GAME", host_order, host_groups, 4, CTRL_HOST_COUNT}};
/* The pad keys, then the Game list's (list_rect, lists). */
static int list_of(int row) { return row >= CTRL_DEST_COUNT; }
static int list_lines(int list) { return lists[list].row_count + lists[list].group_count; }

/* What the backends keep for themselves, shown under the Game list. */
static const char fixed_keys[] = "F10: menu bar.  Alt+Enter: fullscreen.  Shift + Screenshot: whole window.  "
                                 "Esc: quit (asking first), leave fullscreen, close menus, dialogs and this window.";

/* Table line -> row, or -1 for a group heading. */
static int line_action(int list, int line, int *group_out)
{
    const List *l = &lists[list];
    int at = 0;
    for (int g = 0; g < l->group_count; g++) {
        if (line == at) {
            if (group_out)
                *group_out = g;
            return -1;
        }
        at++;
        if (line < at + l->groups[g].count) {
            if (group_out)
                *group_out = g;
            return l->order[l->groups[g].first + line - at];
        }
        at += l->groups[g].count;
    }
    if (group_out)
        *group_out = 0;
    return -1;
}
static int action_line(int action)
{
    for (int line = 0; line < list_lines(list_of(action)); line++)
        if (line_action(list_of(action), line, NULL) == action)
            return line;
    return 0;
}
static const char *action_group(int action)
{
    int group = 0;
    line_action(list_of(action), action_line(action), &group);
    return lists[list_of(action)].groups[group].title;
}

/* ------------------------------------------------------------------ */
/*  State helpers                                                      */
/* ------------------------------------------------------------------ */

static int dirty(void) { return !Controls_Equal(&ui.draft, ControlsRuntime_Config()); }
static ControlsProfile *profile(int create)
{
    return ui.tab ? ControlsRuntime_Profile(&ui.draft, ui.player, create) : &ui.draft.kb;
}
static int current_device(void) { return ControlsRuntime_Assigned(&ui.draft, ui.player); }
static const char *source_label(const ControlSource *src)
{
    CtrlIconStyle style = *ControlsRuntime_Style(&ui.draft, ui.player, 0);
    ControllerDevice *d = ControlsRuntime_Device(current_device());
    if (style == CTRL_ICON_AUTOMATIC)
        style = d ? d->style : CTRL_ICON_GENERIC;
    return Controls_SourceLabel(src, style);
}

static void say(int kind, const char *s)
{
    ui.say = kind;
    snprintf(ui.status, sizeof(ui.status), "%s", s);
}

/* ------------------------------------------------------------------ */
/*  Drawing primitives                                                 */
/* ------------------------------------------------------------------ */

static Rect rect(int x, int y, int w, int h)
{
    Rect r = {x, y, w, h};
    return r;
}
static void fill(int x, int y, int w, int h, uint32_t color)
{
    y += offset_y;
    x *= scale;
    y *= scale;
    w *= scale;
    h *= scale;
    for (int j = y < 0 ? 0 : y; j < y + h && j < canvas->height; j++)
        for (int i = x < 0 ? 0 : x; i < x + w && i < canvas->width; i++)
            canvas->pixels[j * canvas->stride + i] = color;
}
static void box(int x, int y, int w, int h, uint32_t color)
{
    fill(x, y, w, 1, color);
    fill(x, y + h - 1, w, 1, color);
    fill(x, y, 1, h, color);
    fill(x + w - 1, y, 1, h, color);
}
static void frame(Rect r, uint32_t face, uint32_t border)
{
    fill(r.x, r.y, r.w, r.h, face);
    box(r.x, r.y, r.w, r.h, border);
}
/* The keyboard-focus ring sits just outside the widget it belongs to. With
 * a finger it shows only once a key has moved the focus. */
static void ring(Rect r)
{
    if (touch && !ui.keyed)
        return;
    box(r.x - 1, r.y - 1, r.w + 2, r.h + 2, accent);
    box(r.x - 2, r.y - 2, r.w + 4, r.h + 4, accent);
}
/* Darken what is already on the canvas: the scrim behind a dialog. */
static void shade(int x, int y, int w, int h)
{
    y += offset_y;
    x *= scale;
    y *= scale;
    w *= scale;
    h *= scale;
    for (int j = y < 0 ? 0 : y; j < y + h && j < canvas->height; j++)
        for (int i = x < 0 ? 0 : x; i < x + w && i < canvas->width; i++) {
            uint32_t p = canvas->pixels[j * canvas->stride + i];
            canvas->pixels[j * canvas->stride + i] = 0xff000000u | ((p >> 16 & 255) * 2 / 5) << 16 |
                                                     ((p >> 8 & 255) * 2 / 5) << 8 | (p & 255) * 2 / 5;
        }
}
static void ellipse(int cx, int cy, int rx, int ry, uint32_t color)
{
    if (rx < 1 || ry < 1)
        return;
    for (int y = -ry; y <= ry; y++)
        for (int x = -rx; x <= rx; x++)
            if ((long)x * x * ry * ry + (long)y * y * rx * rx <= (long)rx * rx * ry * ry)
                fill(cx + x, cy + y, 1, 1, color);
}
/* A dropdown's downward triangle; the font has no arrow glyphs. */
static void caret(int cx, int cy, uint32_t color)
{
    for (int i = 0; i < 4; i++)
        fill(cx - 3 + i, cy - 2 + i, 7 - 2 * i, 1, color);
}

static int text_w(const char *s) { return (Menu_TextWidthScaled(s, scale) + scale - 1) / scale; }
static void text_at(int x, int middle, const char *s, uint32_t color)
{
    Menu_DrawTextScaled(canvas, x * scale, (middle + offset_y) * scale, s, color, scale);
}
/* `s` in `buf`, cut a whole character at a time to fit `width`, its last
 * three characters "..." when anything was cut. */
static void clip(char *buf, size_t size, const char *s, int width)
{
    snprintf(buf, size, "%s", s);
    Menu_TextTrim(buf);
    size_t n = strlen(buf);
    while (n && text_w(buf) > width)
        buf[n = Menu_TextBack(buf, n)] = 0;
    if (n < strlen(s) && n > 3) {
        for (int i = 0; i < 3; i++)
            n = Menu_TextBack(buf, n);
        memcpy(buf + n, "...", 4);
    }
}
static void text_clip(int x, int middle, const char *s, int width, uint32_t color)
{
    char buf[256];
    clip(buf, sizeof(buf), s, width);
    text_at(x, middle, buf, color);
}
static void text_right(int right, int middle, const char *s, uint32_t color)
{
    text_at(right - text_w(s), middle, s, color);
}
static void text_right_clip(int right, int middle, const char *s, int width, uint32_t color)
{
    char buf[256];
    clip(buf, sizeof(buf), s, width);
    text_right(right, middle, buf, color);
}
/* Word-wrapped body text for the dialogs. With `draw` clear it only counts
 * the lines, so a dialog can size itself before it paints. */
static int text_wrap(int x, int middle, const char *s, int width, uint32_t color, int max_lines, int draw)
{
    char line[256];
    int lines = 0;
    while (*s && lines < max_lines) {
        size_t best = 0, at = 0;
        for (;;) {
            size_t end = at;
            while (s[end] == ' ')
                end++;
            while (s[end] && s[end] != ' ')
                end++;
            if (end == at || end >= sizeof(line))
                break;
            memcpy(line, s, end);
            line[end] = 0;
            if (best && text_w(line) > width)
                break;
            best = at = end;
            if (!s[end])
                break;
        }
        if (!best)
            best = Menu_TextFit(s, sizeof(line) - 1);
        memcpy(line, s, best);
        line[best] = 0;
        if (draw)
            text_clip(x, middle + lines * 18, line, width, color);
        s += best;
        while (*s == ' ')
            s++;
        lines++;
    }
    return lines;
}

static void hit(int id, Rect r)
{
    r.y += offset_y;
    if (clip_bottom > clip_top) { /* a scrolled page: only what shows in its view */
        int bottom = r.y + r.h < clip_bottom ? r.y + r.h : clip_bottom;
        if (r.y < clip_top)
            r.y = clip_top;
        r.h = bottom - r.y;
        if (r.h <= 0)
            return;
    }
    if (ui.count < (int)(sizeof(ui.hits) / sizeof(ui.hits[0])))
        ui.hits[ui.count++] = (Hit){r.x, r.y, r.w, r.h, id};
}

/* BTN_READY is a normal button with something waiting behind it: Apply while
 * the draft differs from the saved configuration. A disabled button loses its
 * raised face as well as its contrast, so the two cannot be confused. */
enum { BTN_NORMAL, BTN_PRIMARY, BTN_READY, BTN_QUIET };
static int button_w(const char *label) { return text_w(label) + 28; }
static void button(int id, Rect r, const char *label, int style)
{
    int hovered = ui.hover == id;
    uint32_t face = style == BTN_PRIMARY ? (hovered ? accent_hot : accent)
                    : style == BTN_QUIET ? sunken
                    : hovered             ? hot
                                          : raised;
    uint32_t ink = style == BTN_PRIMARY ? on_accent : style == BTN_QUIET ? off : text;
    frame(r, face,
          style == BTN_PRIMARY  ? accent_hot
          : style == BTN_READY  ? accent
          : style == BTN_QUIET  ? edge_off
                                : edge);
    text_clip(r.x + (r.w - text_w(label)) / 2, r.y + r.h / 2, label, r.w - 12, ink);
    if (ui.focus == id)
        ring(r);
    hit(id, r);
}

/* ------------------------------------------------------------------ */
/*  Capture and actions                                                */
/* ------------------------------------------------------------------ */

static void cancel_capture(void)
{
    ui.capture.state = CAP_IDLE;
    say(SAY_INFO, "Binding unchanged.");
}
static void apply(int close)
{
    if (ControlsRuntime_Apply(&ui.draft, ui.status, sizeof(ui.status))) {
        say(SAY_DONE, "Controls saved.");
        ui.modal = 0;
        ui.close = close;
    } else
        ui.say = SAY_WARN;
}
void ControlsWindow_RequestClose(void)
{
    if (ui.capture.state) {
        cancel_capture();
        return;
    }
    if (dirty()) {
        ui.modal = 1;
        ui.focus = YES;
    } else
        ui.close = 1;
}
void ControlsWindow_Init(void)
{
    memset(&ui, 0, sizeof(ui));
    memset(row_page_y, 0, sizeof(row_page_y));
    ui.draft = *ControlsRuntime_Config();
    ui.focus = KEYBOARD;
    ui.row = pad_order[0];
    ui.selected_device = -1;
    /* The message line starts empty: it reports what happened, and the hint
     * line above it already says how to edit a binding. */
    if (ControlsRuntime_Error()[0])
        say(SAY_WARN, ControlsRuntime_Error());
    ControlsRuntime_Block(1);
}
void ControlsWindow_Size(int *w, int *h)
{
    *w = SIZE_W * Menu_Scale();
    *h = SIZE_H * Menu_Scale();
}
void ControlsWindow_MinSize(int *w, int *h)
{
    *w = MIN_W;
    *h = MIN_H;
}
int ControlsWindow_ShouldClose(void) { return ui.close; }
int ControlsWindow_Locate(int id, int *x, int *y)
{
    int sc = ui.draw_scale ? ui.draw_scale : 1;
    if (id >= DIAGRAM && id < CHOICE && id - DIAGRAM < CTRL_DEST_COUNT) {
        Rect *r = &pad_rect[id - DIAGRAM];
        if (!r->w)
            return 0;
        *x = (r->x + r->w / 2) * sc;
        *y = (r->y + r->h / 2) * sc;
        return 1;
    }
    for (int i = ui.count - 1; i >= 0; i--) {
        if (ui.hits[i].id != id)
            continue;
        *x = (ui.hits[i].x + ui.hits[i].w / 2) * sc;
        *y = (ui.hits[i].y + ui.hits[i].h / 2) * sc;
        return 1;
    }
    return 0;
}
void ControlsWindow_FocusLost(void)
{
    ui.click_id = 0;
    ui.hover = 0;
    if (ui.capture.state)
        cancel_capture();
    ControlsRuntime_ResetKeys();
}
static void start_capture(void)
{
    ui.click_id = 0;
    if (!ui.tab && ui.player) {
        say(SAY_WARN, "The keyboard always plays as Player 1.");
        return;
    }
    if (ui.tab && ui.draft.profile_count == CTRL_PROFILE_MAX) {
        int found = 0, dev = current_device();
        for (int i = 0; i < ui.draft.profile_count; i++)
            if (dev >= 0 && !strcmp(ui.draft.profiles[i].identity, ControlsRuntime_Device(dev)->identity))
                found = 1;
        if (!found) {
            say(SAY_WARN, "Profile limit reached. Remove old profiles from controls.txt before adding more.");
            return;
        }
    }
    if (ui.tab && current_device() < 0) {
        say(SAY_WARN, "Connect a controller and choose it above before rebinding.");
        return;
    }
    ui.modal = 0;
    ui.popup = 0;
    Controls_CaptureBegin(&ui.capture, ui.row, ui.slot, ControlsRuntime_Now());
    say(SAY_BUSY, "Release everything you are holding, then press the input you want.");
}
/* Keep the selected line, and its heading where possible, inside its list's
 * view. */
static void reveal_row(void)
{
    int line = action_line(ui.row), host = list_of(ui.row);
    int *scroll = host ? &ui.host_scroll : &ui.scroll, shown = host ? ui.host_lines_shown : ui.lines_shown;
    if (!shown)
        return;
    if (line - 1 < *scroll)
        *scroll = line - 1 < 0 ? 0 : line - 1;
    if (line >= *scroll + shown)
        *scroll = line - shown + 1;
}
static void select_row(int action, int slot)
{
    ui.row = action;
    ui.slot = slot;
    ui.focus = ROW + action * 2 + slot;
    reveal_row();
    ui.reveal = 1;
}
/* Arrows stay in the selected row's list; Tab goes from one to the other. */
static void move_row(int delta)
{
    const List *l = &lists[list_of(ui.row)];
    int at = 0;
    for (int i = 0; i < l->row_count; i++)
        if (l->order[i] == ui.row)
            at = i;
    select_row(l->order[(at + delta + l->row_count) % l->row_count], ui.slot);
}
static void activate(int id)
{
    if (id >= CHOICE) {
        int choice = id - CHOICE;
        if (choice == CONTROLS_DEVICES + 2) {
            ui.popup = 0;
            return;
        }
        if (ui.popup == DEVICE) {
            ControlsPort *p = &ui.draft.port[ui.player];
            if (choice < 2) {
                p->mode = choice == 0 ? 1 : 0;
                p->identity[0] = 0;
                say(SAY_INFO, choice == 0 ? "This player uses the first free controller."
                                          : "This player's controller is switched off.");
            } else {
                ControllerDevice *d = ControlsRuntime_Device(choice - 2);
                if (!d || !d->connected)
                    return;
                if (d->ambiguous)
                    say(SAY_WARN, "Two identical controllers: choose this one again after restarting the game.");
                ControlsPort *other = &ui.draft.port[1 - ui.player];
                if (other->mode == 2 && !strcmp(other->identity, d->identity)) {
                    say(SAY_WARN, "That controller belongs to the other player. Release it there first.");
                    ui.popup = 0;
                    return;
                }
                p->mode = 2;
                snprintf(p->identity, sizeof(p->identity), "%s", d->identity);
            }
        }
        ui.popup = 0;
        ui.capture.state = CAP_IDLE;
        memset(&ui.preview, 0, sizeof(ui.preview));
        return;
    }
    if (id >= ROW && id < DIAGRAM) {
        select_row((id - ROW) / 2, (id - ROW) % 2);
        return;
    }
    switch (id) {
    case PLAYER:
    case PLAYER_2: {
        int player = id == PLAYER ? 0 : 1;
        if (player == ui.player)
            break;
        ui.player = player;
        if (ui.player)
            ui.tab = 1;
        ui.capture.state = CAP_IDLE;
        ui.popup = 0;
        memset(&ui.preview, 0, sizeof(ui.preview));
        break;
    }
    case DEVICE:
        ui.popup = ui.popup == id ? 0 : id;
        ui.popup_scroll = 0;
        break;
    case KEYBOARD:
        if (ui.player) {
            say(SAY_WARN, "The keyboard always plays as Player 1. Switch to Player 1 to edit it.");
            break;
        }
        if (ui.tab)
            ui.page_scroll = 0;
        ui.tab = 0;
        ui.slot = 0;
        ui.capture.state = CAP_IDLE;
        break;
    case CONTROLLER:
        if (!ui.tab)
            ui.page_scroll = 0; /* with a finger: the other tab's page from its top */
        ui.tab = 1;
        ui.capture.state = CAP_IDLE;
        break;
    case REBIND:
        if (ui.capture.state)
            cancel_capture();
        else
            start_capture();
        break;
    case CLEAR:
        if (Controls_Row(profile(0), ui.row)[ui.slot].kind == CTRL_SRC_UNBOUND) {
            say(SAY_INFO, "That slot is already empty.");
            break;
        }
        Controls_ClearSlot(profile(1), ui.row, ui.slot);
        /* Esc cancels a capture, so it cannot be pressed back in. */
        say(SAY_INFO, ui.row == CTRL_ROW_EXIT && !ui.tab
                          ? "Exit game cleared; Esc still quits. Apply to save."
                          : "Binding cleared. Apply to save.");
        break;
    case DEFAULTS:
        ui.modal = 2;
        ui.focus = YES;
        break;
    case CANCEL:
        ui.close = 1;
        break;
    case APPLY:
        if (!dirty()) {
            say(SAY_INFO, "Nothing to save.");
            break;
        }
        apply(0);
        break;
    case OK:
        if (dirty())
            apply(1);
        else
            ui.close = 1;
        break;
    case YES:
        if (ui.modal == 1)
            apply(1);
        else if (ui.modal == 2) {
            ControlsConfig defaults;
            Controls_InitDefaults(&defaults);
            *profile(1) = ui.tab ? defaults.ctrl[ui.player] : defaults.kb;
            ui.modal = 0;
            say(SAY_INFO, "Defaults restored. Apply to save.");
        } else if (ui.modal == 3) {
            Controls_MoveSource(profile(1), ui.row, ui.slot, &ui.capture.pending);
            ui.capture.state = CAP_IDLE;
            ui.modal = 0;
            say(SAY_INFO, "Binding moved. Apply to save.");
        }
        break;
    case NO:
        if (ui.modal == 1)
            ui.close = 1;
        else {
            ui.modal = 0;
            cancel_capture();
        }
        break;
    case KEEP:
        ui.modal = 0;
        break;
    }
}

/* ------------------------------------------------------------------ */
/*  Events                                                             */
/* ------------------------------------------------------------------ */

static int hit_at(int x, int y)
{
    for (int i = ui.count - 1; i >= 0; i--) {
        Hit *h = &ui.hits[i];
        if (x >= h->x && x < h->x + h->w && y >= h->y && y < h->y + h->h)
            return i;
    }
    return -1;
}
void ControlsWindow_Event(const MenuEvent *e)
{
    int sc = ui.draw_scale ? ui.draw_scale : 1;
    if (e->type == MENU_EVENT_LEAVE) {
        ui.hover = 0;
        return;
    }
    if (e->type == MENU_EVENT_MOTION) {
        int at = hit_at(e->x / sc, e->y / sc);
        ui.pointer_x = e->x / sc;
        ui.pointer_y = e->y / sc;
        ui.hover = at < 0 ? 0 : ui.hits[at].id;
        return;
    }
    if (e->type == MENU_EVENT_WHEEL) {
        ui.click_id = 0;
        if (touch && !ui.popup) {
            /* The lists are at full length on the page: the wheel scrolls
             * the page, a row per notch, as a finger's drag does. */
            ControlsWindow_Drag(0, 0, e->wheel * ROW_H * (ui.draw_scale ? ui.draw_scale : 1));
            return;
        }
        /* The wheel scrolls the list under the pointer. */
        Rect g = list_rect[1];
        int host = !ui.popup && ui.pointer_x >= g.x && ui.pointer_x < g.x + g.w && ui.pointer_y >= g.y &&
                   ui.pointer_y < g.y + g.h;
        int *offset = ui.popup ? &ui.popup_scroll : host ? &ui.host_scroll : &ui.scroll;
        int maximum = ui.popup ? ui.popup_max : host ? ui.host_scroll_max : ui.scroll_max;
        *offset -= e->wheel;
        if (*offset > maximum)
            *offset = maximum;
        if (*offset < 0)
            *offset = 0;
        return;
    }
    if (e->type != MENU_EVENT_BUTTON_DOWN || e->button != 1)
        return;
    int x = e->x / sc, y = e->y / sc, at = hit_at(x, y);
    ui.keyed = 0;
    if (ui.capture.state && !ui.modal) {
        /* Any click during capture means "stop listening", hit or miss. */
        ui.click_id = 0;
        cancel_capture();
        return;
    }
    if (at < 0) {
        ui.click_id = 0;
        ui.popup = 0;
        return;
    }
    Hit *h = &ui.hits[at];
    uint64_t now = ControlsRuntime_Now();
    int control = h->id >= ROW && h->id < CHOICE;
    int double_click = control && ui.click_id == h->id && now - ui.click_time <= 400000 &&
                       abs(x - ui.click_x) <= 5 && abs(y - ui.click_y) <= 5;
    ui.click_id = control ? h->id : 0;
    ui.click_time = now;
    ui.click_x = x;
    ui.click_y = y;
    ui.focus = h->id;
    if (h->id >= DIAGRAM && h->id < CHOICE) {
        select_row(h->id - DIAGRAM, 0);
        say(SAY_INFO, Controls_Actions[ui.row].name);
        if (double_click)
            start_capture();
        return;
    }
    activate(h->id);
    if (double_click)
        start_capture();
}
/* Tab order: everything that was drawn, except the pad picture, which is a
 * mouse shortcut into the table rather than a separate control. */
static void focus_step(int delta)
{
    int at = -1;
    for (int i = 0; i < ui.count; i++)
        if (ui.hits[i].id == ui.focus) {
            at = i;
            break;
        }
    if (at < 0)
        at = delta > 0 ? -1 : 0;
    for (int i = 0; i < ui.count; i++) {
        at = (at + delta + ui.count) % ui.count;
        int id = ui.hits[at].id;
        if (id == ui.focus || (id >= DIAGRAM && id < CHOICE))
            continue;
        ui.focus = id;
        break;
    }
    if (ui.focus >= ROW && ui.focus < DIAGRAM)
        select_row((ui.focus - ROW) / 2, (ui.focus - ROW) % 2);
}
void ControlsWindow_Key(int key, int down, int repeat, int modifiers)
{
    ui.mods = modifiers;
    if (!down || repeat)
        return;
    ui.keyed = 1;
    ui.click_id = 0;
    if (key == CTRL_KEY_ESCAPE) {
        if (ui.modal) {
            ui.modal = 0;
            cancel_capture();
        } else if (ui.popup)
            ui.popup = 0;
        else
            ControlsWindow_RequestClose();
        return;
    }
    if (ui.capture.state) {
        if (!key)
            say(SAY_WARN, "That key is not supported. Choose a standard keyboard key.");
        return;
    }
    if (key == CTRL_KEY_TAB) {
        focus_step(modifiers & 1 ? -1 : 1);
    } else if (key == CTRL_KEY_ENTER || key == CTRL_KEY_SPACE) {
        if (ui.focus >= ROW && ui.focus < DIAGRAM)
            start_capture();
        else
            activate(ui.focus);
    } else if ((key == CTRL_KEY_DELETE || key == CTRL_KEY_BACKSPACE) && !ui.modal && !ui.popup &&
               ui.focus >= ROW && ui.focus < DIAGRAM) {
        activate(CLEAR);
    } else if ((key == CTRL_KEY_PAGE_UP || key == CTRL_KEY_PAGE_DOWN) && touch) {
        if (!ui.modal && !ui.popup)
            ControlsWindow_Drag(0, 0, (key == CTRL_KEY_PAGE_DOWN ? -1 : 1) *
                                          (ui.view_bottom - ui.view_top - ROW_H) * (ui.draw_scale ? ui.draw_scale : 1));
    } else if (key == CTRL_KEY_PAGE_UP || key == CTRL_KEY_PAGE_DOWN) {
        if (!ui.modal && !ui.popup) {
            int step = ui.lines_shown > 1 ? ui.lines_shown - 1 : 1;
            ui.scroll += key == CTRL_KEY_PAGE_DOWN ? step : -step;
            if (ui.scroll > ui.scroll_max)
                ui.scroll = ui.scroll_max;
            if (ui.scroll < 0)
                ui.scroll = 0;
        }
    } else if (key == CTRL_KEY_ARROW_DOWN || key == CTRL_KEY_ARROW_UP) {
        int delta = key == CTRL_KEY_ARROW_DOWN ? 1 : -1;
        if (ui.modal)
            focus_step(delta);
        else if (ui.popup) {
            int choices[CONTROLS_DEVICES + 3], n = 0;
            choices[n++] = 0;
            choices[n++] = 1;
            if (ui.draft.port[ui.player].mode == 2 && current_device() < 0)
                choices[n++] = CONTROLS_DEVICES + 2;
            for (int i = 0; i < CONTROLS_DEVICES; i++)
                if (ControlsRuntime_Device(i)->connected)
                    choices[n++] = i + 2;
            int at = delta > 0 ? -1 : 0;
            for (int i = 0; i < n; i++)
                if (ui.focus == CHOICE + choices[i])
                    at = i;
            at = (at + delta + n) % n;
            ui.focus = CHOICE + choices[at];
            ui.popup_scroll = at > POPUP_ROWS - 1 ? at - (POPUP_ROWS - 1) : 0;
        } else
            move_row(delta);
    } else if ((key == CTRL_KEY_ARROW_LEFT || key == CTRL_KEY_ARROW_RIGHT) && !ui.modal && !ui.popup) {
        if (ui.tab)
            select_row(ui.row, 1 - ui.slot);
    }
}
void ControlsWindow_Tick(void)
{
    ControlSource keys[CTRL_KEY_COUNT], sources[64];
    uint64_t now = ControlsRuntime_Now();
    int device = current_device(), n;
    if (device != ui.selected_device) {
        ui.click_id = 0;
        if (ui.selected_device >= 0 && ui.capture.state)
            cancel_capture();
        ui.selected_device = device;
        memset(&ui.preview, 0, sizeof(ui.preview));
    }
    ControllerDevice *d = ControlsRuntime_Device(device);
    if (ui.capture.state && ui.modal != 3) {
        if (ui.tab && (!d || !d->connected)) {
            cancel_capture();
            say(SAY_WARN, "Controller disconnected; binding unchanged.");
            return;
        }
        n = ui.tab ? ControlsRuntime_Sources(d, sources, 64, ui.capture.state == CAP_WAIT_NEUTRAL)
                   : ControlsRuntime_Keys(keys);
        ControlSource *src = n ? (ui.tab ? sources : keys) : NULL;
        if ((ui.mods || n > 1) && !ui.tab && ui.capture.state == CAP_AWAIT_INPUT) {
            say(SAY_WARN, "Key combinations cannot be bound. Release the keys and try again.");
            if (now >= ui.capture.deadline_us)
                cancel_capture();
            return;
        }
        int result = Controls_CaptureStep(&ui.capture, profile(0), src, ui.tab && device >= 0, now);
        if (result == CAPTURE_DONE) {
            Controls_MoveSource(profile(1), ui.row, ui.slot, &ui.capture.pending);
            say(SAY_DONE, "Binding updated. Apply to save.");
        } else if (result == CAPTURE_CONFLICT) {
            ui.modal = 3;
            ui.focus = YES;
        } else if (result == CAPTURE_REJECT_RESERVED)
            say(SAY_WARN, Controls_ReservedReason(src->code, Controls_IsModifier(src->code)));
        else if (result == CAPTURE_RESET)
            say(SAY_WARN, "Nothing was pressed in time; binding unchanged.");
    }
}

/* ------------------------------------------------------------------ */
/*  The pad picture                                                    */
/* ------------------------------------------------------------------ */

/* Button regions in image coordinates normalized to a width of 1000, measured
 * from ps1-controller.png itself.
 *
 * Each button has two rectangles. `bx, by, bw, bh` is the button as it is
 * drawn: what the selection ring encloses and what a press fills. `x, y, w, h`
 * is where the mouse has to be, and those tile the picture instead of hugging
 * the artwork, because the drawn buttons are small, some (the L2/R2 strips)
 * only a few pixels tall, and neighbours would be a pixel apart. The D-pad
 * and the face cluster are each split four ways along the lines between their
 * buttons, the shoulders split just under the L2/R2 strip, and no two
 * rectangles overlap, so every click lands on exactly one button.
 *
 * The supplied digital pad has no stick clicks: L3/R3 stay in the list. */
static const struct {
    int destination, x, y, w, h, bx, by, bw, bh;
} controller_regions[] = {
    {8, 165, 55, 165, 45, 192, 80, 110, 17},        /* L2, the upper strip */
    {9, 668, 55, 165, 45, 695, 80, 110, 17},        /* R2 */
    {10, 165, 100, 165, 59, 165, 97, 165, 62},      /* L1 */
    {11, 668, 100, 165, 59, 668, 97, 165, 62},      /* R1 */
    {4, 130, 162, 234, 98, 218, 222, 58, 64},       /* Up: the D-pad's top */
    {5, 247, 260, 117, 81, 261, 272, 65, 57},       /* Right */
    {6, 130, 341, 234, 98, 218, 315, 58, 64},       /* Down */
    {7, 130, 260, 117, 81, 168, 272, 64, 57},       /* Left */
    {12, 620, 162, 261, 104, 714, 194, 73, 73},     /* Triangle: the top */
    {13, 750, 266, 131, 70, 785, 264, 73, 73},      /* Circle */
    {14, 620, 336, 261, 103, 714, 334, 73, 73},     /* Cross */
    {15, 620, 266, 130, 70, 642, 264, 73, 73},      /* Square */
    {0, 400, 320, 99, 70, 418, 337, 52, 36},        /* Select */
    {3, 500, 320, 99, 70, 526, 336, 58, 38}};       /* Start */
#define REGION_COUNT ((unsigned)(sizeof(controller_regions) / sizeof(controller_regions[0])))

/* The two rectangles of a region, placed on a picture drawn at (x, y, w). */
static Rect region_hit(unsigned i, int x, int y, int w)
{
    return rect(x + controller_regions[i].x * w / 1000, y + controller_regions[i].y * w / 1000,
                controller_regions[i].w * w / 1000, controller_regions[i].h * w / 1000);
}
static Rect region_button(unsigned i, int x, int y, int w)
{
    return rect(x + controller_regions[i].bx * w / 1000, y + controller_regions[i].by * w / 1000,
                controller_regions[i].bw * w / 1000, controller_regions[i].bh * w / 1000);
}

static void controller(int x, int y, int w, uint16_t bits)
{
    /* Pressed buttons are filled first so the artwork's own outlines stay on
     * top of the fill; the selection ring is drawn last, over everything. */
    for (unsigned i = 0; i < REGION_COUNT; i++) {
        int dest = controller_regions[i].destination;
        Rect b = region_button(i, x, y, w);
        pad_rect[dest] = b;
        pad_rect[dest].y += offset_y;
        if (bits & Controls_Actions[dest].bit)
            ellipse(b.x + b.w / 2, b.y + b.h / 2, b.w / 2, b.h / 2, held);
        hit(DIAGRAM + dest, region_hit(i, x, y, w));
    }
    if (!ControlsArt_Draw(canvas, x * scale, (y + offset_y) * scale, w * scale)) {
        text_at(x + 20, y + 40, "Controller picture unavailable", dim);
        return;
    }
    /* Tiny PS1 face symbols retain the original line drawing's open buttons. */
    for (unsigned i = 0; i < REGION_COUNT; i++) {
        int dest = controller_regions[i].destination;
        Rect b = region_button(i, x, y, w);
        int cx = b.x + b.w / 2, cy = b.y + b.h / 2;
        if (dest == 14)
            /* The cross and the triangle read a pixel low and right of the
             * circle they sit in; nudge both back. */
            for (int j = -4; j <= 4; j++) {
                fill(cx - 1 + j, cy - 1 + j, 1, 1, text);
                fill(cx - 1 + j, cy - 1 - j, 1, 1, text);
            }
        if (dest == 15)
            box(cx - 4, cy - 4, 9, 9, text);
        if (dest == 12) {
            for (int j = 0; j < 8; j++) {
                fill(cx - 1 - j / 2, cy - 5 + j, 1, 1, text);
                fill(cx - 1 + j / 2, cy - 5 + j, 1, 1, text);
            }
            fill(cx - 5, cy + 3, 9, 1, text);
        }
        if (dest == 13)
            for (int j = -5; j <= 5; j++)
                for (int k = -5; k <= 5; k++)
                    if (j * j + k * k >= 14 && j * j + k * k <= 23)
                        fill(cx + j, cy + k, 1, 1, text);
        /* L1/R1 are labelled inside their button; the L2/R2 strips are too
         * thin, so their labels sit just above them, and both are dropped
         * when the picture is too small to keep them apart. */
        if (dest >= 8 && dest <= 11 && b.h >= 10 && text_w(Controls_Actions[dest].name) + 4 <= b.w)
            text_at(cx - text_w(Controls_Actions[dest].name) / 2, dest <= 9 ? cy - 11 : cy,
                    Controls_Actions[dest].name, dim);
    }
    /* Selection and hover, over the artwork so nothing hides them. */
    for (unsigned i = 0; i < REGION_COUNT; i++) {
        int dest = controller_regions[i].destination;
        Rect b = region_button(i, x, y, w);
        if (ui.row == dest)
            for (int ring_px = 1; ring_px <= 3; ring_px++)
                box(b.x - ring_px, b.y - ring_px, b.w + 2 * ring_px, b.h + 2 * ring_px, marker);
        else if (ui.hover == DIAGRAM + dest)
            box(b.x - 2, b.y - 2, b.w + 4, b.h + 4, edge);
    }
}

/* ------------------------------------------------------------------ */
/*  Panels                                                             */
/* ------------------------------------------------------------------ */

static void held_summary(char *out, size_t size, uint16_t bits)
{
    size_t at = 0;
    out[0] = 0;
    for (int i = 0; i < CTRL_DEST_COUNT && at + 1 < size; i++) {
        int action = pad_order[i];
        if (!(bits & Controls_Actions[action].bit))
            continue;
        int wrote = snprintf(out + at, size - at, "%s%s", at ? ", " : "", Controls_Actions[action].name);
        if (wrote < 0 || (size_t)wrote >= size - at)
            break;
        at += (size_t)wrote;
    }
}

static void draw_diagram(Rect r, uint16_t bits)
{
    char live[160];
    frame(r, panel, edge);
    int title_mid = r.y + 18, title_w = text_w("PlayStation pad");
    text_clip(r.x + 12, title_mid, "PlayStation pad", r.w - 24, dim);
    held_summary(live, sizeof(live), bits);
    int room = r.w - 36 - title_w;
    if (room > 40)
        text_right_clip(r.x + r.w - 12, title_mid, live[0] ? live : "nothing pressed", room,
                        live[0] ? on_held : faint);

    int legend_lines = r.w >= 330 ? 3 : 2;
    int legend_h = legend_lines * 18 + 10;
    int art_top = r.y + 34, art_w = r.w - 24;
    int art_room = r.h - (art_top - r.y) - legend_h;
    if (ControlsArt_Height(art_w) > art_room)
        art_w = art_room * 1474 / 1067;
    if (art_w > 8)
        controller(r.x + (r.w - art_w) / 2, art_top + (art_room - ControlsArt_Height(art_w)) / 2, art_w,
                   bits);

    int y = r.y + r.h - legend_h + 4, swatch = 10;
    fill(r.x + 12, y + 3, swatch, swatch, held);
    text_at(r.x + 12 + swatch + 6, y + 8, "pressed now", faint);
    int x = r.x + 12 + swatch + 6 + text_w("pressed now") + 18;
    box(x, y + 3, swatch, swatch, marker);
    box(x + 1, y + 4, swatch - 2, swatch - 2, marker);
    text_at(x + swatch + 6, y + 8, "selected", faint);
    text_clip(r.x + 12, y + 26, touch ? "Tap a button here to jump to its row." : "Click a button here to jump to its row.",
              r.w - 24, faint);
    if (legend_lines > 2)
        text_clip(r.x + 12, y + 44,
                  ui.tab ? "Stick clicks (L3/R3) are in the list only."
                         : "The picture always shows a PlayStation pad.",
                  r.w - 24, faint);
}

/* How many lines of a list a panel of this height shows, and the height
 * that exactly holds them: the panels are sized from this so they end level. */
static int table_lines(int height, int list)
{
    int shown = (height - HEAD_H - 11) / ROW_H;
    if (shown < 1)
        shown = 1;
    return shown > list_lines(list) ? list_lines(list) : shown;
}
static int table_height(int height, int list) { return HEAD_H + 11 + table_lines(height, list) * ROW_H; }

static void draw_table(Rect r, uint64_t rows, int list)
{
    const ControlsProfile *p = profile(0);
    int slots = ui.tab ? 2 : 1, lines = list_lines(list);
    int *scroll = list ? &ui.host_scroll : &ui.scroll, *scroll_max = list ? &ui.host_scroll_max : &ui.scroll_max;
    list_rect[list] = r;
    frame(r, panel, edge);
    fill(r.x + 1, r.y + 1, r.w - 2, HEAD_H - 1, raised);
    fill(r.x + 1, r.y + HEAD_H, r.w - 2, 1, edge);

    int top = r.y + HEAD_H + 5;
    int shown = table_lines(r.h, list);
    *(list ? &ui.host_lines_shown : &ui.lines_shown) = shown;
    *scroll_max = lines - shown;
    if (*scroll > *scroll_max)
        *scroll = *scroll_max;
    if (*scroll < 0)
        *scroll = 0;

    int bar = *scroll_max ? 10 : 0;
    int x = r.x + 8, inner = r.w - 16 - bar;
    int slot_w = (inner - NAME_W - (slots - 1) * 6) / slots;
    int head_mid = r.y + HEAD_H / 2;
    text_clip(x + 10, head_mid, lists[list].title, NAME_W - 14, faint);
    text_clip(x + NAME_W + 7, head_mid, ui.tab ? "BINDING" : "KEYBOARD KEY", slot_w - 14, faint);
    if (slots > 1)
        text_clip(x + NAME_W + slot_w + 13, head_mid, "ALTERNATE", slot_w - 14, faint);

    for (int i = 0; i < shown; i++) {
        int line = *scroll + i, group = 0;
        int action = line_action(list, line, &group);
        int y = top + i * ROW_H, mid = y + (ROW_H - 2) / 2;
        if (action < 0) {
            const char *title = lists[list].groups[group].title;
            int tw = text_w(title);
            text_at(x + 6, mid, title, faint);
            fill(x + 12 + tw, mid, inner - tw - 18, 1, edge);
            continue;
        }
        int down = rows >> action & 1;
        int chosen = action == ui.row;
        row_page_y[action] = y;
        int over = ui.hover == ROW + action * 2 || ui.hover == ROW + action * 2 + 1;
        uint32_t row_face = down ? held : chosen ? hot : over ? raised : panel;
        fill(x, y, inner, ROW_H - 2, row_face);
        if (chosen)
            fill(x, y, 3, ROW_H - 2, accent);
        text_clip(x + 10, mid, Controls_RowName(action), NAME_W - 16, down ? on_held : text);
        hit(ROW + action * 2, rect(x, y, NAME_W, ROW_H - 2));
        for (int slot = 0; slot < slots; slot++) {
            Rect cell = rect(x + NAME_W + slot * (slot_w + 6), y, slot_w, ROW_H - 2);
            const ControlSource *src = &Controls_RowConst(p, action)[slot];
            int bound = src->kind != CTRL_SRC_UNBOUND;
            int target = chosen && slot == ui.slot;
            frame(cell, down ? held_cell : bg,
                  target ? accent : ui.hover == ROW + action * 2 + slot ? dim : edge);
            if (target && ui.capture.state)
                box(cell.x + 1, cell.y + 1, cell.w - 2, cell.h - 2, accent);
            text_clip(cell.x + 7, mid, bound ? source_label(src) : "Unbound", cell.w - 14,
                      !bound ? faint : down ? on_held : text);
            hit(ROW + action * 2 + slot, cell);
        }
    }
    if (*scroll_max) {
        int track = shown * ROW_H - 2, tx = r.x + r.w - 12;
        int knob = track * shown / lines;
        if (knob < 20)
            knob = 20;
        fill(tx, top, 5, track, bg);
        fill(tx, top + (track - knob) * *scroll / *scroll_max, 5, knob, edge);
    }
}

/* The fixed keys, for reference: text only, nothing to select. */
static int fixed_height(int width) { return 26 + text_wrap(0, 0, fixed_keys, width - 24, dim, FIXED_LINES, 0) * 18 + 6; }
static void draw_fixed(Rect r)
{
    frame(r, panel, edge);
    text_clip(r.x + 12, r.y + 14, "FIXED KEYS (not bindable)", r.w - 24, faint);
    text_wrap(r.x + 12, r.y + 34, fixed_keys, r.w - 24, dim, FIXED_LINES, 1);
}

/* The device list, drawn over everything else and owning every hit. */
static int device_entries(int *out)
{
    int count = 0;
    out[count++] = 0; /* Automatic */
    out[count++] = 1; /* None */
    if (ui.draft.port[ui.player].mode == 2 && current_device() < 0)
        out[count++] = CONTROLS_DEVICES + 2; /* the saved, absent device */
    for (int i = 0; i < CONTROLS_DEVICES; i++)
        if (ControlsRuntime_Device(i)->connected)
            out[count++] = i + 2;
    return count;
}
static int entry_chosen(int entry)
{
    const ControlsPort *p = &ui.draft.port[ui.player];
    if (entry == 0)
        return p->mode == 1;
    if (entry == 1)
        return p->mode == 0;
    if (entry == CONTROLS_DEVICES + 2)
        return p->mode == 2 && current_device() < 0;
    ControllerDevice *d = ControlsRuntime_Device(entry - 2);
    return p->mode == 2 && d && !strcmp(p->identity, d->identity);
}
static void draw_popup(Rect anchor)
{
    int entries[CONTROLS_DEVICES + 3], count = device_entries(entries), most = POPUP_ROWS;
    char line[256];
    ui.count = 0;
    if (touch) { /* finger-tall entries: as many as fit below the field, or above it */
        int below = ui.height - 8 - (anchor.y + anchor.h + 2) - 8, above = anchor.y - 2 - 8 - 8;
        most = (below > above ? below : above) / POPUP_ROW;
        most = most < 2 ? 2 : most > POPUP_ROWS ? POPUP_ROWS : most;
    }
    ui.popup_max = count > most ? count - most : 0;
    if (ui.popup_scroll > ui.popup_max)
        ui.popup_scroll = ui.popup_max;
    if (ui.popup_scroll < 0)
        ui.popup_scroll = 0;
    int shown = count - ui.popup_scroll;
    if (shown > most)
        shown = most;
    Rect list = rect(anchor.x, anchor.y + anchor.h + 2, anchor.w, shown * POPUP_ROW + 8);
    if (list.y + list.h > ui.height - 8)
        list.y = anchor.y - list.h - 2;
    shade(list.x + 3, list.y + 3, list.w, list.h);
    frame(list, raised, accent);
    for (int i = 0; i < shown; i++) {
        int entry = entries[ui.popup_scroll + i];
        Rect row = rect(list.x + 4, list.y + 4 + i * POPUP_ROW, list.w - 8, POPUP_ROW);
        const char *name;
        if (entry < 2)
            name = entry ? "None - no controller for this player" : "Automatic - first free controller";
        else if (entry == CONTROLS_DEVICES + 2)
            name = "Saved controller (not connected)";
        else {
            ControllerDevice *d = ControlsRuntime_Device(entry - 2);
            snprintf(line, sizeof(line), "%s #%d%s", d->name, entry - 1,
                     ControlsRuntime_Assigned(&ui.draft, 1 - ui.player) == entry - 2 ? "  (other player)"
                                                                                     : "");
            name = line;
        }
        int over = ui.hover == CHOICE + entry, focused = ui.focus == CHOICE + entry;
        if (over || focused)
            fill(row.x, row.y, row.w, row.h, focused ? accent : hot);
        if (entry_chosen(entry))
            ellipse(row.x + 12, row.y + row.h / 2, 3, 3, focused ? on_accent : accent);
        text_clip(row.x + 24, row.y + row.h / 2, name, row.w - 34, focused ? on_accent : text);
        hit(CHOICE + entry, row);
    }
    if (ui.popup_max)
        text_right(list.x + list.w - 8, list.y + list.h - 4, "scroll for more", faint);
}

static void draw_modal(void)
{
    char body[256];
    const char *title, *message;
    ui.count = 0;
    shade(0, 0, ui.width, ui.height);
    if (ui.modal == 1) {
        title = "Unsaved changes";
        message = "Save your new bindings before closing the window?";
    } else if (ui.modal == 2) {
        title = "Restore defaults";
        message = ui.tab ? "Restore the default bindings for this controller? Other players and the "
                           "keyboard are not touched."
                         : "Restore the default keyboard bindings? Controllers are not touched.";
    } else {
        int other = ui.capture.conflict_dest;
        snprintf(body, sizeof(body), "%s is already bound to %s. Move it to %s instead?",
                 source_label(&ui.capture.pending),
                 other >= 0 && other < CTRL_ROW_COUNT ? Controls_RowName(other) : "another button",
                 Controls_RowName(ui.row));
        title = "Input already in use";
        message = body;
    }
    int w = ui.width - 60 < 460 ? ui.width - 60 : 460;
    int lines = text_wrap(0, 0, message, w - 32, dim, 3, 0);
    int h = 30 + 26 + lines * 18 + 16 + BTN_H + 16;
    Rect m = rect((ui.width - w) / 2, (ui.height - h) / 2, w, h);
    frame(m, panel, accent);
    fill(m.x + 1, m.y + 1, m.w - 2, 30, raised);
    text_at(m.x + 16, m.y + 16, title, text);
    text_wrap(m.x + 16, m.y + 52, message, m.w - 32, dim, 3, 1);
    int y = m.y + m.h - 16 - BTN_H, right = m.x + m.w - 16;
    const char *accept = ui.modal == 1 ? "Apply" : ui.modal == 2 ? "Restore" : "Move binding";
    const char *reject = ui.modal == 1 ? "Discard" : "Cancel";
    int aw = button_w(accept), rw = button_w(reject);
    button(YES, rect(right - aw, y, aw, BTN_H), accept, BTN_PRIMARY);
    button(NO, rect(right - aw - 8 - rw, y, rw, BTN_H), reject, BTN_NORMAL);
    if (ui.modal == 1) {
        int kw = button_w("Keep editing");
        button(KEEP, rect(m.x + 16, y, kw, BTN_H), "Keep editing", BTN_NORMAL);
    }
}

/* ------------------------------------------------------------------ */
/*  Header, footer and the main pass                                   */
/* ------------------------------------------------------------------ */

static void segment(int id, Rect r, const char *label, int on)
{
    int over = ui.hover == id;
    frame(r, on ? accent : over ? hot : raised, on ? accent_hot : edge);
    text_clip(r.x + (r.w - text_w(label)) / 2, r.y + r.h / 2, label, r.w - 8, on ? on_accent : text);
    if (ui.focus == id)
        ring(r);
    hit(id, r);
}
static int tab_item(int id, int x, int y, int h, const char *label, int on, int disabled)
{
    Rect r = rect(x, y, text_w(label) + 28, h);
    int over = ui.hover == id;
    if (on)
        fill(r.x, r.y, r.w, r.h, bg);
    else if (over && !disabled)
        fill(r.x, r.y, r.w, r.h, raised);
    text_at(r.x + 14, r.y + r.h / 2 - 1, label, disabled ? faint : on ? text : dim);
    fill(r.x, r.y + r.h - 2, r.w, 2, on ? accent : edge);
    if (ui.focus == id && (!touch || ui.keyed))
        box(r.x + 2, r.y + 2, r.w - 4, r.h - 6, accent);
    hit(id, r);
    return x + r.w + 4;
}
static void draw_header(void)
{
    int w = ui.width;
    fill(0, 0, w, HEADER_H, panel);
    fill(0, HEADER_H - 1, w, 1, edge);
    text_at(PAD, 22, "Controls", text);

    int seg = 92, seg_x = w - PAD - 2 * seg;
    text_right(seg_x - 10, 22, "Editing", faint);
    segment(PLAYER, rect(seg_x, 10, seg, 25), "Player 1", ui.player == 0);
    segment(PLAYER_2, rect(seg_x + seg, 10, seg, 25), "Player 2", ui.player == 1);

    int x = PAD;
    x = tab_item(KEYBOARD, x, HEADER_H - 30, 29, "Keyboard", !ui.tab, ui.player == 1);
    tab_item(CONTROLLER, x, HEADER_H - 30, 29, "Controller", ui.tab, 0);
    if (dirty())
        text_right(w - PAD, HEADER_H - 16, "Unsaved changes", warn);
}

static void draw_device_row(Rect r, ControllerDevice *d)
{
    char label[256];
    const ControlsPort *p = &ui.draft.port[ui.player];
    if (!ui.tab) {
        text_clip(r.x + 2, r.y + r.h / 2,
                  "Keyboard bindings always play as Player 1. One key per PlayStation button.", r.w - 4, dim);
        return;
    }
    const char *state;
    uint32_t state_ink;
    if (p->mode == 0) {
        state = "Switched off";
        state_ink = faint;
    } else if (d && d->connected) {
        /* Two identical pads cannot be told apart again after a restart. */
        state = d->ambiguous ? "Choose again after a restart" : "Connected";
        state_ink = d->ambiguous ? warn : good;
    } else if (p->mode == 2) {
        state = "Not connected";
        state_ink = warn;
    } else {
        state = getenv("MEMORIES_NO_GAMEPAD") ? "Disabled this session" : "No controller found";
        state_ink = warn;
    }
    if (p->mode == 0)
        snprintf(label, sizeof(label), "None - no controller for this player");
    else if (p->mode == 1)
        snprintf(label, sizeof(label), "Automatic%s%s", d ? " - " : "", d ? d->name : "");
    else
        snprintf(label, sizeof(label), "%s", d ? d->name : "Saved controller (not connected)");

    text_at(r.x + 2, r.y + r.h / 2, "Controller", dim);
    int left = r.x + 2 + text_w("Controller") + 12;
    int pill_w = text_w(state) + 24, pill_x = r.x + r.w - pill_w;
    Rect drop = rect(left, r.y, pill_x - 10 - left, r.h);
    device_drop = drop;
    device_drop.y += offset_y; /* the list is drawn over the page, unscrolled */
    int over = ui.hover == DEVICE;
    frame(drop, over || ui.popup == DEVICE ? hot : raised, ui.popup == DEVICE ? accent : edge);
    text_clip(drop.x + 10, drop.y + drop.h / 2, label, drop.w - 34, text);
    caret(drop.x + drop.w - 14, drop.y + drop.h / 2, dim);
    if (ui.focus == DEVICE)
        ring(drop);
    hit(DEVICE, drop);
    frame(rect(pill_x, r.y, pill_w, r.h), panel, edge);
    text_at(pill_x + 12, r.y + r.h / 2, state, state_ink);
}

/* With a finger (see the top of the file): the page between the fixed
 * header and footer, drawn first and scrolled, then the header, the message
 * line and the footer over its ends, then the device list or a dialog. */
static void draw_touch(MenuCanvas *c, ControllerDevice *d, uint64_t rows)
{
    char line[256];
    int t, w, h, inner, view_h, y, device_y, diagram_y = 0, diagram_w = 0, diagram_h = 0, pad_y, game_y, fixed_y;
    int fixed_h, defaults_y, header_h, footer_h, message_h = 26, picture_first = 0;
    const char *restore = ui.tab ? "Restore controller defaults" : "Restore keyboard defaults";
    scale = Menu_Scale();
    while (scale > 1 && (c->width / scale < 480 || c->height / scale < 300))
        scale--;
    ui.draw_scale = scale;
    t = (touch + scale - 1) / scale; /* the finger's target in this scale's units */
    row_h = t > ROW_H_MOUSE ? t : ROW_H_MOUSE;
    btn_h = t > BTN_H_MOUSE ? t : BTN_H_MOUSE;
    popup_row = t > POPUP_ROW_MOUSE ? t : POPUP_ROW_MOUSE;
    w = ui.width = c->width / scale;
    h = ui.height = c->height / scale;
    header_h = footer_h = btn_h + 16;
    inner = w - 2 * PAD;
    ui.view_top = header_h;
    ui.view_bottom = h - footer_h - message_h;
    view_h = ui.view_bottom - ui.view_top;
    /* Every pixel, including those past the last whole unit at the right
     * and bottom, which a fill in units leaves see-through. */
    for (int j = 0; j < c->height; j++)
        for (int i = 0; i < c->width; i++)
            c->pixels[j * c->stride + i] = bg;

    /* Where each part of the page goes, from the page's top. */
    y = 12;
    device_y = y;
    y += (ui.tab ? btn_h : 20) + 12;
    /* The pad picture goes first where it leaves half the view to the
     * list; on a phone, where it would fill the first screen, after both
     * lists (tapping one of its buttons still brings that row into view). */
    if (inner >= DIAGRAM_MIN) {
        int most = view_h / 2 > 220 ? view_h / 2 : 220;
        diagram_w = inner < DIAGRAM_MAX ? inner : DIAGRAM_MAX;
        diagram_h = 34 + ControlsArt_Height(diagram_w - 24) + (diagram_w >= 330 ? 64 : 46);
        if (diagram_h > most)
            diagram_h = most;
        picture_first = 2 * diagram_h <= view_h;
    }
    if (diagram_w && picture_first) {
        diagram_y = y;
        y += diagram_h + GAP;
    }
    pad_y = y;
    y += HEAD_H + 11 + list_lines(0) * ROW_H + GAP;
    game_y = y;
    y += HEAD_H + 11 + list_lines(1) * ROW_H + GAP;
    if (diagram_w && !picture_first) {
        diagram_y = y;
        y += diagram_h + GAP;
    }
    fixed_h = fixed_height(inner);
    fixed_y = y;
    y += fixed_h + GAP;
    defaults_y = y;
    y += btn_h + 12;
    ui.page_max = y > view_h ? y - view_h : 0;
    if (ui.reveal && row_page_y[ui.row] > 0) {
        int top = row_page_y[ui.row] - ROW_H, bottom = row_page_y[ui.row] + 2 * ROW_H;
        if (top < ui.page_scroll)
            ui.page_scroll = top;
        else if (bottom > ui.page_scroll + view_h)
            ui.page_scroll = bottom - view_h;
    }
    ui.reveal = 0;
    if (ui.page_scroll > ui.page_max)
        ui.page_scroll = ui.page_max;
    if (ui.page_scroll < 0)
        ui.page_scroll = 0;

    offset_y = ui.view_top - ui.page_scroll;
    clip_top = ui.view_top;
    clip_bottom = ui.view_bottom;
    draw_device_row(rect(PAD, device_y, inner, ui.tab ? btn_h : 20), d);
    if (diagram_w)
        draw_diagram(rect(PAD + (inner - diagram_w) / 2, diagram_y, diagram_w, diagram_h), (uint16_t)rows);
    draw_table(rect(PAD, pad_y, inner, HEAD_H + 11 + list_lines(0) * ROW_H), rows, 0);
    draw_table(rect(PAD, game_y, inner, HEAD_H + 11 + list_lines(1) * ROW_H), rows, 1);
    draw_fixed(rect(PAD, fixed_y, inner, fixed_h));
    button(DEFAULTS, rect(PAD, defaults_y, button_w(restore), btn_h), restore, BTN_NORMAL);
    offset_y = clip_top = clip_bottom = 0;
    if (ui.page_max) { /* where the page is: a thin bar at the right of the view */
        int knob = view_h * view_h / (view_h + ui.page_max);
        knob = knob < 20 ? 20 : knob;
        fill(w - 5, ui.view_top + (view_h - knob) * ui.page_scroll / ui.page_max, 3, knob, edge);
    }

    /* The header: the tabs, and the players at the right. */
    fill(0, 0, w, header_h, panel);
    fill(0, header_h - 1, w, 1, edge);
    {
        int x = tab_item(KEYBOARD, PAD, 8, btn_h, "Keyboard", !ui.tab, ui.player == 1);
        int seg = text_w("Player 2") + 28 > 92 ? text_w("Player 2") + 28 : 92, seg_x = w - PAD - 2 * seg;
        x = tab_item(CONTROLLER, x, 8, btn_h, "Controller", ui.tab, 0);
        segment(PLAYER, rect(seg_x, 8, seg, btn_h), "Player 1", ui.player == 0);
        segment(PLAYER_2, rect(seg_x + seg, 8, seg, btn_h), "Player 2", ui.player == 1);
        if (dirty() && seg_x - 12 - x >= text_w("Unsaved changes"))
            text_right(seg_x - 12, header_h / 2, "Unsaved changes", warn);
        else if (seg_x - 12 - x >= text_w("Controls"))
            text_right(seg_x - 12, header_h / 2, "Controls", dim);
    }

    /* The message line: what the window waits for, what happened, or the
     * selected binding. */
    fill(0, ui.view_bottom, w, message_h, bg);
    fill(0, ui.view_bottom, w, 1, edge);
    if (ui.capture.state) {
        uint64_t now = ControlsRuntime_Now();
        int left = ui.capture.deadline_us > now ? (int)((ui.capture.deadline_us - now + 999999) / 1000000) : 0;
        snprintf(line, sizeof(line), "Press a %s for %s%s - %d second%s left. Back cancels.", ui.tab ? "button" : "key",
                 Controls_RowName(ui.row), ui.tab && ui.slot ? " (alternate)" : "", left, left == 1 ? "" : "s");
        text_clip(PAD, ui.view_bottom + message_h / 2, line, inner, accent);
    } else if (ui.status[0])
        text_clip(PAD, ui.view_bottom + message_h / 2, ui.status, inner,
                  ui.say == SAY_WARN ? warn : ui.say == SAY_DONE ? good : ui.say == SAY_BUSY ? accent : dim);
    else {
        const ControlSource *src = &Controls_Row(profile(0), ui.row)[ui.slot];
        snprintf(line, sizeof(line), "%s / %s%s: %s", action_group(ui.row), Controls_RowName(ui.row),
                 ui.tab ? (ui.slot ? " (alternate)" : " (main)") : "",
                 src->kind != CTRL_SRC_UNBOUND ? source_label(src) : "Unbound");
        text_clip(PAD, ui.view_bottom + message_h / 2, line, inner, text);
    }

    /* The footer: what acts on the selected binding, then the window's own. */
    fill(0, h - footer_h, w, footer_h, panel);
    fill(0, h - footer_h, w, 1, edge);
    {
        int by = h - footer_h + 8, clear_w = button_w("Clear"), rebind_w = button_w("Rebind");
        int ok_w = button_w("OK") + 18, apply_w = button_w("Apply"), cancel_w = button_w("Cancel");
        const ControlSource *src = &Controls_Row(profile(0), ui.row)[ui.slot];
        button(CLEAR, rect(PAD, by, clear_w, btn_h), "Clear", src->kind != CTRL_SRC_UNBOUND ? BTN_NORMAL : BTN_QUIET);
        button(REBIND, rect(PAD + clear_w + 8, by, rebind_w, btn_h), ui.capture.state ? "Stop" : "Rebind", BTN_NORMAL);
        button(OK, rect(w - PAD - ok_w, by, ok_w, btn_h), "OK", BTN_PRIMARY);
        button(APPLY, rect(w - PAD - ok_w - 8 - apply_w, by, apply_w, btn_h), "Apply", dirty() ? BTN_READY : BTN_QUIET);
        button(CANCEL, rect(w - PAD - ok_w - 8 - apply_w - 8 - cancel_w, by, cancel_w, btn_h), "Cancel", BTN_NORMAL);
    }
    if (ui.popup == DEVICE)
        draw_popup(device_drop);
    if (ui.modal)
        draw_modal();
}

/* A finger that went down at x, y moved dy pixels: the device list's
 * entries, or the page, follow it. */
void ControlsWindow_Drag(int x, int y, int dy)
{
    int unit = ui.draw_scale ? ui.draw_scale : 1, step;
    (void)x;
    (void)y;
    if (ui.modal)
        return;
    ui.drag_rest += dy;
    if (ui.popup) {
        step = ui.drag_rest / (POPUP_ROW * unit);
        ui.drag_rest -= step * POPUP_ROW * unit;
        ui.popup_scroll -= step;
        if (ui.popup_scroll > ui.popup_max)
            ui.popup_scroll = ui.popup_max;
        if (ui.popup_scroll < 0)
            ui.popup_scroll = 0;
        return;
    }
    step = ui.drag_rest / unit;
    ui.drag_rest -= step * unit;
    ui.page_scroll -= step;
    if (ui.page_scroll > ui.page_max)
        ui.page_scroll = ui.page_max;
    if (ui.page_scroll < 0)
        ui.page_scroll = 0;
}

void ControlsWindow_Draw(MenuCanvas *c)
{
    ControlSource sources[CTRL_KEY_COUNT];
    char line[256];
    canvas = c;
    touch = Menu_TouchTarget();
    if (touch) {
        ControllerDevice *d = ControlsRuntime_Device(current_device());
        uint64_t rows = 0;
        ui.count = 0;
        memset(pad_rect, 0, sizeof(pad_rect));
        if (ui.tab) {
            if (d) {
                ui.preview.activation = d->threshold;
                rows = Controls_EvalControllerRows(profile(0), &d->snapshot, &ui.preview);
            }
        } else {
            int n = ControlsRuntime_Keys(sources);
            rows = Controls_EvalKeyboardRows(profile(0), sources, n);
        }
        draw_touch(c, d, rows);
        return;
    }
    row_h = ROW_H_MOUSE;
    btn_h = BTN_H_MOUSE;
    popup_row = POPUP_ROW_MOUSE;
    scale = Menu_Scale();
    while (scale > 1 && (c->width / scale < MIN_W || c->height / scale < MIN_H))
        scale--;
    ui.draw_scale = scale;
    int w = ui.width = c->width / scale, h = ui.height = c->height / scale;
    ui.count = 0;
    memset(pad_rect, 0, sizeof(pad_rect)); /* refilled only if the picture fits */
    fill(0, 0, w, h, bg);

    int device = current_device();
    ControllerDevice *d = ControlsRuntime_Device(device);
    uint64_t rows = 0;
    if (ui.tab) {
        if (d) {
            ui.preview.activation = d->threshold;
            rows = Controls_EvalControllerRows(profile(0), &d->snapshot, &ui.preview);
        }
    } else {
        int n = ControlsRuntime_Keys(sources);
        rows = Controls_EvalKeyboardRows(profile(0), sources, n);
    }
    uint16_t bits = (uint16_t)rows;

    draw_header();
    Rect device_row = rect(PAD, HEADER_H + 12, w - 2 * PAD, BTN_H);
    draw_device_row(device_row, d);

    int foot_top = h - FOOTER_H;
    int status_mid = foot_top - 17;
    int squat = h < 560; /* too short for both message lines */
    int hint_mid = status_mid - 19;
    int action_y = (squat ? status_mid : hint_mid) - 12 - BTN_H;
    Rect content = rect(PAD, device_row.y + device_row.h + 14, w - 2 * PAD,
                        action_y - 12 - (device_row.y + device_row.h + 14));
    if (content.h < 120)
        content.h = 120;

    int slots = ui.tab ? 2 : 1;
    int table_w = NAME_W + slots * (ui.tab ? SLOT_W : KEY_W) + (slots - 1) * 6 + 16;
    if (table_w > content.w)
        table_w = content.w;
    int diagram_w = content.w - GAP - table_w;
    if (diagram_w > DIAGRAM_MAX) {
        table_w += diagram_w - DIAGRAM_MAX;
        diagram_w = DIAGRAM_MAX;
    }
    /* The pad list fills the right; the left column stacks the picture, the
     * Game list and the fixed keys. The picture takes two fifths (at least
     * 200, at most its own size) and whatever the Game list leaves. Too
     * narrow or too short for that, the picture drops out and the Game list
     * goes under the pad list. The fixed keys go first when room runs out. */
    int min_game = HEAD_H + 11 + 3 * ROW_H;
    int picture_h = content.h * 2 / 5, natural = 34 + ControlsArt_Height(diagram_w - 24) + 64;
    picture_h = picture_h > natural ? natural : picture_h < 200 ? 200 : picture_h;
    int show_diagram = diagram_w >= DIAGRAM_MIN && content.h - picture_h - GAP >= min_game;
    Rect left = content;
    if (show_diagram) {
        draw_table(rect(content.x + diagram_w + GAP, content.y, table_w, table_height(content.h, 0)), rows, 0);
        left = rect(content.x, content.y + picture_h + GAP, diagram_w, content.h - picture_h - GAP);
    } else {
        int width = table_w + 160 < content.w ? table_w + 160 : content.w;
        Rect pad = rect(content.x + (content.w - width) / 2, content.y, width,
                        table_height(content.h * 11 / 20, 0));
        draw_table(pad, rows, 0);
        left = rect(pad.x, pad.y + pad.h + GAP, pad.w, content.h - pad.h - GAP);
    }
    int fixed_h = fixed_height(left.w);
    if (left.h - fixed_h - GAP < min_game)
        fixed_h = 0;
    int game_h = table_height(left.h - (fixed_h ? fixed_h + GAP : 0), 1);
    if (show_diagram)
        draw_diagram(rect(content.x, content.y, diagram_w,
                          content.h - game_h - (fixed_h ? fixed_h + GAP : 0) - GAP), bits);
    Rect game = rect(left.x, left.y + left.h - game_h - (fixed_h ? fixed_h + GAP : 0), left.w, game_h);
    if (left.h >= HEAD_H + 11 + ROW_H)
        draw_table(game, rows, 1);
    else
        list_rect[1] = rect(0, 0, 0, 0);
    if (fixed_h)
        draw_fixed(rect(left.x, game.y + game.h + GAP, left.w, fixed_h));

    /* Selection and the two buttons that act on it. */
    const ControlSource *src = &Controls_Row(profile(0), ui.row)[ui.slot];
    snprintf(line, sizeof(line), "%s / %s%s: %s", action_group(ui.row), Controls_RowName(ui.row),
             ui.tab ? (ui.slot ? " (alternate)" : " (main)") : "",
             src->kind != CTRL_SRC_UNBOUND ? source_label(src) : "Unbound");
    int rebind_w = button_w("Rebind"), clear_w = button_w("Clear");
    text_clip(PAD, action_y + BTN_H / 2, line, w - 2 * PAD - rebind_w - clear_w - 24, text);
    button(CLEAR, rect(w - PAD - rebind_w - 8 - clear_w, action_y, clear_w, BTN_H), "Clear",
           src->kind != CTRL_SRC_UNBOUND ? BTN_NORMAL : BTN_QUIET);
    button(REBIND, rect(w - PAD - rebind_w, action_y, rebind_w, BTN_H),
           ui.capture.state ? "Stop" : "Rebind", BTN_NORMAL);

    /* Hint line: what to do here, or what the window is waiting for. */
    const char *hint;
    if (ui.capture.state) {
        uint64_t now = ControlsRuntime_Now();
        int left = ui.capture.deadline_us > now ? (int)((ui.capture.deadline_us - now + 999999) / 1000000) : 0;
        snprintf(line, sizeof(line), "Listening for %s%s - %d second%s left. Escape cancels%s.",
                 Controls_RowName(ui.row), ui.tab && ui.slot ? " (alternate)" : "", left, left == 1 ? "" : "s",
                 ui.row == CTRL_ROW_EXIT && !ui.tab ? "; Esc quits whatever is bound here" : "");
        hint = line;
    } else if (ui.hover >= DIAGRAM && ui.hover < CHOICE) {
        snprintf(line, sizeof(line), "%s - click to select it, double-click to rebind it.",
                 Controls_Actions[ui.hover - DIAGRAM].name);
        hint = line;
    } else if (ui.row == CTRL_ROW_EXIT)
        hint = ui.tab ? "Double-click a binding, or select one and press Enter, to change it. Delete clears it."
                      : "Esc always quits; bind a key or button here to quit with it too.";
    else
        hint = "Double-click a binding, or select one and press Enter, to change it. Delete clears it.";
    /* A warning too long for its line (a failed save's path and reason)
     * takes the hint's line too. */
    int long_warning = !squat && !ui.capture.state && ui.say == SAY_WARN && text_w(ui.status) > w - 2 * PAD;
    if (long_warning)
        text_wrap(PAD, hint_mid, ui.status, w - 2 * PAD, warn, 2, 1);
    else if (!squat)
        text_clip(PAD, hint_mid, hint, w - 2 * PAD, ui.capture.state ? accent : faint);
    if (squat && ui.capture.state)
        text_clip(PAD, status_mid, hint, w - 2 * PAD, accent);
    else if (!long_warning)
        text_clip(PAD, status_mid, ui.status, w - 2 * PAD,
                  ui.say == SAY_WARN ? warn : ui.say == SAY_DONE ? good : ui.say == SAY_BUSY ? accent : dim);

    /* Footer. */
    fill(0, foot_top, w, FOOTER_H, panel);
    fill(0, foot_top, w, 1, edge);
    int by = foot_top + (FOOTER_H - BTN_H) / 2;
    const char *restore = ui.tab ? "Restore controller defaults" : "Restore keyboard defaults";
    button(DEFAULTS, rect(PAD, by, button_w(restore), BTN_H), restore, BTN_NORMAL);
    int ok_w = button_w("OK") + 18, apply_w = button_w("Apply"), cancel_w = button_w("Cancel");
    button(OK, rect(w - PAD - ok_w, by, ok_w, BTN_H), "OK", BTN_PRIMARY);
    button(APPLY, rect(w - PAD - ok_w - 8 - apply_w, by, apply_w, BTN_H), "Apply",
           dirty() ? BTN_READY : BTN_QUIET);
    button(CANCEL, rect(w - PAD - ok_w - 8 - apply_w - 8 - cancel_w, by, cancel_w, BTN_H), "Cancel",
           BTN_NORMAL);

    if (ui.popup == DEVICE)
        draw_popup(device_drop);
    if (ui.modal)
        draw_modal();
}
