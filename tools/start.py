#!/usr/bin/env python3
"""Session start in one call (replaces inbox_state + next_job + stats + claims as separate commands).

  python tools/start.py [--limit 3]

Prints at most ~8 lines: inbox freshness, internship counts, open claims, queued items, next jobs (one line each).
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import tracker  # noqa: E402


def run(*args):
    r = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout.strip()


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    limit = argv[argv.index("--limit") + 1] if "--limit" in argv else "3"
    print("inbox:", (run("tools/inbox_state.py", "status").splitlines() or ["?"])[0][:110])
    h, recs, _, _ = tracker.load()
    c = Counter(r[6] for r in recs[1:] if len(r) > 6 and r[4] == "internship")
    sent = sum(v for k, v in c.items() if k not in ("drafted", "withdrawn"))
    print(f"internships: {sent} sent ({c['applied']} applied, {c['interview']} interview, {c['rejected']} rejected), "
          f"{c['drafted']} drafted not sent")
    claims = ROOT / "trackers" / "session_claims.md"
    if claims.exists():
        live = [l.strip()[:100] for l in claims.read_text(encoding="utf-8").splitlines() if "running" in l]
        print(f"claims running: {len(live)}" + (" | " + " || ".join(live[-2:]) if live else ""))
    q = ROOT / "documents" / "manual_apply_queue.md"
    if q.exists():
        open_q = [l for l in q.read_text(encoding="utf-8").splitlines() if l.startswith("- ") and "[DONE" not in l]
        print(f"manual queue: {len(open_q)} open")
    try:
        jobs = json.loads(run("tools/next_job.py", "--limit", limit) or "[]")
    except ValueError:
        jobs = []
    for j in jobs:
        print(f"next: {j.get('score')} | {j.get('company', '')[:28]} | {j.get('title', '')[:70]} | {j.get('url', '')}")
    if not jobs:
        print("next: none ranked >= 60 -> " + run("tools/next_job.py", "--count").replace("\n", " ")[:120])


if __name__ == "__main__":
    main(sys.argv[1:])
