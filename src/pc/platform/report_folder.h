#ifndef MEMORIES_PC_REPORT_FOLDER_H
#define MEMORIES_PC_REPORT_FOLDER_H
/* The reports folder as the Android crash report offer sees it
 * (android_report.c): which report is offered, and taking reports out of the
 * offer once the player has dealt with them. Built on Android only, and for
 * its test (tests/pc/report_folder_test.c, MEMORIES_REPORT_FOLDER_TEST).
 *
 * A report is crash-<pid>.txt or hang-<pid>.txt (crash.c, monitor.c). Share,
 * Save and "Don't ask again" retire every report there is then, by renaming
 * it to <name>.sent, which is no longer a report; the newest
 * REPORT_FOLDER_KEEP of those are kept, the rest removed. Nothing here
 * compares times against a stored one: a report is offered until it is
 * retired, whatever the clock said when it was written. Times only choose
 * the newest report to offer and the retired ones to keep. */

#define REPORT_FOLDER_KEEP 10

typedef struct ReportFile {
    char name[128];      /* in the folder */
    long long sec, nsec; /* its modification time */
    long long size;
} ReportFile;

int ReportFolder_IsReport(const char *name);
/* The newest report in `folder` into *out; 0 when there is none. */
int ReportFolder_Newest(const char *folder, ReportFile *out);
/* Retires every report in `folder` but this process's own (crash-<own_pid>
 * and hang-<own_pid>: a report the running game writes is news), then
 * removes all but the newest `keep` retired ones. 1 when every report was
 * retired, 0 when one could not be (it stays offered); errors go to stderr. */
int ReportFolder_Retire(const char *folder, long own_pid, int keep);

#endif
