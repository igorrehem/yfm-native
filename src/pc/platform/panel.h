#ifndef MEMORIES_PC_PANEL_H
#define MEMORIES_PC_PANEL_H
/* The Mods and Controls windows drawn inside the game's window, for a
 * platform that cannot open a second window (Android; MEMORIES_PANELS=overlay
 * shows them so on a desktop, for testing). One module draws and handles
 * each (mods_window.c, controls_window.c), as in its own window; this is the
 * other host. The panel covers the whole window, opaque, its contents kept
 * inside the safe area (clear of a phone's cutouts) and the rest filled. It
 * has the pointer, the keys and typed text while it shows.
 *
 * A finger is not a mouse: a press is held until it is known to be a tap
 * (it lifts where it went down: the module gets the press and the release
 * then) or a drag (it moves 8 dp: what it went down on scrolls, the module's
 * Drag). A press on something that follows the finger (a slider, a
 * scrollbar: the module's Grabs) goes to the module at once, as a mouse's.
 * Pointer and keys come in window pixels; the module sees panel pixels.
 *
 * The backend (sdl.c) feeds it events, draws it into its overlay canvas,
 * pauses the game while it shows (the picture is covered and the game would
 * get no input), steps the touch controls aside and shows the system's
 * on-screen keyboard while a field takes typing (Panel_TextFocus).
 * Platform-independent and display-free (tests/pc/panels_preview.c drives
 * it); main thread only. */
#include "menu.h"

enum { PANEL_NONE, PANEL_MODS, PANEL_CONTROLS };

/* Shows that panel (one at a time: another one shown closes first) with the
 * module's state fresh, as opening its window does. 1 when it shows. The
 * Controls panel reads the keyboard's key names and held keys as its window
 * does: the backend labels them before and syncs them after. */
int Panel_Open(int kind);
/* Closes it now, unsaved changes or not (the module asked first). */
void Panel_Close(void);
/* The window's close button while the panel shows: the panel closes as its
 * own Close would (asking first about unsaved changes), so nothing it covers
 * asks behind it; the next press of the button reaches the game's prompt. */
void Panel_RequestClose(void);
/* The panel shown (PANEL_*), or PANEL_NONE. */
int Panel_Shown(void);
/* The window's size, and the part of it the panel's contents keep within
 * (the safe area), in window pixels. */
void Panel_Layout(int window_w, int window_h, int x, int y, int w, int h);
int Panel_Left(void);
int Panel_Top(void);
/* Draws the panel over the whole of `window` (a canvas the window's size). */
void Panel_Draw(MenuCanvas *window);
/* A pointer event (button, motion, wheel, leave) in window pixels; `finger`
 * when a touch made it. 1 when the panel must be drawn again. */
int Panel_Pointer(const MenuEvent *event, int finger);
/* A key going down or up, or typed text: `event` as the menu has it (Esc
 * and a phone's Back are MENU_KEY_ESCAPE), `control_key` the Controls
 * module's key code for it (controls.h; CTRL_KEY_ESCAPE for Back), whether
 * it repeats and the modifiers held (1 Shift, 2 Ctrl/Alt/GUI). 1 when the
 * panel must be drawn again. */
int Panel_Key(const MenuEvent *event, int control_key, int repeat, int modifiers);
/* Once per pump while shown: the Controls panel listens for a binding and
 * shows the pad live; the Mods panel takes an import's next step
 * (ModsWindow_Tick). 1 when the panel must be drawn again. */
int Panel_Tick(void);
/* A field of the panel takes typing now: show the on-screen keyboard. */
int Panel_TextFocus(void);
/* The pointer's last release was a tap or a click, not the end of a drag
 * (a tap on the focused field shows the on-screen keyboard again). */
int Panel_Tapped(void);
#endif
