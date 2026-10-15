#ifndef MEMORIES_PC_CARD_TEXT_COLORS_H
#define MEMORIES_PC_CARD_TEXT_COLORS_H

/* Manifest-driven colors for the three pieces of a card detail box. */
struct DuelEffectChannel;

enum {
    CARD_TEXT_COLOR_NAME,
    CARD_TEXT_COLOR_DESCRIPTION,
    CARD_TEXT_COLOR_GUARDIAN_STAR
};

/* Re-read every applied mod's "card_text_colors" after the card and star
 * names are ready.  The calls around a text box preserve its original color
 * while a rule is temporarily in effect. */
void CardTextColors_Build(void);
void CardTextColors_ResetChannel(struct DuelEffectChannel *channel);
void CardTextColors_DestroyChannel(struct DuelEffectChannel *channel);
void CardTextColors_Restore(struct DuelEffectChannel *channel);
void CardTextColors_Apply(struct DuelEffectChannel *channel, int part, int star);

#endif
