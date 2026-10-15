#ifndef MEMORIES_PC_UPDATE_CHECK_H
#define MEMORIES_PC_UPDATE_CHECK_H
/* Help > updates (notes/updates.md). At start, and from Help > Check for
 * updates now, a thread of its own asks GitHub for the project's releases;
 * a newer one is announced in a notice over the picture (Menu_ShowNotice)
 * with Release page, Skip this version and Later. The game only tells: it
 * never downloads or installs a release, the player does that. Nothing here
 * blocks the game: the network is the thread's, and the main thread only
 * looks at its answer once a frame.
 *
 * The check at start is on by default (check_for_updates). It is
 * skipped when this build has no release version (a development build),
 * headless or with scripted input (MEMORIES_HEADLESS, MEMORIES_INPUT,
 * MEMORIES_SDL_SCRIPT), and whenever MEMORIES_NO_UPDATE_CHECK is set to
 * anything but 0. For tests, MEMORIES_UPDATE_URL names another release list
 * (which also lets scripted runs check) and MEMORIES_UPDATE_CURRENT another
 * running version. */

/* Once, after Platform_Open: starts the check if it is wanted. */
void Update_Start(void);
/* Main thread, once a frame: shows what the thread found. */
void Update_Frame(void);
/* Help > Check for updates now: always answers, "up to date" included. */
void Update_CheckNow(void);
/* Help > Releases page. */
void Update_OpenReleases(void);
/* "Version v0.1.0", or "Development build": the Help menu's last row. */
const char *Update_VersionLabel(void);

#endif
