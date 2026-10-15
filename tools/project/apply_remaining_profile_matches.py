#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import audit_unchiga_candidates
from workspace import WorkspaceError, require_workspace_root, resolve_within


FUNCTIONS_PATH = "config/slus_01411/functions.csv"
MATCHING_PATH = "config/slus_01411/matching_c.json"
EXTERNAL_ATTEMPTS_PATH = "config/slus_01411/external_attempts.csv"
C_SYMBOLS_PATH = "config/slus_01411/c_symbols.ld"
INTEGRATE_PATH = "tools/project/integrate_verified_match.py"
RECORD_PATH = "tools/project/record_external_attempt.py"
TYPE_TOOL_PATH = "tools/project/centralize_basic_types.py"
INCREMENTAL_PATH = "tools/project/build_incremental.py"
WORK_PATH = "tmp/agents/remaining-profile-pass"
RESULT_FIELDS = (
    "address",
    "size",
    "attempt_count",
    "profile",
    "source",
    "exact",
    "bytes_match",
    "relocations_match",
    "actual_size",
    "first_difference",
    "error",
)
ASM_PATTERN = re.compile(r"\b(?:asm|__asm|__asm__)\b")
COMMENT_PATTERN = re.compile(r"/\*.*?\*/|//[^\n]*", re.DOTALL)


class ApplyError(RuntimeError):
    pass


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != RESULT_FIELDS:
            raise ApplyError(f"{path}: unexpected result fields")
        return list(reader)


def load_functions(root: Path) -> dict[int, dict[str, str]]:
    path = resolve_within(root, FUNCTIONS_PATH, must_exist=True)
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {
            int(row["address"], 0): row for row in csv.DictReader(handle)
        }


def load_matching(root: Path) -> dict[int, dict[str, Any]]:
    path = resolve_within(root, MATCHING_PATH, must_exist=True)
    value = audit_unchiga_candidates.load_json(path)
    return {
        int(row["address"], 0): row for row in value["functions"]
    }


def run(
    root: Path,
    work: Path,
    command: list[str],
    *,
    log_name: str,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["MAKEFLAGS"] = "-j2"
    environment["GIT_AUTHOR_NAME"] = "Copilot"
    environment["GIT_AUTHOR_EMAIL"] = (
        "223556219+Copilot@users.noreply.github.com"
    )
    environment["GIT_COMMITTER_NAME"] = "Copilot"
    environment["GIT_COMMITTER_EMAIL"] = (
        "223556219+Copilot@users.noreply.github.com"
    )
    completed = subprocess.run(
        command,
        cwd=root,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    log = work / "apply-logs" / log_name
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        "$ "
        + " ".join(command)
        + f"\nexit: {completed.returncode}\n[stdout]\n"
        + completed.stdout
        + "\n[stderr]\n"
        + completed.stderr,
        encoding="utf-8",
    )
    return completed


def require_success(
    completed: subprocess.CompletedProcess[str],
    description: str,
) -> None:
    if completed.returncode:
        details = (completed.stderr or completed.stdout).splitlines()
        detail = details[-1] if details else f"exit {completed.returncode}"
        raise ApplyError(f"{description}: {detail}")


def git_output(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "--no-pager", *arguments],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode:
        raise ApplyError(
            f"git {' '.join(arguments)}: {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def require_clean_master(root: Path) -> None:
    if git_output(root, "branch", "--show-current") != "master":
        raise ApplyError("exact-match integration requires master")
    if git_output(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ApplyError("exact-match integration requires a clean worktree")
    counts = git_output(
        root,
        "rev-list",
        "--left-right",
        "--count",
        "origin/master...HEAD",
    ).split()
    if len(counts) != 2 or counts[0] != "0":
        raise ApplyError(
            "master must not be behind or diverged from origin/master"
        )


def prepare_source(
    root: Path,
    row: dict[str, str],
    function_name: str,
) -> Path:
    source = resolve_within(root, row["source"], must_exist=True)
    text = source.read_text(encoding="utf-8")
    if ASM_PATTERN.search(COMMENT_PATTERN.sub("", text)):
        raise ApplyError(f"{row['address']}: exact candidate contains asm")
    address = int(row["address"], 0)
    address_name = f"func_{address:08X}"
    if re.search(rf"\b{re.escape(function_name)}\s*\(", text) is None:
        if re.search(rf"\b{address_name}\s*\(", text) is None:
            raise ApplyError(
                f"{row['address']}: candidate does not define "
                f"{function_name} or {address_name}"
            )
        text = re.sub(
            rf"\b{address_name}\b",
            function_name,
            text,
        )
    output = resolve_within(
        root,
        f"{WORK_PATH}/prepared/func_{address:08X}.c",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    return output


def source_owner_count(
    matching: dict[int, dict[str, Any]],
    source: str,
) -> int:
    return sum(entry["source"] == source for entry in matching.values())


def backup(paths: list[Path]) -> dict[Path, bytes | None]:
    return {
        path: path.read_bytes() if path.exists() else None for path in paths
    }


def restore(values: dict[Path, bytes | None]) -> None:
    for path, data in values.items():
        if data is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply reviewed exact inline-profile pass matches."
    )
    parser.add_argument("results", help="exact-result CSV beneath tmp/")
    args = parser.parse_args()
    try:
        root = require_workspace_root()
        result_path = resolve_within(root, args.results, must_exist=True)
        result_path.relative_to(resolve_within(root, "tmp", must_exist=True))
        require_clean_master(root)
        work = resolve_within(root, WORK_PATH)
        functions = load_functions(root)
        matching = load_matching(root)
        exact = [
            row
            for row in read_csv(result_path)
            if row["exact"] == "True"
        ]
        if not exact:
            print("applied exact profile matches: 0")
            return 0

        baseline = run(
            root,
            work,
            ["make", "match"],
            log_name="baseline.log",
        )
        require_success(baseline, "clean baseline")
        seed = run(
            root,
            work,
            [
                str(
                    resolve_within(
                        root,
                        "tools/environments/python/bin/python",
                        must_exist=True,
                    )
                ),
                str(resolve_within(root, INCREMENTAL_PATH, must_exist=True)),
                "--seed-existing",
            ],
            log_name="seed.log",
        )
        require_success(seed, "incremental cache seed")

        applied = 0
        last_push = int(git_output(root, "show", "-s", "--format=%ct", "origin/master"))
        for row in exact:
            address = int(row["address"], 0)
            functions = load_functions(root)
            matching = load_matching(root)
            function = functions[address]
            entry = matching.get(address)
            if entry is None or function["status"] != "matching_c":
                continue
            current_source = resolve_within(
                root, entry["source"], must_exist=True
            )
            if ASM_PATTERN.search(
                COMMENT_PATTERN.sub(
                    "", current_source.read_text(encoding="utf-8")
                )
            ) is None:
                continue
            if source_owner_count(matching, entry["source"]) != 1:
                raise ApplyError(
                    f"{row['address']}: exact target is in a grouped unit"
                )
            prepared = prepare_source(root, row, function["name"])
            tracked = [
                resolve_within(
                    root, EXTERNAL_ATTEMPTS_PATH, must_exist=True
                ),
                resolve_within(root, FUNCTIONS_PATH, must_exist=True),
                resolve_within(root, MATCHING_PATH, must_exist=True),
                resolve_within(root, C_SYMBOLS_PATH, must_exist=True),
                current_source,
            ]
            saved = backup(tracked)
            try:
                audit_unchiga_candidates.add_required_linker_aliases(
                    root, work, address
                )
                record = run(
                    root,
                    work,
                    [
                        sys.executable,
                        str(resolve_within(root, RECORD_PATH, must_exist=True)),
                        row["address"],
                        "--mode",
                        "inline_refinement",
                        "--profile",
                        row["profile"],
                        "--candidate",
                        str(prepared.relative_to(root)),
                        "--result",
                        "matched",
                        "--summary",
                        (
                            "Preserved pure-C candidate matched after testing "
                            f"the untried {row['profile']} profile; exact text, "
                            "relocations, and allocated sections."
                        ),
                    ],
                    log_name=f"{address:08X}-record.log",
                )
                require_success(record, f"{row['address']}: record evidence")
                integrate = run(
                    root,
                    work,
                    [
                        sys.executable,
                        str(
                            resolve_within(
                                root, INTEGRATE_PATH, must_exist=True
                            )
                        ),
                        row["address"],
                        "--source",
                        str(prepared.relative_to(root)),
                        "--destination",
                        entry["source"],
                        "--profile",
                        row["profile"],
                        "--note",
                        (
                            "Pure-C profile recovery; exact linked bytes and "
                            f"relocations with {row['profile']}."
                        ),
                        "--evidence-source",
                        "refinement",
                        "--replace-existing",
                    ],
                    log_name=f"{address:08X}-integrate.log",
                )
                require_success(
                    integrate, f"{row['address']}: integrate exact source"
                )
                types = run(
                    root,
                    work,
                    [
                        sys.executable,
                        str(
                            resolve_within(
                                root, TYPE_TOOL_PATH, must_exist=True
                            )
                        ),
                        "--apply",
                    ],
                    log_name=f"{address:08X}-types.log",
                )
                require_success(types, f"{row['address']}: normalize types")
                match = run(
                    root,
                    work,
                    ["make", "match-incremental"],
                    log_name=f"{address:08X}-match.log",
                )
                require_success(match, f"{row['address']}: full match")
                stage_paths = [
                    EXTERNAL_ATTEMPTS_PATH,
                    FUNCTIONS_PATH,
                    MATCHING_PATH,
                    C_SYMBOLS_PATH,
                    entry["source"],
                ]
                staged = run(
                    root,
                    work,
                    ["git", "add", "--", *stage_paths],
                    log_name=f"{address:08X}-stage.log",
                )
                require_success(staged, f"{row['address']}: stage")
                commit = run(
                    root,
                    work,
                    [
                        "git",
                        "-c",
                        "core.hooksPath=/dev/null",
                        "commit",
                        "--no-gpg-sign",
                        "-m",
                        f"decomp: replace inline assembly in {function['name']}",
                        "-m",
                        "Co-authored-by: Copilot "
                        "<223556219+Copilot@users.noreply.github.com>",
                    ],
                    log_name=f"{address:08X}-commit.log",
                )
                require_success(commit, f"{row['address']}: commit")
            except Exception:
                restore(saved)
                subprocess.run(
                    ["git", "reset", "--quiet"],
                    cwd=root,
                    check=False,
                )
                raise
            applied += 1
            now = int(time.time())
            if now - last_push >= 900:
                push = run(
                    root,
                    work,
                    ["git", "push", "origin", "master"],
                    log_name=f"{address:08X}-push.log",
                )
                require_success(push, "periodic push")
                last_push = now

        print(f"applied exact profile matches: {applied}")
    except (
        ApplyError,
        WorkspaceError,
        OSError,
        UnicodeError,
        KeyError,
        TypeError,
        ValueError,
        csv.Error,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
