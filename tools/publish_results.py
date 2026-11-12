"""Refresh the public results: results/*.csv and the summary table in README.md.

Reads the private tracker (job_search_tracker.csv, gitignored) and writes one CSV per job type
with only non-personal columns. Recruiter contacts, notes and document paths are dropped, and
account e-mails are stripped from the channel. Then it rewrites the README block between
<!-- results:start --> and <!-- results:end -->.

  python tools/publish_results.py            # rewrite results/ and README
  python tools/publish_results.py --check    # print the table only
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TRACKER = REPO / "job_search_tracker.csv"
OUT = REPO / "results"
README = REPO / "README.md"

TRACKS = [  # role_type, file, title
    ("internship", "internships.csv", "Internships (main goal)"),
    ("student_job", "student_jobs.csv", "Student jobs (part-time, max 20 h/week)"),
    ("part_time", "part_time_jobs.csv", "Other part-time jobs"),
    ("seasonal", "seasonal_jobs.csv", "Seasonal jobs"),
    ("full_time", "full_time_jobs.csv", "Full-time jobs (track closed)"),
]
COLUMNS = ["date", "company", "sector", "role", "channel", "status", "deadline"]
PERSONAL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|\+?\d[\d .]{8,}\d")


def channel(raw: str) -> str:
    c = re.sub(r"\s*\([^)]*@[^)]*\)", "", raw or "").strip().lower()
    if c.startswith(("company site", "company_site")):
        return "company site"
    if "workday" in c:
        return "workday"
    if c.startswith("email"):
        return "email"
    return c or "unknown"


def clean(text: str) -> str:
    text = PERSONAL.sub("", text or "")
    # "(second interview requested with Jane Doe)" -> "(second interview requested)"
    return re.sub(r"\s+with [A-Z][\w'-]+(?: [A-Z][\w'-]+)+(?=\))", "", text).strip()


def role_type(row: dict) -> str:
    """Same mapping as tools/split_tracker.py, for rows whose role_type was left empty."""
    rt = (row.get("role_type") or "").strip().lower().replace("-", "_")
    if rt in {t[0] for t in TRACKS}:
        return rt
    title = (row.get("role") or "").lower()
    if re.search(r"\b(stage|stagiaire|intern|internship|pfe)\b", title) and "alternance" not in title:
        return "internship"
    if rt == "part_time":
        return "student_job" if re.search(r"étudiant|etudiant|student", title + (row.get("notes") or "").lower()) else "part_time"
    return rt or "full_time"


def build() -> str:
    rows = list(csv.DictReader(TRACKER.open(encoding="utf-8")))
    OUT.mkdir(exist_ok=True)
    lines = ["| Track | Sent | Interviews | Rejections | Withdrawn | Drafted, not sent | Period | Data |",
             "|---|---:|---:|---:|---:|---:|---|---|"]
    channels = []
    for rt, fname, title in TRACKS:
        sel = sorted((r for r in rows if role_type(r) == rt), key=lambda r: r["date"], reverse=True)
        with (OUT / fname).open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(COLUMNS)
            for r in sel:
                w.writerow([r["date"], clean(r["company"]), clean(r["sector"]), clean(r["role"]),
                            channel(r["channel"]), r["status"], r.get("deadline", "")])
        if not sel:
            continue
        st = collections.Counter(r["status"] for r in sel)
        dash = lambda n: str(n) if n else "–"
        lines.append(f"| {title} | {len(sel) - st['drafted']} | {dash(st['interview'])} | {dash(st['rejected'])} | "
                     f"{dash(st['withdrawn'])} | {dash(st['drafted'])} | {min(r['date'] for r in sel)} → "
                     f"{max(r['date'] for r in sel)} | [`{fname}`](results/{fname}) |")
        top = collections.Counter(channel(r["channel"]) for r in sel if r["status"] != "drafted").most_common(4)
        channels.append(f"- {title}: " + ", ".join(f"{k} {v}" for k, v in top))
    return "\n".join(lines + ["", "**Where the applications went** (sent only, top channels):", ""] + channels)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="print the table, change nothing")
    args = ap.parse_args()
    if not TRACKER.exists():
        print(f"missing {TRACKER.name}", file=sys.stderr)
        return 1
    table = build()
    if args.check:
        sys.stdout.reconfigure(encoding="utf-8")
        print(table)
        return 0
    text = README.read_text(encoding="utf-8")
    start, end = "<!-- results:start -->", "<!-- results:end -->"
    if start not in text or end not in text:
        print("README has no results markers", file=sys.stderr)
        return 1
    head, rest = text.split(start, 1)
    _, tail = rest.split(end, 1)
    today = dt.date.today().isoformat()
    head = re.sub(r"## My results so far \(updated [\d-]+\)", f"## My results so far (updated {today})", head)
    README.write_text(f"{head}{start}\n{table}\n{end}{tail}", encoding="utf-8", newline="\n")
    print(f"results/ and README updated ({today})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
