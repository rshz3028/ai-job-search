#!/usr/bin/env python3
"""Stage I.1: scan the candidate profile -> skill keywords -> job-market search queries in data/jobs.db.

  python tools/keywords.py [--track T]          # rebuild track T's queries from config/tracks/T.json, print them
  python tools/keywords.py --show [--track T]   # print the active queries only
  python tools/keywords.py --add "<query>" [--lang fr|en] [--weight N] [--track T]   # manual extra query
  python tools/keywords.py --off "<query>"                                          # deactivate one query

Tracks (tools/tracks): internship (default), parttime. Each track's families live in config/tracks/<track>.json.
Profile: .claude/skills/job-application-assistant/01-candidate-profile.md (Technical Skills + projects); a family
is on when one of its 'profile' terms appears there, or when it has "always": true.
Queries are stored, not run: tools/search_all.py runs them on every portal of the track.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobsdb  # noqa: E402
import tracks  # noqa: E402

ROOT = jobsdb.ROOT
PROFILE = ROOT / ".claude" / "skills" / "job-application-assistant" / "01-candidate-profile.md"


def profile_terms(text: str) -> list[str]:
    """Skill terms from the Technical Skills section (bullets, split on commas / slashes / parentheses)."""
    m = re.search(r"## Technical Skills(.*?)(\n## |\Z)", text, re.S)
    body = m.group(1) if m else ""
    terms: list[str] = []
    for line in body.splitlines():
        line = re.sub(r"\*\*[^*]+:\*\*", "", line.strip().lstrip("-").strip())
        for t in re.split(r"[,;()/]| and ", line):
            t = t.strip(" .*").lower()
            if 2 <= len(t) <= 30 and not t.startswith("#"):
                terms.append(t)
    return list(dict.fromkeys(terms))


def build(con, track: str) -> list[tuple]:
    text = PROFILE.read_text(encoding="utf-8").lower()
    cfg = tracks.config(track)
    rows = []
    for fam in cfg["families"]:
        hit = [t for t in fam.get("profile", []) if t in text]
        if not (hit or fam.get("always")):
            continue
        src = "profile:" + ",".join(hit[:4]) if hit else "target scope"
        for lang in ("en", "fr"):
            for q in fam.get(lang, []):
                rows.append((q, fam["name"], lang, int(fam.get("weight", 5)), src))
    # keep manual queries and deactivations; replace this track's generated ones
    con.execute("DELETE FROM keywords WHERE source NOT LIKE 'manual%' AND active=1 AND track=?", (track,))
    for q, fam, lang, w, src in rows:
        con.execute("INSERT INTO keywords(query, family, lang, weight, source, active, updated, track) "
                    "VALUES (?,?,?,?,?,1,?,?) "
                    "ON CONFLICT(query) DO UPDATE SET family=excluded.family, weight=excluded.weight, "
                    "source=excluded.source, updated=excluded.updated, track=excluded.track WHERE keywords.active=1",
                    (q, fam, lang, w, src, jobsdb.now(), track))
    con.commit()
    return rows


def active(con, track: str) -> list:
    return con.execute("SELECT * FROM keywords WHERE active=1 AND track=? ORDER BY weight DESC, lang, query",
                       (track,)).fetchall()


def main(argv: list[str]) -> int:
    jobsdb.utf8_out()
    argv = list(argv)
    track = tracks.from_argv(argv)
    con = jobsdb.connect()
    if "--add" in argv:
        q = argv[argv.index("--add") + 1]
        lang = argv[argv.index("--lang") + 1] if "--lang" in argv else ("fr" if q.lower().startswith("stage") else "en")
        w = int(argv[argv.index("--weight") + 1]) if "--weight" in argv else 6
        con.execute("INSERT OR REPLACE INTO keywords(query, family, lang, weight, source, active, updated, track) "
                    "VALUES (?,?,?,?,?,1,?,?)", (q, "manual", lang, w, "manual", jobsdb.now(), track))
        con.commit()
        print(f"added [{track}]: {q}")
        return 0
    if "--off" in argv:
        q = argv[argv.index("--off") + 1]
        n = con.execute("UPDATE keywords SET active=0, source='manual-off' WHERE query=?", (q,)).rowcount
        con.commit()
        print(f"deactivated {n}")
        return 0
    if "--show" not in argv:
        terms = profile_terms(PROFILE.read_text(encoding="utf-8"))
        rows = build(con, track)
        print(f"profile: {len(terms)} skill terms ({', '.join(terms[:14])}, ...)")
        print(f"queries [{track}]: {len(rows)} generated from {len({r[1] for r in rows})} families")
    for r in active(con, track):
        print(f"  w{r['weight']:<2} {r['lang']} | {r['query']:<45} | {r['family']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
