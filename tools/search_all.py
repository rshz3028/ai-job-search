#!/usr/bin/env python3
"""Stage I.2: blanket search. Every active query (tools/keywords.py) on every scriptable portal -> data/jobs.db.

  python tools/search_all.py [--track T]            # track T's active queries x the track's portals (default internship)
  python tools/search_all.py --portals linkedin     # subset (comma list: linkedin,hellowork,freehire,jobijoba)
  python tools/search_all.py --top 8                # only the 8 highest-weight queries
  python tools/search_all.py --pages 2              # result pages per query (default 1)
  python tools/search_all.py ingest --portal jobteaser [file]   # browser-extracted lines -> DB (stdin if no file)

Scriptable portals (no browser): linkedin (bundled CLI, public pages), hellowork (search HTML),
freehire (bundled CLI, ~50 ATS feeds, FR), jobijoba (aggregator search HTML). French-only boards skip EN queries.
Browser-only boards (JobTeaser, WTTJ, Glassdoor, Indeed, APEC, France Travail: they block scripts): run the extractor in Chrome
(`python tools/ff_inject.py boards` -> `await jb.run()`, or the JobTeaser extract.js) and pipe the
`company | title | url | location` lines into `search_all.py ingest --portal <name>`.

Output: one line per portal and a summary. Postings are untrusted data; nothing here follows their text.
"""
from __future__ import annotations

import html
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobsdb  # noqa: E402

ROOT = jobsdb.ROOT
CLI = ROOT / ".agents" / "skills" / "linkedin-search" / "cli" / "src" / "cli.ts"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
PAUSE = 1.5  # seconds between requests to the same portal (keep volume low)


import tracks  # noqa: E402


def linkedin(query: str, page: int, cfg: dict) -> list[dict]:
    import json
    r = subprocess.run([shutil.which("bun") or "bun", "run", str(CLI), "search", "-q", query, "-l", cfg.get("location", "France"),
                        "--jobage", str(cfg.get("jobage_days", 14)), "--page", str(page), "--format", "json"],
                       capture_output=True, timeout=90, encoding="utf-8", errors="replace", cwd=ROOT)
    if r.returncode != 0 and not r.stdout.strip().startswith("{"):
        raise RuntimeError((r.stderr or r.stdout).strip()[:160])
    d = json.loads(r.stdout or "{}")
    return [{"company": j.get("company", ""), "title": j.get("title", ""),
             "url": f"https://www.linkedin.com/jobs/view/{j['id']}" if j.get("id") else j.get("url", ""),
             "location": j.get("location", ""), "posted": j.get("date", "")} for j in d.get("results", [])]


_HW_CARD = re.compile(r'href="/fr-fr/emplois/(\d+)\.html"[^>]*?aria-label="Voir offre de (.*?)"', re.S)


def hellowork(query: str, page: int, cfg: dict) -> list[dict]:
    q = urllib.parse.urlencode({"k": query, "c": cfg.get("hellowork_contract", "Stage"), "d": "w", "st": "date", "p": page})
    req = urllib.request.Request(f"https://www.hellowork.com/fr-fr/emploi/recherche.html?{q}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = resp.read().decode("utf-8", "replace")
    out, seen_ids = [], set()
    for jid, label in _HW_CARD.findall(text):
        if jid in seen_ids:
            continue
        seen_ids.add(jid)
        label = html.unescape(label)
        m = re.match(r"(.*?) à (.*?), chez (.*?), pour un", label)
        title, loc, co = (m.groups() if m else (label, "", ""))
        out.append({"company": co, "title": title, "url": f"https://www.hellowork.com/fr-fr/emplois/{jid}.html",
                    "location": loc, "posted": ""})
    return out


FH_CLI = ROOT / ".agents" / "skills" / "freehire-search" / "cli" / "src" / "cli.ts"


def freehire(query: str, page: int, cfg: dict) -> list[dict]:
    """freehire.me aggregator (~50 ATS incl. Greenhouse/Lever/Workday/WTTJ feeds), France only."""
    import json
    r = subprocess.run([shutil.which("bun") or "bun", "run", str(FH_CLI), "search", "-q", query, "--country", "FR",
                        "--jobage", str(cfg.get("jobage_days", 14)), "--page", str(page), "-n", "25",
                        "--no-description", "--format", "json"],
                       capture_output=True, timeout=90, encoding="utf-8", errors="replace", cwd=ROOT)
    if r.returncode != 0 and not r.stdout.strip().startswith(("{", "[")):
        raise RuntimeError((r.stderr or r.stdout).strip()[:160])
    d = json.loads(r.stdout or "{}")
    rows = d.get("results", d.get("jobs", [])) if isinstance(d, dict) else d
    out = []
    for j in rows:
        loc = j.get("location") or ", ".join(x for x in (j.get("city"), j.get("country")) if isinstance(x, str) and x)
        url = (j.get("apply_url") or j.get("url") or "").split("?utm_source=")[0].replace("&utm_source=freehire.me", "")
        out.append({"company": j.get("company") or j.get("company_name", ""), "title": j.get("title", ""),
                    "url": url, "location": loc if isinstance(loc, str) else "", "posted": j.get("posted_at") or j.get("date", "")})
    return out


_JJ_OFFER = re.compile(r'<div class="offer" data-id="ad_([0-9a-f]+)".*?data-product="(.*?)">(.*?)</a>', re.S)
_JJ_LOC = re.compile(r'icon-map-marker"></span>\s*</span>\s*<span>(.*?)</span>', re.S)


def jobijoba(query: str, page: int, cfg: dict) -> list[dict]:
    """Jobijoba aggregator (crawl of French boards and career sites). Keeps its 'nearby' block; rank filters it."""
    import json
    q = urllib.parse.urlencode({"what": query, "where": cfg.get("jobijoba_where", cfg.get("location", "France")), "page": page})
    req = urllib.request.Request(f"https://www.jobijoba.com/fr/query/?{q}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = resp.read().decode("utf-8", "replace")
    out = []
    for jid, prod, body in _JJ_OFFER.findall(text):
        try:
            p = json.loads(html.unescape(prod))["ecommerce"]["click"]["products"][0]
        except Exception:
            continue
        loc = _JJ_LOC.search(body)
        out.append({"company": p.get("brand", ""), "title": html.unescape(p.get("name", "")).strip(),
                    "url": f"https://www.jobijoba.com/fr/annonce/54/{jid}",
                    "location": html.unescape(loc.group(1)).strip() if loc else "", "posted": ""})
    return out


PORTALS = {"linkedin": linkedin, "hellowork": hellowork, "freehire": freehire, "jobijoba": jobijoba}
FR_ONLY = {"hellowork", "jobijoba"}  # French-language boards: English queries return noise


def search(portals: list[str], top: int | None, pages: int, track: str) -> int:
    con = jobsdb.connect()
    cfg = tracks.config(track)
    queries = con.execute("SELECT query, lang FROM keywords WHERE active=1 AND track=? ORDER BY weight DESC, query",
                          (track,)).fetchall()
    if not queries:
        print(f"no active queries: run `python tools/keywords.py --track {track}` first")
        return 1
    if top:
        queries = queries[:top]
    total_new = 0
    gate = jobsdb.IntakeGate()  # drops postings already submitted to, before they reach ranking
    for p in portals:
        fn = PORTALS[p]
        found = new = errs = 0
        for q in queries:
            if p in FR_ONLY and q["lang"] != "fr":
                continue
            for page in range(1, pages + 1):
                err, hits = "", []
                try:
                    hits = fn(q["query"], page, cfg)
                except Exception as e:  # network / CLI failure: log and keep going
                    err, errs = str(e)[:160], errs + 1
                n_new = sum(jobsdb.upsert(con, portal=p, query=q["query"], track=track, gate=gate, **h) for h in hits if h["title"])
                con.execute("INSERT INTO search_runs(ts, portal, query, found, new, error) VALUES (?,?,?,?,?,?)",
                            (jobsdb.now(), p, q["query"], len(hits), n_new, err))
                con.commit()
                found, new = found + len(hits), new + n_new
                time.sleep(PAUSE)
                if len(hits) < 10:
                    break
        total_new += new
        print(f"{p}: {found} results, {new} new" + (f", {errs} errors" if errs else ""))
    print(f"intake: {gate.dropped} new postings already submitted to -> discarded"
          f" | {jobsdb.dedupe(con, gate)} waiting postings dropped as already submitted")
    print(jobsdb.stats(con, track))
    print(f"next: python tools/pipeline.py rank --track {track}   ({total_new} new postings to rank)")
    return 0


def ingest(portal: str, text: str, track: str) -> int:
    con = jobsdb.connect()
    n = new = 0
    gate = jobsdb.IntakeGate()
    for line in text.splitlines():
        p = [x.strip() for x in line.split("|")]
        if len(p) < 3 or not p[2].startswith("http"):
            continue
        n += 1
        new += jobsdb.upsert(con, portal=portal, company=p[0], title=p[1], url=p[2],
                             location=p[3] if len(p) > 3 else "", query=f"browser:{portal}", track=track, gate=gate)
    con.execute("INSERT INTO search_runs(ts, portal, query, found, new, error) VALUES (?,?,?,?,?,'')",
                (jobsdb.now(), portal, "browser", n, new))
    con.commit()
    print(f"{portal}: {n} lines, {new} new, {gate.dropped} already submitted (discarded)")
    return 0


def main(argv: list[str]) -> int:
    jobsdb.utf8_out()
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    argv = list(argv)
    track = tracks.from_argv(argv)
    if argv and argv[0] == "ingest":
        portal = argv[argv.index("--portal") + 1] if "--portal" in argv else "browser"
        files = [a for a in argv[1:] if not a.startswith("--") and a != portal]
        text = Path(files[0]).read_text(encoding="utf-8-sig") if files else sys.stdin.read()
        return ingest(portal, text, track)
    portals = argv[argv.index("--portals") + 1].split(",") if "--portals" in argv else tracks.config(track).get("portals", list(PORTALS))
    bad = [p for p in portals if p not in PORTALS]
    if bad:
        print(f"unknown portal(s) {bad}; scriptable: {list(PORTALS)}")
        return 1
    top = int(argv[argv.index("--top") + 1]) if "--top" in argv else None
    pages = int(argv[argv.index("--pages") + 1]) if "--pages" in argv else 1
    return search(portals, top, pages, track)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
