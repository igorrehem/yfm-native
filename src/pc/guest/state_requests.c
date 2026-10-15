#include "pc/compat/fs.h"
#include "state_requests.h"
#include "pc/platform/paths.h"
#include "pc/platform/menu.h"
#include "pc/debug/log.h"
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void Memories_StateQueue(MemoriesStateRequests *requests, int what, int slot)
{
    if (slot > 0) requests->slot = slot;
    requests->requested = what;
}

/* Never redirect an operation to a silently truncated path. */
static int state_path(char *out, size_t size, const char *setting, const char *name)
{
    const char *directory = getenv(setting);
    char relative[96];
    int length;
    if (!directory && !strcmp(setting, "MEMORIES_AUTOSAVE_DIR")) directory = getenv("MEMORIES_STATE_DIR");
    if (!directory) {
        length = snprintf(relative, sizeof(relative), "states/%s", name);
        if (length < 0 || (size_t)length >= sizeof(relative)) {
            errno = ENAMETOOLONG;
            return -1;
        }
        if (!Paths_User(out, size, relative)) return 0;
        directory = ".";
    }
    length = snprintf(out, size, "%s/%s", directory, name);
    if (length < 0 || (size_t)length >= size) {
        fprintf(stderr, "memories-pc: save-state path is too long\n");
        errno = ENAMETOOLONG;
        return -1;
    }
    Paths_MakeDirs(directory);
    return 0;
}

/* Decimal settings use explicit bounds on every host ABI. */
static int decimal(const char *begin, const char *end, unsigned maximum, unsigned *out)
{
    unsigned value = 0;
    if (begin == end) return -1;
    for (; begin < end; ++begin) {
        unsigned digit = (unsigned)(*begin - '0');
        if (digit > 9 || digit > maximum || value > (maximum - digit) / 10) return -1;
        value = value * 10 + digit;
    }
    *out = value;
    return 0;
}

int Memories_StateSlotFromPath(const char *path)
{
    const char *name = strrchr(path, '/');
    const char *backslash = strrchr(path, '\\');
    unsigned slot;
    size_t length;
    if (backslash && (!name || backslash > name)) name = backslash;
    name = name ? name + 1 : path;
    length = strlen(name);
    if (length <= 10 || strncmp(name, "slot", 4) || strcmp(name + length - 6, ".state") ||
        decimal(name + 4, name + length - 6, INT_MAX, &slot) || !slot) return 0;
    return (int)slot;
}

int Memories_StateSaveFailure(const char *path, int tell)
{
    static const char *const ok[] = {"OK"};
    char why[1200], text[1300];
    Paths_WriteError(why, sizeof(why), path);
    snprintf(text, sizeof(text), "Could not save the state to %s", why);
    fprintf(stderr, "memories-pc: %s\n", text);
    if (tell) Menu_ShowNotice("Save state not saved", text, ok, 1, 0, NULL);
    return -1;
}

/* Invalid, negative or overflowing settings disable autosave on every backend. */
static unsigned autosave_frames(const char *setting)
{
    unsigned seconds;
    if (!setting || decimal(setting, setting + strlen(setting), UINT_MAX / 60u, &seconds)) return 0;
    return seconds * 60u;
}

void Memories_StateProcess(MemoriesStateRequests *requests, unsigned frames,
                           const MemoriesStateActions *actions)
{
    char path[1024], name[64];
    int what;
    if (!requests->startup_done && frames >= 30) {
        const char *wanted = getenv("MEMORIES_LOAD_STATE");
        const char *script = getenv("MEMORIES_SAVE_STATE");
        requests->startup_done = 1;
        const char *separator = script ? strchr(script, ':') : NULL;
        if (separator && separator[1] &&
            !decimal(script, separator, UINT_MAX, &requests->scripted_frame)) {
            requests->scripted_path = separator + 1;
        }
        if (wanted && *wanted) {
            int slot = 0;
            if (strspn(wanted, "0123456789") == strlen(wanted)) {
                unsigned number;
                if (decimal(wanted, wanted + strlen(wanted), INT_MAX, &number) || !number) {
                    fprintf(stderr, "memories-pc: invalid load-state slot\n");
                } else {
                    slot = (int)number;
                    snprintf(name, sizeof(name), "slot%d.state", slot);
                    if (!state_path(path, sizeof(path), "MEMORIES_STATE_DIR", name)) actions->load(path, slot);
                }
            } else if (strlen(wanted) < sizeof(path)) {
                memcpy(path, wanted, strlen(wanted) + 1);
                actions->load(path, slot);
            } else fprintf(stderr, "memories-pc: load-state path is too long\n");
        }
    }
    if (requests->scripted_path && !requests->scripted_done && frames >= requests->scripted_frame) {
        requests->scripted_done = 1;
        actions->save(requests->scripted_path, 0);
    }
    if (!requests->autosave_read) {
        requests->autosave_read = 1;
        requests->autosave_every = autosave_frames(getenv("MEMORIES_AUTOSAVE"));
        requests->autosave_frame = frames;
    }
    if (requests->autosave_every && frames - requests->autosave_frame >= requests->autosave_every) {
        requests->autosave_frame = frames;
        snprintf(name, sizeof(name), "auto%u.state", requests->autosave_index % 3 + 1);
        ++requests->autosave_index;
        if (!state_path(path, sizeof(path), "MEMORIES_AUTOSAVE_DIR", name) &&
            !actions->save(path, 0)) {
            LOG(LOG_STATE, "autosave %s at frame %u", path, frames);
        }
    }
    what = __atomic_exchange_n(&requests->requested, 0, __ATOMIC_SEQ_CST);
    if (what == 1 || what == 2) {
        int slot = requests->slot;
        snprintf(name, sizeof(name), "slot%d.state", slot);
        if (what == 1) Paths_WriteBegin();
        if (!state_path(path, sizeof(path), "MEMORIES_STATE_DIR", name)) {
            if (what == 1) actions->save(path, 1);
            else actions->load(path, slot);
        } else if (what == 1) Memories_StateSaveFailure(path, 1);
    }
}
