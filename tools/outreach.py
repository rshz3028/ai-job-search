"""Recruiter outreach helper for /outreach.

Deterministic bookkeeping only; contact discovery and email writing are done
by Claude following .claude/commands/outreach.md.

  python tools/outreach.py candidates [--min-days 3] [--max-days 45]
                                      [--limit 15] [--company X] [--all-types]
      JSON list of tracked applications eligible for an outreach email.
  python tools/outreach.py log --company C --role R --date D --status S
                               [--to EMAIL] [--name N] [--title T]
                               [--source URL] [--lang en|fr] [--notes TEXT]
      Append one row to outreach/outreach_log.csv. status=sent also appends
      "followed up YYYY-MM-DD outreach email" to the tracker row's notes, so
      /outcome followup counts it.
  python tools/outreach.py stats
      Emails sent today and in total (the command enforces a daily cap).
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
TRACKER = REPO / "job_search_tracker.csv"
LOG = REPO / "outreach" / "outreach_log.csv"
APPS = REPO / "documents" / "applications"
LOG_FIELDS = ["date", "company", "role", "applied_date", "status", "to_email",
              "contact_name", "contact_title", "email_source", "language", "notes"]
STATUSES = {"sent", "drafted", "no_contact", "linkedin_manual", "skipped", "bounced"}
FOLLOWUP_RE = re.compile(r"followed up \d{4}-\d{2}-\d{2}")
FR_HINTS = re.compile(r"\b(stage|stagiaire|ingénieur|alternance|candidature|h/f|f/h|développement|électronique)\b", re.I)


def subfolder(company: str, role: str) -> str:
    """documents/README.md 'Subfolder naming' rule."""
    s = f"{company}_{role}".lower().replace(" ", "_")
    s = re.sub(r"[^\w]", "", s, flags=re.ASCII)
    return re.sub(r"_+", "_", s).strip("_")


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", text.lower())


def find_archive(company: str, role: str, apps: Path = APPS) -> Path | None:
    if not apps.is_dir():
        return None
    exact = apps / subfolder(company, role)
    if exact.is_dir():
        return exact
    comp = _norm(company.split("(")[0])[:12]
    role_words = [_norm(w) for w in role.split() if len(_norm(w)) > 3][:3]
    best, best_score = None, 0
    for d in apps.iterdir():
        if not d.is_dir():
            continue
        n = _norm(d.name)
        if not comp or not n.startswith(comp):
            continue
        score = 1 + sum(1 for w in role_words if w in n)
        if score > best_score:
            best, best_score = d, score
    return best


def find_cv(row: dict, archive: Path | None) -> str:
    cv = (row.get("cv_file") or "").strip()
    if cv:
        p = REPO / cv
        if p.suffix.lower() == ".json":
            p = p.with_suffix(".pdf")
        if p.is_file() and p.suffix.lower() == ".pdf":
            return p.relative_to(REPO).as_posix()
    if archive:
        pdfs = sorted([*archive.glob("*Resume*.pdf"), *archive.glob("*CV*.pdf")],
                      key=lambda f: f.stat().st_mtime, reverse=True)
        if pdfs:
            return pdfs[0].relative_to(REPO).as_posix()
    return ""


def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    if not path.is_file():
        return [], []
    with path.open(encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        return list(r.fieldnames or []), list(r)


def contacted_keys() -> set[tuple[str, str]]:
    _, rows = read_csv(LOG)
    return {(r["company"].strip().lower(), r["role"].strip().lower())
            for r in rows if r.get("status") in ("sent", "drafted", "bounced")}


def candidates(args) -> list[dict]:
    _, rows = read_csv(TRACKER)
    done = contacted_keys()
    today = dt.date.today()
    out = []
    for row in rows:
        if row.get("status", "").strip() != "applied":
            continue
        if not args.all_types and row.get("role_type", "").strip() not in ("internship", ""):
            continue
        if args.company and args.company.lower() not in row["company"].lower():
            continue
        try:
            applied = dt.date.fromisoformat(row["date"].strip()[:10])
        except ValueError:
            continue
        days = (today - applied).days
        if not args.company and not (args.min_days <= days <= args.max_days):
            continue
        if (row["company"].strip().lower(), row["role"].strip().lower()) in done:
            continue
        if len(FOLLOWUP_RE.findall(row.get("notes", ""))) >= 2:
            continue
        archive = find_archive(row["company"], row["role"])
        posting = archive / "job_posting.md" if archive else None
        posting_text = posting.read_text(encoding="utf-8", errors="replace") if posting and posting.is_file() else ""
        emails = sorted(set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", posting_text)))
        fr = len(FR_HINTS.findall(row["role"] + " " + posting_text[:3000]))
        try:
            fit = float(row.get("fit_rating") or 0)
        except ValueError:
            fit = {"high": 80, "medium": 60, "low": 40}.get(row.get("fit_rating", "").lower(), 0)
        out.append({
            "company": row["company"], "role": row["role"], "applied_date": row["date"][:10],
            "days_since": days, "channel": row.get("channel", ""), "fit": fit,
            "contact_person": row.get("contact_person", ""), "source": row.get("source", ""),
            "archive_dir": archive.relative_to(REPO).as_posix() if archive else "",
            "posting_file": posting.relative_to(REPO).as_posix() if posting and posting.is_file() else "",
            "emails_in_posting": emails, "cv_pdf": find_cv(row, archive),
            "lang_hint": "fr" if fr >= 2 else "en",
        })
    out.sort(key=lambda c: (-c["fit"], c["days_since"]))
    return out[: args.limit]


def append_tracker_note(company: str, role: str, applied: str, note: str) -> bool:
    fields, rows = read_csv(TRACKER)
    hit = False
    for r in rows:
        if (r["company"].strip() == company.strip() and r["role"].strip() == role.strip()
                and r["date"].strip()[:10] == applied[:10]):
            r["notes"] = (r.get("notes", "").rstrip("; ") + "; " + note).lstrip("; ")
            hit = True
            break
    if hit:
        with TRACKER.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
    return hit


def log(args) -> dict:
    if args.status not in STATUSES:
        raise SystemExit(f"status must be one of {sorted(STATUSES)}")
    clean = lambda s: re.sub(r"[\r\n]+", " ", s or "").strip()
    LOG.parent.mkdir(exist_ok=True)
    new = not LOG.is_file()
    today = dt.date.today().isoformat()
    with LOG.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if new:
            w.writeheader()
        w.writerow({"date": today, "company": clean(args.company), "role": clean(args.role),
                    "applied_date": clean(args.date), "status": args.status,
                    "to_email": clean(args.to), "contact_name": clean(args.name),
                    "contact_title": clean(args.title), "email_source": clean(args.source),
                    "language": clean(args.lang), "notes": clean(args.notes)})
    tracker = False
    if args.status == "sent":
        tracker = append_tracker_note(args.company, args.role, args.date, f"followed up {today} outreach email")
    return {"logged": True, "tracker_note_added": tracker}


def stats() -> dict:
    _, rows = read_csv(LOG)
    today = dt.date.today().isoformat()
    sent = [r for r in rows if r.get("status") == "sent"]
    return {"sent_today": sum(1 for r in sent if r["date"] == today), "sent_total": len(sent),
            "by_status": {s: sum(1 for r in rows if r.get("status") == s) for s in sorted(STATUSES)}}


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("candidates")
    c.add_argument("--min-days", type=int, default=3)
    c.add_argument("--max-days", type=int, default=45)
    c.add_argument("--limit", type=int, default=15)
    c.add_argument("--company")
    c.add_argument("--all-types", action="store_true")
    l = sub.add_parser("log")
    for k in ("company", "role", "date", "status"):
        l.add_argument(f"--{k}", required=True)
    for k in ("to", "name", "title", "source", "lang", "notes"):
        l.add_argument(f"--{k}", default="")
    sub.add_parser("stats")
    a = ap.parse_args(argv)
    result = candidates(a) if a.cmd == "candidates" else log(a) if a.cmd == "log" else stats()
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
