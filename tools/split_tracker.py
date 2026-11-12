"""Normalise role_type in job_search_tracker.csv and write one CSV per category.

The master tracker (job_search_tracker.csv) stays the single source of truth.
This script:
  1. normalises the role_type column to one of
     internship | student_job | part_time | full_time | seasonal
  2. rewrites the master in place (same 14 columns, same order)
  3. writes per-category views to trackers/:
       internships.csv, student_jobs.csv, part_time_jobs.csv, other_jobs.csv
     (other_jobs = full_time + seasonal)
  4. prints counts per category and status

Usage:  python tools/split_tracker.py
Re-run after every batch of applications; the views are regenerated from scratch.
"""
import csv
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "job_search_tracker.csv"
OUT = ROOT / "trackers"

STAGE = re.compile(r"\bstages?\b|\bstagiaire|\bintern(ship)?\b|\bPFE\b|fin d.études", re.I)
STUDENT = re.compile(r"[ée]tudiant|student|job étudiant|part-time student", re.I)
SEASONAL = re.compile(r"saison|seasonal|ski", re.I)


def categorise(row: dict) -> str:
    rt = (row.get("role_type") or "").strip().lower().replace("-", "_")
    role, notes = row.get("role", ""), row.get("notes", "")
    if rt in {"internship", "student_job", "part_time", "full_time", "seasonal"} and rt != "part_time":
        # already normalised; still catch internships filed under full_time
        if rt == "full_time" and STAGE.search(role) and "alternance" not in role.lower():
            return "internship"
        return rt
    if rt == "internship" or (STAGE.search(role) and "alternance" not in role.lower()):
        return "internship"
    if rt == "seasonal" or (SEASONAL.search(role + " " + notes) and "season" in (role + notes).lower()):
        return "seasonal"
    if rt in {"part_time", "part-time"}:
        if re.search(r"full-time \d+h", notes, re.I) and not STUDENT.search(role):
            return "full_time"
        return "student_job" if STUDENT.search(role + " " + notes) else "part_time"
    if STUDENT.search(role):
        return "student_job"
    return "full_time"


FILES = {
    "internship": "internships.csv",
    "student_job": "student_jobs.csv",
    "part_time": "part_time_jobs.csv",
    "full_time": "other_jobs.csv",
    "seasonal": "other_jobs.csv",
}


def main() -> int:
    with MASTER.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames
        rows = list(reader)
    for r in rows:
        r["role_type"] = categorise(r)
    with MASTER.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        w.writerows(rows)
    OUT.mkdir(exist_ok=True)
    groups: dict[str, list] = {}
    for r in rows:
        groups.setdefault(FILES[r["role_type"]], []).append(r)
    for name in sorted(set(FILES.values())):
        with (OUT / name).open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=header)
            w.writeheader()
            w.writerows(sorted(groups.get(name, []), key=lambda r: r["date"], reverse=True))
    print(f"{len(rows)} rows")
    for cat in ["internship", "student_job", "part_time", "full_time", "seasonal"]:
        c = Counter(r["status"] for r in rows if r["role_type"] == cat)
        print(f"  {cat:12s} {sum(c.values()):4d}  " + "  ".join(f"{k}={v}" for k, v in sorted(c.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
