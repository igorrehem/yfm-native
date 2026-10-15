/* The update check's parts without a window or a network
 * (src/pc/platform/update.h): version order and choosing a release from
 * GitHub's answer. */
#define _POSIX_C_SOURCE 200809L
#include "pc/platform/update.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static int order(const char *a, const char *b)
{
    UpdateVersion va, vb;
    assert(Update_ParseVersion(a, &va));
    assert(Update_ParseVersion(b, &vb));
    return Update_CompareVersions(&va, &vb);
}

static void versions(void)
{
    static const char *const ascending[] = {
        "v0.0.9", "v0.1.0", "v0.1.1", "v0.2.0-alpha", "v0.2.0-alpha.1", "v0.2.0-alpha.beta", "v0.2.0-beta",
        "v0.2.0-beta.2", "v0.2.0-beta.11", "v0.2.0-preview.1", "v0.2.0-preview.2", "v0.2.0-preview.10",
        "v0.2.0-rc.1", "v0.2.0", "v0.10.0", "v1.0.0"};
    size_t i, j, count = sizeof(ascending) / sizeof(ascending[0]);
    UpdateVersion version;
    for (i = 0; i < count; i++)
        for (j = 0; j < count; j++) {
            int want = i < j ? -1 : i > j ? 1 : 0;
            assert(order(ascending[i], ascending[j]) == want);
        }
    assert(Update_ParseVersion("0.1.0", &version) && version.major == 0 && version.minor == 1);
    assert(Update_ParseVersion("v1.2.3+build.5", &version) && version.patch == 3 && !version.pre[0]);
    assert(!order("v1.2.3+a", "v1.2.3"));
    assert(Update_ParseVersion("v0.2.0-preview.1", &version) && !strcmp(version.pre, "preview.1"));
    assert(!Update_ParseVersion("", NULL));
    assert(!Update_ParseVersion("v1.2", NULL));
    assert(!Update_ParseVersion("v1.2.3.4", NULL));
    assert(!Update_ParseVersion("v01.2.3", NULL));
    assert(!Update_ParseVersion("v1.2.3-", NULL));
    assert(!Update_ParseVersion("v1.2.3-a..b", NULL));
    assert(!Update_ParseVersion("dev-0123456789ab", NULL));
    assert(!Update_ParseVersion("20260926-abcdef0", NULL));
    assert(!Update_ParseVersion(NULL, NULL));
    assert(!Update_ParseVersion("v1.2.3+", NULL));
    assert(!Update_ParseVersion("v1.2.3+a\nb", NULL));
    assert(!Update_ParseVersion("v1.2.3+a/../b", NULL));
}

static const char releases[] =
    "[{\"tag_name\":\"v0.3.0\",\"draft\":true,\"prerelease\":false,\"assets\":[]},"
    " {\"tag_name\":\"v0.2.0-rc.1\",\"name\":\"Second release candidate\",\"draft\":false,\"prerelease\":false,"
    "  \"html_url\":\"https://example.invalid/rc1\",\"assets\":[]},"
    " {\"tag_name\":\"v0.2.0-preview.1\",\"name\":\"Preview\",\"draft\":false,\"prerelease\":true,"
    "  \"html_url\":\"https://example.invalid/p1\",\"assets\":[]},"
    " {\"tag_name\":\"v0.1.1\",\"name\":\"\",\"draft\":false,\"prerelease\":false,"
    "  \"html_url\":\"https://example.invalid/v0.1.1\",\"body\":\"caf\\u00e9 \\\"notes\\\" 1.5e3\","
    "  \"assets\":[{\"name\":\"yfm-redecomp-v0.1.1-windows.zip\",\"size\":2000,"
    "               \"browser_download_url\":\"https://example.invalid/w.zip\"},"
    "              {\"name\":\"yfm-redecomp-v0.1.1-linux.tar.gz\",\"size\":1234,\"digest\":\"sha256:ab\","
    "               \"browser_download_url\":\"https://example.invalid/l.tar.gz\",\"download_count\":7}]},"
    " {\"tag_name\":\"nightly\",\"draft\":false,\"prerelease\":false},"
    " {\"tag_name\":\"v0.1.0\",\"name\":\"First\",\"draft\":false,\"prerelease\":false,\"assets\":[]}]";

static void picking(void)
{
    UpdateRelease release;
    /* The release's assets are not looked at: the player downloads it. */
    assert(Update_PickRelease(releases, "v0.1.0", 0, NULL, &release) == 1);
    assert(!strcmp(release.tag, "v0.1.1") && !strcmp(release.title, "v0.1.1") && !release.prerelease);
    assert(!strcmp(release.page, "https://example.invalid/v0.1.1"));
    /* A tag with a hyphen is a pre-release whatever GitHub's flag says;
     * rc sorts after preview; the draft never counts. */
    assert(Update_PickRelease(releases, "v0.1.0", 1, NULL, &release) == 1);
    assert(!strcmp(release.tag, "v0.2.0-rc.1") && release.prerelease);
    assert(!strcmp(release.title, "Second release candidate"));
    /* Skipped, current, and newer-than-everything. Skipping a version skips
     * what is older than it too (skipping rc.1 does not bring up the
     * preview it replaced), but not what is newer. */
    assert(Update_PickRelease(releases, "v0.1.0", 0, "v0.1.1", &release) == 0);
    assert(Update_PickRelease(releases, "v0.1.0", 1, "v0.2.0-rc.1", &release) == 0);
    assert(Update_PickRelease(releases, "v0.1.0", 1, "v0.2.0-preview.1", &release) == 1);
    assert(!strcmp(release.tag, "v0.2.0-rc.1"));
    assert(Update_PickRelease(releases, "v0.1.0", 1, "v0.1.1", &release) == 1);
    assert(!strcmp(release.tag, "v0.2.0-rc.1"));
    assert(Update_PickRelease(releases, "v0.1.1", 0, NULL, &release) == 0);
    assert(Update_PickRelease(releases, "v0.2.0", 1, NULL, &release) == 0);
    assert(Update_PickRelease(releases, "v0.2.0-preview.1", 1, NULL, &release) == 1);
    assert(!strcmp(release.tag, "v0.2.0-rc.1"));
    /* Not an answer, or no version to compare with. */
    assert(Update_PickRelease("{\"message\":\"API rate limit exceeded\"}", "v0.1.0", 0, NULL, &release) == -1);
    assert(Update_PickRelease("<html>", "v0.1.0", 0, NULL, &release) == -1);
    assert(Update_PickRelease(releases, "", 0, NULL, &release) == -1);
    assert(Update_PickRelease("[]", "v0.1.0", 0, NULL, &release) == 0);
    /* Hostile answers: nested too deeply, cut short, not strings. */
    {
        static char deep[20002];
        memset(deep, '[', 20000);
        assert(Update_PickRelease(deep, "v0.1.0", 0, NULL, &release) == -1);
    }
    assert(Update_PickRelease("[{\"tag_name\":\"v9.0.0\"", "v0.1.0", 0, NULL, &release) == -1);
    assert(Update_PickRelease("[{\"tag_name\":9},{\"tag_name\":[\"v9.0.0\"]},1,null]", "v0.1.0", 0, NULL,
                              &release) == 0);
}

int main(void)
{
    versions();
    picking();
    puts("update: ok");
    return 0;
}
