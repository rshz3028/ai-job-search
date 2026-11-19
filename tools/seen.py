#!/usr/bin/env python3
"""Lookup table of every posting already handled: applied, drafted, rejected, skipped, expired.

One cached index (job_scraper/lookup.json, rebuilt automatically when a source changes) over:
  * job_search_tracker.csv          every row (status drafted/applied/rejected/interview/...)
  * job_scraper/seen_jobs.json      scrape history (skipped, expired, ranked, applied, ...)
  * job_scraper/skipped.tsv         in-session skips with a reason (append with `skip`)
  * job_scraper/excluded_employers.txt

A new posting is a HIT when its portal id (LinkedIn numeric id, WTTJ slug, JobTeaser uuid)
matches, or the company matches and the title tokens overlap (truncation-safe), or the
employer is excluded.

  python tools/seen.py check [file ...]        # LinkedIn CLI JSON or "company | title | url" lines
                                               # (stdin when no file). Prints NEW postings only,
                                               # then one summary line. --all also prints hits.
                                               # --intern drops titles that are not internships.
  python tools/seen.py q "<company>" "<title>" [url]   # one line: NEW or the matching record
  python tools/seen.py skip "<company>" "<title>" "<url>" "<reason>"   # remember a skip
  python tools/seen.py stats
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRACKER = ROOT / "job_search_tracker.csv"
SEEN = ROOT / "job_scraper" / "seen_jobs.json"
SKIPS = ROOT / "job_scraper" / "skipped.tsv"
EXCL = ROOT / "job_scraper" / "excluded_employers.txt"
CACHE = ROOT / "job_scraper" / "lookup.json"
SOURCES = [TRACKER, SEEN, SKIPS, EXCL]

CO_DROP = {"group", "groupe", "france", "sas", "sa", "inc", "ltd", "llc", "gmbh", "se", "co", "the",
           "company", "fr", "1", "s", "corp", "corporation", "acquired", "by"}
T_STOP = {"stage", "stagiaire", "stagiaires", "intern", "internship", "trainee", "h", "f", "m", "w", "x", "d",
          "hf", "fh", "mf", "fm", "de", "du", "la", "le", "les", "et", "en", "of", "for", "the", "des", "pour",
          "une", "un", "a", "au", "aux", "with", "and", "in", "on", "to", "l", "bac", "5", "pfe", "fin",
          "etudes", "etude", "mois", "6", "cs27", "2027", "2026", "ingenieur", "ingenieure", "engineer",
          "engineering", "e", "sur", "dans", "par", "final", "year", "end", "of", "studies"}
INTERN_RE = re.compile(r"\b(stage|stagiaire|intern|internship|trainee|pfe|fin d.?etudes)\b")
STATUS_RANK = {"interview": 0, "offer": 0, "hired": 0, "applied": 1, "drafted": 2, "rejected": 3,
               "withdrawn": 4, "no_response": 4}


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def co_key(company: str) -> str:
    toks = [t for t in fold(company).split() if t not in CO_DROP]
    return toks[0] if toks else fold(company)


def t_toks(title: str) -> list[str]:
    return sorted({t for t in fold(title).split() if t not in T_STOP and len(t) > 1})


ID_RES = [
    re.compile(r"linkedin\.com/jobs/view/(?:[^/?#]*?-)?(\d{8,})"),
    re.compile(r"currentJobId=(\d{8,})"),
    re.compile(r"\blinkedin\D{0,12}(\d{9,11})\b", re.I),
    re.compile(r"welcometothejungle\.com/[a-z]{2}/companies/([^/]+/jobs/[^/?#\s]+)"),
    re.compile(r"job-offers/([0-9a-f]{8}-[0-9a-f-]{27})"),
    re.compile(r"glassdoor\.[a-z.]+/\S*?[?&]jl=(\d{8,})"),
    re.compile(r"hellowork\.com/[a-z-]+/emplois/(\d{6,})"),
]


def ids_in(text: str) -> set[str]:
    out = set()
    for r in ID_RES:
        out.update(m.lower() for m in r.findall(text or ""))
    return out


def stale() -> bool:
    if not CACHE.exists():
        return True
    c = CACHE.stat().st_mtime
    return any(p.exists() and p.stat().st_mtime > c for p in SOURCES)


def build() -> dict:
    recs = []
    text = TRACKER.read_text(encoding="utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    h = rows[0]
    for n, r in enumerate(rows[1:], 1):
        g = dict(zip(h, r + [""] * (len(h) - len(r))))
        recs.append({"c": co_key(g["company"]), "t": t_toks(g["role"]),
                     "ids": sorted(ids_in(g["source"] + " " + g["notes"])),
                     "s": g["status"], "why": f"r{n} {g['date']} {g['role_type']} fit {g['fit_rating']}",
                     "lbl": f"{g['company'][:24]} | {g['role'][:55]}"})
    if SEEN.exists():
        seen = json.loads(SEEN.read_text(encoding="utf-8-sig")).get("seen", {})
        for k, v in seen.items():
            st = v.get("status") or "seen"
            if st in ("new", "ranked"):
                continue  # scraped but undecided: not a reason to skip
            recs.append({"c": co_key(v.get("company", "")), "t": t_toks(v.get("title", "")),
                         "ids": sorted(ids_in(v.get("url", ""))), "s": st,
                         "why": f"seen {v.get('first_seen', '')} fit {v.get('fit', '')} {v.get('reason', '')}"[:90],
                         "lbl": f"{v.get('company', '')[:24]} | {v.get('title', '')[:55]}"})
    if SKIPS.exists():
        for line in SKIPS.read_text(encoding="utf-8").splitlines():
            p = line.split("\t")
            if len(p) < 5:
                continue
            d, c, t, u, why = p[:5]
            recs.append({"c": co_key(c), "t": t_toks(t), "ids": sorted(ids_in(u)), "s": "skipped",
                         "why": f"{d} {why}"[:90], "lbl": f"{c[:24]} | {t[:55]}"})
    excl = []
    if EXCL.exists():
        for line in EXCL.read_text(encoding="utf-8-sig").splitlines():
            line = line.split("#")[0].strip()
            if line:
                excl.append(fold(line))
    idx = {"recs": recs, "excl": sorted(set(excl))}
    CACHE.write_text(json.dumps(idx, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return idx


class Lookup:
    def __init__(self):
        idx = build() if stale() else json.loads(CACHE.read_text(encoding="utf-8"))
        self.recs = idx["recs"]
        self.excl = idx["excl"]
        self.by_id, self.by_co = {}, {}
        for i, r in enumerate(self.recs):
            for j in r["ids"]:
                self.by_id.setdefault(j, []).append(i)
            self.by_co.setdefault(r["c"], []).append(i)

    def _best(self, cand):
        return min(cand, key=lambda i: STATUS_RANK.get(self.recs[i]["s"], 5))

    def find(self, company: str, title: str, url: str = ""):
        """Return (kind, record or text) or None when the posting is new."""
        hits = [i for j in ids_in(url) for i in self.by_id.get(j, [])]
        if hits:
            return "id", self.recs[self._best(hits)]
        fc = fold(company)
        for e in self.excl:
            if e and (e == fc or re.search(rf"\b{re.escape(e)}\b", fc)):
                return "excluded", {"s": "excluded", "why": f"excluded employer '{e}'", "lbl": company}
        tt = set(t_toks(title))
        if not tt:
            return None
        cand = []
        for i in self.by_co.get(co_key(company), []):
            rt = set(self.recs[i]["t"])
            if not rt:
                continue
            inter = len(tt & rt)
            small = min(len(tt), len(rt))
            jac = inter / len(tt | rt)
            if jac >= 0.7 or (small >= 3 and inter / small >= 0.85) or (small >= 2 and inter == small and jac >= 0.6):
                cand.append(i)
        return ("title", self.recs[self._best(cand)]) if cand else None


def fmt(kind, r):
    return f"{r['s']:<10} [{kind}] {r['lbl']} ({r['why']})"


def parse_inputs(texts: list[str]):
    """Yield (company, title, url, extra) from LinkedIn CLI JSON or 'company | title | url' lines."""
    for text in texts:
        text = text.lstrip("﻿").strip()
        if not text:
            continue
        if text[0] in "[{":
            d = json.loads(text)
            jobs = d if isinstance(d, list) else d.get("jobs") or d.get("results") or [d]
            for j in jobs:
                jid = str(j.get("id") or j.get("jobId") or "")
                url = j.get("url") or j.get("link") or (f"https://www.linkedin.com/jobs/view/{jid}" if jid else "")
                yield j.get("company", ""), j.get("title", ""), url, (j.get("location") or "")[:25]
        else:
            for line in text.splitlines():
                p = [x.strip() for x in line.split("|")]
                if len(p) >= 2:
                    yield p[0], p[1], p[2] if len(p) > 2 else "", ""


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, args = argv[0], argv[1:]
    if cmd == "skip":
        if len(args) < 4:
            print("usage: skip <company> <title> <url> <reason>")
            return 2
        with SKIPS.open("a", encoding="utf-8") as f:
            f.write("\t".join([date.today().isoformat()] + [a.replace("\t", " ") for a in args[:4]]) + "\n")
        print("skip recorded")
        return 0
    lk = Lookup()
    if cmd == "q":
        res = lk.find(args[0], args[1], args[2] if len(args) > 2 else "")
        print(fmt(*res) if res else "NEW")
        return 0 if res else 1
    if cmd == "stats":
        from collections import Counter
        print(len(lk.recs), "records,", len(lk.by_id), "portal ids,", len(lk.excl), "excluded employers")
        print(dict(Counter(r["s"] for r in lk.recs)))
        return 0
    if cmd == "check":
        show_all = "--all" in args
        intern = "--intern" in args
        import glob
        files = [f for a in args if not a.startswith("--") for f in (sorted(glob.glob(a)) or [a])]
        texts = [Path(f).read_text(encoding="utf-8-sig") for f in files] if files else [sys.stdin.read()]
        from collections import Counter
        cnt, done, new = Counter(), set(), 0
        for c, t, u, extra in parse_inputs(texts):
            key = (co_key(c), tuple(t_toks(t)), next(iter(sorted(ids_in(u))), ""))
            if key in done:
                cnt["dup-in-input"] += 1
                continue
            done.add(key)
            if intern and not INTERN_RE.search(fold(t)):
                cnt["not-internship"] += 1
                continue
            res = lk.find(c, t, u)
            if res:
                cnt[res[1]["s"]] += 1
                if show_all:
                    print("  HIT", fmt(*res))
                continue
            new += 1
            ids = sorted(ids_in(u))
            print(f"NEW {ids[0] if ids else u[:60]} | {c[:28]} | {t[:80]} | {extra}")
        print(f"-- {new} new; filtered: " + ", ".join(f"{k} {v}" for k, v in cnt.most_common()))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
