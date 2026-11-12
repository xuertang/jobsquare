#!/usr/bin/env python3
"""job-ops agent CLI — Claude Code integration (career-ops style, Claude-only).

Launcher:
  python agent.py                    open an interactive Claude session here
  python agent.py scan               headless `/job-ops scan` (new jobs since last scan)
  python agent.py scan -i            interactive session pre-loaded with /job-ops scan
  python agent.py <mode> [words...]  headless `/job-ops <mode> ...` for any router mode
                                     (tokens after the mode words pass through to claude)

Deterministic data helpers — used by mode files, no LLM involved:
  python agent.py db-new  [--since-days N] [--limit N] [--posted-days N]
                          [--dated-only] [-c sources.yaml]
      JSON dump of listings first seen after the last-scan marker.
      First run (no marker yet): the last N days (default 7).
      --posted-days N keeps only jobs whose posted_at falls within the last
      N days; jobs with no parseable date are KEPT (they'd otherwise vanish
      — many sources never emit dates) unless --dated-only is set.
      Never advances the marker — that is db-mark's job.
  python agent.py db-mark <watermark> | --now  [-c sources.yaml]
      Advance the marker. Pass the `watermark` field from the db-new dump you
      just processed (NOT --now) so rows landing mid-analysis aren't skipped.
  python agent.py pdf-render <in.html> [out.pdf] [--format letter|a4]
                            [--max-pages N] [--clean]
      ATS-normalize the HTML (smart quotes, dashes, bullets -> ASCII) and
      print it to PDF via headless Chrome/Chromium (CHROME_PATH overrides
      discovery). --max-pages N exits non-zero (3) if the PDF is longer than
      N pages, keeping the source so the caller can tighten and re-render.
      --clean removes the source HTML on success (PDF is the only artifact).
      Used by modes/pdf.md.
  python agent.py report-num  [-c sources.yaml]
      Atomically claim the next report id (prints zero-padded, e.g. 042).
      Counter lives in jobs.db meta, so ids survive a reports/ cleanup.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from itertools import groupby
from pathlib import Path

from models import parse_posted_at
from pipeline import load_config
from store import Store

_BASE = Path(__file__).resolve().parent          # apps/job-ops
DEFAULT_CONFIG = str(_BASE / "sources.yaml")     # cwd-independent default

MARK_KEY = "last_scan"
FIRST_RUN_DAYS = 7
DUMP_LIMIT = 200
DUMP_FIELDS = ("key", "company", "title", "url", "location", "department",
               "salary_range", "posted_at", "first_seen")

# Tools the headless scan needs: the db helpers via Bash, file reads, and
# appending to data/pipeline.md. acceptEdits auto-approves the file writes.
CLAUDE_HEADLESS_FLAGS = [
    "--permission-mode", "acceptEdits",
    "--allowedTools",
    "Bash(python:*),Bash(python3:*),Read,Grep,Glob,Edit,Write,WebFetch,WebSearch",
]


def _store(config: str) -> Store:
    return Store(load_config(config)["db"])


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- deterministic helpers -------------------------------------------------

def cmd_db_new(argv: list[str]) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="agent.py db-new")
    p.add_argument("-c", "--config", default=DEFAULT_CONFIG)
    p.add_argument("--since-days", type=int, default=FIRST_RUN_DAYS,
                   help="first-run window when no marker exists yet")
    p.add_argument("--limit", type=int, default=DUMP_LIMIT)
    p.add_argument("--posted-days", type=int, default=None,
                   help="keep only jobs posted within the last N days "
                        "(undated jobs are kept unless --dated-only)")
    p.add_argument("--dated-only", action="store_true",
                   help="drop jobs with no parseable posted_at")
    a = p.parse_args(argv)

    with _store(a.config) as store:
        marker = store.get_meta(MARK_KEY)
        first_run = marker is None
        since = marker if marker else (
            datetime.now(timezone.utc) - timedelta(days=a.since_days)
        ).isoformat(timespec="seconds")
        rows = store.added_since(since)

    # Posted-at window. Filter BEFORE group-truncation so the limit applies
    # to what's actually dumped; rows in groups beyond the watermark that we
    # drop here simply re-filter (idempotently) on the next scan.
    dropped_old = undated_kept = undated_dropped = 0
    if a.posted_days is not None or a.dated_only:
        cut = (datetime.now(timezone.utc) - timedelta(days=a.posted_days)
               if a.posted_days is not None else None)
        kept = []
        for r in rows:
            dt = parse_posted_at(r["posted_at"] or "")
            if dt is None:
                if a.dated_only:
                    undated_dropped += 1
                else:
                    undated_kept += 1
                    kept.append(r)
            elif cut is None or dt >= cut:
                kept.append(r)
            else:
                dropped_old += 1
        rows = kept

    # Truncate only at first_seen group boundaries: one pipeline run stamps
    # every new row with the identical timestamp, and the next scan resumes
    # strictly *after* the watermark — splitting a group would lose its tail.
    jobs, truncated, watermark = [], False, since
    for ts, group in groupby(rows, key=lambda r: r["first_seen"]):
        g = list(group)
        if jobs and len(jobs) + len(g) > a.limit:
            truncated = True
            break
        jobs.extend(g)
        watermark = ts

    print(json.dumps({
        "since": since,
        "first_run": first_run,
        "posted_within_days": a.posted_days,
        "dated_only": a.dated_only,
        "dropped_old": dropped_old,
        "undated_kept": undated_kept,
        "undated_dropped": undated_dropped,
        "count": len(jobs),
        "total_new": len(rows),
        "truncated": truncated,
        "watermark": watermark,
        "jobs": [{f: r[f] for f in DUMP_FIELDS} for r in jobs],
    }, indent=2))
    return 0


def cmd_db_mark(argv: list[str]) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="agent.py db-mark")
    p.add_argument("watermark", nargs="?")
    p.add_argument("--now", action="store_true")
    p.add_argument("-c", "--config", default=DEFAULT_CONFIG)
    a = p.parse_args(argv)

    if a.now:
        wm = _iso_now()
    elif a.watermark:
        try:
            datetime.fromisoformat(a.watermark.replace("Z", "+00:00"))
        except ValueError:
            print(f"db-mark: not an ISO timestamp: {a.watermark!r}", file=sys.stderr)
            return 2
        wm = a.watermark
    else:
        print("db-mark: pass a watermark or --now", file=sys.stderr)
        return 2

    with _store(a.config) as store:
        store.set_meta(MARK_KEY, wm)
    print(f"scan marker -> {wm}")
    return 0


def cmd_report_num(argv: list[str]) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="agent.py report-num")
    p.add_argument("-c", "--config", default=DEFAULT_CONFIG)
    a = p.parse_args(argv)
    with _store(a.config) as store:
        print(f"{store.next_seq('report_seq'):03d}")
    return 0


# --- pdf rendering (modes/pdf.md) -------------------------------------------
# Port of career-ops generate-pdf.mjs: ATS character normalization + headless
# Chromium print. Replacements apply to body text only — never inside tags,
# <style>, or <script>.

_ATS_RULES = [(re.compile(rx), repl, label) for rx, repl, label in (
    ("\u2014", "-", "em-dash"),
    ("\u2013", "-", "en-dash"),
    ("[\u201C-\u201F]", '"', "smart-double-quote"),
    ("[\u2018-\u201B]", "'", "smart-single-quote"),
    ("\u2026", "...", "ellipsis"),
    ("[\u200B-\u200D\u2060\uFEFF]", "", "zero-width"),
    ("\u00A0", " ", "nbsp"),
    ("\u2192", " to ", "right-arrow"),
    ("\u2190", " from ", "left-arrow"),
    ("[\u2191\u2193]", " ", "vert-arrow"),
    ("\u00B7", " | ", "middot"),
    ("\u2022", " | ", "bullet"),
    ("\u20AC", "EUR ", "euro"),
    ("\u00A3", "GBP ", "pound"),
)]

_CHROME_APPS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
)


def _chrome_bin() -> str:
    env = os.getenv("CHROME_PATH")
    if env and Path(env).exists():
        return env
    for name in ("google-chrome", "google-chrome-stable", "chromium",
                 "chromium-browser", "chrome"):
        if p := shutil.which(name):
            return p
    for p in _CHROME_APPS:
        if Path(p).exists():
            return p
    sys.exit("pdf-render: no Chrome/Chromium found — set CHROME_PATH")


def _normalize_ats(html: str) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}

    def fix(text: str) -> str:
        for rx, repl, label in _ATS_RULES:
            text, n = rx.subn(repl, text)
            if n:
                counts[label] = counts.get(label, 0) + n
        return text

    # Odd indices of a 1-group re.split are the captured blocks — skip them.
    parts = re.split(r"(<style\b.*?</style>|<script\b.*?</script>)",
                     html, flags=re.I | re.S)
    for i in range(0, len(parts), 2):
        segs = re.split(r"(<[^>]*>)", parts[i])
        for j in range(0, len(segs), 2):
            segs[j] = fix(segs[j])
        parts[i] = "".join(segs)
    return "".join(parts), counts


def cmd_pdf_render(argv: list[str]) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="agent.py pdf-render")
    p.add_argument("input", help="HTML file (usually a temp under output/)")
    p.add_argument("output", nargs="?", help="default: input with .pdf")
    p.add_argument("--format", choices=("letter", "a4"), default="letter")
    p.add_argument("--max-pages", type=int, default=None,
                   help="fail (exit 3) if the PDF exceeds N pages")
    p.add_argument("--clean", action="store_true",
                   help="delete the source HTML on success (PDF-only output)")
    a = p.parse_args(argv)

    src = Path(a.input)
    if not src.is_file():
        print(f"pdf-render: no such file: {src}", file=sys.stderr)
        return 2
    out = Path(a.output) if a.output else src.with_suffix(".pdf")
    out.parent.mkdir(parents=True, exist_ok=True)

    html, counts = _normalize_ats(src.read_text(encoding="utf-8"))
    page_css = f"<style>@page {{ size: {a.format}; margin: 0.6in; }}</style>"
    if re.search(r"</head>", html, re.I):       # last-in-cascade wins
        html = re.sub(r"</head>", page_css + "</head>", html, count=1, flags=re.I)
    else:
        html = page_css + html

    tmp = out.parent / f".{src.stem}.ats.html"
    tmp.write_text(html, encoding="utf-8")
    try:
        r = subprocess.run(
            [_chrome_bin(), "--headless=new", "--disable-gpu",
             "--no-pdf-header-footer", f"--print-to-pdf={out}",
             tmp.resolve().as_uri()],
            capture_output=True, text=True, timeout=120)
    finally:
        tmp.unlink(missing_ok=True)

    data = out.read_bytes() if out.is_file() else b""
    if not data.startswith(b"%PDF"):
        print("pdf-render: render failed", file=sys.stderr)
        if r.stderr:
            print(r.stderr[-800:], file=sys.stderr)
        return 1

    shown = ", ".join(f"{k}={v}" for k, v in counts.items()) or "none needed"
    pages = len(re.findall(rb"/Type\s*/Page(?!s)", data))
    print(f"ATS normalization: {shown}")
    print(f"PDF -> {out}  ({len(data) // 1024} KB, {pages or '?'} page(s))")

    # Enforce a page ceiling (only when we could actually count). Keep the
    # source HTML so the caller can trim and re-render.
    if a.max_pages is not None and pages > a.max_pages:
        print(f"pdf-render: {pages} pages exceeds --max-pages {a.max_pages} — "
              f"tighten content and re-render (kept {src})", file=sys.stderr)
        return 3

    if a.clean:
        src.unlink(missing_ok=True)
        print(f"removed intermediate HTML ({src.name})")
    return 0


# --- claude launcher ---------------------------------------------------------

def _claude() -> str:
    exe = shutil.which("claude")
    if not exe:
        sys.exit("claude CLI not found — install Claude Code first "
                 "(npm install -g @anthropic-ai/claude-code)")
    return exe


def run_claude(mode_words: list[str], interactive: bool, extra: list[str]) -> int:
    exe = _claude()
    prompt = ("/job-ops " + " ".join(mode_words)).strip()
    if interactive:
        os.execvp(exe, [exe, prompt] if mode_words else [exe])  # hand over TTY
    return subprocess.call([exe, "-p", prompt, *CLAUDE_HEADLESS_FLAGS, *extra])


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    if argv and argv[0] == "db-new":
        return cmd_db_new(argv[1:])
    if argv and argv[0] == "db-mark":
        return cmd_db_mark(argv[1:])
    if argv and argv[0] == "pdf-render":
        return cmd_pdf_render(argv[1:])
    if argv and argv[0] == "report-num":
        return cmd_report_num(argv[1:])

    interactive = not argv                      # bare `agent.py` -> REPL
    words = [t for t in argv if t not in ("-i", "--interactive")]
    if len(words) != len(argv):
        interactive = True
    # mode words end at the first flag; the rest passes through to claude
    mode_words, extra = words, []
    for i, t in enumerate(words):
        if t.startswith("-"):
            mode_words, extra = words[:i], words[i:]
            break
    return run_claude(mode_words, interactive, extra)


if __name__ == "__main__":
    raise SystemExit(main())
