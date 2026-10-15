#ifndef MEMORIES_PC_QUIT_PROMPT_H
#define MEMORIES_PC_QUIT_PROMPT_H

/* Every way out of the game the player asks for (Esc, File > Exit, the
 * window's close button or Alt+F4) comes here. With File >
 * Confirm before quitting (SET_CONFIRM_QUIT, on by default) the menu's
 * notice asks first (asked again, it is shown again); otherwise, or on
 * Quit, *quit is set as before. Main thread only. */
void QuitPrompt_Request(int *quit);
/* A phone's Back: the same question, with Menu between Quit and Keep
 * playing, which opens the menu bar's first menu (Menu_Open), a way to the
 * menus without the touch controls (a controller in hand). */
void QuitPrompt_Back(int *quit);

#endif
