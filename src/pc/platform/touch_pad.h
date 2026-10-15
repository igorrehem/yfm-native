#ifndef MEMORIES_PC_TOUCH_PAD_H
#define MEMORIES_PC_TOUCH_PAD_H
/* An on-screen controller for touch screens (phones, tablets, touch
 * laptops): a D-pad, the four face buttons, L1/L2/R1/R2, SELECT and START
 * at the sides of the window, and MENU (which opens the menu bar's first
 * menu) under L2/L1, drawn with the game's own button pictures and font off
 * the disc (touch_pad_art.c). It feeds the first controller's bits beside
 * the keyboard and the pads, as the button it shows (Cross is Cross,
 * whatever View > Japanese buttons says), and a press shorter than a frame
 * still counts once, as a key's does (controls_runtime.c).
 *
 * View > Touch controls: Automatic shows it after the screen is touched and
 * hides it again when a key or a controller button is pressed; Show and
 * Hide keep it so. Hidden, it draws nothing and takes no touch, so the
 * window is what it is without it. Main thread only; the logic here has no
 * other dependency, so tests drive it directly. */
#include <stdint.h>

enum { TOUCH_PAD_AUTO, TOUCH_PAD_SHOW, TOUCH_PAD_HIDE };
typedef enum {
    TOUCH_UP, TOUCH_DOWN, TOUCH_LEFT, TOUCH_RIGHT,
    TOUCH_TRIANGLE, TOUCH_CIRCLE, TOUCH_CROSS, TOUCH_SQUARE,
    TOUCH_L1, TOUCH_L2, TOUCH_R1, TOUCH_R2, TOUCH_SELECT, TOUCH_START,
    TOUCH_MENU, /* no pad bit: TouchPad_TakeMenu */
    TOUCH_BUTTONS
} TouchButton;
enum { TOUCH_FINGER_DOWN, TOUCH_FINGER_MOVE, TOUCH_FINGER_UP };

/* The mode (TOUCH_PAD_*, the setting). 1 when what is shown changed. */
int TouchPad_SetMode(int mode);
/* The window's size, and where below its top the pad may start (the menu
 * bar's height when it shows one). 1 when the layout changed. */
int TouchPad_Layout(int window_w, int window_h, int top);
/* Window pixels per density-independent pixel (Android's dp; 0 when the
 * system does not say): with it, a button is a thumb's width on any screen,
 * 48 to 80 dp, rather than a share of the window. 1 when the layout
 * changed. */
int TouchPad_SetDensity(float pixels_per_dp);
/* While a menu or a notice is up the pad steps aside: it draws nothing and
 * takes no touch, so their rows and buttons are the finger's, and what it
 * held is let go. 1 when that changed what is shown. */
int TouchPad_Block(int blocked);
/* MENU was tapped since the last call. */
int TouchPad_TakeMenu(void);
/* The span across the window between the pad's left and right columns, for
 * what is drawn over the picture while the pad shows. 0 while hidden. */
int TouchPad_FreeSpan(int *left, int *right);
/* A finger in window coordinates. A finger that lands on the pad stays the
 * pad's until it lifts (sliding changes the direction or the button); one
 * that lands elsewhere is not the pad's at all. 1 when the pad's look
 * changed (shown, or a button pressed or let go). */
int TouchPad_Finger(int kind, uint64_t finger, int x, int y);
/* A key or a controller button was pressed: Automatic hides the pad. 1 when
 * that changed what is shown. */
int TouchPad_OtherInput(void);
int TouchPad_Shown(void);
/* The pad takes a touch at x, y (so a mouse event SDL made of it is not the
 * menu's). 0 while hidden. */
int TouchPad_Covers(int x, int y);
/* Once per pump: the PS1 pad bits held now, or pressed since the last call
 * and let go already. */
uint16_t TouchPad_Update(void);
/* Pad bits newly pressed since the last call (what answers a notice). */
uint16_t TouchPad_TakePresses(void);
/* For drawing: where a button is (0 when hidden) and whether it is held. */
int TouchPad_Rect(TouchButton button, int *x, int *y, int *w, int *h);
int TouchPad_Held(TouchButton button);
/* The PS1 pad bit of a button. */
uint16_t TouchPad_Bit(TouchButton button);

#endif
