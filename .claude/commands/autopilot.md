# /autopilot - Keep Applying to the Next Best Fit

Continuous application loop (candidate rule, 2026-11-10): **unless the candidate gives a limit, keep going.** After each application, take the next best-fit job, apply and submit it, and continue. Do not stop to ask, report between jobs, or wait for a "next".

## Arguments (all optional)
- nothing: run until a stop condition below
- `<N>`: stop after N applications submitted in this run
- `until HH:MM`: stop at that local time
- `focus <text>`: only jobs matching the text (passed to `/rank --focus` and used as a title filter)
- `draft`: draft only (no submitting); the loop still continues
- `outreach`: after each submitted application, also run `/outreach` for the next eligible application (cap still 10 per day)

The candidate can say "stop", "pause" or give a new limit at any time. That always wins.

## Setup (once per run)
1. Read `trackers/session_claims.md` and claim a line `autopilot | <session> | running (<date>)`. Never take a job from a site another session has claimed. Pick a different job instead.
2. Rules that stay in force: deal-breakers in `CLAUDE.md`, skip/queue rules in `10-screening-answers.md` ("Unattended runs"), the project-module rules (`11-project-modules.md`, BMS left out), and the Verification Checklist for every CV and letter.

## The loop
Repeat:
1. **Pick.** `python tools/next_job.py --limit 3` gives ranked jobs with score ≥ 60, not already in the tracker, and no passed deadline, urgent ones first. Take the first one that is not claimed by another session.
2. **Refill when empty.** If it returns `[]`:
   - `python tools/next_job.py --count`. If `unranked_new` > 0, run `/rank --limit 10` (add `--focus` when given), then go back to step 1.
   - If nothing is unranked, run `/scrape` once with the standard queries (and JobTeaser through Chrome), then `/rank`, then step 1.
   - If a full scrape and rank still gives nothing ≥ 60, stop (see Stop conditions).
3. **Apply.** Run the `/apply` workflow on the job's URL without pausing at its "present the evaluation" step. If `/apply`'s own evaluation scores it below 60 or hits a deal-breaker, mark it skipped in `seen_jobs.json` through `/rank`'s state helper, log the reason in one line, and go to step 1.
4. **Submit.** Run `/submit` on the drafted application (auto-submit is authorized). If it needs an account, password, CAPTCHA, LinkedIn Easy Apply, or an answer not in the screening bank, queue it in `documents/manual_apply_queue.md`, leave the tab open, and go to step 1. Email-channel jobs go to `email_applications/<Company>_<role>/` (see memory) and count as queued, not submitted.
5. **Record** in the tracker straight away (append-only, per `session_claims.md` rule 2), then continue at step 1.

Every 5 applications, run `python tools/split_tracker.py`, update the counts in `trackers/CLAUDE.md`, and print one status line (sent / queued / skipped so far). Then continue without waiting.

## Stop conditions (the only reasons to stop)
- The candidate says stop or pause, or the given `N` / `until` limit is reached.
- No job ≥ 60 left after a full scrape and rank.
- The same tool or site fails 3 times in a row and there is no other site left to switch to.
- Browser extension or Gmail logged out / not responding (leave everything queued).

When stopping: mark the claim line `stopped (<reason>)`, run `split_tracker.py`, and give a short table of this run (company, role, score, result: submitted / queued / skipped + reason).
