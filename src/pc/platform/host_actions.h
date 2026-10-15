#ifndef MEMORIES_PC_HOST_ACTIONS_H
#define MEMORIES_PC_HOST_ACTIONS_H

/* What the Game list's actions (controls.h CTRL_HOST_*) do, for both
 * backends: once per pump, after the controllers are read, it takes the
 * presses and follows the holds. Exit game sets `quit`, as File > Exit
 * does. Returns 1 when something the menu shows changed (repaint).
 * Main thread only. */
int HostActions_Run(int *quit);

/* The master volume, stepped by 5 and saved, as keypad + and - do. */
void HostActions_StepVolume(int up);

#endif
