/* CoreText discovers installed system faces; FreeType renders their files. */
#ifdef __APPLE__
#include "macos_fonts.h"
#include <CoreText/CoreText.h>

const char *MacOS_FontPath(enum MemoriesMacFont kind)
{
    static char paths[4][1024];
    static unsigned char tried[4];
    CTFontRef font;
    CFURLRef url;
    if ((unsigned)kind >= 4) return NULL;
    if (tried[kind]) return paths[kind][0] ? paths[kind] : NULL;
    tried[kind] = 1;
    if (kind == MEMORIES_FONT_SERIF) font = CTFontCreateWithName(CFSTR("TimesNewRomanPSMT"), 0, NULL);
    else if (kind == MEMORIES_FONT_JAPANESE) font = CTFontCreateWithName(CFSTR("HiraginoSans-W3"), 0, NULL);
    else font = CTFontCreateUIFontForLanguage(kind == MEMORIES_FONT_BOLD ? kCTFontUIFontEmphasizedSystem : kCTFontUIFontSystem, 0, NULL);
    url = font ? CTFontCopyAttribute(font, kCTFontURLAttribute) : NULL;
    if (url && CFGetTypeID(url) == CFURLGetTypeID())
        CFURLGetFileSystemRepresentation(url, true, (UInt8 *)paths[kind], sizeof(paths[kind]));
    if (url) CFRelease(url);
    if (font) CFRelease(font);
    return paths[kind][0] ? paths[kind] : NULL;
}
#endif
