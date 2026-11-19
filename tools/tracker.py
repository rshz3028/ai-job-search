#!/usr/bin/env python3
"""Compact tracker CLI: the token-cheap way to read and edit job_search_tracker.csv.

Never `cat`, `grep` or `sed` the 340 KB CSV. Every command prints one short line per row.

  python tools/tracker.py find <text> [--status S] [--type T] [--since YYYY-MM-DD] [--limit N] [--notes]
  python tools/tracker.py company <name>            # count + list for the 3-per-company cap
  python tools/tracker.py has <company> <role>       # exit 0 + row if already applied (duplicate check)
  python tools/tracker.py add key=value ...          # append one row (date defaults to today)
  python tools/tracker.py set <row> key=value ... [note="text"]   # edit one row in place, note is appended dated
  python tools/tracker.py stats                      # counts by role_type x status

<row> is the number printed in the first column (the CSV record number, header = 0).
`set` rewrites only that record's physical lines, so the rest of the file stays byte-identical.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "job_search_tracker.csv"
STATUSES = {"drafted", "applied", "interview", "offer", "hired", "rejected", "no_response", "offer_declined", "withdrawn"}
ROLE_TYPES = {"internship", "student_job", "part_time", "full_time", "seasonal", ""}
STOP = {"stage", "stagiaire", "intern", "internship", "h/f", "f/h", "the", "and", "des", "les", "pour", "une", "with"}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9+#/ ]+", " ", s).strip()


def load():
    """Return (header, records, text, spans); spans[i] = (first_line, last_line) of record i, 0-based."""
    text = CSV_PATH.read_text(encoding="utf-8")
    reader = csv.reader(io.StringIO(text))
    records, spans, prev = [], [], 0
    for rec in reader:
        records.append(rec)
        spans.append((prev, reader.line_num - 1))
        prev = reader.line_num
    return records[0], records, text, spans


def short(h, n, r, notes=False):
    g = dict(zip(h, r + [""] * (len(h) - len(r))))
    line = f"{n:>4} | {g['date']} | {g['company'][:28]} | {g['role'][:60]} | {g['role_type']} | {g['status']} | {g['fit_rating']}"
    if notes:
        line += " | " + g["notes"][:140].replace("\n", " ")
    return line


def opt(args, name, default=None):
    if name in args:
        i = args.index(name)
        v = args[i + 1]
        del args[i:i + 2]
        return v
    return default


def kv(args):
    out = {}
    for a in args:
        if "=" not in a:
            sys.exit(f"expected key=value, got {a!r}")
        k, v = a.split("=", 1)
        out[k.strip()] = v
    return out


def cmd_find(args):
    notes = "--notes" in args
    args = [a for a in args if a != "--notes"]
    status, rtype, since = opt(args, "--status"), opt(args, "--type"), opt(args, "--since")
    limit = int(opt(args, "--limit", "25"))
    q = norm(" ".join(args))
    h, recs, _, _ = load()
    hits = []
    for n, r in enumerate(recs[1:], 1):
        g = dict(zip(h, r + [""] * (len(h) - len(r))))
        if q and q not in norm(g["company"] + " " + g["role"] + " " + g["source"] + " " + g["notes"][:200]):
            continue
        if status and g["status"] != status:
            continue
        if rtype and g["role_type"] != rtype:
            continue
        if since and g["date"] < since:
            continue
        hits.append(short(h, n, r, notes))
    for line in hits[-limit:]:
        print(line)
    print(f"({len(hits)} match{'es' if len(hits) != 1 else ''}{', last ' + str(limit) + ' shown' if len(hits) > limit else ''})")


def cmd_company(args):
    q = norm(" ".join(args))
    h, recs, _, _ = load()
    rows = [(n, r) for n, r in enumerate(recs[1:], 1) if q and q in norm(r[1])]
    for n, r in rows:
        print(short(h, n, r))
    sent = sum(1 for _, r in rows if len(r) > 6 and r[6] not in ("drafted", "withdrawn"))
    print(f"{len(rows)} rows, {sent} sent")


def cmd_has(args):
    if len(args) < 2:
        sys.exit("usage: has <company> <role>")
    co, role = norm(args[0]), set(norm(" ".join(args[1:])).split()) - STOP
    h, recs, _, _ = load()
    for n, r in enumerate(recs[1:], 1):
        if co[:8] and co[:8] in norm(r[1]):
            words = set(norm(r[3]).split()) - STOP
            if role and len(role & words) / max(1, len(role)) >= 0.6:
                print(short(h, n, r))
                sys.exit(0)
    print("no match")
    sys.exit(1)


def check(g):
    if g.get("status") and g["status"] not in STATUSES:
        sys.exit(f"bad status {g['status']!r}; use one of {sorted(STATUSES)}")
    if g.get("role_type", "") not in ROLE_TYPES:
        sys.exit(f"bad role_type {g['role_type']!r}; use one of {sorted(ROLE_TYPES - {''})}")


def serialize(row):
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerow(row)
    return buf.getvalue()


def cmd_add(args):
    h, recs, text, _ = load()
    g = kv(args)
    unknown = set(g) - set(h)
    if unknown:
        sys.exit(f"unknown columns {sorted(unknown)}")
    g.setdefault("date", dt.date.today().isoformat())
    if not g.get("company") or not g.get("role"):
        sys.exit("company= and role= are required")
    check(g)
    row = [g.get(c, "") for c in h]
    with CSV_PATH.open("a", encoding="utf-8", newline="") as f:
        if not text.endswith("\n"):
            f.write("\n")
        f.write(serialize(row))
    print("added", short(h, len(recs), row))


def cmd_set(args):
    if not args or not args[0].isdigit():
        sys.exit("usage: set <row> key=value ... [note=text]")
    n = int(args[0])
    h, recs, text, spans = load()
    if not 1 <= n < len(recs):
        sys.exit(f"row {n} out of range 1..{len(recs) - 1}")
    g = kv(args[1:])
    note = g.pop("note", None)
    unknown = set(g) - set(h)
    if unknown:
        sys.exit(f"unknown columns {sorted(unknown)}")
    check(g)
    row = recs[n] + [""] * (len(h) - len(recs[n]))
    for k, v in g.items():
        row[h.index(k)] = v
    if note:
        i = h.index("notes")
        stamp = f"{dt.date.today().isoformat()} {note}"
        row[i] = f"{row[i]}; {stamp}" if row[i] else stamp
    lines = text.splitlines(keepends=True)
    a, b = spans[n]
    lines[a:b + 1] = [serialize(row)]
    CSV_PATH.write_text("".join(lines), encoding="utf-8", newline="")
    print("updated", short(h, n, row))


def cmd_stats(_):
    h, recs, _, _ = load()
    c = Counter((r[4] if len(r) > 4 else "", r[6] if len(r) > 6 else "") for r in recs[1:])
    for t in sorted({k[0] for k in c}):
        parts = ", ".join(f"{s} {v}" for (tt, s), v in sorted(c.items()) if tt == t)
        print(f"{t or '(none)'}: {parts}")
    print(f"total {len(recs) - 1}")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return
    cmd, args = sys.argv[1], sys.argv[2:]
    {"find": cmd_find, "company": cmd_company, "has": cmd_has, "add": cmd_add, "set": cmd_set, "stats": cmd_stats}.get(
        cmd, lambda _: sys.exit(f"unknown command {cmd}"))(args)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
