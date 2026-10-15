#!/usr/bin/env python3
"""Execute real shared-bank selection and typed direct overlay imports."""
import argparse
import subprocess
from guest_test_compile import run_fixture
from llvm_guest import ROOT, toolchain, translate, normalize
from macos_deps import sdk_path
from direct_overlay_bridges import ENTRIES, emit_bridge, validate_declaration


def shared_bank(sanitize):
    out = ROOT / 'tmp/direct-overlay-bridge'
    out.mkdir(parents=True, exist_ok=True)
    compiler = str(toolchain() / 'bin/clang')
    flags = ['-O0', '-DMEMORIES_PC', '-DMEMORIES_TRANSLATED', '-fms-extensions',
             '-Isrc', '-isysroot', str(sdk_path())]
    units = []
    for name, source in [('backend', 'src/pc/guest/translated_image_backend.c'),
                         ('modules', 'src/pc/guest/modules.c')]:
        raw = out / (name + '.raw.ll')
        subprocess.run([compiler, *flags, '-S', '-emit-llvm', source, '-o', str(raw)],
                       cwd=ROOT, check=True, timeout=60)
        text = raw.read_text()
        text = (normalize(text, export_functions=('resolve_function',))
                if name == 'backend' else translate(text))
        unit = out / (name + '.ll')
        unit.write_text(text)
        units.append(str(unit))
    for name in ENTRIES:
        if name == 'func_801462B0':
            continue
        arguments = 'i32 noundef' if ENTRIES[name][1] else ''
        validate_declaration(name, f'declare void @{name}({arguments})')
        try:
            validate_declaration(name, f'declare void @{name}(i64)')
        except ValueError as error:
            assert 'Unsupported direct overlay entry signature' in str(error), error
        else:
            raise AssertionError('wrong ABI accepted')
    bridge = out / 'bridge.c'
    bridge.write_text('#include "pc/guest/translated_runtime.h"\n#include <stdint.h>\n' +
        ''.join(emit_bridge(name) for name in ENTRIES if name != 'func_801462B0'))
    if sanitize:
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    run_fixture(out, units,
                [bridge, 'tests/pc/direct_overlay_bridge_test.c', 'src/pc/memory.c',
                 'src/pc/guest/translated_runtime.c', 'src/pc/guest/state_io.c'],
                [*flags, '-O2'], ['-Wl,-dead_strip'])


def duel_effect(sanitize):
    validate_declaration('func_801462B0',
        'declare void @func_801462B0(i16 noundef signext, i16 noundef signext, i32 noundef, ptr noundef)')
    out = ROOT / 'tmp/duel-effect-bridge'
    out.mkdir(parents=True, exist_ok=True)
    bridge = out/'bridge.c'
    bridge.write_text(emit_bridge('func_801462B0'))
    flags = ['-O2', '-w', '-DMEMORIES_PC', '-fms-extensions', '-Isrc',
             '-isysroot', str(sdk_path())]
    if sanitize:
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    run_fixture(out, [bridge, 'src/pc/overlays/duel_effects.c',
                     'tests/pc/duel_effect_bridge_test.c'], [], flags)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--case', choices=('all', 'shared-bank', 'duel-effect'), default='all')
    args = parser.parse_args()
    if args.case in ('all', 'shared-bank'):
        shared_bank(args.sanitize)
    if args.case in ('all', 'duel-effect'):
        duel_effect(args.sanitize)


if __name__ == '__main__':
    main()
