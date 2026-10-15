/* What the scratch sweep (scratch.h) removes and what it must leave: stale
 * folders of a known kind go; live, foreign, malformed and young ones stay;
 * and a link (a junction on Windows, a symbolic link elsewhere) is only ever
 * unlinked, never followed, even where unlinking it fails (a read-only
 * junction). The decoys live in a temporary folder of this test's own. */
#define _POSIX_C_SOURCE 200809L
#include "scratch.h"
#include <assert.h>
#include <stdint.h>
#ifdef _WIN32
#include <windows.h> /* after scratch.h: its declarations must match */
#include <sys/utime.h>
#else
#include <sys/wait.h>
#include <utime.h>
#endif

static char temp[SCRATCH_MAX + 16], outside[SCRATCH_MAX + 16];

static const char *in(const char *folder, const char *name)
{
    static char paths[8][2 * SCRATCH_MAX];
    static int next;
    char *path = paths[next++ % 8];
    int length = snprintf(path, sizeof(paths[0]), "%s/%s", folder, name);
    assert(length > 0 && length < (int)sizeof(paths[0]));
    return path;
}

static void write_file(const char *path)
{
    FILE *file = fopen(path, "wb");
    assert(file);
    assert(fputs("keep me\n", file) >= 0);
    assert(!fclose(file));
}

static int present(const char *path) { return scratch_entry(path) != SCRATCH_NONE; }

#ifdef _WIN32
static int command(const wchar_t *format, const char *first, const char *second)
{
    wchar_t line[3 * SCRATCH_MAX], *a = Memories_Utf8ToWide(first), *b = second ? Memories_Utf8ToWide(second) : NULL;
    int result;
    assert(a && (b || !second));
    for (wchar_t *at = a; *at; at++) if (*at == L'/') *at = L'\\';
    for (wchar_t *at = b; at && *at; at++) if (*at == L'/') *at = L'\\';
    _snwprintf(line, sizeof(line) / sizeof(line[0]), format, a, b);
    line[sizeof(line) / sizeof(line[0]) - 1] = 0;
    result = _wsystem(line);
    free(a);
    free(b);
    return result;
}
#endif

/* A link to a folder outside, optionally one that cannot be unlinked. */
static void make_link(const char *link, const char *target, int stuck)
{
#ifdef _WIN32
    assert(!command(L"mklink /J \"%ls\" \"%ls\" >nul", link, target));
    if (stuck) assert(!command(L"attrib +r /L \"%ls\"", link, NULL));
    assert(scratch_entry(link) == SCRATCH_LINK);
#else
    (void)stuck; /* no link attribute stops unlink here */
    assert(!symlink(target, link));
    assert(scratch_entry(link) == SCRATCH_LINK);
#endif
}

static void clear_link(const char *link)
{
    if (scratch_entry(link) != SCRATCH_LINK) return;
#ifdef _WIN32
    command(L"attrib -r /L \"%ls\"", link, NULL);
#endif
    scratch_unlink(link);
}

/* The links nothing can unlink, freed again even when an assert fails:
 * scratch_dir() sees this handler and leaves SIGABRT to it. */
static char stuck_links[2][2 * SCRATCH_MAX + 8];
static void clear_stuck(void)
{
    clear_link(stuck_links[0]);
    clear_link(stuck_links[1]);
}
static void on_abort(int number)
{
    clear_stuck();
    scratch_cleanup();
    signal(number, SIG_DFL);
    raise(number);
}

/* The PID of a process that has exited. */
static unsigned long dead_pid(void)
{
    unsigned long pid;
#ifdef _WIN32
    intptr_t handle = _wspawnlp(_P_NOWAIT, L"cmd.exe", L"cmd.exe", L"/c", L"exit", NULL);
    assert(handle != -1);
    pid = GetProcessId((HANDLE)handle);
    assert(_cwait(NULL, handle, 0) != -1); /* closes the handle */
#else
    pid_t child = fork();
    assert(child >= 0);
    if (!child) _exit(0);
    assert(waitpid(child, NULL, 0) == child);
    pid = (unsigned long)child;
#endif
    assert(pid && !scratch_alive(pid));
    return pid;
}

static void make_old(const char *path)
{
    time_t when = time(NULL) - 3 * 24 * 60 * 60;
#ifdef _WIN32
    struct _utimbuf times = {when, when};
    wchar_t *wide = Memories_Utf8ToWide(path);
    assert(wide && !_wutime(wide, &times));
    free(wide);
#else
    struct utimbuf times = {when, when};
    assert(!utime(path, &times));
#endif
}

static const char *tagged(char *out, size_t size, const char *kind, unsigned long pid, const char *suffix)
{
    snprintf(out, size, "%s/%s-p%lu-%s", temp, kind, pid, suffix);
    return out;
}

int main(void)
{
    char root[SCRATCH_MAX], name[3 * SCRATCH_MAX], junction[2 * SCRATCH_MAX], stuck[2 * SCRATCH_MAX];
    char top[2 * SCRATCH_MAX], top_stuck[2 * SCRATCH_MAX], stale[2 * SCRATCH_MAX], mine[2 * SCRATCH_MAX];
    char kind_link[2 * SCRATCH_MAX], other_kind[2 * SCRATCH_MAX], *saved = NULL;
    const char *targets[] = {"a", "b", "c", "d", "e"};
    const char *old_temp = getenv("TMPDIR");
    unsigned long dead = dead_pid(), live = scratch_pid();
    size_t i;
    signal(SIGABRT, on_abort);
    if (old_temp && (saved = malloc(strlen(old_temp) + 1))) strcpy(saved, old_temp);
    assert(scratch_dir(root, sizeof(root), "memories-scratch-rules"));
    snprintf(temp, sizeof(temp), "%s/tmp", root);
    snprintf(outside, sizeof(outside), "%s/outside", root);
    assert(!mkdir(temp, 0777) && !mkdir(outside, 0777));
    for (i = 0; i < sizeof(targets) / sizeof(targets[0]); i++) {
        assert(!mkdir(in(outside, targets[i]), 0777));
        snprintf(name, sizeof(name), "%s/%s", outside, targets[i]);
        write_file(in(name, "SENTINEL.txt"));
    }
    assert(!setenv("TMPDIR", temp, 1));

    /* Stale, with a junction inside, and with a junction that will not go. */
    assert(!mkdir(tagged(junction, sizeof(junction), "memories-disc", dead, "junc01"), 0777));
    make_link(in(junction, "j"), in(outside, "a"), 0);
    assert(!mkdir(tagged(stuck, sizeof(stuck), "memories-disc", dead, "ronly1"), 0777));
    snprintf(stuck_links[0], sizeof(stuck_links[0]), "%s/j", stuck);
    make_link(stuck_links[0], in(outside, "b"), 1);
    /* The entry in the temporary folder is itself a junction. */
    make_link(tagged(top, sizeof(top), "memories-disc", dead, "toplv1"), in(outside, "c"), 0);
    snprintf(stuck_links[1], sizeof(stuck_links[1]), "%s", tagged(top_stuck, sizeof(top_stuck), "memories-disc", dead, "toprd1"));
    make_link(stuck_links[1], in(outside, "d"), 1);
    /* Plainly stale. */
    assert(!mkdir(tagged(stale, sizeof(stale), "memories-disc", dead, "stale1"), 0777));
    assert(!mkdir(in(stale, "sub"), 0777));
    snprintf(name, sizeof(name), "%s/sub", stale);
    write_file(in(name, "file"));
    /* Kept: live, foreign kind, no kind, PID past 32 bits, malformed. */
    assert(!mkdir(tagged(mine, sizeof(mine), "memories-disc", live, "livexx"), 0777));
    assert(!mkdir(tagged(name, sizeof(name), "memories-unrelated", dead, "abc123"), 0777));
    assert(!mkdir(tagged(name, sizeof(name), "memories-", dead, "abcdef"), 0777));
    assert(!mkdir(in(temp, "memories-disc-p99999999999999999999-abcdef"), 0777));
    assert(!mkdir(in(temp, "memories-disc-p4294967296-abcdef"), 0777));
    assert(!mkdir(in(temp, "memories-disc-p-p123-abcdef"), 0777));
    /* Untagged, from older builds: a day old and known goes. */
    write_file(in(temp, "memories-log-old123"));
    make_old(in(temp, "memories-log-old123"));
    write_file(in(temp, "memories-log-new123"));
    write_file(in(temp, "memories-foo-old123"));
    make_old(in(temp, "memories-foo-old123"));

    scratch_sweep(NULL, stdout);
    for (i = 0; i < 4; i++) {
        snprintf(name, sizeof(name), "%s/%s", outside, targets[i]);
        assert(present(in(name, "SENTINEL.txt")));
    }
    assert(!present(junction) && !present(top) && !present(stale));
    assert(!present(in(temp, "memories-log-old123")));
#ifdef _WIN32
    /* The stuck junctions stay, and so does the folder around one. */
    assert(scratch_entry(in(stuck, "j")) == SCRATCH_LINK && scratch_entry(top_stuck) == SCRATCH_LINK);
#endif
    assert(present(mine));
    assert(present(tagged(name, sizeof(name), "memories-unrelated", dead, "abc123")));
    assert(present(tagged(name, sizeof(name), "memories-", dead, "abcdef")));
    assert(present(in(temp, "memories-disc-p99999999999999999999-abcdef")));
    assert(present(in(temp, "memories-disc-p4294967296-abcdef")));
    assert(present(in(temp, "memories-disc-p-p123-abcdef")));
    assert(present(in(temp, "memories-log-new123")) && present(in(temp, "memories-foo-old123")));

    /* A sweep of one kind, as scratch_dir() makes it, leaves the others. */
    assert(!mkdir(tagged(kind_link, sizeof(kind_link), "memories-disc", dead, "kind01"), 0777));
    make_link(in(kind_link, "j"), in(outside, "e"), 0);
    assert(!mkdir(tagged(other_kind, sizeof(other_kind), "memories-mods", dead, "kind02"), 0777));
    assert(scratch_sweep("memories-disc", NULL) >= 1);
    assert(!present(kind_link) && present(other_kind));
    snprintf(name, sizeof(name), "%s/e", outside);
    assert(present(in(name, "SENTINEL.txt")));

#ifndef _WIN32
    /* A forked child that exits normally runs the parent's atexit cleanup,
     * which must leave the parent's folders alone. */
    {
        pid_t child = fork();
        int status;
        assert(child >= 0);
        if (!child) exit(0);
        assert(waitpid(child, &status, 0) == child && WIFEXITED(status));
        assert(present(root));
    }
#endif

    /* Undo the stuck junctions; the rest goes with this test's folder. */
    clear_stuck();
    assert(!present(stuck_links[0]) && !present(stuck_links[1]));
    if (saved) assert(!setenv("TMPDIR", saved, 1));
    else assert(!unsetenv("TMPDIR"));
    free(saved);
    puts("scratch rules: ok");
    return 0;
}
