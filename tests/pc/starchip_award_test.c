/* Unit test for Mods_AwardStarchips / MEMORIES_EVENT_STARCHIP. */
#include "pc/mods/mods.h"
#include "pc/mods/events.h"
#include <assert.h>
#include <string.h>

int Mods_Count(void) { return 1; }
int Mods_Active(int owner) { return owner == 0; }
const char *Mods_Id(int owner) { (void)owner; return "test"; }
int Mods_SettingKeyValid(const char *key)
{
    (void)key;
    return 1;
}
void Hooks_Clear(int owner) { (void)owner; }
/* No mod's "limits": the game's own 999999. */
long Mods_Limit(const char *name, long fallback)
{
    (void)name;
    return fallback;
}

static void scale(MemoriesModEvent *e)
{
    if (e->phase == MEMORIES_BEFORE)
        e->a *= 5;
}
static void cancel(MemoriesModEvent *e)
{
    if (e->phase == MEMORIES_BEFORE)
        e->handled = 1;
}
static int after_credited = -1;
static void observe(MemoriesModEvent *e)
{
    if (e->phase == MEMORIES_AFTER)
        after_credited = e->result;
}

int main(void)
{
    unsigned chips = 100;
    int token;

    assert(Mods_AwardStarchips(NULL, 5) == 0);
    assert(Mods_AwardStarchips(&chips, 5) == 105 && chips == 105);

    chips = 10;
    assert(Mods_AwardStarchips(&chips, -3) == 10 && chips == 10);

    /* A mod's largest prize (starchip_prize 1000), up to the cap. */
    chips = 0;
    assert(Mods_AwardStarchips(&chips, 1000) == 1000 && chips == 1000);
    chips = 999500;
    assert(Mods_AwardStarchips(&chips, 1000) == 999999 && chips == 999999);

    chips = 999997;
    assert(Mods_AwardStarchips(&chips, 5) == 999999 && chips == 999999);

    /* A balance past the cap (a mod's "limits", off now) is kept, not cut. */
    chips = 50000000;
    assert(Mods_AwardStarchips(&chips, 5) == 50000000 && chips == 50000000);

    token = Mods_Subscribe(0, MEMORIES_EVENT_STARCHIP, 0, scale);
    assert(token);
    assert(Mods_Subscribe(0, MEMORIES_EVENT_STARCHIP, -1, observe));
    after_credited = -1;
    chips = 10;
    assert(Mods_AwardStarchips(&chips, 5) == 35 && chips == 35);
    assert(after_credited == 25);

    after_credited = -1;
    chips = 999990;
    assert(Mods_AwardStarchips(&chips, 5) == 999999 && chips == 999999);
    assert(after_credited == 9);

    Mods_Unsubscribe(0, token);
    assert(Mods_Subscribe(0, MEMORIES_EVENT_STARCHIP, 0, cancel));
    after_credited = -1;
    chips = 50;
    assert(Mods_AwardStarchips(&chips, 5) == 50 && chips == 50);
    assert(after_credited == 0);
    return 0;
}
