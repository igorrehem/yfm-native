#!/usr/bin/env python3
"""Play the village sequence, exit, and revisit with persistent story flags.

Requires an owned USA disc. A data mod supplies a burn deck and 1000 opposing
LP; victories, dialogue and progression all use ordinary controller input.
"""
import argparse
import json
import os
from pathlib import Path
from yfm_control import Game, ROOT

FLAGS = 0x801D0618

def has_flag(image, flag):
    return bool(image[flag >> 3] & (0x80 >> (flag & 7)))

def run(binary, disc, language, folder):
    mods = folder / 'mods'; fixture = mods / 'fast-duels'
    fixture.mkdir(parents=True)
    (fixture / 'mod.json').write_text(json.dumps({
        'id': 'campaign-regression', 'name': 'Campaign regression', 'enabled': True,
        'starter': {'name': 'Burn deck', '347': 40},
        'limits': {'life_points': {'opponent': 1000}}}))
    records = []
    with Game(binary, out=folder, mods_dir=mods, env={
            'MEMORIES_DISC': str(disc), 'MEMORIES_LANGUAGE': str(language)}) as game:
        game.wait_until(lambda g: g.resident('main_menu'), 3000)
        game.press_until(lambda g: g.resident('password'), ['start', 'cross'], every=40)
        game.press_until(lambda g: g.player_name(), 'cross', every=20)
        game.press('start')
        game.press_until(lambda g: g.mode() == 2, 'cross', every=40)
        game.press_until(lambda g: g.mode() == 5, 'cross', every=50, timeout=20000)
        game.step(400)
        game.press('down'); game.step(400)
        assert game.mode() == 5 and game.u8('gCampaignMap_Location') == 12
        game.press_until(lambda g: g.mode() == 3, 'cross', every=50, timeout=20000)
        for index, opponent in enumerate((2, 4, 5, 6)):
            game.step(30)
            assert game.u8('gDuel_bOpponentID') == opponent
            game.duel_ready()
            assert all(card['id'] == 347 for card in game.duel()[0]['hand'])
            game.play_card(0, face_up=True)
            game.press_until(lambda g: g.mode() != 3, 'cross', every=50, timeout=16000)
            assert game.u8('gCampaignSceneIndex') == (98, 100, 102, 104)[index]
            records.append({'opponent': opponent, 'scene': game.u8('gCampaignSceneIndex')})
            if index < 3:
                game.press_until(lambda g: g.mode() == 3, 'cross', every=50, timeout=20000)
        # The retail scene offers another person or exit. Cross on the
        # first item can revisit this prompt; advancement requires Exit.
        game.press_until(lambda g: g.u32('D_8009B290') == 0x801A85EB and
                         g.u8('gDialog_bChoiceCount') == 2, 'cross', every=50, timeout=6000)
        game.step(300); game.shot('village-complete.png')
        before = game.peek(FLAGS, 256)
        assert all(has_flag(before, 0x1F + opponent) for opponent in (2, 4, 5, 6))
        game.press('down'); game.step(80)
        assert game.u8('gDialog_bChoice') == 1
        game.press('cross')
        game.press_until(lambda g: g.mode() == 5, 'cross', every=50, timeout=10000)
        game.step(300)
        progressed = game.peek(FLAGS, 256)
        assert has_flag(progressed, 0x6F) and not has_flag(before, 0x6F)
        assert all(has_flag(progressed, 0x1F + opponent) for opponent in (2, 4, 5, 6))
        assert game.u8('gCampaignMap_Location') == 10
        game.press('left'); game.step(400)
        assert game.mode() == 5 and game.u8('gCampaignMap_Location') == 12
        game.press('cross'); game.step(250)
        game.press_until(lambda g: g.mode() == 3, 'cross', every=50, timeout=10000)
        assert game.peek(FLAGS, 256) == progressed, 'campaign flags lost on reentry'
        # This is the rematch branch (Jono recalls losing), distinct from
        # the first-visit tournament script. Languages use the same script.
        assert game.u32('D_8009B290') == 0x801A8277
        records.append({'exit_flag': 0x6F, 'reentry_script': '0x277', 'flags': progressed.hex()})
        (folder / 'records.json').write_text(json.dumps(records, indent=2) + '\n')
    print(f'Campaign language {language}: Jono/three villagers, Exit advancement, '
          f'Duel Ground rematch and preserved flags passed; {folder}', flush=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, default=ROOT / 'tmp/pc/macos/memories-arm64')
    parser.add_argument('--disc', type=Path, default=ROOT / 'game/YGOFM Vanilla (Base).bin')
    parser.add_argument('--language', type=int, choices=(0, 2), help='run one language (default: English)')
    parser.add_argument('--all-languages', action='store_true', help='also run French coverage')
    args = parser.parse_args()
    if args.all_languages and args.language is not None:
        parser.error('--all-languages and --language are mutually exclusive')
    binary, disc = args.binary.resolve(), args.disc.resolve()
    if not binary.is_file() or not disc.is_file():
        parser.error('a built game and an owned USA disc are required')
    folder = ROOT / f'tmp/arm64-campaign/test-{os.getpid()}'
    for language in (0, 2) if args.all_languages else (args.language if args.language is not None else 0,):
        run(binary, disc, language, folder / str(language))

if __name__ == '__main__':
    main()
