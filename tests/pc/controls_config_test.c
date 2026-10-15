#define _POSIX_C_SOURCE 200809L
#include "pc/platform/controls_config.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include "pc/compat/posix.h"
#include "scratch.h"
#include <unistd.h>
/* Copy `path` with a new first line, without its host lines when `drop_host`,
 * and with the line `from` replaced by `to`. */
static void rewrite(const char *path, const char *header, int drop_host, const char *from, const char *to)
{
    char temp[SCRATCH_MAX + 80], line[256];
    snprintf(temp, sizeof(temp), "%s.new", path);
    FILE *in = fopen(path, "r"), *out = fopen(temp, "w");
    assert(in && out && fgets(line, sizeof(line), in));
    fputs(header, out);
    while (fgets(line, sizeof(line), in))
        if (!(drop_host && !strncmp(line, "host ", 5)))
            fputs(from && !strcmp(line, from) ? to : line, out);
    fclose(in);
    fclose(out);
    assert(!rename(temp, path));
}
int main(void)
{
    char dir[SCRATCH_MAX], path[SCRATCH_MAX + 64], error[256] = {0};
    assert(scratch_dir(dir, sizeof(dir), "memories-controls"));
    snprintf(path, sizeof(path), "%s/controls.txt", dir);
    assert(!setenv("MEMORIES_CONTROLS", path, 1));
    ControlsConfig a, b;
    Controls_InitDefaults(&a);
    assert(ControlsConfig_Load(&b, error, sizeof(error)) == 0);
    assert(Controls_Equal(&a, &b));
    a.kb.src[14][0] = (ControlSource){CTRL_SRC_KEY, CTRL_KEY_B, 0};
    a.ctrl[0].src[15][1] = (ControlSource){CTRL_SRC_AXIS, CTRL_AXIS_RIGHT_Y, -1};
    a.profile_count = 1;
    strcpy(a.profiles[0].identity, "linux:usb with spaces/serial:abc");
    a.profiles[0].bindings = a.ctrl[0];
    a.profiles[0].icon = CTRL_ICON_NINTENDO;
    a.port[0].mode = 2;
    strcpy(a.port[0].identity, a.profiles[0].identity);
    Controls_SetKeyLabel(CTRL_KEY_B,"Localized B");
    assert(ControlsConfig_Save(&a, error, sizeof(error)));
    assert(ControlsConfig_Load(&b, error, sizeof(error)) == 1);
    assert(Controls_Equal(&a, &b));
    for (int code = CTRL_BTN_TOUCHPAD; code < CTRL_BTN_COUNT; code++) {
        a.ctrl[1].src[14][0] = (ControlSource){CTRL_SRC_BUTTON, (uint16_t)code, 0};
        assert(ControlsConfig_Save(&a, error, sizeof(error)));
        assert(ControlsConfig_Load(&b, error, sizeof(error)) == 1);
        assert(Controls_Equal(&a, &b));
    }
    /* Version 2 keeps the host actions: a controller's Exit, a cleared Esc. */
    a.ctrl[1].host[CTRL_HOST_EXIT][1] = (ControlSource){CTRL_SRC_BUTTON, CTRL_BTN_GUIDE, 0};
    a.kb.host[CTRL_HOST_EXIT][0] = (ControlSource){0};
    assert(ControlsConfig_Save(&a, error, sizeof(error)));
    assert(ControlsConfig_Load(&b, error, sizeof(error)) == 1);
    assert(Controls_Equal(&a, &b));
    /* Version 1, every file before the host actions, still loads with Esc
     * exiting, and the next save writes version 2. */
    Controls_InitDefaults(&a);
    a.kb.src[14][0] = (ControlSource){CTRL_SRC_KEY, CTRL_KEY_B, 0};
    assert(ControlsConfig_Save(&a, error, sizeof(error)));
    rewrite(path, "controls 1 0\n", 1, NULL, NULL);
    assert(ControlsConfig_Load(&b, error, sizeof(error)) == 1);
    assert(Controls_Equal(&a, &b) && b.kb.host[CTRL_HOST_EXIT][0].code == CTRL_KEY_ESCAPE);
    assert(ControlsConfig_Save(&b, error, sizeof(error)));
    char line[256];
    FILE *f = fopen(path, "r");
    assert(f && fgets(line, sizeof(line), f) && !strcmp(line, "controls 2 0\n"));
    fclose(f);
    /* Host lines are optional (a missing one is its default) and one a later
     * build added is skipped. */
    rewrite(path, "controls 2 0\n", 1, "port 0 1 0 -\n", "port 0 1 0 -\nhost 0 from_the_future 0 key.f9\n");
    assert(ControlsConfig_Load(&b, error, sizeof(error)) == 1);
    assert(Controls_Equal(&a, &b) && b.kb.host[CTRL_HOST_SAVE_STATE][0].code == CTRL_KEY_F5);
    /* A default whose key the file gave a pad button stays unbound: keypad
     * + on Cross in a version 1 file leaves Volume up without a key. */
    rewrite(path, "controls 1 0\n", 1, "bind 0 28 key.b\n", "bind 0 28 key.num+\n");
    assert(ControlsConfig_Load(&b, error, sizeof(error)) == 1);
    assert(b.kb.src[14][0].code == CTRL_KEY_KP_PLUS && !b.kb.host[CTRL_HOST_VOLUME_UP][0].kind);
    assert(b.kb.host[CTRL_HOST_VOLUME_DOWN][0].code == CTRL_KEY_KP_MINUS);
    assert(ControlsConfig_Save(&a, error, sizeof(error)));
    /* Invalid: version 1 with host lines, and Esc on a pad row. */
    rewrite(path, "controls 1 0\n", 0, NULL, NULL);
    assert(ControlsConfig_Load(&b, error, sizeof(error)) == -1);
    b = a;
    b.kb.host[CTRL_HOST_EXIT][0] = (ControlSource){0}; /* Esc is nowhere else */
    assert(ControlsConfig_Save(&b, error, sizeof(error)));
    rewrite(path, "controls 2 0\n", 0, "bind 0 28 key.b\n", "bind 0 28 key.esc\n");
    assert(ControlsConfig_Load(&b, error, sizeof(error)) == -1);
    assert(ControlsConfig_Save(&a, error, sizeof(error)));
    f = fopen(path, "a");
    assert(f);
    fputs("bind 0 0 key.x\n", f);
    fclose(f);
    assert(ControlsConfig_Load(&b, error, sizeof(error)) == -1);
    ControlsConfig defaults;
    Controls_InitDefaults(&defaults);
    assert(Controls_Equal(&b, &defaults));
    f = fopen(path, "w");
    assert(f);
    fputs("controls 99 0\n", f);
    fclose(f);
    assert(ControlsConfig_Load(&b, error, sizeof(error)) == -2);
    assert(!ControlsConfig_Save(&a, error, sizeof(error)));
    f = fopen(path, "r");
    assert(f);
    assert(fgets(line, sizeof(line), f));
    fclose(f);
    assert(!strcmp(line, "controls 99 0\n"));
    assert(!unlink(path));
    assert(!mkdir(path, 0700)); /* replacement must fail; directory survives */
    assert(!ControlsConfig_Save(&a, error, sizeof(error)));
    assert(!rmdir(path));
    assert(!rmdir(dir));
    puts("controls config: round trip, version 1, host lines, corruption, future version and write failure passed");
    return 0;
}
