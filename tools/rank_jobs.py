#!/usr/bin/env python3
"""Stage II: fit ranking. Every `found` posting of a track in data/jobs.db -> `fit` (kept, scored) or `discarded`.

  python tools/rank_jobs.py [--track T]     # rank the track's found postings (default internship)
  python tools/rank_jobs.py --min 50        # fit threshold (default: the track's DEFAULT_MIN; title-only pass 15 lower)
  python tools/rank_jobs.py --rescore       # also re-rank postings already marked fit / low-fit discarded
  python tools/rank_jobs.py --no-fetch      # title-only scoring (fast, rough)
  python tools/rank_jobs.py --top 15        # how many fit postings to print (default 15)

The verdict comes from the track's decide() function (tools/tracks/<track>.py): already handled ->
title check -> deal-breakers in the description -> fit score. This file only fetches descriptions and stores
the verdicts. The score is a pre-filter. The model still reads each `fit` posting before writing documents.
"""
from __future__ import annotations

import concurrent.futures as cf
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobsdb  # noqa: E402
import seen  # noqa: E402
import tracks  # noqa: E402
from tracks.common import fetch_description  # noqa: E402


def main(argv: list[str]) -> int:
    jobsdb.utf8_out()
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    argv = list(argv)
    track = tracks.from_argv(argv)
    tr = tracks.get(track)
    min_score = int(argv[argv.index("--min") + 1]) if "--min" in argv else tr.DEFAULT_MIN
    top = int(argv[argv.index("--top") + 1]) if "--top" in argv else 15
    con = jobsdb.connect()
    where = "stage='found'"
    if "--rescore" in argv:
        where = "stage='found' OR stage='fit' OR (stage='discarded' AND reason LIKE 'low fit%')"
    rows = con.execute(f"SELECT * FROM postings WHERE track=? AND ({where})", (track,)).fetchall()
    if not rows:
        print(f"nothing to rank (no `found` postings in track {track}). Run `pipeline.py find --track {track}` first.")
        print(jobsdb.stats(con, track))
        return 0
    lk = seen.Lookup()
    # cheap checks first, so only plausible postings are fetched
    pre, need = {}, []
    for r in rows:
        verdict = tr.decide(r, "", lk, -1)  # title-only, no threshold: drops handled / wrong-type / dead titles
        if verdict[0] != "fit":
            pre[r["id"]] = verdict
        else:
            need.append(r)
    if "--no-fetch" in argv:
        bodies = [r["description"] or "" for r in need]
    else:
        with cf.ThreadPoolExecutor(6) as ex:
            bodies = list(ex.map(lambda r: r["description"] or fetch_description(r), need))
    for r, body in zip(need, bodies):
        if body and not r["description"]:
            con.execute("UPDATE postings SET description=? WHERE id=?", (body, r["id"]))
        pre[r["id"]] = tr.decide(r, body, lk, min_score)
    counts: dict[str, int] = {}
    for pid, (st, sc, hits, flags, reason) in pre.items():
        con.execute("UPDATE postings SET stage=?, score=?, hits=?, flags=?, reason=?, updated=? WHERE id=?",
                    (st, sc, hits, flags, reason, jobsdb.now(), pid))
        key = st if st != "discarded" else "discarded:" + reason.split(" ")[0].split(":")[0]
        counts[key] = counts.get(key, 0) + 1
    con.commit()
    print(f"ranked {len(rows)} [{track}]: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    for r in con.execute("SELECT * FROM postings WHERE stage='fit' AND track=? ORDER BY score DESC LIMIT ?",
                         (track, top)):
        print(f"{r['score']:>3} | {r['id']:>5} | {(r['company'] or '')[:24]} | {(r['title'] or '')[:66]} | "
              f"{(r['location'] or '')[:16]} | +{(r['hits'] or '')[:60]}" + (f" | -{r['flags']}" if r['flags'] else ""))
    print(jobsdb.stats(con, track))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
