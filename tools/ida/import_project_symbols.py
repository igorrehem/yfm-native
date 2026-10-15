"""Import memories-decomp function and global names into an IDA 9.x database."""

from __future__ import annotations

import csv
import re
from pathlib import Path

import ida_auto
import ida_bytes
import ida_funcs
import ida_idaapi
import ida_kernwin
import ida_name
import idc


SYMBOL_PATTERN = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
    r"(0x[0-9A-Fa-f]+|\d+)\s*;(?P<suffix>.*)$"
)
AUTO_PREFIXES = (
    "sub_",
    "loc_",
    "locret_",
    "byte_",
    "word_",
    "dword_",
    "qword_",
    "unk_",
    "off_",
    "asc_",
    "stru_",
    "algn_",
)


class ImportError(Exception):
    pass


def find_project_root() -> Path | None:
    scripted = Path(__file__).resolve().parents[2]
    if (scripted / "config/slus_01411/functions.csv").is_file():
        return scripted
    selected = ida_kernwin.ask_file(
        False,
        "functions.csv",
        "Select config/slus_01411/functions.csv",
    )
    if not selected:
        return None
    path = Path(selected).resolve()
    if path.name != "functions.csv":
        raise ImportError("selected file is not functions.csv")
    root = path.parents[2]
    if not (root / "config/slus_01411/symbols.txt").is_file():
        raise ImportError("could not locate config/slus_01411/symbols.txt")
    return root


def load_functions(root: Path) -> list[dict[str, object]]:
    path = root / "config/slus_01411/functions.csv"
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    result = []
    for row in rows:
        result.append(
            {
                "address": int(row["address"], 0),
                "size": int(row["size"], 0),
                "name": row["name"],
            }
        )
    return result


def load_symbols(root: Path) -> list[dict[str, object]]:
    path = root / "config/slus_01411/symbols.txt"
    result = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        match = SYMBOL_PATTERN.match(line)
        if match is None:
            raise ImportError(f"{path}:{line_number}: invalid symbol line")
        result.append(
            {
                "address": int(match.group(2), 0),
                "name": match.group(1),
                "function": "type:func" in match.group("suffix"),
            }
        )
    return result


def is_automatic_name(name: str) -> bool:
    return not name or name.startswith(AUTO_PREFIXES)


def set_project_name(
    address: int,
    name: str,
    *,
    replace_user_names: bool,
) -> str:
    current = idc.get_name(address)
    if current == name:
        return "unchanged"
    if current and not is_automatic_name(current) and not replace_user_names:
        return "preserved"
    existing = idc.get_name_ea_simple(name)
    if existing not in (ida_idaapi.BADADDR, address):
        return "collision"
    flags = ida_name.SN_FORCE | ida_name.SN_NOWARN
    return "renamed" if ida_name.set_name(address, name, flags) else "failed"


def ensure_function(address: int, size: int) -> str:
    function = ida_funcs.get_func(address)
    if function is not None and function.start_ea == address:
        return "existing"
    if function is not None:
        return "overlap"
    return (
        "created"
        if ida_funcs.add_func(address, address + size)
        else "failed"
    )


def main() -> None:
    try:
        root = find_project_root()
        if root is None:
            return
        answer = ida_kernwin.ask_yn(
            ida_kernwin.ASKBTN_NO,
            "Replace existing non-automatic IDA names with project names?",
        )
        if answer == ida_kernwin.ASKBTN_CANCEL:
            return
        replace_user_names = answer == ida_kernwin.ASKBTN_YES
        functions = load_functions(root)
        symbols = load_symbols(root)
        ida_auto.auto_wait()

        counts: dict[str, int] = {}

        def count(key: str) -> None:
            counts[key] = counts.get(key, 0) + 1

        for row in functions:
            address = int(row["address"])
            if not ida_bytes.is_mapped(address):
                count("unmapped")
                continue
            count(
                "function_" + ensure_function(address, int(row["size"]))
            )
            count(
                "name_"
                + set_project_name(
                    address,
                    str(row["name"]),
                    replace_user_names=replace_user_names,
                )
            )

        for row in symbols:
            address = int(row["address"])
            if not ida_bytes.is_mapped(address):
                count("unmapped")
                continue
            if bool(row["function"]):
                function = ida_funcs.get_func(address)
                if function is None:
                    count(
                        "function_"
                        + (
                            "created"
                            if ida_funcs.add_func(address)
                            else "failed"
                        )
                    )
            count(
                "name_"
                + set_project_name(
                    address,
                    str(row["name"]),
                    replace_user_names=replace_user_names,
                )
            )

        ida_auto.auto_wait()
        summary = ", ".join(
            f"{key}={counts[key]}" for key in sorted(counts)
        )
        ida_kernwin.msg(f"memories-decomp symbol import complete: {summary}\n")
    except (ImportError, OSError, UnicodeError, ValueError, KeyError) as error:
        ida_kernwin.warning(f"memories-decomp symbol import failed:\n{error}")


if __name__ == "__main__":
    main()
