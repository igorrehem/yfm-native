#!/usr/bin/env python3
"""Run deterministic native-game screenshots, the mod export check, the check
that earlier releases' mods still work (check_mod_abi.py --run) and the
portable PC CTests."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXECUTABLE = ROOT / "tmp/pc/game32/memories-pc"
WINDOWS_EXECUTABLE = ROOT / "tmp/pc/win32/memories-pc.exe"  # build_game32.py --target windows
WINE_PREFIX = ROOT / "tmp/pc/wine-prefix"
DEFAULT_BUILD = ROOT / "tmp/pc/cmake-test"
FIXTURES = ROOT / "tests/pc/smoke"
# Each run's frames, settings and user folders go in a folder of its own,
# tmp/pc/smoke/run-XXXXXXXX, kept when a case failed and removed when all
# passed: worktrees share tmp/ (a junction to the main checkout's), and two
# runs at once in two of them overwrote each other's frames when they shared
# tmp/pc/smoke/<case>.ppm.
OUTPUT = ROOT / "tmp/pc/smoke"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def smoke_environment(case: dict[str, object], image: Path, settings: Path, user: Path) -> dict[str, str]:
    preserved_disc = os.environ.get("MEMORIES_DISC")
    environment = {key: value for key, value in os.environ.items() if not key.startswith("MEMORIES_")}
    if preserved_disc:
        environment["MEMORIES_DISC"] = preserved_disc
    environment.update(
        {
            "MEMORIES_HEADLESS": "1",
            # Headless runs never check (update_check.h); said anyway, as
            # a smoke test must not depend on the network.
            "MEMORIES_NO_UPDATE_CHECK": "1",
            "MEMORIES_NO_AUDIO": "1",
            "MEMORIES_NO_GAMEPAD": "1",
            "MEMORIES_SPEED": "-1",
            "MEMORIES_SHOW_HUD": "0",
            "MEMORIES_SETTINGS": str(settings),
            # A folder of its own, so the player's memory cards and states
            # take no part in a case.
            "MEMORIES_USER_DIR": str(user),
            "MEMORIES_INPUT": str(case["input"]),
            "MEMORIES_DUMP_FRAME": str(case["frame"]),
            "MEMORIES_DUMP_PATH": str(image),
            "MEMORIES_WATCHDOG": "0",
        }
    )
    return environment


def launcher(executable: Path) -> tuple[list[str], dict[str, str]]:
    """The command that runs the executable, and what Wine needs when a
    Windows build is tested on another host: a prefix of its own, without the
    Mono and Gecko installers, and quiet."""
    if executable.suffix != ".exe" or sys.platform == "win32":
        return [str(executable)], {}
    return ["wine", str(executable)], {
        "WINEPREFIX": str(WINE_PREFIX),
        "WINEDLLOVERRIDES": "mscoree,mshtml=",
        "WINEDEBUG": "-all",
    }


def run_smoke(executable: Path, record: bool) -> bool:
    if not executable.is_file():
        print(f"smoke: executable is missing: {executable}", file=sys.stderr)
        return False
    command, extra = launcher(executable)
    fixtures = sorted(FIXTURES.glob("*.json"))
    if not fixtures:
        print(f"smoke: no fixtures in {FIXTURES}", file=sys.stderr)
        return False
    OUTPUT.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix="run-", dir=OUTPUT))
    print(f"smoke: frames in {output}", flush=True)
    passed = run_cases(command, extra, fixtures, output, record)
    if passed:
        shutil.rmtree(output, ignore_errors=True)
    return passed


def test_only_variables(executable: Path, case: dict[str, object]) -> list[str]:
    """The variables a case sets that this executable does not read: a
    release leaves test-only paths out (MEMORIES_TEST_HOOKS in
    build_game32.py), and the name goes with its getenv."""
    image = executable.read_bytes()
    return [key for key in case.get("environment", {}) if key.encode() not in image]


def refused_code_mods(executable: Path, case: dict[str, object]) -> list[str]:
    """The code mods a case turns on that this executable refuses: the
    64-bit Windows game (a PE for x86-64) loads a code mod's x86_64-windows
    object, and refuses by name one with none beside it (or a mod that is
    not there at all), so a case about it is not its to pass."""
    try:
        head = executable.read_bytes()[:4096]
        at = int.from_bytes(head[0x3C:0x40], "little")
        wide = head[at:at + 4] == b"PE" + bytes(2) and int.from_bytes(head[at + 4:at + 6], "little") == 0x8664
    except (OSError, ValueError):
        return []
    if not wide:
        return []
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import build_mod
    refused = []
    for key, value in case.get("settings", {}).items():
        manifest = executable.parent / "mods" / key[4:].split(".")[0] / "mod.json"   # mod.<id> or mod.<id>.<option>
        if not key.startswith("mod.") or not value or manifest.parent.name in refused:
            continue
        if not manifest.is_file():
            refused.append(manifest.parent.name)
            continue
        data = json.loads(manifest.read_text(encoding="utf-8-sig"))
        if (data.get("library") or data.get("libraries")) and \
                not (manifest.parent / build_mod.library_name(str(manifest.parent), "x86_64-windows")).is_file():
            refused.append(manifest.parent.name)
    return refused


def run_cases(command: list[str], extra: dict[str, str], fixtures: list[Path], output: Path, record: bool) -> bool:
    executable = Path(command[-1])
    for fixture in fixtures:
        case = json.loads(fixture.read_text(encoding="utf-8"))
        name = str(case["name"])
        # "environment": variables for this case alone, which must show in
        # the game's output ("expect_output"), so a case that tests a path is
        # never passed by a build without it: that build skips it, saying so.
        missing = test_only_variables(executable, case)
        if missing:
            print(f"smoke: {name} skipped: {executable.name} does not read {', '.join(missing)} (a release build, or a system without that hook)")
            continue
        refused = refused_code_mods(executable, case)
        if refused:
            print(f"smoke: {name} skipped: the 64-bit game has no x86_64-windows object for ({', '.join(refused)})")
            continue
        image = output / f"{name}.ppm"
        settings = output / f"{name}.settings"
        user = output / f"{name}.user"
        user.mkdir()
        # A case may set some of the player's settings ("aspect=2" for
        # widescreen, "mod.3d-monsters=1"); everything else is the defaults.
        settings.write_text("".join(f"{key}={value}\n" for key, value in case.get("settings", {}).items()),
                            encoding="utf-8")
        print(f"smoke: {name} (frame {case['frame']})", flush=True)
        expected = case.get("expect_output")
        try:
            result = subprocess.run(
                command,
                cwd=ROOT,
                env={**smoke_environment(case, image, settings, user), **case.get("environment", {}), **extra},
                timeout=float(os.environ.get("MEMORIES_SMOKE_TIMEOUT", "120")),
                check=False,
                **({"stdout": subprocess.PIPE, "stderr": subprocess.STDOUT} if expected else {}),
            )
        except subprocess.TimeoutExpired:
            print(f"smoke: timed out; partial frame: {image}", file=sys.stderr)
            return False
        if expected:
            text = result.stdout.decode(errors="replace")
            sys.stdout.write(text)
            if str(expected) not in text:
                print(f"smoke: {name}: the game never said {expected!r}", file=sys.stderr)
                return False
        if result.returncode != 0 or not image.is_file():
            print(f"smoke: game exited {result.returncode}; differing frame: {image}", file=sys.stderr)
            return False
        actual = digest(image)
        if record:
            case["sha256"] = actual
            fixture.write_text(json.dumps(case, indent=2) + "\n", encoding="utf-8")
            print(f"smoke: recorded {actual}")
        elif actual != case.get("sha256"):
            print(f"smoke: {name} mismatch", file=sys.stderr)
            print(f"  expected {case.get('sha256', '<missing>')}", file=sys.stderr)
            print(f"  actual   {actual}", file=sys.stderr)
            print(f"  differing frame: {image}", file=sys.stderr)
            return False
        else:
            print(f"smoke: {name} passed")
    return True


def check_mod_exports(executable: Path) -> bool:
    """The table code mods bind to matches the link (check_mod_exports.py)."""
    result = subprocess.run([sys.executable, str(ROOT / "tools/pc/check_mod_exports.py"), str(executable)],
                            cwd=ROOT, check=False)
    return result.returncode == 0


def run_ctests(build: Path) -> bool:
    if not (build / "CTestTestfile.cmake").is_file():
        print(f"smoke: CTest build is missing: {build}", file=sys.stderr)
        return False
    result = subprocess.run(
        ["ctest", "--test-dir", str(build), "-R", "^pc_", "--output-on-failure"],
        cwd=ROOT,
        check=False,
    )
    return result.returncode == 0


def check_mod_compat(executable: Path) -> bool:
    """The mods of the releases in mod_compat.txt still load and draw alike
    in this build (check_mod_abi.py --run)."""
    result = subprocess.run([sys.executable, str(ROOT / "tools/pc/check_mod_abi.py"), "--run",
                             "--build", str(executable.parent), "--executable", str(executable)], cwd=ROOT, check=False)
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", action="store_true", help="replace fixture hashes with current output")
    parser.add_argument("--executable", type=Path, default=DEFAULT_EXECUTABLE)
    parser.add_argument("--windows", action="store_true",
                        help=f"test {WINDOWS_EXECUTABLE.relative_to(ROOT)} (under Wine off Windows) and the "
                             "Windows mod loader instead of the CTests")
    parser.add_argument("--build", type=Path, default=DEFAULT_BUILD, help="CTest build directory")
    arguments = parser.parse_args()
    if arguments.windows:
        exports_ok = check_mod_exports(WINDOWS_EXECUTABLE)
        loader_ok = subprocess.run([sys.executable, str(ROOT / "tools/pc/test_object_loader.py"), "--target", "windows"],
                                   cwd=ROOT, check=False).returncode == 0
        lifecycle_ok = subprocess.run([sys.executable, str(ROOT / "tools/pc/test_mods_lifecycle.py"), "--target", "windows"],
                                      cwd=ROOT, check=False).returncode == 0
        compat_ok = check_mod_compat(WINDOWS_EXECUTABLE)
        return 0 if (run_smoke(WINDOWS_EXECUTABLE, arguments.record) and exports_ok and loader_ok and lifecycle_ok
                     and compat_ok) else 1
    exports_ok = check_mod_exports(arguments.executable.resolve())
    compat_ok = check_mod_compat(arguments.executable.resolve())
    screenshots_ok = run_smoke(arguments.executable.resolve(), arguments.record) and exports_ok and compat_ok
    tests_ok = run_ctests(arguments.build.resolve())
    return 0 if screenshots_ok and tests_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
