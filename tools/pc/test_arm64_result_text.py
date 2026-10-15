#!/usr/bin/env python3
"""Check all three result pages after Simon with opponent names on and off.

Uses controller input and an isolated data mod (burn deck, opponent 1000 LP).
Checks the real glyph list, navigation, rewards and the campaign return.
Requires a built macOS game and a user-owned USA disc.
"""
import argparse
import json
import os
from pathlib import Path
from yfm_control import Game, ROOT

CHANNEL = 0x800EB0F8
ENTRY_SIZE = 0x1C


def run(binary, disc, language, names, folder):
    mods = folder / 'mods'
    fixture = mods / 'burn'
    fixture.mkdir(parents=True)
    (fixture / 'mod.json').write_text(json.dumps({
        'id': 'result-text-regression', 'name': 'Result text regression', 'enabled': True,
        'starter': {'name': 'Burn deck', '347': 40},
        'limits': {'life_points': {'opponent': 1000}}}))
    records = []
    with Game(binary, out=folder, mods_dir=mods, settings={'opponent_name': names},
              env={'MEMORIES_DISC': str(disc), 'MEMORIES_LANGUAGE': str(language)}) as game:
        game.wait_until(lambda g: g.resident('main_menu'), 3000)
        game.press_until(lambda g: g.resident('password'), ['start', 'cross'], every=40)
        game.press_until(lambda g: g.player_name(), 'cross', every=20)
        game.press('start')
        game.press_until(lambda g: g.mode() == 2, 'cross', every=40)
        game.press_until(lambda g: g.mode() == 3, 'cross', every=40, timeout=20000)
        assert game.u8('gDuel_bOpponentID') == 1, 'expected Simon Muran'
        game.duel_ready()
        game.play_card(0, face_up=True)
        game.press_until(lambda g: (g.u16('gDuel_wSceneStateFlags') & 15) == 13,
                         'cross', every=40, timeout=16000)
        game.step(200)
        # Next, next, next, previous: cover all pages, wrap and reverse.
        for index, page in enumerate((0, 1, 2, 0, 2)):
            if index:
                game.press('left' if index == 4 else 'right')
                game.step(200)
            state = game.u32('D_8009B1E8')
            assert game.u8(state + 0x37) == page
            head, end = game.u32(CHANNEL + 0x24), game.u32(CHANNEL + 0x20)
            count = (end - head) // ENTRY_SIZE
            assert end >= head and (end - head) % ENTRY_SIZE == 0
            # A missing copied-bank jump used to end immediately, leaving
            # zero entries; every retail page has several lines of text.
            assert count >= 40, f'empty/incomplete result page {page}: {count} glyphs'
            records.append({'page': page, 'glyphs': count})
            game.shot(f'page-{index}-{page}.png')
        game.press_until(lambda g: g.mode() != 3, 'cross', every=40, timeout=10000)
        assert game.u8('gCampaignSceneIndex') == 96, 'expected Simon victory dialogue'
        assert game.u32('gLibrary_dwStarchips') == 5
        assert sum(game.state()['chest'].values()) == 1
    (folder / 'records.json').write_text(json.dumps(records, indent=2) + '\n')
    print(f'Result text language={language} opponent_name={names}: '
          f'three pages, navigation, reward and campaign return passed; {folder}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, default=ROOT / 'tmp/pc/macos/memories-arm64')
    parser.add_argument('--disc', type=Path, default=ROOT / 'game/YGOFM Vanilla (Base).bin')
    parser.add_argument('--language', type=int, choices=(0, 2))
    parser.add_argument('--output', type=Path, default=ROOT / f'tmp/result-text/test-{os.getpid()}')
    args = parser.parse_args()
    binary, disc = args.binary.resolve(), args.disc.resolve()
    if not binary.is_file() or not disc.is_file():
        parser.error('a built game and a user-owned USA disc are required')
    for language in (0, 2) if args.language is None else (args.language,):
        for names in (0, 1):
            run(binary, disc, language, names, args.output.resolve() / f'{language}-{names}')


if __name__ == '__main__':
    main()
