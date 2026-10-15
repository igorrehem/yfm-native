"""Versioned LLVM guest compiler; Python orchestrates, LLVM owns IR semantics."""

import functools
import hashlib
import json
import shlex
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tmp/pc/guest-compiler"
CONFIG = Path(__file__).with_name("macos_toolchain.json")


class TranslationError(ValueError):
    pass


@functools.lru_cache(maxsize=1)
def toolchain():
    config = json.loads(CONFIG.read_text())
    folder = ROOT / "tmp/pc/llvm-macos" / ("LLVM-" + config["version"] + "-macOS-ARM64")
    if not (folder / "bin/llvm-config").is_file():
        from fetch_tools import download, unpack

        unpack(download(config["url"], config["sha256"]), str(folder.parent))
    version = subprocess.check_output(
        [str(folder / "bin/llvm-config"), "--version"], text=True
    ).strip()
    if version != config["version"]:
        raise RuntimeError(f"Expected LLVM {config['version']}, found {version}")
    return folder


# A build uses one toolchain snapshot. Revalidate the full persistent key
# at the start of each process, rather than spawning SDK/Git/LLVM queries
# for every IR operation in the same build.
@functools.lru_cache(maxsize=1)
def compiler():
    OUT.mkdir(parents=True, exist_ok=True)
    binary = OUT / "memories-guest-ir"
    source = ROOT / "tools/pc/llvm/guest_ir.cpp"
    deps_source = Path(__file__).with_name("macos_deps.py")
    llvm = toolchain()
    llvm_config = subprocess.check_output(
        [
            str(llvm / "bin/llvm-config"),
            "--cxxflags",
            "--ldflags",
            "--libs",
            "core",
            "irreader",
            "passes",
            "support",
            "--system-libs",
        ],
        text=True,
    )
    flags = shlex.split(llvm_config)
    from macos_deps import ensure, sdk_path

    dependencies = ROOT / "tmp/pc/macos-deps/install"
    if not (dependencies / "lib/libzstd.a").is_file():
        dependencies = ensure(("zstd",))
    # LLVM's official archive encodes its build machine's absolute zstd
    # path. Replace that dependency by identity, regardless of its prefix.
    flags = [
        str(dependencies / "lib/libzstd.a") if Path(flag).name == "libzstd.a" else flag
        for flag in flags
    ]
    unexpected = [
        flag
        for flag in flags
        if flag.startswith("/")
        and not Path(flag).is_relative_to(llvm)
        and not Path(flag).is_relative_to(dependencies)
    ]
    if unexpected:
        raise RuntimeError(f"Unsupported external LLVM dependencies: {unexpected}")
    sdk = str(sdk_path())
    command = [
        str(llvm / "bin/clang++"),
        "-isysroot",
        sdk,
        "-nostdlib++",
        str(source),
        *flags,
        str(llvm / "lib/libc++.a"),
        str(llvm / "lib/libc++abi.a"),
        "-Wl,-rpath,@loader_path/../llvm-macos/" + llvm.name + "/lib",
        "-O2",
        "-o",
        str(binary),
    ]
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    fingerprint_data = {
        "revision": revision,
        "source": hashlib.sha256(source.read_bytes()).hexdigest(),
        "memory_map": hashlib.sha256((ROOT / "src/pc/memory_map.h").read_bytes()).hexdigest(),
        "config": hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
        "driver": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "dependencies_script": hashlib.sha256(deps_source.read_bytes()).hexdigest(),
        "llvm_config": llvm_config,
        "sdk": sdk,
        "command": command,
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_data, sort_keys=True).encode()
    ).hexdigest()
    stamp = OUT / "compiler.fingerprint"
    if (
        binary.is_file()
        and stamp.is_file()
        and stamp.read_text().strip() == fingerprint
    ):
        return binary
    # Publish a complete executable: parallel runners can still use the old
    # compiler while another process rebuilds it for the same fingerprint.
    with tempfile.TemporaryDirectory(dir=OUT) as temporary:
        staged = Path(temporary) / binary.name
        subprocess.run([*command[:-1], str(staged)], check=True)
        staged.replace(binary)
    stamp.write_text(fingerprint + "\n")
    return binary


def process(operation, text, **options):
    binary = compiler()
    identity = (OUT / "compiler.fingerprint").read_text().strip()
    digest = hashlib.sha256(
        (identity + operation + text + json.dumps(options, sort_keys=True)).encode()
    ).hexdigest()
    cache = OUT / "cache"
    cache.mkdir(exist_ok=True)
    cached = cache / (digest + (".json" if operation == "inspect" else ".ll"))
    if cached.is_file():
        result = cached.read_text()
    else:
        with tempfile.TemporaryDirectory(dir=OUT) as temporary:
            folder = Path(temporary)
            source = folder / "input.ll"
            source.write_text(text)
            config = folder / "options.json"
            config.write_text(json.dumps(options))
            output = folder / "output"
            result = subprocess.run(
                [str(binary), operation, str(source), str(output), str(config)],
                capture_output=True,
                text=True,
            )
            if result.returncode:
                raise TranslationError(result.stderr.strip())
            result = output.read_text()
            with tempfile.NamedTemporaryFile(
                mode="w", dir=cache, delete=False
            ) as staging:
                staging.write(result)
                staged = Path(staging.name)
            staged.replace(cached)
    return json.loads(result) if operation == "inspect" else result


def translate(text, pinned=None, registration=None, *, game_unit=False, hooks=False):
    return process(
        "translate",
        text,
        pins=pinned or {},
        game_unit=game_unit,
        hooks=hooks,
        **({"registration": registration} if registration else {}),
    )


def normalize(
    text, renames=None, drop_definitions=(), *, export_functions=(), keep_functions=None
):
    return process(
        "normalize",
        text,
        renames=renames or {},
        drop_definitions=list(drop_definitions),
        export_functions=list(export_functions),
        **(
            {"keep_functions": sorted(keep_functions)}
            if keep_functions is not None
            else {}
        ),
    )


def inspect(text):
    return process("inspect", text)


def validate_c_abi(name, signature):
    if signature["calling_convention"] != 0:
        raise ValueError(
            f"Unsupported calling convention: {name}: {signature['calling_convention']}"
        )
    if signature["unsupported_abi_attributes"]:
        raise ValueError(
            f"Unsupported native ABI attributes: {name}: "
            + ", ".join(signature["unsupported_abi_attributes"])
        )
