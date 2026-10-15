#define _POSIX_C_SOURCE 200809L
#include "pc/platform/settings.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "pc/compat/posix.h"
#include "scratch.h"
#include <unistd.h>

static int contains(const char *path, const char *wanted)
{
    FILE *file = fopen(path, "r");
    char text[8192];
    size_t length;
    assert(file);
    length = fread(text, 1, sizeof(text) - 1, file);
    text[length] = '\0';
    fclose(file);
    return strstr(text, wanted) != NULL;
}

int main(void)
{
    char directory[SCRATCH_MAX], path[SCRATCH_MAX + 16];
    FILE *file;
    assert(scratch_dir(directory, sizeof(directory), "memories-settings"));
    snprintf(path, sizeof(path), "%s/settings.txt", directory);
    file = fopen(path, "wb");
    assert(file);
    fputs("volume=40\nmusic_volume=70\nunknown=7\npgxp=2\nhd_hud=1\n", file);
    assert(!fclose(file));
    assert(!setenv("MEMORIES_SETTINGS", path, 1));
    Settings_Load();
    assert(Settings_Get(SET_MASTER_VOLUME) == 40);
    assert(Settings_Get(SET_MUSIC_VOLUME) == 70);
    assert(Settings_Get(SET_SFX_VOLUME) == 100);
    /* Only "Textures" (1) is offered yet; a saved, env-supplied or runtime
     * "Textures and positions" (2) preference clamps down to it. */
    assert(Settings_Get(SET_PGXP) == 1);
    assert(!setenv("MEMORIES_PGXP", "1", 1));
    Settings_Load();
    assert(Settings_Get(SET_PGXP) == 1);
    assert(!setenv("MEMORIES_PGXP", "2", 1));
    Settings_Load();
    assert(Settings_Get(SET_PGXP) == 1);
    assert(!unsetenv("MEMORIES_PGXP"));
    Settings_Set(SET_PGXP, 2);
    assert(Settings_Get(SET_PGXP) == 1);
    Settings_Set(SET_ASPECT, 2);
    assert(Settings_Get(SET_ASPECT) == 2);
    Settings_Set(SET_ASPECT, 3);
    assert(Settings_Get(SET_ASPECT) == 2);
    Settings_Set(SET_SPEED, 999);
    assert(Settings_Get(SET_SPEED) == 400);
    assert(Settings_Get(SET_FPS) == 0);
    Settings_Set(SET_FPS, -5);
    assert(Settings_Get(SET_FPS) == -1);
    Settings_Set(SET_FPS, 144);
    assert(Settings_Get(SET_FPS) == 144);
    Settings_Set(SET_SFX_VOLUME, 65);
    assert(Settings_Save());
    assert(contains(path, "master_volume=40\n"));
    assert(contains(path, "volume=40\n"));
    assert(contains(path, "sfx_volume=65\n"));
    assert(contains(path, "unknown=7\n"));
    assert(contains(path, "pgxp=1\n"));
    /* A retired id keeps its number for code mods (settings.h), but has no
     * key: its old line is carried through as any other unknown one. */
    assert(SET_HD_TEXT == 32 && SET_CARD_DROPS == 38 && Settings_Key(SET_HD_HUD) == NULL);
    Settings_Set(SET_HD_HUD, 1);
    assert(Settings_Get(SET_HD_HUD) == 0 && Settings_GetNamed("hd_hud", -1) == 1);
    assert(contains(path, "hd_hud=1\n"));
    for (int i = 0; i < 1024; i++) {
        char key[200]; snprintf(key, sizeof(key), "mod.a_very_long_mod_id_that_used_to_exceed_the_old_key_limit.option_%d", i);
        Settings_SetNamed(key, i);
    }
    assert(Settings_Save()); Settings_Load();
    for (int i = 0; i < 1024; i++) {
        char key[200]; snprintf(key, sizeof(key), "mod.a_very_long_mod_id_that_used_to_exceed_the_old_key_limit.option_%d", i);
        assert(Settings_GetNamed(key, -1) == i);
    }
    /* Names that could not read back as themselves are refused. */
    Settings_SetNamed("mod.bad=name", 1);
    Settings_SetNamed("mod.x\nvolume", 99);
    assert(Settings_GetNamed("mod.bad=name", -1) == -1 && Settings_GetNamed("mod.x\nvolume", -1) == -1);
    assert(Settings_Save()); Settings_Load();
    assert(Settings_Get(SET_MASTER_VOLUME) != 99 && !contains(path, "bad="));
    assert(!*Settings_LastError() && !Settings_TakeNewError());
    unlink(path);
    assert(!setenv("MEMORIES_SETTINGS", "/dev/null/settings", 1));
    assert(!Settings_Save());
    /* A failed save says where and why ("...settings: <the system's
     * reason>."), told once until the reason changes or a save succeeds. */
    {
        const char *error = Settings_LastError(), *reason = strstr(error, "settings: ");
        printf("%s\n", error);
        assert(!strncmp(error, "Could not save settings to ", 27));
        assert(strstr(error, "null") && reason && strlen(reason) > strlen("settings: ") + 1);
        assert(error[strlen(error) - 1] == '.');
        assert(Settings_TakeNewError() == error && !Settings_TakeNewError());
        assert(!Settings_Save() && !Settings_TakeNewError()); /* the same reason: not news */
    }
    assert(!setenv("MEMORIES_SETTINGS", path, 1));
    assert(Settings_Save() && !*Settings_LastError() && !Settings_TakeNewError());
    unlink(path);
    return 0;
}
