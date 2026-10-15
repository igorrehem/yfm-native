/* Guardian Stars as mods change them (src/pc/cards/stars.c): the matchup
 * table, the names, and the game's matchup function reading it.
 *
 * tests/pc/guardian_stars/ holds manifests and, beside each, the table a
 * game built with it uses for every ordered pair of 4-bit star ids
 * (.expected: 16 rows of 16, the attacker's star down, the defender's
 * across). The FM Editor's own test (tools/pc/fm_editor/tests/
 * test_guardian_stars.py) checks its arithmetic against the same files, so
 * the editor and the game agree on every pair. */
#include "../../src/pc/cards/stars.c"
#include "game/duel_calc_guardian_star_matchup.h"
#include <assert.h>
#include <stdarg.h>

int gCard_nCount = 4;
int gDuel_adwCardStats[4];
static int notes;
static char last_note[512];
static int language;

void Mods_Note(const char *id, const char *format, ...)
{
    va_list arguments;
    (void)id;
    va_start(arguments, format);
    vsnprintf(last_note, sizeof(last_note), format, arguments);
    va_end(arguments);
    fprintf(stderr, "note: %s\n", last_note);
    notes++;
}
int Mods_LoadedCount(void) { return 0; }
int Mods_Loaded(int index) { return index; }
int Mods_Active(int mod) { return mod >= 0; }
const char *Mods_Id(int mod) { (void)mod; return ""; }
const char *Mods_Directory(int mod) { (void)mod; return "."; }
const JsonValue *Mods_Manifest(int mod) { (void)mod; return NULL; }
int Paths_Contained(const char *relative) { return relative[0] != '/' && !strstr(relative, ".."); }
int Tables_StatCapEither(void) { return 9999; }
int Language_Current(void) { return language; }
const char *Language_Code(int which) { return which ? "fr" : "en-us"; }
/* ASCII letters are their own codes here; anything else has none. */
uint32_t Glyphs_NextCharacter(const char **text) { return (unsigned char)*(*text)++; }
int Glyphs_Code(uint32_t character) { return character < 0x80 ? (int)character : -1; }

static JsonDocument *load(const char *name)
{
    char path[512], error[256];
    JsonDocument *document;
    snprintf(path, sizeof(path), "%s/tests/pc/guardian_stars/%s", MEMORIES_SOURCE_DIR, name);
    document = Json_ParseFile(path, error, sizeof(error));
    if (!document) fprintf(stderr, "%s: %s\n", path, error);
    assert(document);
    return document;
}

/* The game's Duel_CalcGuardianStarMatchup for every pair against the
 * .expected file beside the manifest. */
static void check_table(const char *manifest, const char *expected)
{
    char path[512];
    FILE *file;
    int a, d;
    JsonDocument *document = load(manifest);
    Stars_Clear();
    Stars_Add(Json_String(Json_Member(Json_Root(document), "id"), ""), Json_Root(document));
    snprintf(path, sizeof(path), "%s/tests/pc/guardian_stars/%s", MEMORIES_SOURCE_DIR, expected);
    file = fopen(path, "r");
    assert(file);
    for (a = 0; a <= STARS_MAX; a++) {
        for (d = 0; d <= STARS_MAX; d++) {
            int want;
            assert(fscanf(file, "%d", &want) == 1);
            if (Duel_CalcGuardianStarMatchup(a, d) != want || Stars_Bonus(a, d) != want) {
                fprintf(stderr, "%s: %d against %d: the game gives %d, %s says %d\n", manifest, a, d,
                        Duel_CalcGuardianStarMatchup(a, d), expected, want);
                assert(0);
            }
        }
    }
    fclose(file);
    Json_Free(document);
}

static const char *name_of(int star)
{
    static char out[64];
    const unsigned char *codes = Stars_NameText(star);
    size_t n = 0;
    if (!codes) return NULL;
    while (*codes != 0xFF && n + 1 < sizeof(out)) out[n++] = (char)*codes++;
    out[n] = '\0';
    return out;
}

int main(void)
{
    int a, d;
    JsonDocument *document;

    /* No mod: nothing decided, the disc's arithmetic everywhere, its quirks
     * outside 1-10 included. */
    Stars_Clear();
    for (a = 0; a <= STARS_MAX; a++) {
        for (d = 0; d <= STARS_MAX; d++) {
            int bonus;
            assert(!Stars_Matchup(a, d, &bonus));
        }
    }
    assert(Stars_RetailMatchup(1, 2) == 500 && Stars_RetailMatchup(2, 1) == -500);
    assert(Stars_RetailMatchup(6, 1) == 500 && Stars_RetailMatchup(10, 7) == 500 && Stars_RetailMatchup(7, 10) == -500);
    assert(Stars_RetailMatchup(1, 7) == 0 && Stars_RetailMatchup(1, 3) == 0);
    assert(Stars_RetailMatchup(0, 1) == 500 && Stars_RetailMatchup(11, 7) == 500);   /* the disc's quirks */
    assert(Stars_Count() == STARS_RETAIL && !Stars_NameText(1) && !strcmp(Stars_Name(9), "Moon"));
    assert(Stars_DisplayStep(500) == 16 && Stars_DisplayStep(512) == 16 && Stars_DisplayStep(1000) == 32);
    assert(Stars_DisplayStep(32767) * 32 >= 32767);

    /* The golden tables, shared with the FM Editor's test. */
    check_table("retail.json", "retail.expected");
    check_table("bonus.json", "bonus.expected");
    check_table("new_stars.json", "new_stars.expected");
    check_table("replace.json", "replace.expected");

    /* A few pairs by hand, so the golden files are not the only word. */
    document = load("bonus.json");
    Stars_Clear();
    Stars_Add("bonus", Json_Root(document));
    assert(Duel_CalcGuardianStarMatchup(1, 2) == 1500);     /* the matchup */
    assert(Duel_CalcGuardianStarMatchup(2, 1) == -1000);    /* the cycle, at the default */
    assert(Duel_CalcGuardianStarMatchup(8, 9) == 0 && Duel_CalcGuardianStarMatchup(9, 8) == -1000);
    assert(Duel_CalcGuardianStarMatchup(8, 1) == -250 && Duel_CalcGuardianStarMatchup(1, 8) == 0);
    assert(Duel_CalcGuardianStarMatchup(0, 1) == 500);      /* no star: the disc's, untouched */
    Json_Free(document);

    document = load("new_stars.json");
    Stars_Clear();
    Stars_Add("new-stars", Json_Root(document));
    assert(Stars_Count() == 13 && Stars_Declared(11) && Stars_Declared(1) && !Stars_Declared(14));
    assert(Duel_CalcGuardianStarMatchup(11, 12) == 500 && Duel_CalcGuardianStarMatchup(12, 11) == -500);
    assert(Duel_CalcGuardianStarMatchup(11, 13) == -300 && Duel_CalcGuardianStarMatchup(13, 11) == 500);
    assert(Duel_CalcGuardianStarMatchup(1, 11) == 1000 && Duel_CalcGuardianStarMatchup(11, 1) == -1000);
    assert(Duel_CalcGuardianStarMatchup(11, 7) == 0);       /* declared: neutral, not the disc's quirk */
    assert(Duel_CalcGuardianStarMatchup(15, 14) == 500);    /* undeclared, still the table's */
    assert(Duel_CalcGuardianStarMatchup(1, 2) == 500);      /* renaming Mars leaves its cycle */
    assert(Stars_Find("Fire") == 11 && Stars_Find("plante") == 12 && Stars_Find("Ares") == 1 &&
           Stars_Find("Mars") == 1 && Stars_Find("13") == 13 && Stars_Find("Nothing") == -1);
    language = 0;
    assert(!strcmp(name_of(11), "Fire") && !strcmp(name_of(12), "Grass") && !strcmp(name_of(1), "Ares"));
    assert(Stars_Named(11) && !Stars_Named(14) && !name_of(14) && !name_of(2));
    Stars_Clear();
    Stars_Add("new-stars", Json_Root(document));
    language = 1;
    assert(!strcmp(name_of(12), "Plante") && !strcmp(Stars_Name(12), "Plante"));
    language = 0;
    /* The checks once the cards are known: star 13 on no card. */
    gDuel_adwCardStats[0] = (11 << 22) | (12 << 18);
    gDuel_adwCardStats[1] = (1 << 22) | (14 << 18);
    notes = 0;
    Stars_Check();
    assert(notes >= 2);
    Json_Free(document);

    /* A new star with no name is "Star N" (not the names bank's Dragon). */
    document = Json_Parse("{\"guardian_stars\": {\"stars\": [{\"id\": 15}]}}", NULL, 0);
    Stars_Clear();
    Stars_Add("x", Json_Root(document));
    assert(!strcmp(name_of(15), "Star 15") && !Stars_Named(15) && Stars_Count() == 15);
    Json_Free(document);

    /* "default_bonus" is its own section's: a later mod's "beats" and
       bonus-less matchups give the disc's 500, as the FM Editor reads it. */
    {
        JsonDocument *first = Json_Parse("{\"guardian_stars\": {\"default_bonus\": 1000}}", NULL, 0);
        JsonDocument *second = Json_Parse("{\"guardian_stars\": {\"stars\": [{\"id\": 11, \"beats\": [\"Mars\"]}],"
                                          " \"matchups\": [{\"attacker\": 8, \"defender\": 1}]}}", NULL, 0);
        Stars_Clear();
        Stars_Add("first", Json_Root(first));
        Stars_Add("second", Json_Root(second));
        assert(Duel_CalcGuardianStarMatchup(1, 2) == 1000);
        assert(Duel_CalcGuardianStarMatchup(11, 1) == 500 && Duel_CalcGuardianStarMatchup(1, 11) == -500);
        assert(Duel_CalcGuardianStarMatchup(8, 1) == 500);
        Json_Free(first);
        Json_Free(second);
    }

    /* What is refused, each with a note and nothing decided. */
    document = Json_Parse("{\"guardian_stars\": {\"stars\": [{\"id\": 16}, {\"id\": 0}, {\"name\": \"x\"}],"
                          " \"matchups\": [{\"attacker\": 1, \"defender\": 2, \"bonus\": 40000},"
                          " {\"attacker\": \"Nowhere\", \"defender\": 2}, {\"attacker\": 1, \"defender\": 2, \"bonus\": \"a\"}],"
                          " \"default_bonus\": 99999, \"color\": 1}}", NULL, 0);
    Stars_Clear();
    notes = 0;
    Stars_Add("bad", Json_Root(document));
    assert(notes == 8);
    assert(Duel_CalcGuardianStarMatchup(1, 2) == 500 && Stars_Count() == 10);
    Json_Free(document);

    /* Past the cap is a note, not an error. */
    document = Json_Parse("{\"guardian_stars\": {\"matchups\": [{\"attacker\": 1, \"defender\": 2, \"bonus\": 12000}]}}",
                          NULL, 0);
    Stars_Clear();
    Stars_Add("big", Json_Root(document));
    assert(Duel_CalcGuardianStarMatchup(1, 2) == 12000);
    memset(gDuel_adwCardStats, 0, sizeof(gDuel_adwCardStats));
    notes = 0;
    Stars_Check();
    assert(notes == 1 && strstr(last_note, "cap"));
    Json_Free(document);

    /* The summon choice: one-star cards never ask; "first", "best" and
       "ask" (the default); a bad "choice" is a note and stays "ask". */
    {
        int enemy[2] = {3, 3};   /* two face-up Saturns */
        Stars_Clear();
        assert(Stars_ChoiceMode() == STARS_CHOICE_ASK);
        assert(Stars_Single(5, 0) && Stars_Single(5, 5) && !Stars_Single(5, 6));
        assert(Stars_SummonChoice(5, 0, enemy, 2) == 0 && Stars_SummonChoice(5, 6, enemy, 2) == -1);
        document = Json_Parse("{\"guardian_stars\": {\"choice\": \"First\"}}", NULL, 0);
        Stars_Add("c", Json_Root(document));
        assert(Stars_ChoiceMode() == STARS_CHOICE_FIRST && Stars_SummonChoice(4, 2, enemy, 2) == 0);
        Json_Free(document);
        document = Json_Parse("{\"guardian_stars\": {\"choice\": \"best\"}}", NULL, 0);
        Stars_Clear();
        Stars_Add("c", Json_Root(document));
        /* Uranus (4) against Saturn: -500 attacking, +500 attacked, so -2000
           over two; Jupiter (2) against Saturn: +2000. The second wins. */
        assert(Stars_SummonChoice(4, 2, enemy, 2) == 1);
        assert(Stars_SummonChoice(2, 4, enemy, 2) == 0);
        assert(Stars_SummonChoice(1, 7, enemy, 2) == 0);   /* a tie: the first */
        assert(Stars_SummonChoice(4, 2, enemy, 0) == 0);   /* no one to face */
        Json_Free(document);
        document = Json_Parse("{\"guardian_stars\": {\"choice\": \"sometimes\"}}", NULL, 0);
        Stars_Clear();
        notes = 0;
        Stars_Add("c", Json_Root(document));
        assert(notes == 1 && Stars_ChoiceMode() == STARS_CHOICE_ASK);
        Json_Free(document);
    }

    /* No star: a card's "stars" may say none, [none, X] is [X, none], and
       once a mod has a monster with no star, star 0 is neutral both ways.
       Before that, star 0 is the disc's (the golden tables' row 0). */
    {
        const JsonValue *value;
        int first, second, a, d, bonus;
        static const int want[] = {0, 0, 0, 0, 1, -1, 3, -1, 20, -1, 0};
        size_t i = 0;
        document = Json_Parse("[0, null, \"none\", \"(None)\", \"Mars\", \"Nothing\", 3, -2, 20, true, \"0\"]", NULL, 0);
        Stars_Clear();
        for (value = Json_At(Json_Root(document), 0); value; value = Json_Next(value), i++) {
            if (Stars_Value(value) != want[i]) {
                fprintf(stderr, "Stars_Value #%d: %d, not %d\n", (int)i, Stars_Value(value), want[i]);
                assert(0);
            }
        }
        assert(i == sizeof(want) / sizeof(want[0]) && Stars_Value(NULL) == -1);
        Json_Free(document);
        /* A star a mod names "None" is that star. */
        document = Json_Parse("{\"guardian_stars\": {\"stars\": [{\"id\": 11, \"name\": \"None\"}]}}", NULL, 0);
        Stars_Add("named", Json_Root(document));
        {
            JsonDocument *text = Json_Parse("\"(none)\"", NULL, 0);
            assert(Stars_Value(Json_Root(text)) == 11);
            Json_Free(text);
        }
        Json_Free(document);

        first = 0, second = 8;
        assert(Stars_Normalize(&first, &second) && first == 8 && second == 0);
        first = 0, second = 0;
        assert(!Stars_Normalize(&first, &second) && first == 0 && second == 0);
        first = 5, second = 0;
        assert(!Stars_Normalize(&first, &second) && first == 5 && second == 0);
        first = 5, second = 6;
        assert(!Stars_Normalize(&first, &second) && first == 5 && second == 6);
        assert(Stars_Single(0, 0));   /* no box at a summon */

        /* The flag off: star 0 is the disc's, untouched. */
        Stars_Clear();
        assert(!Stars_NoStarUsed() && !Stars_Matchup(0, 1, &bonus));
        assert(Duel_CalcGuardianStarMatchup(0, 1) == 500 && Duel_CalcGuardianStarMatchup(0, 5) == -500);
        /* On: 0 against anything and anything against 0 is 0; the rest as
           before, a mod's table included. */
        Stars_NoteNoStar();
        assert(Stars_NoStarUsed());
        for (a = 0; a <= STARS_MAX; a++) {
            assert(Duel_CalcGuardianStarMatchup(0, a) == 0 && Duel_CalcGuardianStarMatchup(a, 0) == 0);
            assert(Stars_Matchup(0, a, &bonus) && bonus == 0 && Stars_Bonus(a, 0) == 0);
            for (d = 1; a && d <= STARS_MAX; d++) {
                assert(Duel_CalcGuardianStarMatchup(a, d) == Stars_RetailMatchup(a, d));
            }
        }
        document = load("replace.json");
        Stars_Add("replace", Json_Root(document));
        assert(Stars_NoStarUsed() && Duel_CalcGuardianStarMatchup(0, 1) == 0);
        Json_Free(document);
        document = load("bonus.json");
        Stars_Clear();
        Stars_Add("bonus", Json_Root(document));
        Stars_NoteNoStar();
        assert(Duel_CalcGuardianStarMatchup(1, 2) == 1500 && Duel_CalcGuardianStarMatchup(0, 1) == 0 &&
               Duel_CalcGuardianStarMatchup(1, 0) == 0);
        {
            /* "best" against a face-up monster with no star: both stars
               score 0, so the first. */
            int enemy[1] = {0};
            JsonDocument *best = Json_Parse("{\"guardian_stars\": {\"choice\": \"best\"}}", NULL, 0);
            Stars_Add("c", Json_Root(best));
            assert(Stars_SummonChoice(4, 2, enemy, 1) == 0);
            Json_Free(best);
        }
        Json_Free(document);
    }

    puts("stars: ok");
    return 0;
}
