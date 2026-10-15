/* The few fontconfig calls the port makes (menu.c, glyphs.c, cards/art.c,
 * libapi_krom.c), for Android, which has no fontconfig: a pattern's family
 * picks one of the system's own fonts under /system/fonts. Only the Android
 * build has this folder on its include path (tools/pc/build_game32.py). */
#ifndef MEMORIES_PC_COMPAT_ANDROID_FONTCONFIG_H
#define MEMORIES_PC_COMPAT_ANDROID_FONTCONFIG_H
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

typedef unsigned char FcChar8;
typedef int FcBool;
typedef enum { FcResultMatch, FcResultNoMatch } FcResult;
typedef enum { FcMatchPattern } FcMatchKind;
typedef struct { const char *file; } FcPattern;
#define FC_FILE "file"

static inline FcBool FcInit(void) { return 1; }

/* The first of the candidates the system has. */
static inline const char *memories_system_font(const char *const *candidates)
{
    for (; *candidates; candidates++) {
        if (!access(*candidates, R_OK)) return *candidates;
    }
    return NULL;
}

static inline FcPattern *FcNameParse(const FcChar8 *name)
{
    static const char *const serif[] = {"/system/fonts/NotoSerif-Regular.ttf", "/system/fonts/DroidSerif-Regular.ttf",
                                        "/system/fonts/Roboto-Regular.ttf", NULL};
    static const char *const bold[] = {"/system/fonts/Roboto-Bold.ttf", "/system/fonts/Roboto-Regular.ttf",
                                       "/system/fonts/DroidSans-Bold.ttf", NULL};
    static const char *const japanese[] = {"/system/fonts/NotoSansCJK-Regular.ttc",
                                           "/system/fonts/NotoSansJP-Regular.otf", "/system/fonts/DroidSansFallback.ttf",
                                           NULL};
    static const char *const sans[] = {"/system/fonts/Roboto-Regular.ttf", "/system/fonts/DroidSans.ttf", NULL};
    const char *text = (const char *)name;
    FcPattern *pattern = (FcPattern *)malloc(sizeof(FcPattern));
    if (!pattern) return NULL;
    pattern->file = memories_system_font(strstr(text, "lang=ja") ? japanese : strstr(text, "Times") ? serif :
                                         strstr(text, "bold") ? bold : sans);
    return pattern;
}

static inline FcBool FcConfigSubstitute(void *config, FcPattern *pattern, FcMatchKind kind)
{
    (void)config; (void)pattern; (void)kind;
    return 1;
}

static inline void FcDefaultSubstitute(FcPattern *pattern) { (void)pattern; }

static inline FcPattern *FcFontMatch(void *config, FcPattern *pattern, FcResult *result)
{
    FcPattern *match;
    (void)config;
    if (!pattern || !pattern->file || !(match = (FcPattern *)malloc(sizeof(FcPattern)))) {
        *result = FcResultNoMatch;
        return NULL;
    }
    *match = *pattern;
    *result = FcResultMatch;
    return match;
}

static inline FcResult FcPatternGetString(const FcPattern *pattern, const char *object, int n, FcChar8 **value)
{
    if (!pattern || !pattern->file || n || strcmp(object, FC_FILE)) return FcResultNoMatch;
    *value = (FcChar8 *)pattern->file;
    return FcResultMatch;
}

static inline void FcPatternDestroy(FcPattern *pattern) { free(pattern); }
#endif
