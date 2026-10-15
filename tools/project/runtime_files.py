#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path
from typing import Any

from psx_exe import load_verified_executable
from workspace import WorkspaceError, require_workspace_root, resolve_within


class RuntimeFileError(RuntimeError):
    pass


FILENAME_POINTER_TABLE = 0x8009078C
RUNTIME_LBA_TABLE = 0x800E9EA8
EXPECTED_FILE_COUNT = 7


def read_c_string(image: bytes, offset: int) -> str:
    end = image.find(b"\0", offset)
    if end < 0:
        raise RuntimeFileError(f"unterminated string at file offset {offset:#x}")
    try:
        return image[offset:end].decode("ascii")
    except UnicodeDecodeError as error:
        raise RuntimeFileError(
            f"non-ASCII filename at file offset {offset:#x}"
        ) from error


def normalize_disc_path(path: str) -> str:
    normalized = path.replace("\\", "/").lstrip("/")
    if ";" in normalized:
        normalized = normalized.split(";", 1)[0]
    return normalized.upper()


def scan(root: Path) -> dict[str, Any]:
    executable, _metadata, _header_bytes, header = load_verified_executable(root)
    image = executable.read_bytes()
    table_offset = header.vram_to_file_offset(FILENAME_POINTER_TABLE)

    pointers: list[int] = []
    for index in range(EXPECTED_FILE_COUNT + 1):
        pointer = struct.unpack_from("<I", image, table_offset + index * 4)[0]
        if pointer == 0:
            break
        pointers.append(pointer)
    if len(pointers) != EXPECTED_FILE_COUNT:
        raise RuntimeFileError(
            f"filename table contains {len(pointers)} entries, "
            f"expected {EXPECTED_FILE_COUNT}"
        )
    terminator = struct.unpack_from(
        "<I", image, table_offset + EXPECTED_FILE_COUNT * 4
    )[0]
    if terminator != 0:
        raise RuntimeFileError("filename table is not null-terminated")

    disc_layout_path = resolve_within(
        root, "config/slus_01411/disc_layout.json", must_exist=True
    )
    with disc_layout_path.open("r", encoding="utf-8") as handle:
        disc_layout = json.load(handle)
    disc_files = {
        str(entry["path"]).upper(): entry for entry in disc_layout["files"]
    }

    entries: list[dict[str, Any]] = []
    for index, pointer in enumerate(pointers):
        path = read_c_string(image, header.vram_to_file_offset(pointer))
        disc_path = normalize_disc_path(path)
        disc_entry = disc_files.get(disc_path)
        if disc_entry is None:
            raise RuntimeFileError(
                f"runtime filename {path} is absent from the disc manifest"
            )
        entries.append(
            {
                "index": index,
                "filename_vram": f"0x{pointer:08X}",
                "runtime_path": path,
                "disc_path": disc_path,
                "lba": disc_entry["lba"],
                "msf": disc_entry["msf"],
                "size": disc_entry["size"],
                "lba_slot_vram": f"0x{RUNTIME_LBA_TABLE + index * 4:08X}",
            }
        )

    return {
        "schema": 1,
        "filename_pointer_table_vram": f"0x{FILENAME_POINTER_TABLE:08X}",
        "runtime_lba_table_vram": f"0x{RUNTIME_LBA_TABLE:08X}",
        "entry_count": len(entries),
        "entries": entries,
    }


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    try:
        temporary.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def print_summary(value: dict[str, Any]) -> None:
    for entry in value["entries"]:
        print(
            f"{entry['index']}: {entry['disc_path']:<20} "
            f"LBA {entry['lba']:>6} -> {entry['lba_slot_vram']}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify executable runtime file order against disc LBAs."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("info")
    subparsers.add_parser("write")
    subparsers.add_parser("verify")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        root = require_workspace_root()
        value = scan(root)
        path = resolve_within(
            root, "config/slus_01411/runtime_files.json"
        )
        if args.command == "write":
            atomic_write_json(path, value)
            print(f"runtime files: {path.relative_to(root)}")
        elif args.command == "verify":
            if not path.is_file():
                raise RuntimeFileError(
                    f"missing runtime file manifest: {path.relative_to(root)}"
                )
            with path.open("r", encoding="utf-8") as handle:
                expected = json.load(handle)
            if expected != value:
                raise RuntimeFileError(
                    "runtime file metadata changed; run make runtime-files"
                )
            print("runtime files: OK")
        elif args.command == "info":
            print_summary(value)
        else:
            raise RuntimeFileError(f"unsupported command: {args.command}")
    except (
        RuntimeFileError,
        WorkspaceError,
        OSError,
        UnicodeError,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        struct.error,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
