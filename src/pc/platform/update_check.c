/* The update check's thread and its notices (update_check.h). The thread
 * owns `job` from start() until it publishes `done`; the main thread reads
 * the result only after that, so nothing else is shared. */
#define _GNU_SOURCE
#include "pc/compat/fs.h"
#include "update_check.h"
#include "update.h"
#include "update_net.h"
#include "menu.h"
#include "paths.h"
#include "platform.h"
#include "settings.h"
#include "pc/compat/signal.h"
#include <ctype.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* The release this executable is (tools/pc/build_game32.py writes it from
 * the tag it was built for), or "" for a development build. */
extern const char Memories_Version[];

#define REPOSITORY "Unchiga/Yu-Gi-Oh-Forbidden-Memories-Recompiled"
#define RELEASES_API "https://api.github.com/repos/" REPOSITORY "/releases?per_page=30"
#define RELEASES_PAGE "https://github.com/" REPOSITORY "/releases"
#define CHECK_SECONDS 20
#define LIST_LIMIT (8L * 1024 * 1024)

enum { FOUND_NEWER = 1, FOUND_LATEST, CHECK_FAILED };

static struct {
    int running; /* main thread: a check has started and not been answered */
    int manual;  /* whether the player asked for it */
    int done;    /* the thread's answer (atomic); 0 while it works */
    /* Read by start() on the main thread, so the thread touches neither the
     * settings nor the environment nor the user folder. */
    int prereleases;
    char url[512], current[64], skip[64];
    UpdateRelease release;
    char why[256];
} job;

static UpdateRelease offered; /* the release the notice shown is about */

static const char *current_version(void)
{
    const char *named = getenv("MEMORIES_UPDATE_CURRENT");
    return named && *named ? named : Memories_Version;
}

static int known_version(void) { return Update_ParseVersion(current_version(), NULL); }

const char *Update_VersionLabel(void)
{
    static char label[96];
    if (known_version()) snprintf(label, sizeof(label), "Version %s", current_version());
    else snprintf(label, sizeof(label), "Development build");
    return label;
}

static int flag(const char *name)
{
    const char *value = getenv(name);
    return value && *value && strcmp(value, "0");
}

static void read_skip(char *out, size_t size)
{
    char path[1024];
    FILE *file;
    out[0] = '\0';
    snprintf(path, sizeof(path), "%s/updates/skip.txt", Paths_UserDir()); /* nothing created */
    if ((file = fopen(path, "r"))) {
        if (!fgets(out, (int)size, file)) out[0] = '\0';
        out[strcspn(out, "\r\n")] = '\0';
        fclose(file);
    }
}

static void write_skip(const char *tag)
{
    char path[1024];
    FILE *file;
    if (Paths_User(path, sizeof(path), "updates/skip.txt")) return;
    if ((file = fopen(path, "w"))) {
        fprintf(file, "%s\n", tag);
        fclose(file);
    }
}

/* --- the thread ------------------------------------------------------ */

typedef struct { char *data; long size, capacity; } Buffer;

static int to_buffer(const void *data, size_t size, void *context)
{
    Buffer *buffer = context;
    if (buffer->size + (long)size + 1 > buffer->capacity) {
        long capacity = buffer->capacity ? buffer->capacity : 65536;
        char *grown;
        while (capacity < buffer->size + (long)size + 1) capacity *= 2;
        if (capacity > LIST_LIMIT || !(grown = realloc(buffer->data, (size_t)capacity))) return 1;
        buffer->data = grown;
        buffer->capacity = capacity;
    }
    memcpy(buffer->data + buffer->size, data, size);
    buffer->size += (long)size;
    buffer->data[buffer->size] = '\0';
    return 0;
}

static int check(void)
{
    Buffer list = {0};
    int found;
    if (UpdateNet_Get(job.url, CHECK_SECONDS, to_buffer, &list, job.why, sizeof(job.why)) || !list.data) {
        free(list.data);
        return CHECK_FAILED;
    }
    found = Update_PickRelease(list.data, job.current, job.prereleases, job.skip, &job.release);
    free(list.data);
    if (found < 0) {
        snprintf(job.why, sizeof(job.why), "GitHub's list of releases could not be read.");
        return CHECK_FAILED;
    }
    return found ? FOUND_NEWER : FOUND_LATEST;
}

static void *run(void *unused)
{
    (void)unused;
    __atomic_store_n(&job.done, check(), __ATOMIC_RELEASE);
    return NULL;
}

static int start(int manual)
{
    pthread_t thread;
    sigset_t all, previous;
    UpdateVersion current;
    const char *url = getenv("MEMORIES_UPDATE_URL");
    int error;
    if (job.running) return -1;
    job.manual = manual;
    job.done = 0;
    job.why[0] = '\0';
    snprintf(job.url, sizeof(job.url), "%s", url && *url ? url : RELEASES_API);
    snprintf(job.current, sizeof(job.current), "%s", current_version());
    job.skip[0] = '\0';
    if (!manual) read_skip(job.skip, sizeof(job.skip));
    job.prereleases = Settings_Get(SET_UPDATE_PRERELEASES);
    /* Someone running a preview wants to hear of the next one. */
    if (Update_ParseVersion(job.current, &current) && current.pre[0]) job.prereleases = 1;
    /* The game's clock signal belongs to the main thread (platform_common.c). */
    sigfillset(&all);
    pthread_sigmask(SIG_BLOCK, &all, &previous);
    error = pthread_create(&thread, NULL, run, NULL);
    pthread_sigmask(SIG_SETMASK, &previous, NULL);
    if (error) return -1;
    pthread_detach(thread);
    job.running = 1;
    return 0;
}

/* --- the notices ----------------------------------------------------- */

static void open_url(const char *url)
{
    if (Platform_OpenUrl(url && *url ? url : RELEASES_PAGE))
        fprintf(stderr, "memories-pc: update: could not open %s\n", url && *url ? url : RELEASES_PAGE);
}

/* The release's html_url when it is a release page of this repository, else
 * the releases page: the answer never chooses what the browser (or, on
 * Windows, the shell) is handed. */
static const char *release_page(const char *page)
{
    static const char prefix[] = RELEASES_PAGE "/tag/";
    size_t length = sizeof(prefix) - 1;
    const char *at;
    if (strncmp(page, prefix, length) || !page[length]) return RELEASES_PAGE;
    for (at = page + length; *at; at++)
        if (!isalnum((unsigned char)*at) && !strchr(".-_%", *at)) return RELEASES_PAGE;
    return page;
}

static void chosen_newer(int button, int *quit)
{
    (void)quit;
    switch (button) {
    case 0: open_url(release_page(offered.page)); break;
    case 1: write_skip(offered.tag); break;
    default: break;
    }
}

static void show_newer(void)
{
    static const char *const buttons[] = {"Release page", "Skip this version", "Later"};
    char title[128], text[1024];
    snprintf(title, sizeof(title), "%s %s is out", offered.prerelease ? "Pre-release" : "Version", offered.tag);
    snprintf(text, sizeof(text),
             "%s is available; you have %s.\n\n"
             "The game does not download or install anything itself. Get the new version from its release "
             "page and unpack it the way you did this one; your saves, settings and mods stay in your user folder.",
             offered.title, current_version());
    Menu_ShowNotice(title, text, buttons, 3, -1, chosen_newer);
}

static void chosen_plain(int button, int *quit)
{
    (void)button;
    (void)quit;
}

static void chosen_releases(int button, int *quit)
{
    (void)quit;
    if (button == 0) open_url(RELEASES_PAGE);
}

void Update_Frame(void)
{
    int done;
    char text[1024];
    if (!job.running) return;
    done = __atomic_load_n(&job.done, __ATOMIC_ACQUIRE);
    if (!done) return;
    job.running = 0;
    switch (done) {
    case FOUND_NEWER:
        offered = job.release;
        fprintf(stderr, "memories-pc: update: %s is out (running %s)\n", offered.tag, current_version());
        show_newer();
        break;
    case FOUND_LATEST:
        fprintf(stderr, "memories-pc: update: no newer release to offer than %s\n", current_version());
        if (job.manual) {
            static const char *const ok[] = {"OK"};
            snprintf(text, sizeof(text), "%s is the newest release.", current_version());
            Menu_ShowNotice("You're up to date", text, ok, 1, 0, chosen_plain);
        }
        break;
    case CHECK_FAILED:
        fprintf(stderr, "memories-pc: update: check failed: %s\n", job.why);
        if (job.manual) {
            static const char *const buttons[] = {"Releases page", "Close"};
            snprintf(text, sizeof(text), "%s\n\nYou can look at the releases page instead.", job.why);
            Menu_ShowNotice("Could not check for updates", text, buttons, 2, 1, chosen_releases);
        }
        break;
    default: break;
    }
}

void Update_CheckNow(void)
{
    if (job.running) return;
    if (!known_version()) {
        static const char *const buttons[] = {"Releases page", "Close"};
        Menu_ShowNotice("Development build",
                        "This build was not made from a release, so it has no version to compare with the "
                        "releases. The releases page lists what is out.",
                        buttons, 2, 1, chosen_releases);
        return;
    }
    start(1);
}

void Update_OpenReleases(void) { open_url(RELEASES_PAGE); }

void Update_Start(void)
{
    const char *url = getenv("MEMORIES_UPDATE_URL");
    int tested = url && *url;
    if (flag("MEMORIES_NO_UPDATE_CHECK") || getenv("MEMORIES_HEADLESS") || !Settings_Get(SET_UPDATE_CHECK) ||
        !known_version())
        return;
    /* Scripted runs are tests: they reach the network only when told where. */
    if (!tested && (getenv("MEMORIES_SDL_SCRIPT") || getenv("MEMORIES_INPUT"))) return;
    start(0);
}
