#ifndef MEMORIES_PC_UPDATE_H
#define MEMORIES_PC_UPDATE_H
/* Update checks against the project's GitHub releases (notes/updates.md).
 *
 * This half is the part without a window or a network: version numbers
 * and choosing a release from the GitHub API's answer. update_net.c
 * fetches, and update_check.c runs the check on a thread of its own and
 * tells the player in a notice over the picture (Menu_ShowNotice). */

/* vMAJOR.MINOR.PATCH with an optional -PRE (v0.2.0, v0.2.0-preview.1). */
typedef struct {
    long major, minor, patch;
    char pre[64];
} UpdateVersion;

/* 1 when `text` is such a version (the leading v is optional), else 0. */
int Update_ParseVersion(const char *text, UpdateVersion *out);
/* Semantic versioning order: <0, 0, >0. A pre-release sorts before its
 * release; its dot-separated parts compare numerically when both are
 * numbers, else as text, and a number sorts before text. */
int Update_CompareVersions(const UpdateVersion *a, const UpdateVersion *b);

typedef struct {
    char tag[64];    /* v0.2.0 */
    char title[160]; /* the release's name, else its tag */
    char page[512];  /* the release's page on GitHub */
    int prerelease;
} UpdateRelease;

/* The newest release in a GitHub /releases answer that is newer than
 * `current` and is not `skip` (NULL or "" for none). Drafts are never
 * chosen; pre-releases (GitHub's flag, or a tag with a hyphen) only when
 * `prereleases` is nonzero. 1: found, 0: none newer, -1: not a release
 * list. */
int Update_PickRelease(const char *json, const char *current, int prereleases, const char *skip,
                       UpdateRelease *out);

#endif
