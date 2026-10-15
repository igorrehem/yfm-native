#ifndef MEMORIES_PC_MODS_HD_PACK_H
#define MEMORIES_PC_MODS_HD_PACK_H
/* The HD pack's download (notes/mods-window.md, "HD pack..."): the Android
 * Mods panel's HD pack... button, which fetches the release's
 * yfm-redecomp-hd-mod-<tag>.zip from GitHub and puts it in the mods folder
 * through the importer (import.h), as Import mod... does with a .zip the
 * player picked.
 *
 * Platform-independent: the network is the platform's (HdNet, set by
 * android.c; Java's HttpURLConnection and DownloadManager there), and
 * nothing is contacted until HdPack_Lookup. Every desktop leaves it unset, so the panel has no
 * button and nothing here runs; the tests drive it with a fake network.
 *
 * One job at a time, each step on a thread of its own (never the game's):
 *   HdPack_Lookup: GET /releases/latest (drafts and pre-releases are never
 *     "latest"), and its asset HD_PACK_PREFIX<tag>.zip (else the first
 *     HD_PACK_PREFIX*.zip) -> HD_FOUND.
 *   HdPack_Download: the asset into `folder` (beside the mods folder, on
 *     the same file system) by the system's download manager (HdNet.fetch),
 *     its size and SHA-256 checked against what the API gave, then read by
 *     Mods_ImportOpen -> HD_DOWNLOADED.
 *   HdPack_Install: Mods_ImportInstall (its hidden folder, then the rename
 *     into place) and the release's tag in HD_PACK_MARKER -> HD_INSTALLED.
 * The caller (mods_window.c, on the game thread) looks between the steps:
 * what is installed already, the free space, which folder a new copy
 * replaces (ModsImportMod.replace) and, at the end, Mods_Discover.
 * HdPack_Cancel stops any step at its next chunk or file; a failure or a
 * cancel removes what the step wrote (HD_FAILED, HdPack_Why), and
 * HdPack_Reset removes the downloaded .zip. */
#include "import.h"
#include <stddef.h>

#define HD_PACK_ID "forbidden-memories-hd"
#define HD_PACK_PREFIX "yfm-redecomp-hd-mod-"
#define HD_PACK_REPOSITORY "Unchiga/Yu-Gi-Oh-Forbidden-Memories-Recompiled"
#define HD_PACK_LATEST "https://api.github.com/repos/" HD_PACK_REPOSITORY "/releases/latest"
/* In the installed mod's folder: the release tag it came from. Its
 * mod.json says "version": "1.0" in every release (hd_assets_pack.py). */
#define HD_PACK_MARKER ".hd-release"

typedef struct {
    char tag[64];        /* v0.2.0 */
    char asset[160];     /* yfm-redecomp-hd-mod-v0.2.0.zip */
    char url[1024];      /* its browser_download_url */
    char sha256[65];     /* lowercase hex, from the asset's "digest" */
    unsigned long size;  /* bytes */
} HdRelease;

/* The network, called only on the job's threads. The release's question is
 * a GET the job reads itself; the pack is downloaded by the system (on
 * Android its DownloadManager), which goes on while the app is in the
 * background: Android 15 closes an app's own connections a few seconds
 * after it leaves the screen, and freezes the app. */
enum { HD_NET_OFFLINE = -1, HD_NET_TIMEOUT = -2, HD_NET_FAILED = -3, HD_NET_NO_MANAGER = -4 };
enum { HD_FETCH_RUNNING = 1, HD_FETCH_WAITING, HD_FETCH_DONE, HD_FETCH_FAILED, HD_FETCH_GONE };
typedef struct HdNet {
    /* A GET of GitHub's JSON API at `url` (redirects followed): 0 with the
     * HTTP status in *status and the stream in *stream, else HD_NET_*. */
    int (*open)(const char *url, void **stream, int *status);
    /* >0 bytes into `buffer`, 0 at the end, HD_NET_* on a failure. */
    long (*read)(void *stream, unsigned char *buffer, size_t size);
    void (*close)(void *stream);
    /* Starts the download of `url` into the file `path` (beside the mods
     * folder): 0 with its handle in *id, else HD_NET_* (HD_NET_NO_MANAGER:
     * the system's download manager is turned off). */
    int (*fetch)(const char *url, const char *path, long long *id);
    /* How it goes (HD_FETCH_*: WAITING for the network or a retry, GONE
     * when it was cancelled outside the game), its bytes so far in *done,
     * and for HD_FETCH_FAILED the reason in *reason: an HTTP status, or
     * the download manager's own (1006: no room). */
    int (*poll)(long long id, unsigned long *done, int *reason);
    /* Once it is done: the file it was saved as (the system may have named
     * it <name>-1 if <name> was in the way): 1, else 0. */
    int (*where)(long long id, char *path, size_t size);
    /* Ends it and forgets it; its file, if still at `path`, is removed. */
    void (*stop)(long long id);
    /* 1 with the lowercase hex SHA-256 of the file `path` in `out` (65
     * bytes), else 0. */
    int (*sha256)(const char *path, char *out);
    /* Stops every download of this app's that the system still has (a job
     * cut short when the app ended). */
    void (*forget)(void);
    /* Tests only (the platform passes it only in a development build):
     * the SHA-256 a download must have instead of the release's. */
    const char *test_sha256;
} HdNet;

enum {
    HD_IDLE,
    HD_LOOKING,     /* a thread asks GitHub */
    HD_FOUND,       /* HdPack_Release */
    HD_DOWNLOADING, /* a thread downloads; HdPack_Done counts */
    HD_DOWNLOADED,  /* HdPack_Import: read and checked, nothing installed */
    HD_INSTALLING,  /* a thread unpacks; HdPack_Done counts */
    HD_INSTALLED,   /* in the mods folder */
    HD_FAILED,      /* HdPack_Why; HdPack_Cancelled when that was the reason */
    HD_CLEANING     /* HdPack_Cleanup's thread, back to HD_IDLE */
};

/* NULL (every desktop): no download. Never while a job runs. */
void HdPack_SetNet(const HdNet *net);
int HdPack_Available(void);
/* The job's state (above); a step's thread is joined once it ended. */
int HdPack_State(void);
/* A thread runs (HD_LOOKING, HD_DOWNLOADING, HD_INSTALLING, HD_CLEANING). */
int HdPack_Busy(void);
/* The step's bytes so far and its whole (the asset's size, then the
 * unpacked size), as of now; whether the download waits for the network. */
unsigned long HdPack_Done(void);
unsigned long HdPack_Total(void);
/* The download waits: 1 for the network (or a retry), 2 for Wi-Fi. */
int HdPack_Waiting(void);
const HdRelease *HdPack_Release(void);
ModsImport *HdPack_Import(void);
const char *HdPack_Why(void);
int HdPack_Cancelled(void);

/* Each starts its step from the state before it: 1, else 0 (wrong state,
 * no network, or no thread: HD_FAILED with the reason). */
int HdPack_Lookup(void);
int HdPack_Download(const char *folder);
int HdPack_Install(const char *mods);
void HdPack_Cancel(void);
/* Back to HD_IDLE from any state but a running step; the .zip removed. */
void HdPack_Reset(void);
/* Removes what a download cut short left (the app ended in it): the
 * system's downloads of this app, then the HD_PACK_PREFIX* files in
 * `folder`; on a thread of its own (HD_CLEANING), only from HD_IDLE. */
void HdPack_Cleanup(const char *folder);

/* What a download and its unpacking need on the disk at once, about: the
 * .zip and its files (a PNG barely shrinks in a .zip: room for a quarter
 * more than the .zip), and a margin past the importer's own 16 MB. */
unsigned long long HdPack_SpaceNeeded(const HdRelease *release);
/* The free bytes where `path` is; -1 when unknown. */
long long HdPack_FreeBytes(const char *path);

/* The release's HD pack in a GitHub /releases/latest answer: 1 with it in
 * `out`; 0 with the reason in `why` (no such asset, no digest); -1 when the
 * text is not a release. */
int HdPack_PickAsset(const char *json, HdRelease *out, char *why, size_t why_size);
/* The tag in `directory`'s HD_PACK_MARKER: 1, else 0 (none; a copy that
 * came another way). */
int HdPack_InstalledTag(const char *directory, char *tag, size_t size);
int HdPack_WriteTag(const char *directory, const char *tag);
#endif
