#!/usr/bin/env python3
"""The job database (stages I-II of the pipeline): one SQLite file, data/jobs.db.

Tables
  keywords      search queries derived from the profile (stage I.1, tools/keywords.py)
  postings      every posting found by the blanket search (stage I.2, tools/search_all.py)
                stage: found -> fit | discarded (tools/rank_jobs.py) -> drafted | applied | queued | closed
  search_runs   one row per (portal, query) search, for yield and error tracking
  portal_logins last login attempt per portal (tools/portal_login.py)

job_search_tracker.csv stays the record of applications (stage III). The database never edits it;
`pipeline.py sync` copies tracker statuses back onto matching postings.

  python tools/jobsdb.py init                   # create tables (idempotent)
  python tools/jobsdb.py import-legacy          # one-time: seen_jobs.json + cached postings -> postings
  python tools/jobsdb.py stats
  python tools/jobsdb.py show <id>
  python tools/jobsdb.py list [--stage fit] [--limit 20] [--portal linkedin] [--q text]
  python tools/jobsdb.py set <id> stage=<stage> [note="..."] [score=NN]
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "jobs.db"
STAGES = ("found", "fit", "discarded", "drafted", "applied", "queued", "closed")

SCHEMA = """
CREATE TABLE IF NOT EXISTS keywords(
  query TEXT PRIMARY KEY, family TEXT, lang TEXT, weight INTEGER DEFAULT 5,
  source TEXT, active INTEGER DEFAULT 1, updated TEXT);
CREATE TABLE IF NOT EXISTS postings(
  id INTEGER PRIMARY KEY, key TEXT UNIQUE, portal TEXT, portal_id TEXT,
  company TEXT, title TEXT, location TEXT, url TEXT, posted TEXT,
  first_seen TEXT, last_seen TEXT, query TEXT, description TEXT,
  stage TEXT DEFAULT 'found', score INTEGER, hits TEXT, flags TEXT, reason TEXT,
  tracker_row INTEGER, note TEXT, updated TEXT);
CREATE INDEX IF NOT EXISTS postings_stage ON postings(stage, score);
CREATE TABLE IF NOT EXISTS search_runs(
  id INTEGER PRIMARY KEY, ts TEXT, portal TEXT, query TEXT, found INTEGER, new INTEGER, error TEXT);
CREATE TABLE IF NOT EXISTS portal_logins(
  portal TEXT PRIMARY KEY, last_try TEXT, result TEXT, detail TEXT);
"""


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def today() -> str:
    return dt.date.today().isoformat()


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    for table in ("keywords", "postings"):  # tracks (tools/tracks): every query and posting belongs to one
        cols = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
        if "track" not in cols:
            con.execute(f"ALTER TABLE {table} ADD COLUMN track TEXT DEFAULT 'internship'")
    con.commit()
    return con


def utf8_out() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------- identity
_ID_RES = [
    ("linkedin", re.compile(r"linkedin\.com/jobs/view/(?:[^/?#]*?-)?(\d{8,})")),
    ("linkedin", re.compile(r"currentJobId=(\d{8,})")),
    ("hellowork", re.compile(r"hellowork\.com/[a-z-]+/emplois/(\d{6,})")),
    ("jobteaser", re.compile(r"job-offers/([0-9a-f]{8}-[0-9a-f-]{27})")),
    ("wttj", re.compile(r"welcometothejungle\.com/[a-z]{2}/companies/([^/]+/jobs/[^/?#\s]+)")),
    ("glassdoor", re.compile(r"glassdoor\.[a-z.]+/\S*?[?&]jl=(\d{8,})")),
    # Workday: tenant + requisition id at the end of the job path (".../job/Paris/Stage-X_R0281234")
    ("workday", re.compile(r"//([a-z0-9-]+)\.wd\d+\.myworkdayjobs\.com/[^?#\s]*?_([A-Za-z]*\d[\w-]*?)(?:/apply\S*)?(?:[?#]|$)")),
]


def portal_id(url: str) -> tuple[str, str]:
    for portal, rx in _ID_RES:
        m = rx.search(url or "")
        if m:
            return portal, "/".join(m.groups()).lower()
    return "", ""


def fold(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def make_key(company: str, title: str, url: str) -> str:
    p, pid = portal_id(url)
    if pid:
        return f"{p}:{pid}"
    return "ct:" + fold(company)[:30].replace(" ", "-") + "|" + fold(title)[:60].replace(" ", "-")


SUBMITTED = ("applied", "interview", "offer", "hired", "rejected", "withdrawn", "no_response")


class IntakeGate:
    """Intake check (between find and rank): a new posting that matches an application already submitted
    (job_search_tracker.csv: applied / interview / rejected / ...) is stored as `discarded` with the tracker
    row as reason, so it never reaches ranking or `pipeline.py next`. Matching is seen.Lookup: portal id,
    company (or the company in an ATS URL) + title overlap. Drafted-but-unsent rows are left to rank."""

    def __init__(self, lookup=None):
        if lookup is None:
            sys.path.insert(0, str(ROOT / "tools"))
            import seen
            lookup = seen.Lookup()
        self.lk = lookup
        self.dropped = 0

    def reason(self, company: str, title: str, url: str) -> str:
        hit = self.lk.find(company or "", title or "", url or "")
        if not hit or hit[1]["s"] not in SUBMITTED:
            return ""
        kind, rec = hit
        return f"already submitted: {rec['s']} [{kind}] {rec['why']} | {rec['lbl']}"[:160]


def upsert(con: sqlite3.Connection, *, company: str, title: str, url: str, portal: str = "",
           location: str = "", posted: str = "", query: str = "", description: str = "",
           track: str = "internship", gate: IntakeGate | None = None) -> bool:
    """Insert a posting or refresh last_seen. Returns True when it is new and goes to ranking.
    With a gate, a new posting already submitted to is stored as `discarded` and returns False."""
    key = make_key(company, title, url)
    _, pid = portal_id(url)
    row = con.execute("SELECT id, description FROM postings WHERE key=?", (key,)).fetchone()
    if row:
        con.execute("UPDATE postings SET last_seen=?, description=COALESCE(NULLIF(description,''), ?) WHERE id=?",
                    (today(), description or "", row["id"]))
        return False
    why = gate.reason(company, title, url) if gate else ""
    con.execute(
        "INSERT INTO postings(key, portal, portal_id, company, title, location, url, posted, first_seen, last_seen,"
        " query, description, stage, reason, updated, track) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (key, portal, pid, company.strip(), title.strip(), location.strip(), url.strip(), posted, today(), today(),
         query, description, "discarded" if why else "found", why or None, now(), track))
    if why:
        gate.dropped += 1
        return False
    return True


def dedupe(con: sqlite3.Connection, gate: IntakeGate | None = None) -> int:
    """Apply the intake gate to postings already in the db that are still waiting (found / fit)."""
    gate = gate or IntakeGate()
    n = 0
    for r in con.execute("SELECT id, company, title, url FROM postings WHERE stage IN ('found','fit')").fetchall():
        why = gate.reason(r["company"], r["title"], r["url"])
        if why:
            con.execute("UPDATE postings SET stage='discarded', reason=?, updated=? WHERE id=?", (why, now(), r["id"]))
            n += 1
    con.commit()
    return n


# ---------------------------------------------------------------- legacy import
def import_legacy(con: sqlite3.Connection) -> str:
    seen_path = ROOT / "job_scraper" / "seen_jobs.json"
    n_new = n_all = 0
    if seen_path.exists():
        seen = json.loads(seen_path.read_text(encoding="utf-8-sig")).get("seen", {})
        for v in seen.values():
            n_all += 1
            if upsert(con, company=v.get("company", ""), title=v.get("title", ""), url=v.get("url", ""),
                      portal=(v.get("portal") or "").replace("-search", ""), location=v.get("location") or "",
                      posted=v.get("posted_date") or "", query="legacy:seen_jobs"):
                n_new += 1
                st = v.get("status") or ""
                stage = {"skipped": "discarded", "expired": "closed", "applied": "applied"}.get(st)
                if stage:
                    con.execute("UPDATE postings SET stage=?, reason=? WHERE key=?",
                                (stage, f"legacy {st} {v.get('reason', '')}".strip(),
                                 make_key(v.get("company", ""), v.get("title", ""), v.get("url", ""))))
    # cached LinkedIn detail texts become descriptions
    cache = ROOT / "job_scraper" / "postings"
    n_desc = 0
    if cache.exists():
        for f in cache.glob("*.txt"):
            r = con.execute("UPDATE postings SET description=? WHERE key=? AND COALESCE(description,'')=''",
                            (f.read_text(encoding="utf-8", errors="replace"), f"linkedin:{f.stem}"))
            n_desc += r.rowcount
    con.commit()
    return f"legacy import: {n_all} seen_jobs entries, {n_new} new postings, {n_desc} descriptions attached"


# ---------------------------------------------------------------- CLI
def fmt(r: sqlite3.Row) -> str:
    sc = "" if r["score"] is None else r["score"]
    return (f"{r['id']:>5} | {r['stage']:<9} | {sc!s:>3} | {(r['company'] or '')[:24]:<24} | "
            f"{(r['title'] or '')[:62]} | {(r['location'] or '')[:18]} | {r['url'] or ''}")


def stats(con: sqlite3.Connection, track: str | None = None) -> str:
    w, a = ("WHERE track=?", (track,)) if track else ("", ())
    rows = con.execute(f"SELECT stage, COUNT(*) n FROM postings {w} GROUP BY stage", a).fetchall()
    by = {r["stage"]: r["n"] for r in rows}
    kw = con.execute(f"SELECT COUNT(*) FROM keywords WHERE active=1 {'AND track=?' if track else ''}", a).fetchone()[0]
    last = con.execute("SELECT MAX(ts) FROM search_runs").fetchone()[0] or "never"
    parts = " ".join(f"{s}={by.get(s, 0)}" for s in STAGES if by.get(s))
    label = f"jobs.db[{track}]" if track else "jobs.db"
    return f"{label}: {sum(by.values())} postings ({parts or 'empty'}) | {kw} active queries | last search {last}"


def main(argv: list[str]) -> int:
    utf8_out()
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    con = connect()
    cmd, rest = argv[0], argv[1:]

    def opt(name, default=None):
        return rest[rest.index(name) + 1] if name in rest else default

    if cmd == "init":
        print(stats(con))
    elif cmd == "import-legacy":
        print(import_legacy(con))
        print(stats(con))
    elif cmd == "stats":
        print(stats(con))
    elif cmd == "show":
        r = con.execute("SELECT * FROM postings WHERE id=?", (int(rest[0]),)).fetchone()
        if not r:
            print("no such id")
            return 1
        for k in r.keys():
            v = r[k]
            if k == "description" and v:
                v = f"{len(v)} chars: " + v[:300].replace("\n", " ")
            print(f"{k}: {v}")
    elif cmd == "list":
        q = "SELECT * FROM postings WHERE 1=1"
        args: list = []
        if opt("--stage"):
            q += " AND stage=?"
            args.append(opt("--stage"))
        if opt("--portal"):
            q += " AND portal=?"
            args.append(opt("--portal"))
        if opt("--track"):
            q += " AND track=?"
            args.append(opt("--track"))
        if opt("--q"):
            q += " AND (company LIKE ? OR title LIKE ?)"
            args += [f"%{opt('--q')}%"] * 2
        q += " ORDER BY COALESCE(score,-1) DESC, id DESC LIMIT ?"
        args.append(int(opt("--limit", 20)))
        for r in con.execute(q, args):
            print(fmt(r))
    elif cmd == "set":
        pid, sets = int(rest[0]), dict(a.split("=", 1) for a in rest[1:])
        if "stage" in sets and sets["stage"] not in STAGES:
            print(f"stage must be one of {STAGES}")
            return 1
        note = sets.pop("note", None)
        cols = {k: v for k, v in sets.items() if k in ("stage", "score", "reason", "tracker_row")}
        if note:
            con.execute("UPDATE postings SET note=COALESCE(note||' ; ','')||? WHERE id=?", (f"{today()} {note}", pid))
        if cols:
            con.execute(f"UPDATE postings SET {', '.join(k + '=?' for k in cols)}, updated=? WHERE id=?",
                        (*cols.values(), now(), pid))
        con.commit()
        print(fmt(con.execute("SELECT * FROM postings WHERE id=?", (pid,)).fetchone()))
    else:
        print(f"unknown command {cmd}; see --help")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
