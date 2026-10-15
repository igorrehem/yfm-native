# Updates

A release build can ask GitHub for the project's releases when it starts
and, when a newer one is out, say so in a notice over the picture:

- **Release page** opens the release on GitHub in the browser (only a
  `github.com/Unchiga/Yu-Gi-Oh-Forbidden-Memories-Recompiled/releases/tag/...`
  address from the answer; anything else opens the releases page).
- **Skip this version** is remembered: that version, and any older one, is
  not offered again at start (a newer one still is).
- **Later** (Esc) asks again next start.

That is all the game does. It never downloads, unpacks or installs a
release: the player gets the new version from its release page and extracts
it as they did the first one. A program that replaces its own files is one
more way for malware to reach a machine (a hijacked account or release, a
tampered download), so the game only tells, and the player decides what to
run.

Nothing blocks the game: the request runs on a thread of its own, and the
main thread only looks at the answer once a frame. Offline, the check at
start fails silently.

## Settings

**Help** on the menu bar. Both are in `settings.txt` and, as every setting,
have an environment override. The check at start is **on by default**:
it only reads the list of releases once per start and tells the player,
so a release reaches players who would not look for it. Turn it off with
**Check for updates at start** in the Help menu, `check_for_updates=0` in
`settings.txt` or `MEMORIES_CHECK_FOR_UPDATES=0` in the environment.

| Menu | Key | Default | Environment |
|---|---|---|---|
| Check for updates at start | `check_for_updates` | 1 | `MEMORIES_CHECK_FOR_UPDATES` |
| Include pre-releases | `update_prereleases` | 0 | `MEMORIES_UPDATE_PRERELEASES` |

**Check for updates now** works whether the check at start is on or not. It
always answers, "You're up to date" and "Could not check for updates"
included, and ignores a skipped version. **Releases page** opens the list.
The last row shows this build's version, or "Development build".

A pre-release is only offered when **Include pre-releases** is on, or when
the running version is itself a pre-release (someone on `v0.2.0-preview.1`
hears of `-preview.2`, `-rc.1` and `v0.2.0`).

## Which version a build is

`tools/pc/build_game32.py` writes `version.c` (`Memories_Version`) beside the
executable's objects on every link: `MEMORIES_VERSION` when it is set, else
the `v*` tag the checkout is exactly at (`git describe --tags --exact-match`).
`tools/pc/package.py` sets `MEMORIES_VERSION` to its `--version`, which the
release workflow takes from the tag. Anything that is not `vX.Y.Z` or
`vX.Y.Z-PRE` (`dev-<sha>` from CI on master, the date-and-commit label of a
local package, an untagged checkout) is a development build: it never checks
at start, and Check for updates now points at the releases page.

Versions compare as [semantic versions](https://semver.org/#spec-item-11):
`v0.2.0-preview.2 < v0.2.0-preview.10 < v0.2.0-rc.1 < v0.2.0`. A tag with a
hyphen is a pre-release whatever GitHub's flag says; drafts never count.

## Networking

No TLS library is linked in. Windows uses WinHTTP (`-lwinhttp`); Linux runs
`curl` (present on practically every distribution; without it the check
fails silently) with `posix_spawn`, reading the body from a pipe, with the
signal mask cleared for the child. The check has 20 seconds (curl's
whole-transfer limit; WinHTTP's per wait). Only the release list is fetched,
never a release's files.

## Tests and scripted runs

The check at start is skipped when any of these hold, so tests and CI never
touch the network:

- `check_for_updates` is 0 (it is 1 by default);
- `MEMORIES_NO_UPDATE_CHECK` is set to anything but `0` (`tools/pc/smoke.py`
  sets it);
- `MEMORIES_HEADLESS` is set;
- the input is scripted (`MEMORIES_INPUT`, `MEMORIES_SDL_SCRIPT`) and
  `MEMORIES_UPDATE_URL` is not set;
- the build is a development build.

For testing the notice end to end:

- `MEMORIES_UPDATE_URL` names another release list (the same JSON as
  `https://api.github.com/repos/Unchiga/Yu-Gi-Oh-Forbidden-Memories-Recompiled/releases`),
  for example one a local `python3 -m http.server` serves;
- `MEMORIES_UPDATE_CURRENT` pretends the running version is another one;
- `MEMORIES_USER_DIR` keeps `updates/skip.txt` and settings away from the
  player's own.

Keys drive the notice from `MEMORIES_SDL_SCRIPT`: Left/Right move the focus
(it starts on the last button), Return presses it, Escape presses the last.

`tests/pc/update_test.c` (CTest `pc_update`) covers the version order and
choosing a release from a GitHub answer. The code is
`src/pc/platform/update.c` (no window, no network), `update_net.c` and
`update_check.c`; the notice is `Menu_ShowNotice` (`menu.h`).

## Limits

- Builds made from source (`play.sh`, `play.bat`) are development builds
  unless the checkout is exactly at a release tag; update those with git.
