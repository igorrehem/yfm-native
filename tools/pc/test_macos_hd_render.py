#!/usr/bin/env python3
"""Exercise the real macOS OpenGL presenter with isolated settings and an owned disc.

Requires access to the macOS window server. Optionally reuse an installed texture
pack and a COPY of a portable save to reach Build Deck, without changing the save.
Captures the presented window; inspect window.png beside each run's logs.
"""
import argparse
import os
from pathlib import Path
import re
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disc', type=Path, required=True)
    parser.add_argument('--binary', type=Path, default=ROOT/'tmp/pc/macos/memories-arm64')
    parser.add_argument('--texture-mod', type=Path)
    parser.add_argument('--save', type=Path)
    parser.add_argument('--cases', nargs='+', choices=['1x', '2x', '4x', 'effects'], default=['1x', '2x', '4x', 'effects'])
    args = parser.parse_args()
    binary, disc = args.binary.resolve(), args.disc.resolve()
    if not binary.is_file() or not disc.is_file():
        parser.error('a built executable and owned retail disc are required')
    if args.texture_mod and not (args.texture_mod/'mod.json').is_file():
        parser.error('--texture-mod must contain mod.json')
    folder = ROOT/f'tmp/macos-hd-render/run-{os.getpid()}'
    for case in args.cases:
        output = folder/case
        mods = output/'mods'
        mods.mkdir(parents=True)
        if args.texture_mod:
            (mods/'assets-hd').symlink_to(args.texture_mod.resolve(), target_is_directory=True)
        scale = int(case[0]) if case != 'effects' else 4
        env = {k: v for k, v in os.environ.items() if not k.startswith('MEMORIES_')}
        for key in ('SDL_VIDEODRIVER', 'SDL_RENDER_DRIVER'):
            env.pop(key, None)
        end, sequence = 1100, '700:0008,706:0000'
        if args.save:
            saves = output/'saves'
            saves.mkdir()
            saved = args.save.read_bytes()
            (saves/'slot01.sav').write_bytes(saved)
            events = [(700,'0008'), (780,'0040'), (820,'4000'), (1100,'4000'),
                      (1400,'0040'), (1460,'0040'), (1550,'4000'),
                      (1750,'0020')]  # Select the populated deck pane for visual review.
            events += [(f+6,'0000') for f,_ in list(events)]
            sequence = ','.join(f'{f}:{b}' for f,b in sorted(events))
            end = 2200
        env.update(MEMORIES_DISC=str(disc), MEMORIES_USER_DIR=str(output),
                   MEMORIES_MODS_DIR=str(mods), MEMORIES_NO_UPDATE_CHECK='1',
                   MEMORIES_DETERMINISTIC='1', MEMORIES_SPEED='-1', MEMORIES_DECK_SLOTS='0',
                   MEMORIES_INTERNAL_SCALE=str(scale), MEMORIES_HD_TEXT=str(int(scale > 1)),
                   MEMORIES_INPUT=sequence, MEMORIES_TRACE='window,frames,mods',
                   MEMORIES_TRACE_GAMEPLAY='1', MEMORIES_DUMP_FRAME=str(end),
                   MEMORIES_WINDOW_SHOT=str(end-40), MEMORIES_DUMP_PATH=str(output/'frame.ppm'),
                   MEMORIES_LOG=str(output/'timing.log'), MEMORIES_PAUSE_ON_FOCUS_LOSS='0')
        if case == 'effects':
            env.update(MEMORIES_CRT='1', MEMORIES_REDUCE_FLASHES='1',
                       MEMORIES_XBR='1', MEMORIES_BRIGHTNESS='110', MEMORIES_FILTER='2')
        with (output/'run.log').open('w') as stream:
            subprocess.run([str(binary)], cwd=ROOT, env=env, stdout=stream,
                           stderr=subprocess.STDOUT, check=True, timeout=150)
        log = (output/'run.log').read_text()
        assert re.search(r'OpenGL picture pass on \([34]\.', log), f'no GPU pass: {output}'
        assert not re.search(r'shader:|present pass unavailable|flash reduction unavailable|needs OpenGL 3', log), output
        assert (output/'frame.ppm').is_file(), output
        if scale > 1:
            assert f'per replay at {scale}x' in log, f'no scaled GPU replay: {output}'
        if args.texture_mod:
            assert re.search(r'texture packs: [1-9]\d* images', log), f'pack not loaded: {output}'
        if args.save:
            assert 'mode=c7' in log, f'did not reach Build Deck: {output}'
            assert (output/'saves/slot01.sav').read_bytes() == saved, 'test changed copied save'
        shots = list((output/'screenshots').glob('*.bmp'))
        assert len(shots) == 1, f'no presented window: {output}'
        header = shots[0].read_bytes()[:26]
        assert header[:2] == b'BM' and all(v > 0 for v in struct.unpack_from('<ii', header, 18)), output
        subprocess.run(['sips', '-s', 'format', 'png', str(shots[0]), '--out', str(output/'window.png')],
                       capture_output=True, check=True)
        print(f'{case}: context/replay/window checks passed; inspect content: {output}', flush=True)
    print(f'Inspect presented captures under {folder}', flush=True)


if __name__ == '__main__':
    main()
