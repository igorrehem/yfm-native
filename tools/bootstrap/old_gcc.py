#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any

PROJECT_TOOLS = Path(__file__).resolve().parents[1] / "project"
sys.path.insert(0, str(PROJECT_TOOLS))

from workspace import (  # noqa: E402
    WorkspaceError,
    local_environment,
    require_workspace_root,
    resolve_within,
)


class CompilerError(RuntimeError):
    pass


def run(
    root: Path,
    command: list[str],
    *,
    cwd: Path | None = None,
    capture_output: bool = False,
) -> str:
    environment = os.environ.copy()
    environment.update(local_environment(root))
    try:
        result = subprocess.run(
            command,
            cwd=cwd or root,
            env=environment,
            check=True,
            text=True,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
        )
    except subprocess.CalledProcessError as error:
        details = error.stderr.strip() if error.stderr else ""
        message = f"command failed with exit code {error.returncode}: {command[0]}"
        if details:
            message = f"{message}: {details}"
        raise CompilerError(message) from error
    return result.stdout.strip() if capture_output else ""


def load_lock(root: Path) -> dict[str, Any]:
    path = resolve_within(root, "tools/bootstrap/old_gcc.json", must_exist=True)
    with path.open("r", encoding="utf-8") as handle:
        lock = json.load(handle)
    if lock.get("schema") != 1:
        raise CompilerError(f"{path}: unsupported lock schema")
    return lock


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify_hash(path: Path, expected: str) -> None:
    actual = sha256_file(path)
    if actual != expected:
        raise CompilerError(f"{path}: SHA-256 is {actual}, expected {expected}")


def clone_repository(
    root: Path, lock: dict[str, Any], *, allow_install: bool = True
) -> Path:
    config = lock["repository"]
    destination = resolve_within(root, str(config["destination"]))
    if not destination.exists():
        if not allow_install:
            raise CompilerError(f"missing old-gcc repository: {destination}")
        staging = resolve_within(root, "tmp/bootstrap/old-gcc-repository")
        if staging.exists():
            raise CompilerError(
                f"stale repository staging path exists: {staging}"
            )
        staging.parent.mkdir(parents=True, exist_ok=True)
        run(root, ["git", "init", "--quiet", str(staging)])
        run(
            root,
            [
                "git",
                "-C",
                str(staging),
                "remote",
                "add",
                "origin",
                str(config["url"]),
            ],
        )
        run(
            root,
            [
                "git",
                "-C",
                str(staging),
                "fetch",
                "--quiet",
                "--depth",
                "1",
                "origin",
                str(config["commit"]),
            ],
        )
        run(
            root,
            [
                "git",
                "-C",
                str(staging),
                "checkout",
                "--quiet",
                "--detach",
                "FETCH_HEAD",
            ],
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging.replace(destination)

    if not (destination / ".git").is_dir():
        raise CompilerError(f"{destination}: not a Git checkout")
    head = run(
        root,
        ["git", "-C", str(destination), "rev-parse", "HEAD"],
        capture_output=True,
    )
    tree = run(
        root,
        ["git", "-C", str(destination), "rev-parse", "HEAD^{tree}"],
        capture_output=True,
    )
    origin = run(
        root,
        ["git", "-C", str(destination), "remote", "get-url", "origin"],
        capture_output=True,
    )
    status = run(
        root,
        ["git", "-C", str(destination), "status", "--porcelain"],
        capture_output=True,
    )
    if head != config["commit"] or tree != config["tree"]:
        raise CompilerError(f"{destination}: unexpected repository revision")
    if origin != config["url"]:
        raise CompilerError(f"{destination}: unexpected origin {origin}")
    if status:
        raise CompilerError(f"{destination}: checkout has local changes")

    for patch in lock["patches"]:
        patch_path = destination / str(patch["path"])
        if not patch_path.is_file():
            raise CompilerError(f"missing compiler patch: {patch_path}")
        verify_hash(patch_path, str(patch["sha256"]))
    return destination


def download_source(root: Path, lock: dict[str, Any]) -> Path:
    config = lock["source"]
    archive = resolve_within(root, str(config["archive"]))
    if archive.exists():
        verify_hash(archive, str(config["sha256"]))
        return archive

    archive.parent.mkdir(parents=True, exist_ok=True)
    partial = resolve_within(root, f"tmp/bootstrap/{archive.name}.part")
    partial.parent.mkdir(parents=True, exist_ok=True)
    partial.unlink(missing_ok=True)
    request = urllib.request.Request(
        str(config["url"]),
        headers={"User-Agent": "yugioh-decomp-compiler-bootstrap/1"},
    )
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            with partial.open("wb") as handle:
                while chunk := response.read(1024 * 1024):
                    digest.update(chunk)
                    handle.write(chunk)
    except OSError:
        partial.unlink(missing_ok=True)
        raise

    actual = digest.hexdigest()
    expected = str(config["sha256"])
    if actual != expected:
        partial.unlink(missing_ok=True)
        raise CompilerError(
            f"downloaded {archive.name} has SHA-256 {actual}, expected {expected}"
        )
    partial.replace(archive)
    return archive


def validate_tar_members(archive: tarfile.TarFile) -> None:
    for member in archive.getmembers():
        member_path = PurePosixPath(member.name)
        if member_path.is_absolute() or ".." in member_path.parts:
            raise CompilerError(f"unsafe archive path: {member.name}")
        if member.isdev():
            raise CompilerError(f"unsupported archive device: {member.name}")
        if member.issym() or member.islnk():
            link = PurePosixPath(member.linkname)
            if link.is_absolute():
                raise CompilerError(f"unsafe archive link: {member.name}")
            normalized: list[str] = []
            for part in member_path.parent.joinpath(link).parts:
                if part == "..":
                    if not normalized:
                        raise CompilerError(
                            f"archive link leaves extraction root: {member.name}"
                        )
                    normalized.pop()
                elif part not in ("", "."):
                    normalized.append(part)


def source_marker(source: Path) -> Path:
    return source / ".project-source.json"


def expected_source_marker(lock: dict[str, Any]) -> dict[str, Any]:
    return {
        "repository_commit": lock["repository"]["commit"],
        "repository_tree": lock["repository"]["tree"],
        "source_sha256": lock["source"]["sha256"],
        "patches": {
            patch["path"]: patch["sha256"] for patch in lock["patches"]
        },
    }


def check_source(root: Path, lock: dict[str, Any]) -> Path:
    source = resolve_within(
        root, str(lock["source"]["destination"]), must_exist=True
    )
    marker = source_marker(source)
    if not marker.is_file() or not (source / "configure").is_file():
        raise CompilerError(f"incomplete GCC probe source tree: {source}")
    with marker.open("r", encoding="utf-8") as handle:
        actual = json.load(handle)
    if actual != expected_source_marker(lock):
        raise CompilerError(f"{source}: source marker does not match the lock")
    return source


def patch_source(
    root: Path,
    lock: dict[str, Any],
    repository: Path,
    archive_path: Path,
) -> Path:
    destination = resolve_within(root, str(lock["source"]["destination"]))
    if destination.exists():
        return check_source(root, lock)

    staging_root = resolve_within(root, "tmp/bootstrap/gcc-source")
    if staging_root.exists():
        raise CompilerError(f"stale source staging path exists: {staging_root}")
    staging_root.mkdir(parents=True)

    with tarfile.open(archive_path, "r:gz") as archive:
        validate_tar_members(archive)
        archive.extractall(staging_root)

    extracted = staging_root / "gcc-2.8.1"
    if not extracted.is_dir():
        raise CompilerError(f"{archive_path}: missing gcc-2.8.1 source directory")

    # Make all extracted files writable for patching
    for path in extracted.rglob("*"):
        if path.is_file():
            path.chmod(path.stat().st_mode | 0o200)

    for source_file in extracted.glob("*.c"):
        text = source_file.read_text(encoding="latin-1")
        updated = text.replace("include <varargs.h>", "include <stdarg.h>")
        if updated != text:
            source_file.write_text(updated, encoding="latin-1")

    for patch in lock["patches"]:
        patch_path = repository / str(patch["path"])
        command = [
            "patch",
            *[str(argument) for argument in patch["arguments"]],
            "-i",
            str(patch_path),
        ]
        run(root, command, cwd=extracted)

    marker = expected_source_marker(lock)
    source_marker(extracted).write_text(
        json.dumps(marker, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    extracted.replace(destination)
    staging_root.rmdir()
    return check_source(root, lock)


def compiler_paths(root: Path, lock: dict[str, Any]) -> dict[str, Path]:
    prefix = str(lock["prefix"])
    target = str(lock["target"])
    version = str(lock["version"])
    library = f"{prefix}/lib/gcc-lib/{target}/{version}"
    return {
        "gcc": resolve_within(root, f"{prefix}/bin/{target}-gcc"),
        "cc1": resolve_within(root, f"{library}/cc1"),
        "cpp": resolve_within(root, f"{library}/cpp"),
        "manifest": resolve_within(root, f"{prefix}/build-manifest.json"),
    }


def check_compiler(root: Path, lock: dict[str, Any]) -> None:
    paths = compiler_paths(root, lock)
    for name in ("gcc", "cc1", "cpp", "manifest"):
        path = resolve_within(root, paths[name].relative_to(root), must_exist=True)
        if not path.is_file():
            raise CompilerError(f"missing GCC probe file: {path}")

    machine = run(root, [str(paths["gcc"]), "-dumpmachine"], capture_output=True)
    version = run(root, [str(paths["gcc"]), "-dumpversion"], capture_output=True)
    if machine != lock["target"] or version != lock["version"]:
        raise CompilerError(
            f"GCC probe identifies as {machine} {version}, expected "
            f"{lock['target']} {lock['version']}"
        )

    cc1_path = Path(
        run(
            root,
            [str(paths["gcc"]), "-print-prog-name=cc1"],
            capture_output=True,
        )
    ).resolve(strict=True)
    if cc1_path != paths["cc1"].resolve(strict=True):
        raise CompilerError(f"GCC probe resolves cc1 outside its local prefix")

    with paths["manifest"].open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    for name in ("gcc", "cc1", "cpp"):
        actual = sha256_file(paths[name])
        if manifest.get("sha256", {}).get(name) != actual:
            raise CompilerError(f"GCC probe hash mismatch for {name}")


def build_compiler(root: Path, lock: dict[str, Any], source: Path) -> None:
    paths = compiler_paths(root, lock)
    prefix = resolve_within(root, str(lock["prefix"]))
    if prefix.exists():
        raise CompilerError(
            f"incomplete GCC probe prefix exists; remove it before retrying: {prefix}"
        )

    build = resolve_within(root, str(lock["build"]))
    if build.exists():
        raise CompilerError(
            f"stale GCC probe build exists; remove it before retrying: {build}"
        )
    shutil.copytree(source, build)

    run(
        root,
        [
            str(build / "configure"),
            f"--target={lock['target']}",
            f"--prefix={prefix}",
            "--with-endian-little",
            "--with-gnu-as",
            "--disable-gprof",
            "--disable-gdb",
            "--disable-werror",
            "--host=i686-pc-linux-gnu",
            "--build=i686-pc-linux-gnu",
        ],
        cwd=build,
    )
    (build / "insn-config.h").touch()

    jobs = max(1, min(os.cpu_count() or 1, 2))
    run(
        root,
        [
            "make",
            f"-j{jobs}",
            "cpp",
            "cc1",
            "xgcc",
            f"CFLAGS={lock['host_cflags']}",
        ],
        cwd=build,
    )

    library = paths["cc1"].parent
    paths["gcc"].parent.mkdir(parents=True, exist_ok=True)
    library.mkdir(parents=True, exist_ok=True)
    shutil.copy2(build / "xgcc", paths["gcc"])
    shutil.copy2(build / "cc1", paths["cc1"])
    shutil.copy2(build / "cpp", paths["cpp"])
    for path in (paths["gcc"], paths["cc1"], paths["cpp"]):
        path.chmod(0o755)

    license_directory = prefix / "share/licenses/gcc-2.8.1"
    license_directory.mkdir(parents=True, exist_ok=True)
    shutil.copy2(build / "COPYING", license_directory / "COPYING")

    manifest = {
        "repository_commit": lock["repository"]["commit"],
        "repository_tree": lock["repository"]["tree"],
        "source_sha256": lock["source"]["sha256"],
        "target": lock["target"],
        "version": lock["version"],
        "host_cflags": lock["host_cflags"],
        "probe_flags": lock["probe_flags"],
        "sha256": {
            "gcc": sha256_file(paths["gcc"]),
            "cc1": sha256_file(paths["cc1"]),
            "cpp": sha256_file(paths["cpp"]),
        },
    }
    paths["manifest"].write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    check_compiler(root, lock)


def install(root: Path, lock: dict[str, Any]) -> None:
    try:
        check_compiler(root, lock)
        return
    except (CompilerError, WorkspaceError):
        pass

    repository = clone_repository(root, lock)
    archive = download_source(root, lock)
    source = patch_source(root, lock, repository, archive)
    build_compiler(root, lock, source)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install or verify the GCC 2.8.1 PSX probe compiler."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the local probe compiler without changing it",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        root = require_workspace_root()
        lock = load_lock(root)
        if args.check:
            clone_repository(root, lock, allow_install=False)
            check_source(root, lock)
            check_compiler(root, lock)
        else:
            install(root, lock)
    except (
        CompilerError,
        WorkspaceError,
        OSError,
        UnicodeError,
        KeyError,
        TypeError,
        ValueError,
        tarfile.TarError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"{lock['target']} GCC {lock['version']} probe: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
