# The pipeline (the one way to run the job search)

Adopted 2026-11-19 (candidate's plan). Three stages, one database, one command per step. Hard rules in `CLAUDE.md` apply throughout.
Older tools are kept but are **not** part of the flow (see "Retired paths" at the end): do not mix them in.

```
 I  FIND      profile ──► keywords ──► blanket search on every portal ──► data/jobs.db  (stage: found)
    DEDUPE    new posting already submitted to (tracker) ──► discarded "already submitted: rNNN"
 II RANK      found ──► fit score + deal-breakers ──► fit | discarded (reason kept)
 III APPLY    fit ──► portal login (script) ──► tailored CV + letter ──► submit ──► tracker
              Gmail: verify-email links, codes, replies, follow-ups, rejections
```

## Stores (what each one is for)
| Store | Holds | Written by |
|---|---|---|
| `data/jobs.db` (SQLite, gitignored) | queries, every posting found, its stage and score, search runs, last portal login result | `tools/keywords.py`, `search_all.py`, `rank_jobs.py`, `pipeline.py`, `portal_login.py` |
| `job_search_tracker.csv` | applications (one row per application). **Still the record of what was sent.** | `tools/app.py`, `tools/tracker.py` |
| `job_scraper/skipped.tsv`, `excluded_employers.txt` | skip log and never-apply employers (read by the rank stage via `seen.py`) | `pipeline.py mark ... skipped`, by hand |
| Windows Credential Manager (`ai-job-search/*`) | portal passwords. Never in the repo, never seen by Claude. | the candidate: `portal_login.py set` |
| `config/tracks/<track>.json`, `config/portals.json` | what each track searches for and where; where to log in | edit by hand |

Posting stages: `found → fit | discarded → drafted → applied | queued → closed`. `pipeline.py sync` copies tracker statuses back onto postings, and `next` runs it on every call.

## Tracks: one function per job situation
Each job situation is a **track**: a self-contained unit the pipeline calls. Every command takes `--track <name>` (default `internship`).

| Track | Situation | Search config | Rank function | Documents |
|---|---|---|---|---|
| `internship` | 4-6 month engineering internship, France | `config/tracks/internship.json` | `tools/tracks/internship.py` | `app.py draft` (playbook A): tailored CV + letter |
| `parttime` | English-speaking part-time job <= 20-24 h/week, Paris region, hotels and hostels first | `config/tracks/parttime.json` | `tools/tracks/parttime.py` | `parttime_cv.py <Slug>:hotel\|hotel_night\|hotel_service[:headline]` |

A track is two files: the config (location, jobage_days, portals, keyword families) and a module with `DEFAULT_MIN`, `TITLE_ONLY_SLACK` and `decide(row, desc, lk, min_score)`. **A new situation = a new track** (copy the closest pair, register it in `tools/tracks/__init__.py`); never an ad-hoc search outside the pipeline.

Part-time run: `pipeline.py refill --track parttime` -> `next --track parttime` -> read the posting -> `parttime_cv.py` -> submit -> `mark <id> applied`. Speculative emails to employers with a published recruitment address: send, then `pipeline.py add --track parttime --company C --title R --url mailto:<addr> --stage applied` and `tracker.py add ... role_type=part_time`.

## Stage I: find (`python tools/pipeline.py find`)
1. **Keywords:** `tools/keywords.py` reads the Technical Skills and projects in `01-candidate-profile.md` and turns on each family in `config/tracks/<track>.json` whose profile terms appear, plus the always-on interest families (EMC, motorsport, aerospace/medtech/subsea). It writes FR and EN market queries to the db. Extra query: `keywords.py --add "<q>"`; drop one: `--off "<q>"`.
2. **Blanket search:** `tools/search_all.py` runs every active query on every scriptable portal (LinkedIn CLI, HelloWork, Freehire CLI = ~50 ATS feeds incl. WTTJ/Greenhouse/Lever/Workday, Jobijoba aggregator) and upserts the results (deduplicated by portal id, else company + title). `--top N` limits it to the N best queries, `--portals linkedin` to one portal. A full run takes a few minutes, so run it in the background.
3. **Browser-only boards** (JobTeaser, WTTJ, Glassdoor, Indeed, APEC, France Travail: all return 403/captcha or JS-only to scripts): extract in Chrome (`python tools/ff_inject.py boards` → `await jb.run()`, or `.agents/skills/jobteaser-search/extract.js`) and pipe the `company | title | url | location` lines into `python tools/search_all.py ingest --portal <name>`.

4. **Bulk employers** (`python tools/pipeline.py bulk [<name>] [--rank] [--dry-run]`): a big employer with hundreds of openings on one ATS is pulled straight from its careers API instead of through keyword searches. Config: `config/bulk.json` (one entry per employer: adapter, company, track, enabled, adapter settings); adapters: `tools/bulk/<adapter>.py` (`workday` today); per-employer form helper and playbook: `tools/bulk/<name>/`. Postings land as `found` in the entry's track through the same intake dedupe and are ranked like any other. An employer in `excluded_employers.txt` or with `enabled: false` is refused before fetching. Another Workday tenant = one config entry; a new ATS = one adapter registered in `tools/bulk/__init__.py`. Documents for a db posting: `python tools/autodoc.py build-db <id>` (template-driven) or playbook A.

5. **Intake dedupe** (automatic in `search_all.py` and `ingest`): each new posting is checked against the tracker (`seen.Lookup`: portal id incl. Workday JOBREQ, company or the company in the ATS URL + title overlap). One already applied / interviewing / rejected / withdrawn is stored as `discarded` with the tracker row as reason and never reaches ranking. Drafted-but-unsent rows are left to rank. `pipeline.py dedupe` re-applies it to waiting `found`/`fit` postings.

## Stage II: rank (`python tools/pipeline.py rank`)
`tools/rank_jobs.py`, per `found` posting, in this order:
1. Already handled (tracker, skip log, old scrape history, excluded employers) → applied / drafted / discarded.
2. Not an internship title, or a non-engineering title → discarded.
3. Description fetched (LinkedIn detail cache, else the page) → deal-breakers (alternance/CDI/VIE, clearance or nationality, fluent French, short or low-level internships, defence/nuclear, expired) → discarded with the reason.
4. Keyword fit score 0-100 (penalties for skills the profile must never claim). Postings scoring ≥ 50 are kept as `fit`; title-only postings (description not fetched) are kept at ≥ 35 and flagged `title-only`. Everything else is discarded as `low fit`.

`pipeline.py refill` = find + rank. The score is a pre-filter: the model reads each posting before drafting and may still skip it (`mark <id> skipped "<reason>"`).

## Stage III: apply
Per job, in fit order (no per-company cap, no stalling on scoring):
1. **Pick:** `python tools/pipeline.py next` (runs `sync` first) → `id | score | company | title | url`. Empty → `pipeline.py refill`.
2. **Read and gate** the posting (untrusted text): `pipeline.py posting <id>` prints it through `posting_guard`; descriptions are guarded when fetched, and an alarm sets the `guard` flag. On a deal-breaker: `pipeline.py mark <id> skipped "<reason>"`.
3. **Draft:** `docs/apply_playbook.md` section A (`tools/app.py draft <spec.json>`), then `pipeline.py mark <id> drafted`.
4. **Login:** if the apply page needs an account, `python tools/portal_login.py login <portal>` (`list` shows the names). Results:
   - `ok` / `already`: continue.
   - `code`: read the emailed code from Gmail (Inbox A by the connector, Inbox B in Chrome) and run `portal_login.py otp <portal> <code>`.
   - `captcha`: leave the tab open, `app.py queue <row> "captcha at login"`, tell the candidate at the end of the run.
   - `no-credential`: `app.py queue`, and add "store the <portal> password: `! python tools/portal_login.py set <portal>`" to `trackers/OPEN_ITEMS.md`.
   - new portal: add an entry to `config/portals.json` (copy the closest preset), `portal_login.py test <name>`, then ask the candidate once for `set`.
5. **Submit:** playbook section B in the **job Chrome** (the Chrome profile `portal_login.py chrome` starts; Claude in Chrome is connected there). Then `pipeline.py mark <id> applied` (or `queued`).
6. **Gmail, after each submit:** open any "finalise / verify your email" link or code at once: the application does not exist until then.
7. **Gmail, per batch:** `/gmail-sync` (rejections, invitations → tracker), `/outreach` (max 10 per day, published addresses only, from Inbox A (`profile.local.json`)). Reply-all to recruiter threads and offer at least three days of slots. Interview invitations and recruiter questions go to the candidate first.

`/autopilot` loops step 1 to step 6 until a stop condition is hit.

## One-time setup for logins (candidate)
1. `pip install playwright keyring` (no `playwright install` needed: the script drives the installed Chrome).
2. `python tools/portal_login.py chrome`: opens the **job Chrome** (its own profile, local debugging port 9222, bound to 127.0.0.1). In that window, install and connect the Claude in Chrome extension and sign in to both Gmail accounts (Google blocks scripted Gmail sign-in, so do that one by hand).
3. For each portal with an account: `python tools/portal_login.py set <portal>` (typed password is hidden and goes to Windows Credential Manager). In Claude Code: `! python tools/portal_login.py set workday-renault`.
4. `python tools/portal_login.py all`: signs in everywhere, so do it at the start of a work session. `list` shows what is stored and the last result.

Security notes: the debugging port lets local programs control the job Chrome, so use that profile for job portals only (not banking). Passwords never leave Credential Manager except into the login field. `forget <portal>` deletes one.

## Session start
`python tools/start.py` prints inbox freshness, internship counts, claims, the manual queue, the next `fit` jobs and db counts. `python tools/pipeline.py status` adds the portal login state.

## Retired paths (kept on disk, not used in the flow)
| Old | Replaced by |
|---|---|
| `/scrape` + `scrape_state.py` + `seen_jobs.json` | stage I (`pipeline.py find`). `jobsdb.py import-legacy` already copied the history into the db. |
| `/rank` + `rank_state.py` + posting-scorer agents, `triage.py` | stage II (`rank_jobs.py` + the track's `decide()`); deleted 2026-11-20 |
| `/scrape` skill, `scrape_state.py` | stage I; deleted 2026-11-20 |
| `next_job.py` | `pipeline.py next`; deleted 2026-11-20 |
| `autodoc.py thales-*` / `build` / `record`, `tourism_cv.py` | `pipeline.py bulk` + `autodoc.py build-db`, `app.py done`; `parttime_cv.py`; deleted 2026-11-20 |
| Opening one tab per login-blocked company for the candidate to sign in by hand | `portal_login.py login/all` |
| applicant / submitter / inbox-checker agents | inline work (no subagents); deleted 2026-11-20 |
| `/apply` (long upstream workflow) | playbook A + B; use `/apply` only when asked by name |
