#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import struct
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from function_inventory import Function, InventoryError, load_inventory
from select_candidates import TERMINAL_RESULTS, load_attempts
from workspace import WorkspaceError, require_workspace_root, resolve_within


class SiblingError(RuntimeError):
    pass


LOAD_ADDRESS = 0x80010000
HEADER_SIZE = 0x800
BRANCH_OPS = {0x01, 0x04, 0x05, 0x06, 0x07, 0x14, 0x15, 0x16, 0x17}
LOAD_STORE_OPS = set(range(0x20, 0x3F))


def parse_integer(value: str) -> int:
    try:
        return int(value, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"invalid integer: {value}") from error


def immediate_bucket(value: int) -> str:
    signed = value if value < 0x8000 else value - 0x10000
    if signed == 0:
        return "zero"
    if signed in {-1, 1}:
        return "unit"
    magnitude = abs(signed)
    if magnitude <= 8:
        return "tiny"
    if magnitude <= 0x7F:
        return "byte"
    if magnitude <= 0x7FF:
        return "small"
    return "large"


def base_register(register: int) -> str:
    if register == 28:
        return "gp"
    if register == 29:
        return "sp"
    if register == 0:
        return "zero"
    return "reg"


def normalize_instruction(word: int) -> str:
    opcode = word >> 26
    rs = (word >> 21) & 0x1F
    rt = (word >> 16) & 0x1F
    immediate = word & 0xFFFF

    if opcode == 0:
        function = word & 0x3F
        shamt = (word >> 6) & 0x1F
        if function in {0x00, 0x02, 0x03}:
            return f"special:{function:02x}:shift:{shamt}"
        return f"special:{function:02x}"
    if opcode == 0x01:
        return f"regimm:{rt:02x}:{'back' if immediate & 0x8000 else 'forward'}"
    if opcode in {0x02, 0x03}:
        return f"jump:{opcode:02x}"
    if opcode in BRANCH_OPS:
        return f"branch:{opcode:02x}:{'back' if immediate & 0x8000 else 'forward'}"
    if opcode in LOAD_STORE_OPS:
        return (
            f"memory:{opcode:02x}:{base_register(rs)}:"
            f"{immediate_bucket(immediate)}"
        )
    if opcode == 0x0F:
        return "lui"
    if opcode in {0x10, 0x11, 0x12, 0x13}:
        return f"cop:{opcode:02x}:{rs:02x}:{word & 0x3F:02x}"
    return f"opcode:{opcode:02x}:{immediate_bucket(immediate)}"


def function_tokens(executable: bytes, function: Function) -> list[str]:
    if function.size % 4:
        raise SiblingError(
            f"{function.address:#010x}: size is not instruction-aligned"
        )
    offset = function.address - LOAD_ADDRESS + HEADER_SIZE
    end = offset + function.size
    if offset < HEADER_SIZE or end > len(executable):
        raise SiblingError(
            f"{function.address:#010x}: executable range is out of bounds"
        )
    return [
        normalize_instruction(word)
        for (word,) in struct.iter_unpack("<I", executable[offset:end])
    ]


def ngrams(tokens: list[str], width: int) -> Counter[tuple[str, ...]]:
    return Counter(
        tuple(tokens[index : index + width])
        for index in range(len(tokens) - width + 1)
    )


def multiset_jaccard(
    left: Counter[tuple[str, ...]],
    right: Counter[tuple[str, ...]],
) -> float:
    keys = left.keys() | right.keys()
    if not keys:
        return 1.0
    intersection = sum(min(left[key], right[key]) for key in keys)
    union = sum(max(left[key], right[key]) for key in keys)
    return intersection / union


def similarity(left: list[str], right: list[str]) -> float:
    length_ratio = min(len(left), len(right)) / max(len(left), len(right))
    bigrams = multiset_jaccard(ngrams(left, 2), ngrams(right, 2))
    trigrams = multiset_jaccard(ngrams(left, 3), ngrams(right, 3))
    fourgrams = multiset_jaccard(ngrams(left, 4), ngrams(right, 4))
    shape = 0.2 * bigrams + 0.5 * trigrams + 0.3 * fourgrams
    return shape * (0.4 + 0.6 * length_ratio)


def load_matching(path: Path) -> dict[int, dict[str, str]]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if value.get("schema") != 1 or not isinstance(value.get("functions"), list):
        raise SiblingError(f"{path}: unsupported matching manifest")
    result: dict[int, dict[str, str]] = {}
    for entry in value["functions"]:
        address = int(entry["address"], 0)
        result[address] = {
            "source": entry["source"],
            "profile": entry["profile"],
        }
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find exact-C functions with similar target instruction shapes."
    )
    parser.add_argument(
        "addresses",
        nargs="*",
        type=parse_integer,
        help="specific untouched function addresses",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="smallest zero-attempt candidates when no addresses are supplied",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="matching siblings to report per candidate",
    )
    parser.add_argument(
        "--format",
        choices=("csv", "json"),
        default="csv",
        help="output format",
    )
    return parser.parse_args()


def select_candidates(
    functions: list[Function],
    attempts: dict[int, list[dict[str, str]]],
    addresses: list[int],
    limit: int,
) -> list[Function]:
    by_address = {function.address: function for function in functions}
    if addresses:
        selected: list[Function] = []
        for address in addresses:
            function = by_address.get(address)
            if function is None:
                raise SiblingError(f"{address:#010x}: not in function inventory")
            history = attempts.get(address, [])
            if function.module != "game" or function.status != "unmatched_asm":
                raise SiblingError(f"{address:#010x}: not unmatched game code")
            if history:
                terminal = history[-1]["result"]
                state = "terminal" if terminal in TERMINAL_RESULTS else "partial"
                raise SiblingError(
                    f"{address:#010x}: has an existing {state} attempt history"
                )
            selected.append(function)
        return selected

    if limit < 1:
        raise SiblingError("limit must be at least one")
    selected = [
        function
        for function in functions
        if function.module == "game"
        and function.status == "unmatched_asm"
        and not attempts.get(function.address)
    ]
    selected.sort(key=lambda function: (function.size, function.address))
    return selected[:limit]


def main() -> int:
    args = parse_args()
    try:
        root = require_workspace_root()
        functions = load_inventory(
            resolve_within(
                root, "config/slus_01411/functions.csv", must_exist=True
            )
        )
        attempts = load_attempts(
            resolve_within(
                root, "config/slus_01411/attempts.csv", must_exist=True
            )
        )
        matching = load_matching(
            resolve_within(
                root, "config/slus_01411/matching_c.json", must_exist=True
            )
        )
        executable = resolve_within(
            root, "game/SLUS_014.11", must_exist=True
        ).read_bytes()
        candidates = select_candidates(
            functions, attempts, args.addresses, args.limit
        )
        matching_functions = [
            function for function in functions if function.address in matching
        ]

        tokens = {
            function.address: function_tokens(executable, function)
            for function in candidates + matching_functions
        }
        rows: list[dict[str, Any]] = []
        for candidate in candidates:
            ranked = sorted(
                matching_functions,
                key=lambda function: similarity(
                    tokens[candidate.address], tokens[function.address]
                ),
                reverse=True,
            )[: args.top]
            for rank, sibling in enumerate(ranked, start=1):
                entry = matching[sibling.address]
                rows.append(
                    {
                        "candidate": f"0x{candidate.address:08X}",
                        "candidate_size": f"0x{candidate.size:X}",
                        "rank": rank,
                        "sibling": f"0x{sibling.address:08X}",
                        "sibling_size": f"0x{sibling.size:X}",
                        "score": round(
                            similarity(
                                tokens[candidate.address],
                                tokens[sibling.address],
                            ),
                            6,
                        ),
                        "source": entry["source"],
                        "profile": entry["profile"],
                    }
                )

        if args.format == "json":
            print(json.dumps({"schema": 1, "siblings": rows}, indent=2))
        else:
            fields = (
                "candidate",
                "candidate_size",
                "rank",
                "sibling",
                "sibling_size",
                "score",
                "source",
                "profile",
            )
            writer = csv.DictWriter(
                sys.stdout, fieldnames=fields, lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)
    except (
        SiblingError,
        InventoryError,
        WorkspaceError,
        OSError,
        UnicodeError,
        KeyError,
        TypeError,
        ValueError,
        csv.Error,
        json.JSONDecodeError,
        struct.error,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
