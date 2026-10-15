#include "pc/guest/state.h"
#include "game/build_deck_transition_state.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>

static int entered, vsync_calls, diagnostics;
const unsigned Memories_GameFingerprint = 0x13572468u;
/* Optional gameplay tracing reads the real layout; this unit does not run
 * the deck menu or bind a game image. */
BuildDeckTransitionState gBuildDeck_aWorkspace[2];
extern int VSync(int mode);
/* Observing test doubles for the SDK/frame service and diagnostic sink.
 * No fake game routines are linked into the shipping backend. */
int Memories_VSync(int mode)
{
    assert(mode == 0);
    ++vsync_calls;
    Memories_StatePoint((unsigned)vsync_calls);
    return 263;
}
void Crash_ReportSoft(const char *kind, const char *detail)
{
    assert(strcmp(kind, "native save states unavailable") == 0);
    assert(detail && *detail);
    ++diagnostics;
}
static int game_entry(void)
{
    ++entered;
    assert(VSync(0) == 263);
    return 37;
}
int main(void)
{
    char path[32] = "not-cleared";
    assert(!Memories_StateStartupDone());
    assert(Memories_StateBuildId() == Memories_GameFingerprint);
    assert(Memories_StateRunGame(game_entry) == 37);
    assert(entered == 1 && vsync_calls == 1 && diagnostics == 0);
    assert(Memories_StateStartupDone());
    assert(Memories_StateRunGame(NULL) == 1 && errno == EINVAL);
    Memories_StateRequest(1, 2);
    assert(diagnostics == 0);
    assert(VSync(0) == 263 && diagnostics == 1 && errno == ENOTSUP);
    assert(VSync(0) == 263 && diagnostics == 1);
    Memories_StateRequest(2, 2);
    assert(VSync(0) == 263 && diagnostics == 2 && errno == ENOTSUP);
    assert(Memories_LastStateSlot() == 0);
    assert(Memories_StateLoading(NULL) == 0);
    assert(Memories_StateChunk(NULL, "test", NULL, 0) == 0 && errno == EINVAL);
    assert(diagnostics == 2);
    Memories_StateRemapRange(NULL, 1, 2, 4);
    assert(diagnostics == 3 && errno == ENOTSUP);
    assert(Memories_SymbolTablePath(path, sizeof(path)) == -1);
    assert(path[0] == '\0' && errno == ENOTSUP);
    assert(Memories_StateSaveHere("unused.state") == -1 && errno == ENOTSUP);
    assert(Memories_StateLoadHere("unused.state", path, sizeof(path)) == -1 && errno == ENOTSUP);
    assert(strstr(path, "unsupported") && diagnostics == 5);
    assert(Memories_StateLoadHere("unused.state", NULL, 0) == -1 && errno == ENOTSUP);
    puts("Native game entry/VSync delegation and explicit state rejection passed");
    return 0;
}
