/* The reports folder of the Android crash report offer (report_folder.h). */
#if defined(__ANDROID__) || defined(MEMORIES_REPORT_FOLDER_TEST)
#define _POSIX_C_SOURCE 200809L
#include "pc/compat/fs.h"
#include "report_folder.h"
#include <dirent.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#define SENT ".sent"

int ReportFolder_IsReport(const char *name)
{
    size_t length = strlen(name);
    return (!strncmp(name, "crash-", 6) || !strncmp(name, "hang-", 5)) && length > 4 &&
           !strcmp(name + length - 4, ".txt");
}

/* A retired report: <report>.sent. */
static int retired(const char *name)
{
    char report[sizeof(((ReportFile *)0)->name)];
    size_t length = strlen(name), sent = strlen(SENT);
    if (length <= sent || length - sent >= sizeof(report) || strcmp(name + length - sent, SENT)) return 0;
    memcpy(report, name, length - sent);
    report[length - sent] = '\0';
    return ReportFolder_IsReport(report);
}

/* A regular file's modification time and size; 0 when it is not one. */
static int file_info(const char *folder, ReportFile *file)
{
    char path[1200];
    struct stat info;
    if (snprintf(path, sizeof(path), "%s/%s", folder, file->name) >= (int)sizeof(path)) return 0;
    if (stat(path, &info) || !S_ISREG(info.st_mode)) return 0;
#ifdef _WIN32
    file->sec = (long long)info.st_mtime;
    file->nsec = 0;
#elif defined(__APPLE__) /* no st_mtim: a developer's macOS test build */
    file->sec = (long long)info.st_mtimespec.tv_sec;
    file->nsec = (long long)info.st_mtimespec.tv_nsec;
#else
    file->sec = (long long)info.st_mtim.tv_sec;
    file->nsec = (long long)info.st_mtim.tv_nsec;
#endif
    file->size = (long long)info.st_size;
    return 1;
}

/* Newest first; the name settles a tie. */
static int newer(const ReportFile *a, const ReportFile *b)
{
    if (a->sec != b->sec) return a->sec > b->sec;
    if (a->nsec != b->nsec) return a->nsec > b->nsec;
    return strcmp(a->name, b->name) > 0;
}

static int newest_first(const void *a, const void *b)
{
    return newer(a, b) ? -1 : newer(b, a) ? 1 : 0;
}

/* The regular files of `folder` that `wanted` takes, with their times, into
 * a list the caller frees: read whole before anything is renamed, since a
 * folder read while it changes may skip or repeat names. 0 when the folder
 * cannot be read. */
static int list(const char *folder, int (*wanted)(const char *), ReportFile **out, size_t *count)
{
    DIR *directory = opendir(folder);
    struct dirent *entry;
    ReportFile *files = NULL, *grown;
    size_t room = 0, length;
    *out = NULL;
    *count = 0;
    if (!directory) return 0;
    while ((entry = readdir(directory)) != NULL) {
        length = strlen(entry->d_name);
        if (!wanted(entry->d_name) || length >= sizeof(files->name)) continue;
        if (*count == room) {
            room = room ? room * 2 : 16;
            if (!(grown = realloc(files, room * sizeof(*files)))) {
                free(files);
                closedir(directory);
                return 0;
            }
            files = grown;
        }
        memcpy(files[*count].name, entry->d_name, length + 1);
        if (file_info(folder, &files[*count])) ++*count;
    }
    closedir(directory);
    *out = files;
    return 1;
}

int ReportFolder_Newest(const char *folder, ReportFile *out)
{
    ReportFile *files;
    size_t count, i;
    int found = 0;
    if (!list(folder, ReportFolder_IsReport, &files, &count)) return 0;
    for (i = 0; i < count; i++) {
        /* An empty one is a crash that wrote nothing: not worth offering. */
        if (files[i].size <= 0) continue;
        if (!found || newer(&files[i], out)) {
            *out = files[i];
            found = 1;
        }
    }
    free(files);
    return found;
}

static int own(const char *name, long own_pid)
{
    char mine[64];
    snprintf(mine, sizeof(mine), "crash-%ld.txt", own_pid);
    if (!strcmp(name, mine)) return 1;
    snprintf(mine, sizeof(mine), "hang-%ld.txt", own_pid);
    return !strcmp(name, mine);
}

int ReportFolder_Retire(const char *folder, long own_pid, int keep)
{
    ReportFile *files;
    size_t count, i;
    char from[1200], to[1200];
    int ok = 1;
    if (!list(folder, ReportFolder_IsReport, &files, &count)) {
        fprintf(stderr, "memories-pc: crash report: could not read %s: %s\n", folder, strerror(errno));
        return 0;
    }
    for (i = 0; i < count; i++) {
        if (own(files[i].name, own_pid)) continue;
        if (snprintf(from, sizeof(from), "%s/%s", folder, files[i].name) >= (int)sizeof(from) ||
            snprintf(to, sizeof(to), "%s" SENT, from) >= (int)sizeof(to)) {
            fprintf(stderr, "memories-pc: crash report: the path of %s is too long\n", files[i].name);
            ok = 0;
        } else if (rename(from, to)) {
            if (errno == ENOENT) continue; /* gone already is as good as retired */
            fprintf(stderr, "memories-pc: crash report: could not retire %s: %s\n", from, strerror(errno));
            ok = 0;
        } else {
            fprintf(stderr, "memories-pc: crash report %s retired\n", files[i].name);
        }
    }
    free(files);
    /* The newest `keep` retired ones stay; a failure here costs only room. */
    if (list(folder, retired, &files, &count)) {
        if (count) qsort(files, count, sizeof(*files), newest_first);
        for (i = keep > 0 ? (size_t)keep : 0; i < count; i++) {
            snprintf(from, sizeof(from), "%s/%s", folder, files[i].name);
            if (remove(from)) fprintf(stderr, "memories-pc: crash report: could not remove %s: %s\n", from, strerror(errno));
        }
        free(files);
    }
    return ok;
}
#endif
