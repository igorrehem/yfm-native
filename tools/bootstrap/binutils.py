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


class ToolchainError(RuntimeError):
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
        raise ToolchainError(message) from error
    return result.stdout.strip() if capture_output else ""


def load_lock(root: Path) -> dict[str, Any]:
    path = resolve_within(root, "tools/bootstrap/binutils.json", must_exist=True)
    with path.open("r", encoding="utf-8") as handle:
        lock = json.load(handle)
    if lock.get("schema") != 1:
        raise ToolchainError(f"{path}: unsupported lock schema")
    return lock


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify_archive(path: Path, expected_sha256: str) -> None:
    actual_sha256 = hash_file(path)
    if actual_sha256 != expected_sha256:
        raise ToolchainError(
            f"{path}: SHA-256 is {actual_sha256}, expected {expected_sha256}"
        )


def download_archive(root: Path, lock: dict[str, Any]) -> Path:
    archive = resolve_within(root, str(lock["archive"]))
    expected_sha256 = str(lock["sha256"])
    if archive.exists():
        verify_archive(archive, expected_sha256)
        return archive

    archive.parent.mkdir(parents=True, exist_ok=True)
    partial = resolve_within(root, f"tmp/bootstrap/{archive.name}.part")
    partial.parent.mkdir(parents=True, exist_ok=True)
    partial.unlink(missing_ok=True)

    request = urllib.request.Request(
        str(lock["url"]),
        headers={"User-Agent": "yugioh-decomp-tool-bootstrap/1"},
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

    actual_sha256 = digest.hexdigest()
    if actual_sha256 != expected_sha256:
        partial.unlink(missing_ok=True)
        raise ToolchainError(
            f"downloaded {archive.name} has SHA-256 {actual_sha256}, "
            f"expected {expected_sha256}"
        )
    partial.replace(archive)
    return archive


def validate_tar_members(archive: tarfile.TarFile) -> None:
    for member in archive.getmembers():
        member_path = PurePosixPath(member.name)
        if member_path.is_absolute() or ".." in member_path.parts:
            raise ToolchainError(f"unsafe archive path: {member.name}")
        if member.isdev():
            raise ToolchainError(f"unsupported archive device: {member.name}")
        if member.issym() or member.islnk():
            link_path = PurePosixPath(member.linkname)
            if link_path.is_absolute():
                raise ToolchainError(
                    f"unsafe absolute archive link: {member.name}"
                )
            target = member_path.parent.joinpath(link_path)
            normalized: list[str] = []
            for part in target.parts:
                if part == "..":
                    if not normalized:
                        raise ToolchainError(
                            f"archive link leaves extraction root: {member.name}"
                        )
                    normalized.pop()
                elif part not in ("", "."):
                    normalized.append(part)


def source_marker(source: Path) -> Path:
    return source / ".project-source-sha256"


def check_source(root: Path, lock: dict[str, Any]) -> Path:
    source = resolve_within(root, str(lock["source"]), must_exist=True)
    configure = source / "configure"
    marker = source_marker(source)
    if not configure.is_file() or not marker.is_file():
        raise ToolchainError(f"incomplete binutils source tree: {source}")
    recorded_sha256 = marker.read_text(encoding="ascii").strip()
    if recorded_sha256 != lock["sha256"]:
        raise ToolchainError(
            f"{source}: source marker is {recorded_sha256}, "
            f"expected {lock['sha256']}"
        )
    return source


def extract_source(root: Path, lock: dict[str, Any], archive_path: Path) -> Path:
    source = resolve_within(root, str(lock["source"]))
    if source.exists():
        return check_source(root, lock)

    staging_root = resolve_within(root, "tmp/bootstrap/binutils-source")
    if staging_root.exists():
        raise ToolchainError(
            f"stale extraction directory exists; remove it before retrying: "
            f"{staging_root}"
        )
    staging_root.mkdir(parents=True)

    with tarfile.open(archive_path, "r:xz") as archive:
        validate_tar_members(archive)
        archive.extractall(staging_root)

    extracted = staging_root / f"binutils-{lock['version']}"
    if not extracted.is_dir() or not (extracted / "configure").is_file():
        raise ToolchainError(
            f"{archive_path}: expected binutils-{lock['version']} source directory"
        )

    source.parent.mkdir(parents=True, exist_ok=True)
    extracted.replace(source)
    source_marker(source).write_text(f"{lock['sha256']}\n", encoding="ascii")
    staging_root.rmdir()
    return check_source(root, lock)


def tool_paths(root: Path, lock: dict[str, Any]) -> list[Path]:
    prefix = str(lock["prefix"])
    target = str(lock["target"])
    return [
        resolve_within(root, f"{prefix}/bin/{target}-{tool}")
        for tool in lock["required_tools"]
    ]


def check_toolchain(root: Path, lock: dict[str, Any]) -> None:
    expected_version = str(lock["version"])
    target = str(lock["target"])
    for path in tool_paths(root, lock):
        path = resolve_within(
            root,
            path.relative_to(root),
            must_exist=True,
        )
        if not path.is_file():
            raise ToolchainError(f"required tool is not a file: {path}")
        output = run(root, [str(path), "--version"], capture_output=True)
        first_line = output.splitlines()[0] if output else ""
        if expected_version not in first_line:
            raise ToolchainError(
                f"{path}: version output does not contain {expected_version}"
            )

    assembler = resolve_within(
        root,
        f"{lock['prefix']}/bin/{target}-as",
        must_exist=True,
    )
    assembler_version = run(
        root, [str(assembler), "--version"], capture_output=True
    )
    if target not in assembler_version:
        raise ToolchainError(
            f"{assembler}: assembler is not configured for target {target}"
        )


def build_toolchain(root: Path, lock: dict[str, Any], source: Path) -> None:
    prefix = resolve_within(root, str(lock["prefix"]))
    if prefix.exists():
        raise ToolchainError(
            f"incomplete toolchain prefix exists; remove it before retrying: {prefix}"
        )

    build = resolve_within(root, str(lock["build"]))
    if build.exists():
        raise ToolchainError(
            f"stale build directory exists; remove it before retrying: {build}"
        )
    build.mkdir(parents=True)

    configure = source / "configure"
    command = [
        str(configure),
        f"--target={lock['target']}",
        f"--prefix={prefix}",
        *[str(option) for option in lock["configure"]],
    ]
    run(root, command, cwd=build)

    jobs = max(1, min(os.cpu_count() or 1, 2))
    run(
        root,
        [
            "make",
            f"-j{jobs}",
            "MAKEINFO=true",
            "all-binutils",
            "all-gas",
            "all-ld",
        ],
        cwd=build,
    )
    run(
        root,
        [
            "make",
            "MAKEINFO=true",
            "install-binutils",
            "install-gas",
            "install-ld",
        ],
        cwd=build,
    )
    check_toolchain(root, lock)


def install(root: Path, lock: dict[str, Any]) -> None:
    try:
        check_toolchain(root, lock)
        return
    except (ToolchainError, WorkspaceError):
        pass

    archive = download_archive(root, lock)
    source = extract_source(root, lock, archive)
    build_toolchain(root, lock, source)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install or verify the pinned local MIPS binutils toolchain."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the local toolchain without changing it",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        root = require_workspace_root()
        lock = load_lock(root)
        if args.check:
            check_source(root, lock)
            check_toolchain(root, lock)
        else:
            install(root, lock)
    except (
        ToolchainError,
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
    print(f"{lock['target']} binutils {lock['version']}: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
