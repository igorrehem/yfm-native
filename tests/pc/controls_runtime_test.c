#define _POSIX_C_SOURCE 200809L
#include "pc/platform/controls_runtime.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "pc/compat/posix.h"
#include "scratch.h"
#include <unistd.h>
int main(void)
{
    char dir[SCRATCH_MAX], path[SCRATCH_MAX + 64], error[256];
    assert(scratch_dir(dir, sizeof(dir), "memories-runtime"));
    snprintf(path, sizeof(path), "%s/controls.txt", dir);
    setenv("MEMORIES_CONTROLS", path, 1);
    ControlsConfig cfg = *ControlsRuntime_Config();
    for (int i = 0; i < 3; i++) {
        ControllerDevice *d = ControlsRuntime_Device(i);
        d->connected = 1;
        snprintf(d->identity, sizeof(d->identity), "test:%d", i);
        d->threshold = 1.0f / 3;
    }
    ControlsRuntime_Update();
    assert(ControlsRuntime_Assigned(&cfg, 0) == 0);
    assert(ControlsRuntime_Assigned(&cfg, 1) == 1);
    cfg.port[0].mode = 2;
    strcpy(cfg.port[0].identity, "test:2");
    assert(ControlsRuntime_Apply(&cfg, error, sizeof(error)));
    ControlsRuntime_Update();
    assert(ControlsRuntime_Assigned(&cfg, 0) == 2);
    ControllerDevice *d = ControlsRuntime_Device(2);
    d->snapshot.buttons_down = 1u << (CTRL_BTN_SOUTH - 1);
    ControlsRuntime_Update();
    assert(ControlsRuntime_Pad(0) == CTRL_DEST_CROSS);
    assert(!ControlsRuntime_Pad(1));
    ControlsRuntime_Block(1);
    ControlsRuntime_Update();
    assert(!ControlsRuntime_Pad(0));
    ControlsRuntime_Block(0);
    ControlsRuntime_Update();
    assert(!ControlsRuntime_Pad(0));
    d->snapshot.buttons_down = 0;
    ControlsRuntime_Update();
    d->snapshot.buttons_down = 1;
    ControlsRuntime_Update();
    assert(ControlsRuntime_Pad(0) == CTRL_DEST_CROSS);
    d->connected = 0;
    ControlsRuntime_Update();
    assert(!ControlsRuntime_Pad(0));
    assert(!ControlsRuntime_Connected(0));
    assert(ControlsRuntime_Assigned(&cfg, 0) == -1);
    d->connected = 1;
    d->snapshot.buttons_down = 0;
    ControlsRuntime_Update();
    assert(ControlsRuntime_Assigned(&cfg, 0) == 2);
    cfg.port[1] = cfg.port[0];
    assert(!ControlsRuntime_Apply(&cfg, error, sizeof(error)));
    cfg = *ControlsRuntime_Config();
    cfg.port[0].mode = 0;
    assert(ControlsRuntime_Apply(&cfg, error, sizeof(error)));
    ControlsRuntime_Update();
    ControlsRuntime_Key(CTRL_KEY_X, 1);
    ControlsRuntime_Update();
    assert(ControlsRuntime_Keyboard() == CTRL_DEST_CROSS);
    assert(!ControlsRuntime_Pad(0));
    ControlsRuntime_Key(CTRL_KEY_X, 0);
    ControlsRuntime_Update();
    assert(!ControlsRuntime_Keyboard());
    /* A tap released before the update (Android's injected key events come
     * down and up in one millisecond) is seen by that one update. */
    ControlsRuntime_Key(CTRL_KEY_X, 1);
    ControlsRuntime_Key(CTRL_KEY_X, 0);
    ControlsRuntime_Update();
    assert(ControlsRuntime_Keyboard() == CTRL_DEST_CROSS);
    ControlsRuntime_Update();
    assert(!ControlsRuntime_Keyboard());
    ControlsRuntime_Key(CTRL_KEY_X, 1);
    ControlsRuntime_Key(CTRL_KEY_X, 0);
    ControlsRuntime_ResetKeys();
    ControlsRuntime_Update();
    assert(!ControlsRuntime_Keyboard());
    ControlsRuntime_Update();
    cfg = *ControlsRuntime_Config();
    cfg.port[0].mode = 2;
    strcpy(cfg.port[0].identity, "test:2");
    ControlsProfile *profile = ControlsRuntime_Profile(&cfg, 0, 1);
    assert(cfg.profile_count == 1);
    profile->src[14][0] = (ControlSource){CTRL_SRC_BUTTON, CTRL_BTN_GUIDE, 0};
    assert(ControlsRuntime_Apply(&cfg, error, sizeof(error)));
    ControlsRuntime_Update();
    d->snapshot.buttons_down = 1u << (CTRL_BTN_GUIDE - 1);
    ControlsRuntime_Update();
    assert(ControlsRuntime_Pad(0) == CTRL_DEST_CROSS);

    /* While held (a notice is up) the game sees nothing, but the pad's
     * presses are there for the notice. Release waits for neutral. */
    d->snapshot.buttons_down = 0;
    ControlsRuntime_Update();
    ControlsRuntime_TakePadPresses();
    ControlsRuntime_Hold(1);
    d->snapshot.buttons_down = 1u << (CTRL_BTN_GUIDE - 1);
    ControlsRuntime_Update();
    assert(ControlsRuntime_Blocked() && !ControlsRuntime_Pad(0));
    assert(ControlsRuntime_TakePadPresses() == CTRL_DEST_CROSS && !ControlsRuntime_TakePadPresses());
    ControlsRuntime_Hold(0);
    ControlsRuntime_Update();
    assert(!ControlsRuntime_Pad(0));
    d->snapshot.buttons_down = 0;
    ControlsRuntime_Update();
    d->snapshot.buttons_down = 1u << (CTRL_BTN_GUIDE - 1);
    ControlsRuntime_Update();
    assert(!ControlsRuntime_Blocked() && ControlsRuntime_Pad(0) == CTRL_DEST_CROSS);
    /* Exit game (Esc by default) fires once per press, from a tap too short
     * for any update to see it held, and never for a press made while the
     * input is blocked or held. */
    d->snapshot.buttons_down = 0;
    ControlsRuntime_Update();
    ControlsRuntime_TakeHost();
    ControlsRuntime_Key(CTRL_KEY_ESCAPE, 1);
    ControlsRuntime_Update();
    assert(ControlsRuntime_TakeHost() == 1u << CTRL_HOST_EXIT);
    ControlsRuntime_Update();
    assert(!ControlsRuntime_TakeHost() && !ControlsRuntime_Keyboard());
    ControlsRuntime_Key(CTRL_KEY_ESCAPE, 0);
    ControlsRuntime_Key(CTRL_KEY_ESCAPE, 1);
    ControlsRuntime_Key(CTRL_KEY_ESCAPE, 0);
    ControlsRuntime_Update();
    assert(ControlsRuntime_TakeHost() == 1u << CTRL_HOST_EXIT);
    ControlsRuntime_Block(1);
    ControlsRuntime_Key(CTRL_KEY_ESCAPE, 1);
    ControlsRuntime_Update();
    ControlsRuntime_Block(0);
    ControlsRuntime_Update();
    assert(!ControlsRuntime_TakeHost()); /* still the same press */
    ControlsRuntime_Key(CTRL_KEY_ESCAPE, 0);
    ControlsRuntime_Update();

    /* Turbo (Tab) is a hold action: held while the key is, and not while
     * input is blocked. Volume up (keypad +) fires on the press, then again
     * once held past the repeat delay. */
    ControlsRuntime_TakeHost();
    ControlsRuntime_Key(CTRL_KEY_TAB, 1);
    ControlsRuntime_Update();
    assert(ControlsRuntime_HostHeld() == 1u << CTRL_HOST_TURBO && ControlsRuntime_KeyDown(CTRL_KEY_TAB));
    ControlsRuntime_Block(1);
    ControlsRuntime_Update();
    assert(!ControlsRuntime_HostHeld());
    ControlsRuntime_Key(CTRL_KEY_TAB, 0);
    ControlsRuntime_Block(0);
    ControlsRuntime_Update();
    ControlsRuntime_Update();
    ControlsRuntime_TakeHost();
    ControlsRuntime_Key(CTRL_KEY_KP_PLUS, 1);
    ControlsRuntime_Update();
    assert(ControlsRuntime_TakeHost() == 1u << CTRL_HOST_VOLUME_UP);
    ControlsRuntime_Update();
    assert(!ControlsRuntime_TakeHost());
    nanosleep(&(struct timespec){0, 450000000}, NULL);
    ControlsRuntime_Update();
    assert(ControlsRuntime_TakeHost() == 1u << CTRL_HOST_VOLUME_UP);
    ControlsRuntime_Key(CTRL_KEY_KP_PLUS, 0);
    ControlsRuntime_Update();

    /* The controller's own Exit binding, kept out of the pad bits. */
    cfg = *ControlsRuntime_Config();
    ControlsRuntime_Profile(&cfg, 0, 1)->host[CTRL_HOST_EXIT][0] = (ControlSource){CTRL_SRC_BUTTON, CTRL_BTN_BACK, 0};
    ControlsRuntime_Profile(&cfg, 0, 1)->src[0][0] = (ControlSource){0};
    assert(ControlsRuntime_Apply(&cfg, error, sizeof(error)));
    ControlsRuntime_Update();
    d->snapshot.buttons_down = 1u << (CTRL_BTN_BACK - 1);
    ControlsRuntime_Update();
    assert(ControlsRuntime_TakeHost() == 1u << CTRL_HOST_EXIT && !ControlsRuntime_Pad(0));
    d->snapshot.buttons_down = 0;
    ControlsRuntime_Update();

    /* With Exit game's key cleared, Esc (held or tapped) is still Exit. */
    cfg = *ControlsRuntime_Config();
    cfg.kb.host[CTRL_HOST_EXIT][0] = (ControlSource){0};
    assert(ControlsRuntime_Apply(&cfg, error, sizeof(error)));
    ControlsRuntime_Update();
    ControlsRuntime_TakeHost();
    ControlsRuntime_Key(CTRL_KEY_ESCAPE, 1);
    ControlsRuntime_Update();
    assert(ControlsRuntime_TakeHost() == 1u << CTRL_HOST_EXIT);
    ControlsRuntime_Key(CTRL_KEY_ESCAPE, 0);
    ControlsRuntime_Key(CTRL_KEY_ESCAPE, 1);
    ControlsRuntime_Key(CTRL_KEY_ESCAPE, 0);
    ControlsRuntime_Update();
    assert(ControlsRuntime_TakeHost() == 1u << CTRL_HOST_EXIT);
    unlink(path);
    rmdir(dir);
    puts("controls runtime: selection, hotplug, profiles, release gate, host actions, hold, held and repeating actions passed");
    return 0;
}
