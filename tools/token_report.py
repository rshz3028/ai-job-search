#!/usr/bin/env python3
"""Token use per Claude Code session and per application sent, from the local transcripts.

  python tools/token_report.py [--since YYYY-MM-DD] [--sources]

Reads ~/.claude/projects/<this project>/*.jsonl (main sessions) and <session>/subagents/*.jsonl (agents).
"processed" = input + cache_read + cache_write tokens: everything the model read, turn by turn. The whole
context is re-read on every turn, so processed tokens grow with context size x number of turns; that is
the number the token-efficiency work (docs/token_efficiency_report.md) targets.
Applications sent are tracker rows whose status is past `drafted`, counted by their tracker date, so the
per-day table divides that day's processed tokens by that day's applications.
--sources adds which tools filled the main context (approximate attribution of context growth).
"""
from __future__ import annotations

import collections
import csv
import glob
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJ = Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(ROOT))
SENT = {"applied", "interview", "offer", "hired", "rejected", "no_response", "no response", "offer_declined"}


def tool_key(name):
    if name.startswith("mcp__claude-in-chrome__"):
        return "browser"
    if name.startswith("mcp__claude_ai_Gmail__"):
        return "gmail"
    if name in ("Bash", "PowerShell"):
        return "shell"
    return name.split("__")[-1].lower()


def size(content):
    if isinstance(content, str):
        return len(content)
    n = 0
    for c in content or []:
        if isinstance(c, dict):
            n += len(c.get("text", "")) if c.get("type") == "text" else (6000 if c.get("type") == "image" else 500)
    return n


def scan(path, sources=None):
    seen, ctxs, tools, pending = {}, [], {}, []
    out_by_msg, first_ts, last_out = {}, None, 0
    for line in open(path, encoding="utf-8", errors="replace"):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        first_ts = first_ts or d.get("timestamp")
        m = d.get("message") or {}
        if d.get("type") == "assistant":
            u = m.get("usage") or {}
            mid = m.get("id")
            out_by_msg[mid] = max(out_by_msg.get(mid, 0), u.get("output_tokens") or 0)
            if mid and mid not in seen:
                ctx = (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)
                if ctx:
                    if sources is not None and ctxs and pending:
                        delta, tot = ctx - ctxs[-1] - last_out, sum(c for _, c in pending) or 1
                        if delta > 0:
                            for k, c in pending:
                                sources[k] += delta * c / tot
                    seen[mid] = ctx
                    ctxs.append(ctx)
                    pending = []
            last_out = u.get("output_tokens") or 0
            for c in m.get("content") or []:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    tools[c["id"]] = c.get("name", "")
        elif d.get("type") == "user" and isinstance(m.get("content"), list):
            for c in m["content"]:
                if isinstance(c, dict) and c.get("type") == "tool_result":
                    pending.append((tool_key(tools.get(c.get("tool_use_id"), "?")), max(1, size(c.get("content")))))
    return {"date": (first_ts or "")[:10], "turns": len(ctxs), "first": ctxs[0] if ctxs else 0,
            "avg": sum(ctxs) // len(ctxs) if ctxs else 0, "peak": max(ctxs) if ctxs else 0,
            "processed": sum(seen.values()), "output": sum(out_by_msg.values())}


def M(n):
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.0f}k"


def main(argv):
    since = argv[argv.index("--since") + 1] if "--since" in argv else ""
    sources = collections.Counter() if "--sources" in argv else None
    day = collections.Counter()
    print(f"{'session':9} {'date':10} {'turns':>5} {'start':>6} {'avg ctx':>7} {'peak':>6} {'processed':>9} {'agents':>6} {'agent proc':>10} {'output':>7}")
    for f in sorted(glob.glob(str(PROJ / "*.jsonl")), key=os.path.getmtime):
        s = scan(f, sources)
        if not s["turns"] or s["date"] < since:
            continue
        agents = [scan(a) for a in glob.glob(str(Path(f[:-6]) / "subagents" / "*.jsonl"))]
        ap, ao = sum(a["processed"] for a in agents), sum(a["output"] for a in agents)
        day[s["date"]] += s["processed"] + ap
        print(f"{Path(f).stem[:8]:9} {s['date']:10} {s['turns']:>5} {M(s['first']):>6} {M(s['avg']):>7} {M(s['peak']):>6} "
              f"{M(s['processed']):>9} {len(agents):>6} {M(ap):>10} {M(s['output'] + ao):>7}")
    sent = collections.Counter()
    with open(ROOT / "job_search_tracker.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("status") in SENT:
                sent[r.get("date", "")] += 1
    print(f"\n{'date':10} {'processed':>9} {'apps sent':>9} {'per app':>8}")
    tp = ta = 0
    for d in sorted(day):
        n = sent.get(d, 0)
        tp, ta = tp + day[d], ta + n
        print(f"{d:10} {M(day[d]):>9} {n:>9} {M(day[d] / n) if n else '-':>8}")
    if ta:
        print(f"{'all':10} {M(tp):>9} {ta:>9} {M(tp / ta):>8}")
    if sources:
        t = sum(sources.values()) or 1
        print("\nmain-context growth by source:", ", ".join(f"{k} {100 * v / t:.0f}%" for k, v in sources.most_common(8)))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main(sys.argv[1:])
