"""replay.py's check on made-up recordings (CTest pc_replay_check): no game needed.

A game closed while it waits for a VBlank presents its last frame without
one, so the recording ends with two frame hashes at one VBlank, which the
play reaches a VBlank later; the check must pass a play that agrees, and
still name the first frame that differs."""
import io
import json
from pathlib import Path
import sys
import tempfile
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools/pc"))
import replay  # noqa: E402

HEAD = "yfm-recording 1\nbuild 0000abcd\nstart boot\nF clock: virtual\nI 1 0000 0000 0000 0000 0\n"
RECORDED = HEAD + "H 1 1 aa\nH 2 2 bb\nH 7307 6399 cc\nH 7307 6400 dd\nE 7307 6400\n"


def replay_of(folder: Path, text: str, clock: str = "virtual") -> replay.Replay:
    folder.mkdir(parents=True)
    (folder / "recording.txt").write_text(text)
    (folder / "replay.json").write_text(json.dumps({"format": 1, "kind": "recorded", "start": {"kind": "boot"},
                                                    "recording": "recording.txt",
                                                    "header": {"clock": clock}}))
    return replay.Replay(folder)


def failed_runs(work: Path) -> None:
    """Exercise real subprocess exits/timeouts, including --update's writes."""
    expected_text = HEAD + "H 1 1 aa\nE 100 100\n"  # thinned hashes
    expected = replay_of(work / "failures", expected_text)
    script = work / "fake_game.py"
    cases = (
        ("crash", HEAD + "H 1 1 aa\nE 100 100\n", "raise SystemExit(17)", 5),
        ("timeout", HEAD + "H 1 1 aa\nE 100 100\n", "import time; time.sleep(10)", 0.5),
        ("missing-end", HEAD + "H 1 1 aa\n", "", 5),
        ("premature-end", HEAD + "H 1 1 aa\nE 2 2\n", "", 5),
        ("missing-output", None, "", 5),
    )
    with mock.patch.object(replay, "OUTPUT", work / "output"), \
         mock.patch.object(replay, "launcher", return_value=([sys.executable, str(script)], {})):
        for name, recording, tail, timeout in cases:
            script.write_text("import os\nfrom pathlib import Path\n" +
                (f"Path(os.environ['MEMORIES_RECORD']).write_text({recording!r})\n" if recording is not None else "") +
                tail + "\n")
            for check, update in ((True, False), (False, True), (False, False)):
                before = set(replay.OUTPUT.iterdir()) if replay.OUTPUT.exists() else set()
                assert not replay.play(expected.path, Path(sys.executable), check, update, timeout), name
                assert (expected.path / "recording.txt").read_text() == expected_text, name
                created = set(replay.OUTPUT.iterdir()) - before
                assert len(created) == 1 and (created.pop() / "game.log").is_file(), name
        # An update still accepts changed hashes from a complete successful run.
        updated = HEAD + "H 1 1 bb\nE 100 100\n"
        script.write_text("import os\nfrom pathlib import Path\n" +
                          f"Path(os.environ['MEMORIES_RECORD']).write_text({updated!r})\n")
        assert replay.play(expected.path, Path(sys.executable), False, True, 5)
        assert (expected.path / "recording.txt").read_text() == updated
        assert replay.play(expected.path, Path(sys.executable), True, False, 5)


def main() -> int:
    work = Path(tempfile.mkdtemp())
    expected = replay_of(work / "replay", RECORDED)
    same = work / "same.txt"
    same.write_text(RECORDED)
    assert replay.check(expected, same), "a play that agrees, with two frames in its last VBlank, passes"
    later = work / "later.txt"
    later.write_text(HEAD + "H 1 1 aa\nH 2 2 bb\nH 7307 6399 cc\nH 7308 6400 dd\nE 7308 6400\n")
    assert replay.check(expected, later), "the last frame a VBlank later in the play (the quit cut its wait) passes"
    stopped = work / "stopped.txt"
    stopped.write_text(HEAD + "H 1 1 aa\nH 2 2 bb\nH 7307 6399 cc\nE 7307 6399\n")
    assert not replay.check(expected, stopped), "a play that stops a frame early fails"
    stopped.write_text(RECORDED.rsplit("E ", 1)[0])
    assert not replay.check(expected, stopped), "all hashes without a clean end still fail"
    stopped.write_text(RECORDED.replace("E 7307 6400", "E 7308 6399"))
    assert not replay.check(expected, stopped), "a later VBlank does not excuse an early final frame"
    other = work / "other.txt"
    other.write_text(RECORDED.replace("H 2 2 bb", "H 2 2 b0"))
    assert not replay.check(expected, other), "a frame that differs fails"
    parsed = replay.parse(same)
    assert parsed["H"][(7307, 6399)] == "cc" and parsed["H"][(7307, 6400)] == "dd"
    assert replay.header_from(parsed)["clock"] == "virtual"
    real = replay_of(work / "real", RECORDED.replace("clock: virtual", "clock: real"), clock="real")
    assert not replay.play(real.path, Path(sys.executable), True, False, 1), "a real-time recording is refused"
    # Windows CI runs under Unicode temp paths with a legacy stdout code page.
    # Failure reporting must not throw before returning the failed verdict.
    output = io.BytesIO()
    with io.TextIOWrapper(output, encoding="cp1252", write_through=True) as console:
        with mock.patch.object(sys, "stdout", console):
            failed_runs(work / "paths-e\u0301-\u6771\u4eac")
        assert b"\\u6771" in output.getvalue()
    print("replay check: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
