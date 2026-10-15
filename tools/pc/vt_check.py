#!/usr/bin/env python3
"""Look files up on VirusTotal (API v3) and show which engines flag them.

For each file: its SHA-256 is looked up (GET /files/<sha256>). A file
VirusTotal has never seen, or any file with --reanalyze, is uploaded and the
analysis is polled until it completes. --lookup-only never uploads.

    python tools/pc/vt_check.py --lookup-only old.exe
    python tools/pc/vt_check.py --label master --label av a.exe b.exe
    python tools/pc/vt_check.py --max 0 --json vt.json --markdown vt.md dist/*.exe

Uploads are shared with antivirus vendors: only upload builds that are, or
will be, public. The API key comes from the VT_API_KEY environment variable,
else from ~/.config/yfm/vt_api_key (%USERPROFILE%/.config/yfm/vt_api_key).
It is never printed. The free tier allows 4 requests a minute and 500 a day;
--rate spaces requests for that (notes/pc-release.md, "VirusTotal").

Detections count the engines whose verdict is "malicious", out of those that
gave any verdict (malicious, suspicious, undetected, harmless), as the web
page does. "Suspicious" verdicts are listed apart, marked (suspicious).

Exit status: 0 fine, 1 a file has more than --max detections, 2 an error
(no key, network, quota, an analysis that did not finish in --timeout).
"""
import argparse
import hashlib
import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

API = "https://www.virustotal.com/api/v3"
GUI = "https://www.virustotal.com/gui/file/"
KEY_FILE = os.path.join("~", ".config", "yfm", "vt_api_key")
DIRECT_UPLOAD_LIMIT = 32 * 1024 * 1024   # larger files go through /files/upload_url
VERDICTS = ("malicious", "suspicious", "undetected", "harmless")


class VTError(Exception):
    pass


def load_key(environ=os.environ):
    """(key, where it came from). The key itself is never shown anywhere."""
    key = environ.get("VT_API_KEY", "").strip()
    source = "the VT_API_KEY environment variable"
    if not key:
        path = os.path.expanduser(KEY_FILE)
        try:
            with open(path, encoding="utf-8") as handle:
                key = handle.read().strip()
        except (OSError, ValueError):
            key = ""
        source = KEY_FILE.replace(os.sep, "/")
    if not key:
        raise VTError(f"no API key: set VT_API_KEY or write it to {KEY_FILE}")
    # A header value with a line break or a non-Latin-1 character makes
    # http.client raise an error that quotes it: refuse such a key first.
    if not (key.isascii() and key.isprintable()) or any(c.isspace() for c in key):
        raise VTError(f"the API key in {source} has spaces, line breaks or other odd characters")
    return key, source


def urllib_transport(method, url, headers, body, timeout=300):
    """(status, body bytes). HTTP errors are answers too, not exceptions."""
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()
    except (urllib.error.URLError, OSError) as error:
        # Only the reason: the URL may be a signed upload URL.
        raise VTError(f"network error: {getattr(error, 'reason', error)}") from None
    except (http.client.HTTPException, ValueError) as error:
        # Only the kind: these may quote a header (the key) or the URL.
        raise VTError(f"network error: {type(error).__name__}") from None


class Client:
    """VirusTotal API v3 with the free tier's pace. transport, sleep and
    clock are replaceable so the tests run without a network or waiting."""

    def __init__(self, key, transport=urllib_transport, sleep=time.sleep, clock=time.monotonic,
                 per_minute=4, per_day=500, retries=4, backoff=60, poll=15, log=None):
        self._key = key
        self.transport, self.sleep, self.clock = transport, sleep, clock
        self.interval = 60.0 / per_minute if per_minute else 0.0
        self.per_day, self.retries, self.backoff, self.poll = per_day, retries, backoff, poll
        self.requests = 0
        self._last = None
        self.log = log or (lambda text: print(text, file=sys.stderr, flush=True))

    def _pace(self):
        if self.requests >= self.per_day:
            raise VTError(f"daily request budget of {self.per_day} used up")
        if self._last is not None and self.interval:
            wait = self._last + self.interval - self.clock()
            if wait > 0:
                self.sleep(wait)
        self._last = self.clock()
        self.requests += 1

    def request(self, method, url, body=None, content_type=None, what="request"):
        """(status, decoded JSON or None) for 200 and 404; raises otherwise.
        A 429 (too many requests / quota) or a 5xx is retried with a growing
        wait."""
        headers = {"x-apikey": self._key, "accept": "application/json"}
        if content_type:
            headers["content-type"] = content_type
        full = url if url.startswith("http") else API + url
        for attempt in range(self.retries + 1):
            self._pace()
            status, data = self.transport(method, full, headers, body)
            if (status == 429 or status >= 500) and attempt < self.retries:
                wait = self.backoff * 2 ** attempt
                reason = "rate limited" if status == 429 else "server error"
                self.log(f"vt_check: {what}: {reason} (HTTP {status}), waiting {wait} s")
                self.sleep(wait)
                continue
            break
        try:
            parsed = json.loads(data) if data else None
        except ValueError:
            parsed = None
        if status in (200, 404):
            return status, parsed
        detail = ""
        if isinstance(parsed, dict) and isinstance(parsed.get("error"), dict):
            detail = f": {parsed['error'].get('code', '')} {parsed['error'].get('message', '')}".rstrip()
        raise VTError(f"{what}: HTTP {status}{detail}")

    def file_report(self, sha256):
        status, data = self.request("GET", f"/files/{sha256}", what="lookup")
        return data["data"] if status == 200 else None

    def upload(self, name, content, direct_limit=DIRECT_UPLOAD_LIMIT):
        url = "/files"
        if len(content) > direct_limit:
            status, data = self.request("GET", "/files/upload_url", what="upload URL")
            url = data["data"]
        boundary = uuid.uuid4().hex
        body = b"".join([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="file"; filename="{os.path.basename(name)}"\r\n'.encode(),
            b"Content-Type: application/octet-stream\r\n\r\n", content,
            f"\r\n--{boundary}--\r\n".encode()])
        status, data = self.request("POST", url, body, f"multipart/form-data; boundary={boundary}",
                                    what="upload")
        if status != 200:
            raise VTError(f"upload: HTTP {status}")
        return data["data"]["id"]

    def wait_analysis(self, analysis, timeout):
        start = self.clock()
        while True:
            status, data = self.request("GET", f"/analyses/{analysis}", what="analysis")
            if status == 404:
                raise VTError(f"analysis {analysis} not found")
            if data["data"]["attributes"].get("status") == "completed":
                return data["data"]
            if self.clock() - start > timeout:
                raise VTError(f"analysis not finished after {timeout} s")
            # The pace between requests is the poll interval; without one
            # (--rate 0, a paid key) wait here instead.
            if self.poll > self.interval:
                self.sleep(self.poll - self.interval)


def summarize(results):
    """(detections, total, {engine: label}, {engine: label} suspicious)."""
    flagged, suspicious = {}, {}
    total = 0
    for engine, verdict in sorted((results or {}).items()):
        category = verdict.get("category")
        if category not in VERDICTS:
            continue
        total += 1
        label = verdict.get("result") or category
        if category == "malicious":
            flagged[engine] = label
        elif category == "suspicious":
            suspicious[engine] = label
    return len(flagged), total, flagged, suspicious


def check_file(client, path, label, lookup_only=False, reanalyze=False, timeout=1200,
               direct_limit=DIRECT_UPLOAD_LIMIT):
    with open(path, "rb") as handle:
        content = handle.read()
    sha256 = hashlib.sha256(content).hexdigest()
    entry = {"file": path, "label": label, "sha256": sha256, "size": len(content), "link": GUI + sha256}
    report = client.file_report(sha256)
    if report is not None and not reanalyze:
        attributes = report.get("attributes", {})
        results, source = attributes.get("last_analysis_results"), "lookup"
        stamp = attributes.get("last_analysis_date")
    elif lookup_only:
        entry.update(status="unknown")   # never seen by VirusTotal
        return entry
    else:
        client.log(f"vt_check: {label}: uploading {len(content)} bytes")
        analysis = client.upload(path, content, direct_limit)
        client.log(f"vt_check: {label}: waiting for the analysis")
        done = client.wait_analysis(analysis, timeout)
        results, source = done["attributes"].get("results"), "uploaded"
        stamp = done["attributes"].get("date")
    detections, total, flagged, suspicious = summarize(results)
    entry.update(status=source, detections=detections, total=total, flagged=flagged,
                 suspicious=suspicious,
                 analysis_date=time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(stamp)) if stamp else None)
    return entry


def score(entry):
    return f"{entry['detections']}/{entry['total']}" if "detections" in entry else entry["status"]


def engines(entries):
    names = set()
    for entry in entries:
        names.update(entry.get("flagged", {}), entry.get("suspicious", {}))
    return sorted(names, key=str.lower)


def cell(entry, engine, width=None):
    if "detections" not in entry:
        return "?"
    label = entry["flagged"].get(engine)
    if label is None and engine in entry["suspicious"]:
        label = entry["suspicious"][engine] + " (suspicious)"
    label = label or "-"
    return label if width is None or len(label) <= width else label[:width - 1] + "~"


def text_report(entries, width=28):
    lines = []
    name_width = max([len("file")] + [len(e["label"]) for e in entries])
    lines.append(f"{'file':<{name_width}}  sha256        detections  when")
    for entry in entries:
        lines.append(f"{entry['label']:<{name_width}}  {entry['sha256'][:12]}  {score(entry):<10}  "
                     f"{entry.get('analysis_date') or ''} ({entry['status']})".rstrip())
        for engine, label in entry.get("flagged", {}).items():
            lines.append(f"{'':<{name_width}}    {engine}: {label}")
        for engine, label in entry.get("suspicious", {}).items():
            lines.append(f"{'':<{name_width}}    {engine}: {label} (suspicious)")
    rows = engines(entries)
    if len(entries) > 1 and rows:
        lines.append("")
        engine_width = max(len("engine"), max(len(name) for name in rows))
        widths = [max(len(e["label"]), min(width, max(len(cell(e, r)) for r in rows))) for e in entries]
        lines.append("  ".join([f"{'engine':<{engine_width}}"] + [f"{e['label']:<{w}}" for e, w in zip(entries, widths)]).rstrip())
        for row in rows:
            lines.append("  ".join([f"{row:<{engine_width}}"] + [f"{cell(e, row, w):<{w}}" for e, w in zip(entries, widths)]).rstrip())
    lines.append("")
    for entry in entries:
        lines.append(f"{entry['label']}: {entry['link']}")
    return "\n".join(lines) + "\n"


def markdown_report(entries):
    def escape(text):
        return str(text).replace("|", "\\|")
    lines = ["| File | SHA-256 | Detections | Flagged by |", "|---|---|---|---|"]
    for entry in entries:
        found = [f"{engine}: {label}" for engine, label in entry.get("flagged", {}).items()]
        found += [f"{engine}: {label} (suspicious)" for engine, label in entry.get("suspicious", {}).items()]
        lines.append(f"| [{escape(entry['label'])}]({entry['link']}) | `{entry['sha256'][:12]}` | "
                     f"{score(entry)} | {escape('; '.join(found)) or '-'} |")
    rows = engines(entries)
    if len(entries) > 1 and rows:
        lines += ["", "| Engine | " + " | ".join(escape(e["label"]) for e in entries) + " |",
                  "|---" * (len(entries) + 1) + "|"]
        for row in rows:
            lines.append(f"| {escape(row)} | " + " | ".join(escape(cell(e, row)) for e in entries) + " |")
    return "\n".join(lines) + "\n"


def main(argv=None, client_factory=Client, environ=os.environ, stdout=sys.stdout):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+", help="files to check")
    parser.add_argument("--label", action="append", default=[],
                        help="readable name for the files, in order: the first --label names the first file")
    parser.add_argument("--lookup-only", action="store_true", help="never upload; unknown files stay unknown")
    parser.add_argument("--reanalyze", action="store_true", help="upload again even if VirusTotal knows the file")
    parser.add_argument("--max", type=int, help="exit 1 if a file has more than this many detections")
    parser.add_argument("--json", metavar="OUT", help="write the results as JSON")
    parser.add_argument("--markdown", metavar="OUT", help="write a Markdown table (for a job summary)")
    parser.add_argument("--rate", type=float, default=4, help="requests a minute (free tier: 4; 0: no pacing)")
    parser.add_argument("--daily", type=int, default=500, help="requests allowed in this run (free tier: 500 a day)")
    parser.add_argument("--timeout", type=int, default=1200, help="seconds to wait for each analysis")
    args = parser.parse_args(argv)
    if len(args.label) > len(args.files):
        parser.error("more --label than files")
    if args.lookup_only and args.reanalyze:
        parser.error("--lookup-only and --reanalyze exclude each other")
    labels = args.label + [os.path.basename(path) for path in args.files[len(args.label):]]
    try:
        key, source = load_key(environ)
        client = client_factory(key, per_minute=args.rate, per_day=args.daily)
        client.log(f"vt_check: API key from {source}")
        entries = [check_file(client, path, label, args.lookup_only, args.reanalyze, args.timeout)
                   for path, label in zip(args.files, labels)]
    except (VTError, OSError) as error:
        print(f"vt_check: {error}", file=sys.stderr)
        return 2
    except (KeyError, TypeError, AttributeError, IndexError) as error:
        # An answer shaped unlike the API's documentation. Not exit 1, which
        # means "too many detections"; only the kind, never a request's parts.
        print(f"vt_check: unexpected answer from VirusTotal ({type(error).__name__})", file=sys.stderr)
        return 2
    stdout.write(text_report(entries))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(entries, handle, indent=2)
            handle.write("\n")
    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8") as handle:
            handle.write(markdown_report(entries))
    over = [e["label"] for e in entries if args.max is not None and e.get("detections", 0) > args.max]
    if over:
        print(f"vt_check: more than {args.max} detections: {', '.join(over)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
