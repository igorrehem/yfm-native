/* The European releases' narrow letters (serif.h). */
#include "serif.h"

static int body(const unsigned char *cell, int pitch, int x, int y)
{
    return cell[y * pitch + x] >= SERIF_BODY;
}

static int row_has_body(const unsigned char *cell, int pitch, int from, int to, int y)
{
    int x;
    for (x = from; x <= to; x++) {
        if (body(cell, pitch, x, y)) return 1;
    }
    return 0;
}

/* A row of the stem's brightest index: a serif is a stroke across, and
 * the US letters shade their strokes across by row (the stems' columns
 * differ, lighter on the right of an i, on the left of a large one). */
static unsigned char brightest(const unsigned char *cell, int pitch, int left, int right, int y)
{
    unsigned char most = 0;
    int x;
    for (x = left; x <= right; x++) {
        if (cell[y * pitch + x] > most) most = cell[y * pitch + x];
    }
    return most;
}

int Serif_Stem(const unsigned char *cell, int pitch, int width, int height, SerifStem *stem)
{
    int x, y, bottom = -1, measure, left = -1, right = -1;
    for (y = height - 1; y >= 0 && bottom < 0; y--) {
        if (row_has_body(cell, pitch, 0, width - 1, y)) bottom = y;
    }
    if (bottom < 0) return 0;
    measure = bottom > 0 && row_has_body(cell, pitch, 0, width - 1, bottom - 1) ? bottom - 1 : bottom;
    /* The first run of body across that row. */
    for (x = 0; x < width; x++) {
        if (body(cell, pitch, x, measure)) {
            if (left < 0) left = x;
            right = x;
        } else if (left >= 0) {
            break;
        }
    }
    stem->left = left;
    stem->right = right;
    stem->bottom = bottom;
    y = bottom;
    while (y > 0 && row_has_body(cell, pitch, left, right, y - 1)) y--;
    stem->top = y;
    return 1;
}

int Serif_Add(unsigned char *cell, int pitch, int width, int height, int reach, int outline)
{
    SerifStem stem;
    int added[16][2], count = 0, i, k, dx, dy;
    unsigned char foot, head;
    if (!Serif_Stem(cell, pitch, width, height, &stem) || reach < 1 || reach > 4) return 0;
    if (stem.left - reach - 1 < 0 || stem.right + reach + 1 >= width || stem.bottom + 1 >= height || stem.top < 1)
        return 0;
    foot = brightest(cell, pitch, stem.left, stem.right, stem.bottom);
    head = brightest(cell, pitch, stem.left, stem.right, stem.top);
    for (k = 1; k <= reach; k++) {
        /* The foot, either side; the serif, on the left of the first row. */
        cell[stem.bottom * pitch + stem.left - k] = foot;
        added[count][0] = stem.left - k, added[count++][1] = stem.bottom;
        cell[stem.bottom * pitch + stem.right + k] = foot;
        added[count][0] = stem.right + k, added[count++][1] = stem.bottom;
        cell[stem.top * pitch + stem.left - k] = head;
        added[count][0] = stem.left - k, added[count++][1] = stem.top;
    }
    /* The outline round what was added, where there is nothing yet. */
    for (i = 0; i < count; i++) {
        for (dy = -1; dy <= 1; dy++) {
            for (dx = -1; dx <= 1; dx++) {
                int x = added[i][0] + dx, y = added[i][1] + dy;
                if (x >= 0 && x < width && y >= 0 && y < height && !cell[y * pitch + x])
                    cell[y * pitch + x] = (unsigned char)outline;
            }
        }
    }
    return 1;
}
