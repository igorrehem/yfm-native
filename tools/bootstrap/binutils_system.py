#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import binutils

from workspace import WorkspaceError, require_workspace_root, resolve_within


CONFIG_PATH = "tools/bootstrap/binutils_system.json"
MANIFEST_NAME = "system-manifest.json"


class SystemToolchainError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict) or value.get("schema") != 1:
        raise SystemToolchainError(f"{path}: unsupported schema")
    return value


def load_config(root: Path) -> dict[str, Any]:
    config = load_json(resolve_within(root, CONFIG_PATH, must_exist=True))
    required = {
        "package",
        "package_version",
        "program_prefix",
        "version",
        "target",
    }
    if not required.issubset(config):
        raise SystemToolchainError("system binutils config is incomplete")
    return config


def package_version(package: str) -> str:
    completed = subprocess.run(
        ["dpkg-query", "-W", "-f=${Version}", package],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode:
        raise SystemToolchainError(
            f"required Ubuntu package is not installed: {package}"
        )
    return completed.stdout.strip()


def system_tools(
    lock: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Path]:
    result: dict[str, Path] = {}
    prefix = str(config["program_prefix"])
    for name in lock["required_tools"]:
        executable = shutil.which(f"{prefix}{name}")
        if executable is None:
            raise SystemToolchainError(
                f"missing packaged tool: {prefix}{name}"
            )
        path = Path(executable).resolve(strict=True)
        completed = subprocess.run(
            [str(path), "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode:
            raise SystemToolchainError(f"cannot execute packaged tool: {path}")
        output = completed.stdout + completed.stderr
        if str(config["version"]) not in output:
            raise SystemToolchainError(
                f"{path}: expected binutils {config['version']}"
            )
        result[str(name)] = path
    assembler_output = subprocess.check_output(
        [str(result["as"]), "--version"],
        text=True,
    )
    if str(config["target"]) not in assembler_output:
        raise SystemToolchainError(
            f"packaged assembler is not configured for {config['target']}"
        )
    return result


def wrapper_text(executable: Path) -> str:
    return f"""#!/bin/sh
set -eu
exec {executable} "$@"
"""


def manifest_path(root: Path, lock: dict[str, Any]) -> Path:
    return resolve_within(root, f"{lock['prefix']}/{MANIFEST_NAME}")


def install(
    root: Path,
    lock: dict[str, Any],
    config: dict[str, Any],
) -> None:
    try:
        check(root, lock, config)
        return
    except (SystemToolchainError, WorkspaceError, OSError, ValueError):
        pass

    prefix = resolve_within(root, str(lock["prefix"]))
    if prefix.exists():
        raise SystemToolchainError(
            f"incomplete toolchain prefix exists: {prefix}"
        )
    actual_package_version = package_version(str(config["package"]))
    if actual_package_version != config["package_version"]:
        raise SystemToolchainError(
            f"{config['package']} is {actual_package_version}, "
            f"expected {config['package_version']}"
        )
    tools = system_tools(lock, config)
    staging = resolve_within(root, "tmp/bootstrap/binutils-system")
    if staging.exists():
        shutil.rmtree(staging)
    try:
        binary_directory = staging / "bin"
        binary_directory.mkdir(parents=True)
        wrappers: dict[str, str] = {}
        sources: dict[str, dict[str, str]] = {}
        for name, executable in tools.items():
            wrapper = binary_directory / f"{lock['target']}-{name}"
            wrapper.write_text(wrapper_text(executable), encoding="ascii")
            wrapper.chmod(0o755)
            wrappers[name] = sha256(wrapper)
            sources[name] = {
                "path": str(executable),
                "sha256": sha256(executable),
            }
        manifest = {
            "schema": 1,
            "distribution": "ubuntu-system-binutils",
            "package": config["package"],
            "package_version": actual_package_version,
            "version": config["version"],
            "target": config["target"],
            "wrappers": wrappers,
            "sources": sources,
        }
        (staging / MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        prefix.parent.mkdir(parents=True, exist_ok=True)
        staging.replace(prefix)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def check(
    root: Path,
    lock: dict[str, Any],
    config: dict[str, Any],
) -> None:
    prefix = resolve_within(root, str(lock["prefix"]), must_exist=True)
    manifest = load_json(manifest_path(root, lock))
    expected = {
        "distribution": "ubuntu-system-binutils",
        "package": config["package"],
        "package_version": config["package_version"],
        "version": config["version"],
        "target": config["target"],
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise SystemToolchainError(
                f"{manifest_path(root, lock)}: {key} differs"
            )
    if package_version(str(config["package"])) != config["package_version"]:
        raise SystemToolchainError("installed Ubuntu package version differs")
    tools = system_tools(lock, config)
    wrappers = manifest.get("wrappers")
    sources = manifest.get("sources")
    if not isinstance(wrappers, dict) or not isinstance(sources, dict):
        raise SystemToolchainError("system binutils manifest is incomplete")
    for name, executable in tools.items():
        wrapper = prefix / "bin" / f"{lock['target']}-{name}"
        if not wrapper.is_file() or sha256(wrapper) != wrappers.get(name):
            raise SystemToolchainError(f"packaged wrapper differs: {wrapper}")
        source = sources.get(name)
        if not isinstance(source, dict):
            raise SystemToolchainError(f"missing packaged source record: {name}")
        if (
            source.get("path") != str(executable)
            or source.get("sha256") != sha256(executable)
        ):
            raise SystemToolchainError(
                f"packaged source binary differs: {executable}"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install local wrappers for Ubuntu MIPS binutils."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify wrappers and packaged binaries without changing them",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        root = require_workspace_root()
        lock = binutils.load_lock(root)
        config = load_config(root)
        if args.check:
            check(root, lock, config)
        else:
            install(root, lock, config)
            check(root, lock, config)
    except (
        SystemToolchainError,
        binutils.ToolchainError,
        WorkspaceError,
        OSError,
        UnicodeError,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(
        f"{config['target']} binutils {config['version']} package wrappers: OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
