/* The Android crash report offer's reports folder (report_folder.h): which
 * report is offered, and that a retired one stays out of the offer without
 * any clock in it (a report written while the clock was behind is offered). */
#define _POSIX_C_SOURCE 200809L
#include "pc/platform/report_folder.h"
#include "scratch.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#ifdef _WIN32
#include <sys/utime.h>
#else
#include <utime.h>
#endif

static char folder[SCRATCH_MAX];

static void path_of(char *out, size_t size, const char *name)
{
    assert(snprintf(out, size, "%s/%s", folder, name) < (int)size);
}

/* A file `name` holding `text`, last written `when`. */
static void write_file(const char *name, const char *text, time_t when)
{
    char path[SCRATCH_MAX + 64];
    FILE *file;
    path_of(path, sizeof(path), name);
    assert((file = fopen(path, "wb")) != NULL);
    assert(fputs(text, file) >= 0);
    assert(!fclose(file));
    {
#ifdef _WIN32
        /* The wide call: the scratch folder's path is UTF-8 (fs.h). */
        struct _utimbuf times;
        wchar_t *wide = Memories_Utf8ToWide(path);
        times.actime = times.modtime = when;
        assert(wide && !_wutime(wide, &times));
        free(wide);
#else
        struct utimbuf times;
        times.actime = times.modtime = when;
        assert(!utime(path, &times));
#endif
    }
}

static int exists(const char *name)
{
    char path[SCRATCH_MAX + 64];
    struct stat info;
    path_of(path, sizeof(path), name);
    return !stat(path, &info);
}

static const char *newest(void)
{
    static ReportFile file;
    return ReportFolder_Newest(folder, &file) ? file.name : NULL;
}

int main(void)
{
    char name[64], path[SCRATCH_MAX + 64];
    time_t now = time(NULL);
    int i, kept;
    assert(scratch_dir(folder, sizeof(folder), "memories-report-folder"));

    assert(ReportFolder_IsReport("crash-12.txt") && ReportFolder_IsReport("hang-3.txt"));
    assert(!ReportFolder_IsReport("crash-12.txt.sent") && !ReportFolder_IsReport("hang-3.dmp") &&
           !ReportFolder_IsReport("handled.txt") && !ReportFolder_IsReport("crash-.tx"));

    /* Nothing to offer: no report, or only an empty one and other files. */
    assert(!newest());
    write_file("crash-101.txt", "", now);
    write_file("handled.txt", "1 2 crash-1.txt\n", now);
    write_file("hang-101.dmp", "dump", now);
    assert(!newest());

    /* The newest report is offered; Retire takes all of them out. */
    write_file("crash-100.txt", "older", now - 60);
    write_file("hang-102.txt", "newer", now);
    assert(newest() && !strcmp(newest(), "hang-102.txt"));
    assert(ReportFolder_Retire(folder, 999, REPORT_FOLDER_KEEP));
    assert(exists("crash-100.txt.sent") && exists("hang-102.txt.sent") && !exists("crash-100.txt"));
    assert(exists("handled.txt") && exists("hang-101.dmp")); /* not reports: left alone */
    assert(!newest());

    /* The clock was a day behind when the next crash wrote its report: it is
     * older than every retired one, and offered all the same. */
    write_file("crash-200.txt", "behind", now - 24 * 60 * 60);
    assert(newest() && !strcmp(newest(), "crash-200.txt"));

    /* The running game's own report stays offered. */
    write_file("crash-999.txt", "this run", now - 30);
    assert(ReportFolder_Retire(folder, 999, REPORT_FOLDER_KEEP));
    assert(exists("crash-200.txt.sent") && exists("crash-999.txt"));
    assert(newest() && !strcmp(newest(), "crash-999.txt"));
    assert(ReportFolder_Retire(folder, 1, REPORT_FOLDER_KEEP));
    assert(!newest());

    /* A report that cannot be retired (its .sent name is a folder) is told
     * and stays offered; the others still go. */
    path_of(path, sizeof(path), "crash-300.txt.sent");
    assert(!mkdir(path, 0700));
    snprintf(path + strlen(path), 16, "/inside");
    write_file("crash-300.txt.sent/inside", "x", now);
    write_file("crash-300.txt", "stuck", now);
    write_file("crash-301.txt", "goes", now);
    assert(!ReportFolder_Retire(folder, 999, REPORT_FOLDER_KEEP));
    assert(exists("crash-301.txt.sent"));
    assert(newest() && !strcmp(newest(), "crash-300.txt"));
    assert(!remove(path));
    path_of(path, sizeof(path), "crash-300.txt.sent");
    assert(!rmdir(path));
    assert(ReportFolder_Retire(folder, 999, REPORT_FOLDER_KEEP));

    /* Only the newest REPORT_FOLDER_KEEP retired reports are kept. Retired
     * so far: crash-101 (the empty one: retired too, so it does not linger),
     * crash-100, hang-102, crash-200, crash-999, crash-301 and crash-300
     * (seven); twelve more, written an hour ago and before, go past ten. */
    for (i = 0; i < 12; i++) {
        snprintf(name, sizeof(name), "crash-%d.txt", 400 + i);
        write_file(name, "many", now - 3600 - i * 60);
    }
    assert(ReportFolder_Retire(folder, 999, REPORT_FOLDER_KEEP));
    kept = 0;
    for (i = 0; i < 12; i++) {
        snprintf(name, sizeof(name), "crash-%d.txt.sent", 400 + i);
        kept += exists(name);
    }
    /* The seven from before are newer than all twelve but crash-200 (a day
     * old): the six of them and the four newest of the twelve stay. */
    assert(kept == 4);
    assert(exists("crash-400.txt.sent") && exists("crash-403.txt.sent") && !exists("crash-404.txt.sent"));
    assert(!exists("crash-200.txt.sent") && exists("crash-100.txt.sent") && exists("crash-101.txt.sent"));

    /* A folder that cannot be read is a failure, never a success. */
    path_of(path, sizeof(path), "missing");
    assert(!ReportFolder_Retire(path, 999, REPORT_FOLDER_KEEP));
    puts("report_folder: ok");
    return 0;
}
