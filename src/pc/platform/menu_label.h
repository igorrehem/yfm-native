#ifndef MEMORIES_PC_PLATFORM_MENU_LABEL_H
#define MEMORIES_PC_PLATFORM_MENU_LABEL_H
/* A menu button of words (menu_label.c): the words on a frame drawn as the
 * title's own entries are -- a dark box in an olive rim with a grey line
 * above and below, or, with the cursor on it, in red and orange with blue
 * lines and green letters -- in the serif face the card names are set in.
 * It is made as a PNG MENU_LABEL_FACTOR times the size it is drawn at, so
 * it goes through the same pictures as a mod's own PNG (title_images.c)
 * and is sharp at every internal resolution. */
#include <stddef.h>

enum { MENU_LABEL_FACTOR = 4, MENU_LABEL_HEIGHT = 28 };

/* Writes the button (under the user directory's cache) unless it is there
 * already, and gives its path and its size in the game's pixels (at 100%).
 * The PNG is `factor` times that size (MENU_LABEL_FACTOR at least): more
 * for a button drawn bigger ("scale"), so it is as sharp. 0 when there is
 * no serif face or the file cannot be written; `why` says which. */
int MenuLabel_Make(const char *text, int selected, int factor, char *path, size_t size, int *width, int *height,
                   char *why, size_t why_size);
#endif
