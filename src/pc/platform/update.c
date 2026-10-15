/* Versions and release choice (update.h). No window, no network and no
 * game state: the unit tests (tests/pc/update_test.c) link this file alone
 * with the JSON reader. */
#define _POSIX_C_SOURCE 200809L
#include "update.h"
#include "pc/mods/json.h"
#include <ctype.h>
#include <stdio.h>
#include <string.h>

/* --- versions -------------------------------------------------------- */

static int read_number(const char **text, long *out)
{
    const char *at = *text;
    long value = 0;
    if (!isdigit((unsigned char)*at)) return 0;
    if (*at == '0' && isdigit((unsigned char)at[1])) return 0; /* no leading zeros */
    while (isdigit((unsigned char)*at)) {
        if (value > 100000000L) return 0;
        value = value * 10 + (*at++ - '0');
    }
    *out = value;
    *text = at;
    return 1;
}

int Update_ParseVersion(const char *text, UpdateVersion *out)
{
    UpdateVersion version;
    const char *at = text;
    size_t length;
    if (!text) return 0;
    memset(&version, 0, sizeof(version));
    if (*at == 'v' || *at == 'V') at++;
    if (!read_number(&at, &version.major) || *at++ != '.' || !read_number(&at, &version.minor) ||
        *at++ != '.' || !read_number(&at, &version.patch))
        return 0;
    if (*at == '-') {
        at++;
        length = strlen(at);
        if (!length || length >= sizeof(version.pre)) return 0;
        for (size_t i = 0; i < length; i++) {
            char c = at[i];
            if (!isalnum((unsigned char)c) && c != '.' && c != '-') return 0;
            if (c == '.' && (i == 0 || at[i - 1] == '.' || i + 1 == length)) return 0;
        }
        memcpy(version.pre, at, length + 1);
    } else if (*at == '+') {
        /* Build metadata does not take part in the order, but is checked as
         * the pre-release is: the tag is shown and written to skip.txt. */
        if (!at[1] || strspn(at + 1, "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.-") !=
                          strlen(at + 1))
            return 0;
    } else if (*at) {
        return 0;
    }
    if (out) *out = version;
    return 1;
}

static int all_digits(const char *text, size_t length)
{
    for (size_t i = 0; i < length; i++)
        if (!isdigit((unsigned char)text[i])) return 0;
    return length > 0;
}

static int compare_pre(const char *a, const char *b)
{
    if (!*a || !*b) return !*a && !*b ? 0 : !*a ? 1 : -1; /* the release after its pre-releases */
    for (;;) {
        size_t la = strcspn(a, "."), lb = strcspn(b, ".");
        int na = all_digits(a, la), nb = all_digits(b, lb), order;
        if (na && nb) {
            order = la != lb ? (la < lb ? -1 : 1) : strncmp(a, b, la);
        } else if (na != nb) {
            order = na ? -1 : 1;
        } else {
            size_t shorter = la < lb ? la : lb;
            order = strncmp(a, b, shorter);
            if (!order && la != lb) order = la < lb ? -1 : 1;
        }
        if (order) return order < 0 ? -1 : 1;
        a += la;
        b += lb;
        if (!*a || !*b) return !*a && !*b ? 0 : !*a ? -1 : 1; /* fewer parts sort first */
        a++;
        b++;
    }
}

int Update_CompareVersions(const UpdateVersion *a, const UpdateVersion *b)
{
    if (a->major != b->major) return a->major < b->major ? -1 : 1;
    if (a->minor != b->minor) return a->minor < b->minor ? -1 : 1;
    if (a->patch != b->patch) return a->patch < b->patch ? -1 : 1;
    return compare_pre(a->pre, b->pre);
}

/* --- choosing a release ---------------------------------------------- */

int Update_PickRelease(const char *json, const char *current, int prereleases, const char *skip,
                       UpdateRelease *out)
{
    char error[128];
    JsonDocument *document = json ? Json_Parse(json, error, sizeof(error)) : NULL;
    const JsonValue *root = document ? Json_Root(document) : NULL, *item, *best = NULL;
    UpdateVersion now, newest = {0}, skipped = {0};
    int have_skip = skip && *skip && Update_ParseVersion(skip, &skipped);
    if (!root || Json_TypeOf(root) != JSON_ARRAY || !Update_ParseVersion(current, &now)) {
        Json_Free(document);
        return -1;
    }
    for (item = Json_At(root, 0); item; item = Json_Next(item)) {
        const char *tag = Json_String(Json_Member(item, "tag_name"), NULL);
        UpdateVersion version;
        int pre;
        if (Json_TypeOf(item) != JSON_OBJECT || !tag || !Update_ParseVersion(tag, &version)) continue;
        if (Json_Bool(Json_Member(item, "draft"), 0)) continue;
        pre = Json_Bool(Json_Member(item, "prerelease"), 0) || version.pre[0];
        if (pre && !prereleases) continue;
        if (Update_CompareVersions(&version, &now) <= 0) continue;
        /* Skipping a version also skips any older one it would have hidden. */
        if (have_skip && Update_CompareVersions(&version, &skipped) <= 0) continue;
        if (best && Update_CompareVersions(&version, &newest) <= 0) continue;
        best = item;
        newest = version;
    }
    if (best && out) {
        const char *title = Json_String(Json_Member(best, "name"), NULL);
        memset(out, 0, sizeof(*out));
        snprintf(out->tag, sizeof(out->tag), "%s", Json_String(Json_Member(best, "tag_name"), ""));
        snprintf(out->title, sizeof(out->title), "%s", title && *title ? title : out->tag);
        snprintf(out->page, sizeof(out->page), "%s", Json_String(Json_Member(best, "html_url"), ""));
        out->prerelease = Json_Bool(Json_Member(best, "prerelease"), 0) || newest.pre[0];
    }
    Json_Free(document);
    return best ? 1 : 0;
}
