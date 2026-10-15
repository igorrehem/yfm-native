/* A won duel's starchips past the results row's eight
 * (src/pc/cards/starchip_prize.c): the pictures the row draws, and the "xN"
 * beside the one picture, in the game's text codes. */
#include "../../src/pc/cards/starchip_prize.c"
#include <stdlib.h>
#include <string.h>

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition);     \
            exit(1);                                                            \
        }                                                                       \
    } while (0)

DuelResultDisplayState *G32 D_8009B1E8;

/* The game's letters as ASCII, but for one that needs the extended form. */
int Glyphs_Code(uint32_t character) { return character == 'x' ? 0x1F1 : (int)character; }

int main(void)
{
    static const unsigned char x250[] = {0xF8, 0x04, 2, 0xF8, 0x0A, 0x00, 0xF1, 0xF1, '2', '5', '0', 0xFF};
    static const unsigned char x1000[] = {0xF8, 0x04, 2, 0xF8, 0x0A, 0x00, 0xF1, 0xF1, '1', '0', '0', '0', 0xFF};
    DuelResultDisplayState record;
    int prize;

    /* The disc's row up to eight; one picture past it. */
    CHECK(StarchipPrize_Pictures(0) == 0 && StarchipPrize_Pictures(-3) == 0);
    for (prize = 1; prize <= STARCHIP_PRIZE_ROW; prize++) {
        CHECK(StarchipPrize_Pictures(prize) == prize);
        CHECK(!StarchipPrize_Counted(prize) && StarchipPrize_Compose(prize) == NULL);
    }
    CHECK(StarchipPrize_Pictures(9) == 1 && StarchipPrize_Pictures(1000) == 1);
    CHECK(StarchipPrize_Counted(9) && StarchipPrize_Counted(1000) && !StarchipPrize_Counted(0));

    /* "xN": the letters' size, white, then the count. */
    CHECK(!memcmp(StarchipPrize_Compose(250), x250, sizeof(x250)));
    CHECK(!memcmp(StarchipPrize_Compose(1000), x1000, sizeof(x1000)));
    CHECK(StarchipPrize_Compose(9)[8] == '9' && StarchipPrize_Compose(9)[9] == 0xFF);

    /* Text_Resolve's question: only its own id, from the results record. */
    CHECK(StarchipPrize_Text(STARCHIP_PRIZE_TEXT_ID) == NULL);   /* no record yet */
    memset(&record, 0, sizeof(record));
    D_8009B1E8 = &record;
    record.starchip_prize = 5;
    CHECK(StarchipPrize_Text(STARCHIP_PRIZE_TEXT_ID) == NULL);   /* the disc's row */
    record.starchip_prize = 1000;
    CHECK(sizeof(record) == 0x40 && *((unsigned char *)&record + 0x3A) == (1000 & 0xFF) &&
          *((unsigned char *)&record + 0x3B) == (1000 >> 8));
    CHECK(!memcmp(StarchipPrize_Text(STARCHIP_PRIZE_TEXT_ID), x1000, sizeof(x1000)));
    CHECK(StarchipPrize_Text(STARCHIP_PRIZE_TEXT_ID - 1) == NULL && StarchipPrize_Text(0x44) == NULL);
    puts("starchip_prize: ok");
    return 0;
}
