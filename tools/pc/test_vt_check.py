#!/usr/bin/env python3
"""tools/pc/vt_check.py against a fake VirusTotal: no network, no key."""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vt_check

KEY = "fake-key-0123456789abcdef-never-shown"


def verdicts(**engines):
    """{engine: (category, result)} as the API's results dictionary."""
    return {name: {"category": category, "result": result, "engine_name": name}
            for name, (category, result) in engines.items()}


REPORT = verdicts(Bkav=("malicious", "W32.AIDetectMalware"), Kaspersky=("undetected", None),
                  SecureAge=("suspicious", "Malicious"), Avast=("undetected", None),
                  Cylance=("type-unsupported", None), Zillya=("timeout", None))


class FakeVT:
    """Answers requests from queued responses per (method, path); keeps a log.
    Its clock only moves when the client sleeps."""

    def __init__(self):
        self.now = 1000.0
        self.calls, self.sleeps = [], []
        self.routes = {}

    def on(self, method, path, *responses):
        self.routes.setdefault((method, path), []).extend(responses)

    def transport(self, method, url, headers, body):
        assert headers["x-apikey"] == KEY
        path = url.replace(vt_check.API, "")
        self.calls.append((self.now, method, path, body))
        queue = self.routes[(method, path)]
        status, data = queue.pop(0) if len(queue) > 1 else queue[0]
        return status, json.dumps(data).encode() if data is not None else b""

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def clock(self):
        return self.now

    def factory(self, key, **options):
        return vt_check.Client(key, transport=self.transport, sleep=self.sleep, clock=self.clock,
                               log=lambda text: print(text, file=sys.stderr), **options)


def known(results, stamp=1759190400):
    return 200, {"data": {"attributes": {"last_analysis_results": results, "last_analysis_date": stamp}}}


NOT_FOUND = (404, {"error": {"code": "NotFoundError", "message": "File not found"}})


class VTCheckTest(unittest.TestCase):
    def setUp(self):
        self.vt = FakeVT()
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def file(self, name, content):
        path = os.path.join(self.folder.name, name)
        with open(path, "wb") as handle:
            handle.write(content)
        return path, vt_check.hashlib.sha256(content).hexdigest()

    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stderr(err):
            status = vt_check.main(list(argv), client_factory=self.vt.factory,
                                   environ={"VT_API_KEY": KEY}, stdout=out)
        self.assertNotIn(KEY, out.getvalue() + err.getvalue())
        self.assertNotIn(KEY[-8:], out.getvalue() + err.getvalue())
        return status, out.getvalue(), err.getvalue()

    def test_known_file_is_looked_up_only(self):
        path, sha = self.file("a.exe", b"known")
        self.vt.on("GET", f"/files/{sha}", known(REPORT))
        status, out, _ = self.run_main(path)
        self.assertEqual(status, 0)
        self.assertEqual([call[1:3] for call in self.vt.calls], [("GET", f"/files/{sha}")])
        # malicious out of the engines with a verdict; unsupported/timeout left out
        self.assertIn("1/4", out)
        self.assertIn("Bkav: W32.AIDetectMalware", out)
        self.assertIn("SecureAge: Malicious (suspicious)", out)
        self.assertIn(vt_check.GUI + sha, out)
        self.assertIn(sha[:12], out)

    def test_unknown_file_is_uploaded_and_polled(self):
        path, sha = self.file("new.exe", b"MZ fresh build")
        self.vt.on("GET", f"/files/{sha}", NOT_FOUND)
        self.vt.on("POST", "/files", (200, {"data": {"type": "analysis", "id": "abc=="}}))
        queued = (200, {"data": {"attributes": {"status": "queued"}}})
        done = (200, {"data": {"attributes": {"status": "completed", "date": 1759190400,
                                              "results": verdicts(Bkav=("undetected", None))}}})
        self.vt.on("GET", "/analyses/abc==", queued, queued, done)
        status, out, _ = self.run_main("--label", "master", path)
        self.assertEqual(status, 0)
        self.assertEqual([call[1:3] for call in self.vt.calls],
                         [("GET", f"/files/{sha}"), ("POST", "/files")] + [("GET", "/analyses/abc==")] * 3)
        body = self.vt.calls[1][3]
        self.assertIn(b'name="file"; filename="new.exe"', body)
        self.assertIn(b"MZ fresh build", body)
        self.assertIn("master", out)
        self.assertIn("0/1", out)
        # the free tier: at least 15 s between any two requests
        times = [call[0] for call in self.vt.calls]
        self.assertTrue(all(b - a >= 15 for a, b in zip(times, times[1:])), times)

    def test_lookup_only_never_uploads(self):
        path, sha = self.file("new.exe", b"never seen")
        self.vt.on("GET", f"/files/{sha}", NOT_FOUND)
        status, out, _ = self.run_main("--lookup-only", "--max", "0", path)
        self.assertEqual(status, 0)
        self.assertEqual([call[1] for call in self.vt.calls], ["GET"])
        self.assertIn("unknown", out)

    def test_reanalyze_uploads_a_known_file(self):
        path, sha = self.file("a.exe", b"known")
        self.vt.on("GET", f"/files/{sha}", known(REPORT))
        self.vt.on("POST", "/files", (200, {"data": {"id": "x"}}))
        self.vt.on("GET", "/analyses/x", (200, {"data": {"attributes": {"status": "completed", "results": {}}}}))
        self.assertEqual(self.run_main("--reanalyze", path)[0], 0)
        self.assertIn(("POST", "/files"), [call[1:3] for call in self.vt.calls])

    def test_large_file_goes_through_upload_url(self):
        path, sha = self.file("big.exe", b"x" * 64)
        self.vt.on("GET", f"/files/{sha}", NOT_FOUND)
        self.vt.on("GET", "/files/upload_url", (200, {"data": "https://upload.example/signed?token=1"}))
        self.vt.on("POST", "https://upload.example/signed?token=1", (200, {"data": {"id": "big"}}))
        self.vt.on("GET", "/analyses/big", (200, {"data": {"attributes": {"status": "completed", "results": {}}}}))
        client = self.vt.factory(KEY)
        with redirect_stderr(io.StringIO()) as err:
            entry = vt_check.check_file(client, path, "big", direct_limit=32)
        self.assertEqual(entry["status"], "uploaded")
        self.assertIn(("POST", "https://upload.example/signed?token=1"), [call[1:3] for call in self.vt.calls])
        self.assertNotIn("signed", err.getvalue())

    def test_rate_limit_backs_off(self):
        path, sha = self.file("a.exe", b"known")
        self.vt.on("GET", f"/files/{sha}", (429, {"error": {"code": "QuotaExceededError"}}),
                   (429, {"error": {"code": "QuotaExceededError"}}), known(REPORT))
        status, _, err = self.run_main(path)
        self.assertEqual(status, 0)
        self.assertIn(60, self.vt.sleeps)
        self.assertIn(120, self.vt.sleeps)
        self.assertIn("rate limited", err)

    def test_rate_limit_gives_up(self):
        path, sha = self.file("a.exe", b"known")
        self.vt.on("GET", f"/files/{sha}", (429, {"error": {"code": "QuotaExceededError", "message": "quota"}}))
        status, _, err = self.run_main(path)
        self.assertEqual(status, 2)
        self.assertIn("HTTP 429", err)
        self.assertEqual(len(self.vt.calls), 5)

    def test_daily_budget(self):
        paths = []
        for index in range(3):
            path, sha = self.file(f"{index}.exe", bytes([index]))
            self.vt.on("GET", f"/files/{sha}", known(REPORT))
            paths.append(path)
        status, _, err = self.run_main("--daily", "2", *paths)
        self.assertEqual(status, 2)
        self.assertIn("daily", err)
        self.assertEqual(len(self.vt.calls), 2)

    def test_analysis_timeout(self):
        path, sha = self.file("slow.exe", b"slow")
        self.vt.on("GET", f"/files/{sha}", NOT_FOUND)
        self.vt.on("POST", "/files", (200, {"data": {"id": "slow"}}))
        self.vt.on("GET", "/analyses/slow", (200, {"data": {"attributes": {"status": "in-progress"}}}))
        status, _, err = self.run_main("--timeout", "60", path)
        self.assertEqual(status, 2)
        self.assertIn("not finished", err)

    def test_unpaced_polling_still_waits(self):
        path, sha = self.file("new.exe", b"new")
        self.vt.on("GET", f"/files/{sha}", NOT_FOUND)
        self.vt.on("POST", "/files", (200, {"data": {"id": "n"}}))
        queued = (200, {"data": {"attributes": {"status": "queued"}}})
        self.vt.on("GET", "/analyses/n", queued, (200, {"data": {"attributes": {"status": "completed", "results": {}}}}))
        self.assertEqual(self.run_main("--rate", "0", path)[0], 0)
        self.assertEqual(self.vt.sleeps, [15])

    def test_max_and_outputs(self):
        clean, clean_sha = self.file("clean.exe", b"clean")
        dirty, dirty_sha = self.file("dirty.exe", b"dirty")
        self.vt.on("GET", f"/files/{clean_sha}", known(verdicts(Bkav=("undetected", None), Avast=("harmless", None))))
        self.vt.on("GET", f"/files/{dirty_sha}", known(REPORT))
        out_json = os.path.join(self.folder.name, "vt.json")
        out_md = os.path.join(self.folder.name, "vt.md")
        status, out, err = self.run_main("--max", "0", "--json", out_json, "--markdown", out_md,
                                         "--label", "v0.1.3", "--label", "v0.1.4", clean, dirty)
        self.assertEqual(status, 1)
        self.assertIn("v0.1.4", err)
        self.assertEqual(self.run_main("--max", "1", clean, dirty)[0], 0)
        # matrix: one row per engine that flagged any file, one column per file
        matrix = out[out.index("engine"):]
        bkav = next(line for line in matrix.splitlines() if line.startswith("Bkav"))
        self.assertEqual(bkav.split()[1:], ["-", "W32.AIDetectMalware"])
        self.assertIn("SecureAge", matrix)
        self.assertNotIn("Kaspersky", matrix)
        with open(out_json, encoding="utf-8") as handle:
            text = handle.read()
        data = json.loads(text)
        self.assertEqual([(e["label"], e["detections"], e["total"]) for e in data], [("v0.1.3", 0, 2), ("v0.1.4", 1, 4)])
        self.assertEqual(data[1]["flagged"], {"Bkav": "W32.AIDetectMalware"})
        with open(out_md, encoding="utf-8") as handle:
            markdown = handle.read()
        self.assertIn(f"[v0.1.4]({vt_check.GUI}{dirty_sha})", markdown)
        self.assertIn("| Bkav | - | W32.AIDetectMalware |", markdown)
        self.assertNotIn(KEY, text + markdown)

    def test_unexpected_answer_exits_2(self):
        # Not 1, which the release step reads as "too many detections".
        path, sha = self.file("new.exe", b"odd")
        self.vt.on("GET", f"/files/{sha}", NOT_FOUND)
        self.vt.on("POST", "/files", (200, {"data": {"type": "analysis"}}))
        status, _, err = self.run_main(path)
        self.assertEqual(status, 2)
        self.assertIn("unexpected answer", err)

    def test_missing_analysis_exits_2(self):
        path, sha = self.file("new.exe", b"lost")
        self.vt.on("GET", f"/files/{sha}", NOT_FOUND)
        self.vt.on("POST", "/files", (200, {"data": {"id": "lost"}}))
        self.vt.on("GET", "/analyses/lost", NOT_FOUND)
        status, _, err = self.run_main(path)
        self.assertEqual(status, 2)
        self.assertIn("not found", err)

    def test_network_errors_do_not_quote_the_request(self):
        # As http.client does for a header value it cannot send.
        def urlopen(request, timeout):
            raise ValueError(f"Invalid header value {request.get_header('X-apikey')!r}")
        original = vt_check.urllib.request.urlopen
        vt_check.urllib.request.urlopen = urlopen
        self.addCleanup(setattr, vt_check.urllib.request, "urlopen", original)
        with self.assertRaises(vt_check.VTError) as caught:
            vt_check.urllib_transport("GET", vt_check.API + "/files/x", {"x-apikey": KEY}, None)
        self.assertNotIn(KEY, str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)

    def test_too_many_labels(self):
        path, _ = self.file("a.exe", b"a")
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            vt_check.main(["--label", "a", "--label", "b", path], client_factory=self.vt.factory,
                          environ={"VT_API_KEY": KEY}, stdout=io.StringIO())


class KeyTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        saved = {name: os.environ.get(name) for name in ("HOME", "USERPROFILE")}
        for name in saved:
            os.environ[name] = self.home.name
        self.addCleanup(lambda: [os.environ.pop(n, None) if v is None else os.environ.__setitem__(n, v)
                                 for n, v in saved.items()])

    def test_environment_first(self):
        self.assertEqual(vt_check.load_key({"VT_API_KEY": " k1 \n"})[0], "k1")

    def test_file_second(self):
        folder = os.path.join(self.home.name, ".config", "yfm")
        os.makedirs(folder)
        with open(os.path.join(folder, "vt_api_key"), "w") as handle:
            handle.write(KEY + "\n")
        key, source = vt_check.load_key({})
        self.assertEqual(key, KEY)
        self.assertNotIn(KEY, source)

    def test_odd_key_is_refused_without_showing_it(self):
        for key in ("abc\ndef-" + KEY, KEY + "é", "two " + KEY):
            err = io.StringIO()
            with redirect_stderr(err):
                status = vt_check.main([__file__], environ={"VT_API_KEY": key}, stdout=io.StringIO())
            self.assertEqual(status, 2)
            self.assertIn("odd characters", err.getvalue())
            self.assertNotIn(KEY, err.getvalue())

    def test_missing_key_exits_2(self):
        err = io.StringIO()
        with redirect_stderr(err):
            status = vt_check.main([__file__], environ={}, stdout=io.StringIO())
        self.assertEqual(status, 2)
        self.assertIn("no API key", err.getvalue())


if __name__ == "__main__":
    unittest.main()
