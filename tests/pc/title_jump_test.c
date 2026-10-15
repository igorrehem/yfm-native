#define _POSIX_C_SOURCE 200809L
#include "pc/platform/title_jump.h"
#include "pc/platform/menu.h"
#include "pc/guest/state.h"
#include "pc/compat/posix.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int enabled, restart_enabled, saving, jumps, notices;
static void (*notice_chosen)(int button, int *quit);

void Menu_SetItemEnabled(int id, int value)
{
    assert(id == MENU_ITEM_TITLE || id == MENU_ITEM_RESTART);
    if (id == MENU_ITEM_TITLE) enabled = value;
    else restart_enabled = value;
}
void Menu_ShowNotice(const char *title, const char *text, const char *const *buttons, int count, int focus,
                     void (*chosen)(int button, int *quit))
{
    (void)title;
    (void)text;
    /* Yes, then No: No is focused and last, which Escape presses. */
    assert(count == 2 && !strcmp(buttons[0], "Yes") && !strcmp(buttons[1], "No") && focus == 1 && chosen);
    notices++;
    notice_chosen = chosen;
}
static void answer(int button)
{
    int quit = 0;
    void (*chosen)(int, int *) = notice_chosen;
    assert(chosen);
    notice_chosen = NULL;
    chosen(button, &quit);
    assert(!quit);
}
int SaveMenu_Active(void) { return saving; }
void TitleJump_Execute(void)
{
    assert(!enabled);
    jumps++;
    /* Input remains live inside the actual disc wait and fade. */
    TitleJump_Request();
    TitleJump_Frame(30);
}

/* The debug menu, as the game side would report it (overrides/title_jump.c). */
static int in_debug_menu, debug_idle, entered = -1, entered_opponent;
static char entered_deck[64];
int TitleJump_InDebugMenu(void) { return in_debug_menu; }
int TitleJump_DebugMenuIdle(void) { return debug_idle; }
int TitleJump_EnterTarget(int target, int opponent, const char *deck)
{
    entered = target;
    entered_opponent = opponent;
    snprintf(entered_deck, sizeof(entered_deck), "%s", deck);
    return 0;
}
int Duelists_Count(void) { return 40; }
int Duelists_Valid(int duelist) { return duelist >= 0 && duelist < 40; }
static int save_loaded;
int Cheats_SaveLoaded(void) { return save_loaded; }
int Cheats_DeckCount(const char *list) { return list[0] >= '0' && list[0] <= '9' ? 40 : 0; }
/* No tower here: nothing refused (tower.h). */
int Tower_Guard(int what, int tell, char *why, size_t size) { (void)what; (void)tell; (void)why; (void)size; return 0; }

struct MemoriesState { int loading, present, active; };
int Memories_StateLoading(const MemoriesState *state) { return state->loading; }
int Memories_StateChunk(MemoriesState *state, const char *tag, const MemoriesStateField *fields, size_t count)
{
    assert(!strcmp(tag, "title-jump") && count == 1 && fields[0].size == sizeof(int));
    if (state->loading) {
        if (!state->present) return 0;
        memcpy(fields[0].data, &state->active, sizeof(int));
        return 1;
    }
    state->present = 1;
    memcpy(&state->active, fields[0].data, sizeof(int));
    return 0;
}

int main(void)
{
    MemoriesState title = {0}, game = {0}, old = {1, 0, 0};
    assert(!setenv("MEMORIES_TITLE_AT", "10,20,30", 1));

    /* Requests at the title, including scheduled ones, must not fire later. */
    TitleJump_SetActive(0);
    TitleJump_Request();
    TitleJump_Frame(10);
    TitleJump_State(&title);
    TitleJump_Poll();
    assert(enabled && jumps == 0);
    TitleJump_State(&game);

    /* Scheduled requests only execute at a safe poll, after saves close. */
    TitleJump_Frame(20);
    assert(jumps == 0);
    saving = 1;
    TitleJump_Poll();
    TitleJump_Poll();
    assert(enabled && jumps == 0);
    saving = 0;
    TitleJump_Poll();
    assert(!enabled && jumps == 1);
    TitleJump_Poll(); /* next game: clicks during the jump were discarded */
    assert(enabled && jumps == 1);

    /* A retail game-over/debug exit enters the frontend too. Clear a
     * queued request and disable input even when our jump did not run. */
    TitleJump_Request();
    TitleJump_SetActive(0);
    assert(!enabled);
    TitleJump_Request();
    TitleJump_Poll();
    assert(enabled && jumps == 1);

    /* Loading a title state while a jump waits on a save discards the
     * request and disables the item immediately. */
    saving = 1;
    TitleJump_Request();
    TitleJump_Poll();
    title.loading = 1;
    TitleJump_State(&title);
    assert(!enabled);
    saving = 0;
    TitleJump_Request();
    TitleJump_Poll();
    assert(jumps == 1);

    /* Loading gameplay at the title enables the item immediately, without
     * waiting for a runner to finish its nested loop. */
    TitleJump_SetActive(0);
    game.loading = 1;
    TitleJump_State(&game);
    assert(enabled);
    TitleJump_Request();
    TitleJump_Poll();
    assert(jumps == 2);

    /* A snapshot never replays an old UI request, nor retains a newer one. */
    TitleJump_Poll();
    TitleJump_Request();
    game.loading = 0;
    TitleJump_State(&game);
    game.loading = 1;
    TitleJump_State(&game);
    TitleJump_Poll();
    assert(jumps == 2);

    /* Older states have no chunk; fail closed until the next safe poll. */
    TitleJump_Request();
    TitleJump_State(&old);
    assert(!enabled);
    TitleJump_Poll();
    assert(enabled && jumps == 2);

    /* Game > Restart game follows the Debug item and asks first: No keeps
     * playing, Yes makes the same request. */
    assert(restart_enabled);
    TitleJump_Confirm();
    assert(notices == 1);
    answer(1);
    TitleJump_Poll();
    assert(jumps == 2);
    TitleJump_Confirm();
    answer(0);
    TitleJump_Poll();
    assert(jumps == 3 && !restart_enabled);
    TitleJump_Poll();
    assert(restart_enabled);

    /* At the title there is nothing to ask; a Yes given as the game got
     * there by itself is dropped. */
    TitleJump_SetActive(0);
    assert(!restart_enabled);
    TitleJump_Confirm();
    assert(notices == 2);
    TitleJump_SetActive(1);
    TitleJump_Confirm();
    TitleJump_SetActive(0);
    answer(0);
    TitleJump_Poll();
    assert(jumps == 3);
    /* Another screen: refused targets, then by way of the title, which
     * gives way to the debug menu, whose entry is taken once it is idle. */
    {
        char why[96];
        unsigned taken;
        assert(TitleJump_RequestTo(JUMP_COUNT, 0, NULL, why, sizeof(why)) == -1);
        assert(TitleJump_RequestTo(JUMP_DUEL, 40, NULL, why, sizeof(why)) == -1 && strstr(why, "no duelist 40"));
        assert(TitleJump_RequestTo(JUMP_DUEL, 0, "1-40", why, sizeof(why)) == -1 && strstr(why, "needs an opponent"));
        assert(TitleJump_RequestTo(JUMP_DUEL, 3, "abc", why, sizeof(why)) == -1 && strstr(why, "no card in the deck"));
        assert(TitleJump_RequestTo(JUMP_DUEL, 3, NULL, why, sizeof(why)) == -1 && strstr(why, "no deck"));
        taken = TitleJump_Count(); /* the title jumps above */
        assert(TitleJump_TargetByName("duel") == JUMP_DUEL && TitleJump_TargetByName("nowhere") == -1);
        assert(!strcmp(TitleJump_TargetName(JUMP_BUILD_DECK), "build_deck"));
        TitleJump_SetActive(1);
        assert(TitleJump_RequestTo(JUMP_DUEL, 3, "1-40", why, sizeof(why)) == 0 && TitleJump_Pending());
        TitleJump_Poll();
        assert(jumps == 4 && entered == -1); /* to the title first */
        TitleJump_SetActive(0);              /* the title's loop */
        assert(TitleJump_Pending());
        TitleJump_TitleGaveWay();            /* its menu returned the debug menu's choice */
        assert(!TitleJump_Pending());
        TitleJump_Poll();                    /* Main_Loop, the debug menu not started yet */
        assert(jumps == 4 && entered == -1);
        debug_idle = 1;
        TitleJump_Poll();
        assert(entered == JUMP_DUEL && entered_opponent == 3 && !strcmp(entered_deck, "1-40") && jumps == 4);
        assert(TitleJump_Count() == taken + 1); /* the duel; the title stage on the way is not counted */
        TitleJump_Poll();
        assert(jumps == 4);
        /* From the idle debug menu itself, no title jump. */
        in_debug_menu = 1;
        entered = -1;
        assert(TitleJump_RequestTo(JUMP_LIBRARY, 0, NULL, why, sizeof(why)) == 0);
        TitleJump_Poll();
        assert(entered == JUMP_LIBRARY && jumps == 4);
        /* A state load drops a waiting jump. */
        in_debug_menu = debug_idle = 0;
        entered = -1;
        assert(TitleJump_RequestTo(JUMP_MAP, 0, NULL, why, sizeof(why)) == 0);
        game.loading = 1;
        TitleJump_State(&game);
        assert(!TitleJump_Pending());
        TitleJump_Poll();
        assert(jumps == 4 && entered == -1);
    }
    puts("title jump: ok");
    return 0;
}
