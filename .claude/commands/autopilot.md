# /autopilot - Keep Applying to the Next Best Fit

Continuous application loop (candidate rule, 2026-11-10): **unless the candidate gives a limit, keep going.** After each application, take the next best-fit job, apply and submit it, and continue. Do not stop to ask, report between jobs, or wait for a "next".

## Arguments (all optional)
- nothing: run until a stop condition below
- `<N>`: stop after N applications submitted in this run
- `until HH:MM`: stop at that local time
- `focus <text>`: only jobs matching the text (title filter on `pipeline.py next` output; add matching queries with `keywords.py --add`)
- `draft`: draft only (no submitting); the loop still continues
- `outreach`: after each submitted application, also run `/outreach` for the next eligible application (cap still 10 per day)

The candidate can say "stop", "pause" or give a new limit at any time. That always wins.

## Setup (once per run)
1. Read `trackers/session_claims.md` and claim a line `autopilot | <session> | running (<date>)`. Never take a job from a site another session has claimed. Pick a different job instead.
2. Rules that stay in force: deal-breakers in `CLAUDE.md`, skip/queue rules in `10-screening-answers.md` ("Unattended runs"), the project-module rules (`11-project-modules.md`, BMS left out), and the Verification Checklist for every CV and letter.

## The loop (inline: no subagents, candidate 2026-11-16)
Everything runs in this session, so keep every step to one compact call (`docs/apply_playbook.md` token rules): `tools/app.py` for documents and records, `ff.all` / `ff.state` / `ff.wait` instead of screenshots, one result line per job.

Repeat:
1. **Pick.** `python tools/pipeline.py next --limit 3` gives `fit` postings from `data/jobs.db` (score order, already-applied ones synced out from the tracker). Take the first one that is not claimed by another session. Pipeline reference: `docs/PIPELINE.md`.
2. **Refill when empty.** `python tools/pipeline.py refill` (stage I keywords + blanket search, stage II rank; run it in the background). Add browser-only boards with `search_all.py ingest`, then `pipeline.py rank`. If a full refill still gives no `fit` posting, stop (see Stop conditions).
3. **Draft** with `docs/apply_playbook.md` A (ends in `python tools/app.py draft <spec.json>` → `DRAFTED ...`, then `pipeline.py mark <id> drafted`). On a skip, `python tools/pipeline.py mark <id> skipped "<reason>"` and go to step 1.
4. **Submit** with playbook B, unless `draft` was given. Login-gated sites: `python tools/portal_login.py login <portal>` first (playbook B4). Ends in `python tools/app.py done ...` (`SUBMITTED`) or `python tools/app.py queue ...` (`QUEUED`: CAPTCHA, missing credential, Easy Apply, unknown question), then `pipeline.py mark <id> applied|queued`. Email-channel jobs go to `email_applications/<Company>_<role>/` and count as queued.
5. **Log** the one result line, then continue at step 1. Do not re-read the documents or re-check the tracker: the tools recorded it.

Every 5 applications, run `python tools/split_tracker.py | tail -8` and print one status line (sent / queued / skipped so far). Then continue without waiting.

## Stop conditions (the only reasons to stop)
- The candidate says stop or pause, or the given `N` / `until` limit is reached.
- No `fit` posting left after a full `pipeline.py refill`.
- The same tool or site fails 3 times in a row and there is no other site left to switch to.
- Browser extension or Gmail logged out / not responding (leave everything queued).

When stopping: mark the claim line `stopped (<reason>)`, run `split_tracker.py`, and give a short table of this run (company, role, score, result: submitted / queued / skipped + reason).
