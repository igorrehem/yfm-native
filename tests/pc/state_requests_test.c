#define _POSIX_C_SOURCE 200809L
#include "pc/compat/fs.h"
#include "pc/guest/state_requests.h"
#include "pc/platform/paths.h"
#include "pc/platform/menu.h"
#include "pc/debug/log.h"
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <setjmp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int saves, loads, notices, told, loaded_slot, user_failure, jump_on_load;
static char saved_path[1024], loaded_path[1024];
static int reported_error;
static jmp_buf resumed;
int Paths_User(char *out, size_t size, const char *relative)
{
    snprintf(out, size, "/user/%s", relative);
    return user_failure;
}
int Paths_MakeDirs(const char *path) { assert(path && *path); return 0; }
void Paths_WriteBegin(void) { errno = 0; }
const char *Paths_WriteError(char *out, size_t size, const char *path)
{
    reported_error = errno;
    snprintf(out, size, "%s: %s", path,
             errno == ENAMETOOLONG ? "path too long" : "write refused");
    return out;
}
void Menu_ShowNotice(const char *title, const char *text, const char *const *buttons,
                     int count, int focus, void (*chosen)(int, int *))
{
    assert(!strcmp(title, "Save state not saved"));
    assert(strstr(text, "write refused") || strstr(text, "path too long"));
    assert(count == 1 && !strcmp(buttons[0], "OK") && !focus && !chosen);
    ++notices;
}
int Log_Wanted(LogChannel channel) { (void)channel; return 0; }
void Log_Printf(LogChannel channel, const char *format, ...) { (void)channel; (void)format; }
static int save(const char *path, int tell)
{
    ++saves; told = tell;
    snprintf(saved_path, sizeof(saved_path), "%s", path);
    return 0;
}
static void load(const char *path, int slot)
{
    ++loads; loaded_slot = slot;
    snprintf(loaded_path, sizeof(loaded_path), "%s", path);
    if (jump_on_load) longjmp(resumed, 1);
}
int main(void)
{
    static MemoriesStateRequests requests = MEMORIES_STATE_REQUESTS_INIT;
    const MemoriesStateActions actions = {save, load};
    unsetenv("MEMORIES_STATE_DIR");
    unsetenv("MEMORIES_AUTOSAVE_DIR");
    setenv("MEMORIES_LOAD_STATE", "7", 1);
    setenv("MEMORIES_SAVE_STATE", "40:/script.state", 1);
    setenv("MEMORIES_AUTOSAVE", "1", 1);
    Memories_StateProcess(&requests, 29, &actions);
    assert(!requests.startup_done && !saves && !loads);
    /* Loading replaces the current stack: startup bookkeeping must survive. */
    jump_on_load = 1;
    if (!setjmp(resumed)) Memories_StateProcess(&requests, 30, &actions);
    assert(requests.startup_done && loads == 1 && loaded_slot == 7);
    assert(!strcmp(loaded_path, "/user/states/slot7.state"));
    jump_on_load = 0;
    Memories_StateProcess(&requests, 31, &actions);
    assert(loads == 1);
    Memories_StateProcess(&requests, 40, &actions);
    assert(saves == 1 && !told && !strcmp(saved_path, "/script.state"));
    Memories_StateProcess(&requests, 41, &actions);
    assert(saves == 1);
    for (unsigned i = 0; i < 4; ++i) {
        char expected[64];
        Memories_StateProcess(&requests, 89 + i * 60, &actions);
        snprintf(expected, sizeof(expected), "/user/states/auto%u.state", i % 3 + 1);
        assert(!strcmp(saved_path, expected) && !told);
    }
    assert(saves == 5);
    setenv("MEMORIES_STATE_DIR", "/custom/nested", 1);
    {
        MemoriesStateRequests custom = MEMORIES_STATE_REQUESTS_INIT;
        unsetenv("MEMORIES_LOAD_STATE"); unsetenv("MEMORIES_SAVE_STATE");
        Memories_StateProcess(&custom, 30, &actions);
        Memories_StateProcess(&custom, 90, &actions);
        assert(!strcmp(saved_path, "/custom/nested/auto1.state"));
    }
    Memories_StateQueue(&requests, 1, 9);
    Memories_StateProcess(&requests, 270, &actions);
    assert(told && !strcmp(saved_path, "/custom/nested/slot9.state"));
    Memories_StateQueue(&requests, 2, 0);
    Memories_StateProcess(&requests, 271, &actions);
    assert(loaded_slot == 9 && !strcmp(loaded_path, saved_path));
    Memories_StateProcess(&requests, 272, &actions);
    assert(loads == 2);
    setenv("MEMORIES_AUTOSAVE_DIR", "/auto/nested", 1);
    Memories_StateProcess(&requests, 329, &actions);
    assert(!strcmp(saved_path, "/auto/nested/auto2.state"));
    unsetenv("MEMORIES_STATE_DIR");
    user_failure = 1;
    Memories_StateQueue(&requests, 1, 2);
    Memories_StateProcess(&requests, 330, &actions);
    assert(!strcmp(saved_path, "./slot2.state"));
    {
        const char *bad[] = {"-1", "71582789", "9999999999999999999999", "1garbage", "", "0"};
        for (unsigned i = 0; i < sizeof(bad) / sizeof(bad[0]); ++i) {
            MemoriesStateRequests invalid = MEMORIES_STATE_REQUESTS_INIT;
            int before = saves;
            unsetenv("MEMORIES_LOAD_STATE"); unsetenv("MEMORIES_SAVE_STATE");
            setenv("MEMORIES_AUTOSAVE", bad[i], 1);
            Memories_StateProcess(&invalid, 30, &actions);
            Memories_StateProcess(&invalid, 1000, &actions);
            assert(!invalid.autosave_every && saves == before);
        }
    }
    {
        MemoriesStateRequests wrapping = MEMORIES_STATE_REQUESTS_INIT;
        int before = saves;
        setenv("MEMORIES_AUTOSAVE", "1", 1);
        Memories_StateProcess(&wrapping, UINT_MAX - 20u, &actions);
        Memories_StateProcess(&wrapping, UINT_MAX - 1u, &actions);
        Memories_StateProcess(&wrapping, 38, &actions);
        assert(saves == before);
        Memories_StateProcess(&wrapping, 39, &actions);
        assert(saves == before + 1);
    }
    unsetenv("MEMORIES_AUTOSAVE");
    {
        const char *bad_slots[] = {"0", "2147483648", "9999999999999999999999"};
        const char *bad_scripts[] = {":/bad", "-1:/bad", "4294967296:/bad", "30garbage:/bad", "30:"};
        for (unsigned i = 0; i < sizeof(bad_slots) / sizeof(bad_slots[0]); ++i) {
            MemoriesStateRequests invalid = MEMORIES_STATE_REQUESTS_INIT;
            int before = loads;
            setenv("MEMORIES_LOAD_STATE", bad_slots[i], 1);
            Memories_StateProcess(&invalid, 30, &actions);
            assert(loads == before);
        }
        unsetenv("MEMORIES_LOAD_STATE");
        for (unsigned i = 0; i < sizeof(bad_scripts) / sizeof(bad_scripts[0]); ++i) {
            MemoriesStateRequests invalid = MEMORIES_STATE_REQUESTS_INIT;
            int before = saves;
            setenv("MEMORIES_SAVE_STATE", bad_scripts[i], 1);
            Memories_StateProcess(&invalid, 30, &actions);
            Memories_StateProcess(&invalid, UINT_MAX, &actions);
            assert(!invalid.scripted_path && saves == before);
        }
    }
    unsetenv("MEMORIES_SAVE_STATE");
    {
        char long_path[2048];
        MemoriesStateRequests invalid = MEMORIES_STATE_REQUESTS_INIT;
        int before = saves, before_loads = loads, before_notices = notices;
        memset(long_path, 'x', sizeof(long_path) - 1); long_path[sizeof(long_path) - 1] = 0;
        setenv("MEMORIES_STATE_DIR", long_path, 1);
        setenv("MEMORIES_LOAD_STATE", long_path, 1);
        Memories_StateQueue(&invalid, 1, 3);
        Memories_StateProcess(&invalid, 30, &actions);
        assert(saves == before && loads == before_loads);
        assert(notices == before_notices + 1 && reported_error == ENAMETOOLONG);
        Memories_StateProcess(&invalid, 31, &actions);
        assert(notices == before_notices + 1 && !invalid.requested);
        /* Background autosaves refuse the same path without a modal notice. */
        setenv("MEMORIES_AUTOSAVE_DIR", long_path, 1);
        setenv("MEMORIES_AUTOSAVE", "1", 1);
        MemoriesStateRequests automatic = MEMORIES_STATE_REQUESTS_INIT;
        Memories_StateProcess(&automatic, 30, &actions);
        Memories_StateProcess(&automatic, 90, &actions);
        assert(saves == before && notices == before_notices + 1);
    }
    assert(Memories_StateSlotFromPath("/user/slot2147483647.state") == INT_MAX);
    assert(Memories_StateSlotFromPath("C:\\states\\slot7.state") == 7);
    assert(!Memories_StateSlotFromPath("slot2147483648.state"));
    assert(!Memories_StateSlotFromPath("slot0.state"));
    assert(!Memories_StateSlotFromPath("slot1.state.extra"));
    assert(!Memories_StateSlotFromPath("slot-1.state"));
    {
        int before = notices;
        errno = EACCES;
        assert(Memories_StateSaveFailure("/refused.state", 0) == -1 && notices == before);
        assert(Memories_StateSaveFailure("/refused.state", 1) == -1 && notices == before + 1);
    }
    puts("Shared state requests: startup resume, scripted save, slots, autosave rotation and failures passed");
    return 0;
}
