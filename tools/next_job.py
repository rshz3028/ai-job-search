"""Pick the next best-fit job for /autopilot.

Reads ranked entries from job_scraper/seen_jobs.json (never prints the whole
file), drops ones already in job_search_tracker.csv (company + similar title,
any channel), passed deadlines and fits below the threshold, then orders by
deadline urgency (<= 7 days first) and score.

  python tools/next_job.py [--min-score 60] [--limit 5]
  python tools/next_job.py --count     # how many ranked / unranked remain

Score: numeric `score`/`overall`/`rank_score` when present, else the legacy
`fit` label (high=80, medium=65, low=40).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SEEN = REPO / "job_scraper" / "seen_jobs.json"
TRACKER = REPO / "job_search_tracker.csv"
LABELS = {"high": 80, "strong": 80, "medium": 65, "good": 65, "moderate": 50, "low": 40, "weak": 35}
STOP = {"stage", "stagiaire", "intern", "internship", "hf", "fh", "mf", "fm", "de", "du", "la", "le",
        "des", "en", "et", "the", "and", "for", "of", "a", "un", "une", "pour", "ingenieur", "engineer"}


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]", " ", text)


def words(text: str) -> set[str]:
    return {w for w in norm(text).split() if len(w) > 2 and w not in STOP}


def company_key(name: str) -> str:
    return "".join(norm(name.split("(")[0]).split())[:10]


def score_of(entry: dict) -> float:
    for k in ("score", "overall", "rank_score", "fit_score"):
        v = entry.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return float(LABELS.get(str(entry.get("fit", "")).strip().lower(), 0))


def already_applied(entry: dict, tracker: list[dict]) -> bool:
    ck, tw = company_key(entry.get("company", "")), words(entry.get("title", ""))
    if len(ck) < 3:
        return False
    for r in tracker:
        rk = company_key(r.get("company", ""))
        if len(rk) < 3 or not (rk.startswith(ck) or ck.startswith(rk)):
            continue
        rw = words(r.get("role", ""))
        if not tw or not rw or len(tw & rw) / min(len(tw), len(rw)) >= 0.5:
            return True
    return False


def load(seen_path: Path = SEEN, tracker_path: Path = TRACKER):
    seen = json.loads(seen_path.read_text(encoding="utf-8")).get("seen", {})
    with tracker_path.open(encoding="utf-8", newline="") as f:
        tracker = list(csv.DictReader(f))
    return seen, tracker


def pick(seen: dict, tracker: list[dict], min_score: float, today: dt.date) -> list[dict]:
    out = []
    for key, e in seen.items():
        if e.get("status") != "ranked":
            continue
        s = score_of(e)
        if s < min_score:
            continue
        days_left = None
        if e.get("deadline"):
            try:
                days_left = (dt.date.fromisoformat(str(e["deadline"])[:10]) - today).days
            except ValueError:
                pass
        if days_left is not None and days_left < 0:
            continue
        if already_applied(e, tracker):
            continue
        out.append({"key": key, "company": e.get("company", ""), "title": e.get("title", ""),
                    "url": e.get("url", ""), "score": s, "deadline": e.get("deadline"),
                    "urgent": days_left is not None and days_left <= 7})
    out.sort(key=lambda j: (not j["urgent"], -j["score"]))
    return out


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--min-score", type=float, default=60)
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--count", action="store_true")
    a = ap.parse_args(argv)
    seen, tracker = load()
    jobs = pick(seen, tracker, a.min_score, dt.date.today())
    if a.count:
        print(json.dumps({"ready": len(jobs),
                          "unranked_new": sum(1 for e in seen.values() if e.get("status") == "new")}))
    else:
        print(json.dumps(jobs[: a.limit], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
