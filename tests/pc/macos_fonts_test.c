#include "pc/platform/macos_fonts.h"
#include <ft2build.h>
#include FT_FREETYPE_H
#include <assert.h>
#include <stdio.h>

int main(void)
{
    FT_Library library;
    assert(!FT_Init_FreeType(&library));
    assert(!MacOS_FontPath((enum MemoriesMacFont)4));
    for (unsigned kind = 0; kind < 4; ++kind) {
        const char *path = MacOS_FontPath((enum MemoriesMacFont)kind);
        FT_Face face;
        assert(path && path == MacOS_FontPath((enum MemoriesMacFont)kind));
        assert(!FT_New_Face(library, path, 0, &face));
        assert(!FT_Set_Pixel_Sizes(face, 0, 16));
        FT_UInt glyph = FT_Get_Char_Index(face, kind == MEMORIES_FONT_JAPANESE ? 0x65e5 : 'A');
        assert(glyph && !FT_Load_Glyph(face, glyph, FT_LOAD_RENDER));
        assert(face->glyph->bitmap.width && face->glyph->bitmap.rows);
        FT_Done_Face(face);
        printf("macOS font %u: load and rasterize passed (%s)\n", kind, path);
    }
    FT_Done_FreeType(library);
    return 0;
}
