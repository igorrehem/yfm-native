#!/usr/bin/env python3
"""Verify a macOS ARM64 release ZIP without a ROM or user data."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import plistlib
import re
import shutil
import struct
import subprocess
import tempfile
import zipfile
import uuid

from build_game32 import VERSION_PATTERN
from package_macos import APP, EXECUTABLE, MINIMUM, ROOT, inspect_binary, inspect_icon, shipped_mod_files

LANGUAGES = {f'{name}.txt' for name in ('en-eu', 'fr', 'de', 'it', 'es')}
LICENSES = {'SDL3.txt', 'libpng.txt', 'zlib.txt', 'FreeType.txt'}
REQUIRED_EXPORTS = {'Duel_DrawFieldCards', 'D_800E9DB0', 'SoftGpu_Bank'}


def mach_uuid(image):
    magic, _, _, _, commands, command_bytes, _, _ = struct.unpack_from('<8I', image)
    assert magic == 0xfeedfacf, 'expected a 64-bit Mach-O image'
    offset, end, uuids, signatures, identity = 32, 32 + command_bytes, 0, 0, None
    for _ in range(commands):
        command, size = struct.unpack_from('<II', image, offset)
        assert size >= 8 and offset + size <= end, 'invalid Mach-O load command'
        if command == 0x1b:  # LC_UUID
            uuids += 1
            identity = image[offset + 8:offset + 24]
            assert identity != bytes(16), 'Mach-O UUID is empty'
        elif command == 0x1d:  # LC_CODE_SIGNATURE
            signatures += 1
        offset += size
    assert offset == end and uuids == 1, 'Mach-O must have exactly one build UUID'
    assert signatures <= 1, 'Mach-O has repeated code-signature commands'
    return identity, signatures


def check_archive(path):
    path = path.resolve()
    assert path.is_file(), f'archive does not exist: {path}'
    checksum = path.with_suffix(path.suffix + '.sha256')
    assert checksum.is_file(), f'missing external SHA-256 file: {checksum.name}'
    fields = checksum.read_text(encoding='ascii').strip().split()
    assert len(fields) == 2 and fields[1] == path.name and re.fullmatch(r'[0-9a-f]{64}', fields[0]), \
        f'invalid SHA-256 file: {checksum.name}'
    actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    assert fields[0] == actual_hash, f'{path.name}: SHA-256 does not match its external checksum'

    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None, f'{path.name}: ZIP CRC failure'
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        assert len(names) == len(set(names)), 'archive contains duplicate paths'
        assert names, 'archive is empty'
        for entry in entries:
            item = PurePosixPath(entry.filename)
            assert not item.is_absolute() and '..' not in item.parts and '\\' not in entry.filename, \
                f'unsafe ZIP path: {entry.filename!r}'
            mode = entry.external_attr >> 16
            assert not mode or (mode & 0o170000) in (0, 0o100000), \
                f'archive contains a link or special file: {entry.filename}'
            assert not entry.is_dir(), f'archive should contain files only: {entry.filename}'

        root = APP
        executable_rel = f'{root}/Contents/MacOS/{EXECUTABLE}'
        info_rel = f'{root}/Contents/Info.plist'
        build_rel = f'{root}/Contents/Resources/build.json'
        info = plistlib.loads(archive.read(info_rel))
        icon_name = info.get('CFBundleIconFile')
        assert icon_name in (None, 'Memories.icns'), 'unexpected bundle icon resource'
        expected = {
            'README.txt', 'LICENSE.txt', f'{root}/Contents/PkgInfo', info_rel,
            executable_rel, build_rel, f'{root}/Contents/Resources/LICENSE.txt',
            f'{root}/Contents/_CodeSignature/CodeResources',
        }
        if icon_name:
            expected.add(f'{root}/Contents/Resources/{icon_name}')
        expected |= {f'{root}/Contents/Resources/languages/{name}' for name in LANGUAGES}
        expected |= {f'{root}/Contents/Resources/licenses/{name}' for name in LICENSES}
        mod_files = shipped_mod_files()
        mod_paths = {str(path) for path in mod_files}
        for relative in mod_files:
            if relative.name == 'mod.json':
                mod = json.loads((ROOT / relative).read_text(encoding='utf-8-sig'))
                library = mod.get('library')
                if library:
                    name = library if '.' in library and not library.endswith('.o') else \
                        (library[:-2] if library.endswith('.o') else library) + '.dylib'
                    mod_paths.add(str(relative.parent / name))
        expected |= {f'{root}/Contents/Resources/{name}' for name in mod_paths}
        # codesign seals nested Mach-O libraries as well as the executable.
        assert set(names) == expected, (
            f'archive contents differ; missing={sorted(expected - set(names))}, '
            f'unexpected={sorted(set(names) - expected)}'
        )

        assert info.get('CFBundleExecutable') == EXECUTABLE, 'Info.plist names the wrong executable'
        assert info.get('CFBundleIdentifier') == 'org.yfm-redecomp.memories', 'unexpected bundle identifier'
        assert info.get('CFBundlePackageType') == 'APPL', 'Info.plist is not an application bundle'
        assert info.get('LSMinimumSystemVersion') == MINIMUM, f'minimum macOS must be {MINIMUM}'
        assert info.get('LSArchitecturePriority') == ['arm64'], 'Info.plist must select ARM64'
        assert archive.read(f'{root}/Contents/PkgInfo') == b'APPL????', 'invalid PkgInfo'

        binary = archive.read(executable_rel)
        manifest = json.loads(archive.read(build_rel))
        assert set(manifest.get('mod_files', {})) == mod_paths, 'bundled mod inventory differs'
        for name in mod_paths:
            data = archive.read(f'{root}/Contents/Resources/{name}')
            assert hashlib.sha256(data).hexdigest() == manifest['mod_files'][name], \
                f'bundled mod checksum differs: {name}'
            if name.endswith('.dylib'):
                assert struct.unpack_from('<4I', data)[:2] == (0xfeedfacf, 0x0100000c), \
                    f'mod is not native ARM64: {name}'
                assert struct.unpack_from('<4I', data)[3] == 6, f'mod is not a dylib: {name}'
        for relative in mod_files:
            assert archive.read(f'{root}/Contents/Resources/{relative}') == (ROOT / relative).read_bytes(), \
                f'bundled mod resource differs: {relative}'
        expected_version = manifest['version'] if re.fullmatch(VERSION_PATTERN, manifest['version']) else ''
        assert manifest['game_version'] == expected_version, 'incoherent game/package version'
        assert re.fullmatch(r'[0-9a-f]{64}', manifest['build_fingerprint']), 'missing build identity'
        assert manifest.get('architecture') == 'arm64' and manifest.get('minimum_macos') == MINIMUM
        assert manifest.get('signing') == 'ad-hoc' and manifest.get('notarized') is False
        if icon_name:
            icon_data = archive.read(f'{root}/Contents/Resources/{icon_name}')
            inspect_icon(icon_data)
            assert hashlib.sha256(icon_data).hexdigest() == manifest.get('icon_sha256'), 'icon differs from build manifest'
        else:
            assert manifest.get('icon_sha256') is None, 'manifest describes a missing icon'
        source_hash = manifest.get('source_binary_sha256', '')
        assert re.fullmatch(r'[0-9a-f]{64}', source_hash), 'build manifest has no source binary SHA-256'
        # The manifest records the pre-signing build artifact. codesign adds
        # the Mach-O signature, so the sealed executable's bytes must differ.
        # Its UUID remains the identity save states use to reject other builds.
        _, signatures = mach_uuid(binary)
        assert signatures == 1, \
            'signed executable must retain one build UUID and one code signature command'

        assert archive.read(f'{root}/Contents/Resources/LICENSE.txt') == (ROOT / 'LICENSE').read_bytes(), \
            'bundled application license differs from the repository license'
        for name in LANGUAGES:
            source = ROOT / 'languages' / name
            assert archive.read(f'{root}/Contents/Resources/languages/{name}') == source.read_bytes(), \
                f'language resource differs from the repository: {name}'
        for name in LICENSES:
            contents = archive.read(f'{root}/Contents/Resources/licenses/{name}')
            assert contents.strip(), f'empty dependency license: {name}'

        # Preserve the archive's Unix modes explicitly: zipfile extraction does
        # not restore them consistently across Python versions.
        extract_root = ROOT / 'tmp'
        extract_root.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix='package-macos-', dir=extract_root)
        isolated = Path(temporary.name)
        try:
            for entry in entries:
                destination = isolated.joinpath(*PurePosixPath(entry.filename).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, destination.open('wb') as target:
                    shutil.copyfileobj(source, target)
                mode = (entry.external_attr >> 16) & 0o777
                destination.chmod(mode or 0o644)
            executable = isolated / executable_rel
            app = isolated / root
            assert executable.stat().st_mode & 0o111, 'ZIP did not preserve executable permission'
            inspect_binary(executable)
        except BaseException:
            temporary.cleanup()
            raise
        return temporary, isolated, app, executable


def verify_signature(app):
    codesign = shutil.which('codesign')
    assert codesign, 'codesign is required to verify a macOS release archive'
    subprocess.run([codesign, '--verify', '--strict', '--deep', str(app)], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    display = subprocess.run([codesign, '--display', '--verbose=2', str(app)], check=True,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    details = display.stdout + display.stderr
    assert 'Signature=adhoc' in details, 'application is not signed with the expected ad-hoc signature'


def verify_exports(executable, cwd, home):
    environment = {
        'HOME': str(home), 'TMPDIR': str(home), 'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
        'LANG': 'C', 'MEMORIES_MOD_EXPORTS': '1',
    }
    result = subprocess.run([str(executable)], cwd=cwd, env=environment,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
    assert result.returncode == 0, (
        f'packaged executable failed its ROM-free export path ({result.returncode}): {result.stderr}'
    )
    rows = []
    for line in result.stdout.splitlines():
        match = re.fullmatch(r'([0-9a-fA-F]{8,16}) (\S+)', line)
        assert match, f'invalid mod-export row: {line!r}'
        rows.append((int(match.group(1), 16), match.group(2)))
    names = [name for _, name in rows]
    assert names and names == sorted(set(names), key=lambda value: value.encode()), \
        'mod exports are empty, unsorted or duplicated'
    missing = REQUIRED_EXPORTS - set(names)
    assert not missing, f'packaged executable is missing required mod exports: {sorted(missing)}'
    addresses = dict((name, address) for address, name in rows)
    assert all(addresses[name] for name in REQUIRED_EXPORTS), 'required mod export has a null address'
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True, help='macOS release ZIP')
    args = parser.parse_args()
    assert sys_platform_is_macos_arm64(), 'run this check on an Apple Silicon Mac'
    temporary, isolated, app, executable = check_archive(args.archive)
    try:
        verify_signature(app)
        manifest = json.loads((app / 'Contents/Resources/build.json').read_text(encoding='utf-8'))
        assert str(uuid.UUID(bytes=mach_uuid(executable.read_bytes())[0])) == manifest.get('source_uuid'), \
            'code signing changed the Mach-O UUID used by native save states'
        cwd = isolated / 'independent-working-directory'
        home = isolated / 'isolated-home'
        cwd.mkdir()
        home.mkdir()
        count = verify_exports(executable, cwd, home)
    finally:
        temporary.cleanup()
    print(f'{args.archive.name}: bundle, ARM64/minimum OS, resources, checksum, signature and {count} exports passed')


def sys_platform_is_macos_arm64():
    return platform.system() == 'Darwin' and platform.machine() in ('arm64', 'aarch64')


if __name__ == '__main__':
    main()
