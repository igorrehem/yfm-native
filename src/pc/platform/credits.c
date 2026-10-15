/* After the credits. The retail game's last mode never leaves: once the save
 * and the secret number are done, Main_RunCredits (src/game/main_run_credits.c)
 * runs the credits scene in its phase 2 and, every frame after, asks
 * Model_IsCreditsPresentationComplete and drops the answer, so the screen
 * stays black until the console is reset. The port resets it three seconds
 * after the presentation is complete: the game starts again, as the console
 * would, with the logos and the title.
 *
 * Not a jump to the title: the presentation loads over what only the boot
 * sets up, and nothing puts it back since retail never needed to. The
 * resident VRAM palettes the boot uploads (the Build Deck trunk's among them,
 * which came out green) stay overwritten; left half way, the music buffer
 * also stays moved into the presentation's area (title_jump.c). If the
 * restart fails, the main menu's mode is published instead, as a menu choice
 * would, and the game goes back to the title as it did before. The game's
 * own code is not changed. */
#include "credits.h"
#include "platform.h"
#include <stdio.h>

extern unsigned char D_8009B26C; /* main_mode_state.h: the active mode, 0x80 once it runs */
extern unsigned char D_8009B26E; /* Main_RunCredits: its phase, 0x80 once the phase started */
extern signed char D_8009AF9A;   /* -2 once the credits presentation is complete */

#define MAIN_MODE_MENU 8
#define MAIN_MODE_CREDITS 15
#define CREDITS_PHASE_SCENE 2
#define CREDITS_HOLD_FRAMES 180

void Credits_Frame(void)
{
    static unsigned held;
    if ((D_8009B26C & 0x9F) != (0x80 | MAIN_MODE_CREDITS) ||
        (D_8009B26E & 0x8F) != (0x80 | CREDITS_PHASE_SCENE) || D_8009AF9A != -2) {
        held = 0;
        return;
    }
    if (++held < CREDITS_HOLD_FRAMES) return;
    held = 0;
    fprintf(stderr, "memories-pc: the credits are over; restarting the game\n");
    Platform_RestartGame();
    fprintf(stderr, "memories-pc: the restart failed; back to the title screen instead\n");
    D_8009B26C = MAIN_MODE_MENU;
}
