# Token efficiency report (2026-11-15)

## 1. Where the tokens went (measured baseline)

Source: the 11 Claude Code transcripts of this project (11-15 Nov 2026), via `python tools/token_report.py --sources`.

| Measure | Value |
|---|---|
| Sessions / model turns | 11 / 1,945 |
| Tokens processed (read by the model, all turns) | **602 M** |
| Tokens written (output) | 1.2 M |
| Applications sent in that period (tracker) | 117 |
| **Processed tokens per application sent** | **5.1 M** |
| Context at the start of a session | 52-59 k |
| Average context per turn, long sessions | 216-433 k |
| Peak context | 804 k (compacted once in 11 sessions) |

**Why it is so large:** every turn re-reads the whole conversation. Each token added to the context was re-read about 225 times on average. So the cost is driven by **context size x number of turns**, not by the size of any one file.

What filled the context (share of all context growth):

| Source | Share |
|---|---|
| Browser automation (clicks, JS, screenshots, page text) | 57 % |
| Shell output (inline Python, cat / grep / sed on the 340 KB tracker, logs) | 27 % |
| Gmail checks | 6 % |
| File reads (PDF visual checks, docs) | 5 % |
| Tool-schema loading | 4 % |
| Skill / command files, CLAUDE.md | < 1 % |

## 2. What changed and what each change does

| # | Change | Files | Measured effect |
|---|---|---|---|
| 1 | **One fresh context per application.** `/autopilot` became a thin loop that only picks jobs and dispatches an `applicant` agent (draft + verify + record) and a `submitter` agent (form + verify-email + record). Each returns 1-8 lines. Lean 1.5 k-token playbook replaces the 11 k-token `/apply` on this path. | `.claude/commands/autopilot.md`, `.claude/agents/applicant.md`, `.claude/agents/submitter.md`, `docs/apply_playbook.md` | Replay of the real per-turn context of the 10 past sessions, with every application restarting from a fresh context: **594 M → 181 M processed (-70 %)**. Assumes each agent starts at 52 k like a main session; at 40 k it is -73 %. |
| 1b | **Auto-compact window 300 k** (backstop for long manual sessions) | `tools/hooks/settings.proposed.json` → `.claude/settings.json` (**you apply it, see §4**) | 6 of the 10 past sessions went past 300 k (peaks of 366-804 k). With the window, they compact at 300 k instead of growing further. |
| 2 | **Form helper** `tools/form_fill.js`: `ff.scan / fill / consent / file / fileBack / click / text`. Bilingual label matching (Chrome auto-translate). | `tools/form_fill.js` | Past: 1,596 browser calls for 117 applications = **13.6 calls per application**, many with screenshots (~1.5 k tokens each). Local test form: 1 JS call filled 7 fields (text, email, select, radio, textarea), 1 call ticked only the required consent (not the newsletter), shadow-DOM file upload worked. A scan returns ~600 characters instead of a screenshot. Real-portal effect: measure with `token_report.py` after the next batch. |
| 3a | **Tracker CLI** `tools/tracker.py find / has / company / add / set / stats`. One line per row; `set` rewrites only that row (tested: 1 physical line changed, file otherwise byte-identical). | `tools/tracker.py` | Past: 124 shell commands on the CSV, 3,715 characters each on average. Same lookups now: "decathlon" 1,451 → 428 chars (**-71 %**), "renault" 18,988 → 3,206 chars (**-83 %**). |
| 3b | **Build + verify in one call** `tools/build_verify.py`: builds both documents and prints one PASS/FAIL line per check. Two new checks: no end/graduation date, no banned terms. | `tools/build_verify.py` | One CV + letter, all checks: 5,135 → 421 characters (**-92 %**). Past: 37 separate verify commands, 2,103 characters each. |
| 4 | **Inbox check moved to a Haiku agent**, skipped when checked within 4 h, searches only since the last check, drops pure-noise senders (job alerts, social). Only application sessions do it. | `.claude/agents/inbox-checker.md`, `tools/inbox_state.py`, `CLAUDE.md` | This session's inline check added **34 k tokens** to the main context (53.8 k → 87.5 k), re-read on every later turn: about 10 M processed tokens over a 300-turn session. Agent version (live test, 72 h window, 90 messages): the main context receives a **~0.5 k-token digest**; the agent itself processed 1.1 M tokens in 14 turns, on a cheaper model. Net: about -85 % for a long session. For a session under ~30 turns the inline check would have been cheaper, so the 4 h skip rule matters. |
| 5 | **graphify hook scoped to code.** It now stays silent for tracker, site-notes and document lookups, and code lookups behave as before. The graphify section moved out of `CLAUDE.md` into `docs/graphify.md`. | `tools/hooks/graphify_scope.py` (needs the settings in §4), `docs/graphify.md`, `CLAUDE.md` | Replay of 208 past calls that triggered the stock hook: **111 would trigger now (-47 %)**. Test: tracker lookup nudge 681 → 0 chars, site-notes lookup 296 → 0, code lookups unchanged. `CLAUDE.md` 8,484 → 8,198 bytes even after adding the new tool lines. |
| 6 | **Model routing.** `posting-fetcher`, `posting-scorer` → Haiku; `application-reviewer`, `submitter`, `inbox-checker` → Sonnet; `applicant` keeps the main model for writing. | `.claude/agents/*.md` | Changes the price per token, not the count. Haiku and Sonnet tokens cost less than the main model's. `inbox-checker` was first set to Haiku, but the live test found Haiku miscounted the Chrome inbox (6 messages reported, 49 real), so it runs on Sonnet. |
| 7 | **Measurement tool** `tools/token_report.py`: per session, per day, per application; `--sources` shows what filled the context. | `tools/token_report.py` | Produced every baseline number above. |

**Dropped:** hiding the six unused commands (`notion-sync`, `add-portal`, `add-template`, `setup`, `reset`, `expand`) would save about 120 tokens per turn (≈ 0.04 %), but it broke two upstream spec tests, so it was reverted.

## 3. Expected result

| | Before (measured) | After (projected) |
|---|---|---|
| Processed tokens per application | 5.1 M | ≈ 1.5 M (change 1 alone, -70 %) |
| Main-session context during `/autopilot` | grows 30-60 k per application, up to 804 k | ≈ 1 k per application (one result line + dispatch) |
| Inbox check in the main context | ≈ 34 k tokens, every session | 12-line digest, skipped if checked < 4 h ago |
| Tracker lookup | 1.5-19 k characters | 0.4-3 k characters |
| Verify output per application | ≈ 5 k characters | ≈ 0.4 k characters |

Changes 2-5 also shrink the context inside each agent, so they add to the -70 %. They are not stacked in the projection, to keep it conservative.

Checked: tracker CLI (read, write, error cases), `build_verify.py` (real CV and letter, 12/12 PASS), form helper (local test form in Chrome), hook wrapper (4 payloads), inbox agent (two live runs: the first, on Haiku, under-counted the Chrome inbox; after hardening, the Sonnet run matched a manual count, 48 vs 49), test suite (953 tests: no new failures; the 7 failures are 4 already failing on the committed version + 3 caused by the personalised skip-worktree profile files).

## 4. What you need to do

1. ~~**Apply the settings**~~ **Done 2026-11-15** (copied by you, checked identical and valid JSON). This turns on the 300 k auto-compact window and the scoped graphify hook, allows the new tools, and removes the four Danish job-portal permissions that are not used here.
2. **Start a new session.** The `applicant`, `submitter` and `inbox-checker` agents and the new `CLAUDE.md` load only at session start.
3. Optional: in `/mcp`, disable the connectors this project does not use (Adobe, Google Calendar, Google Drive, Claude Docs). Their instructions and tool names are loaded on every turn.
4. After the next `/autopilot` batch, run `python tools/token_report.py --since 2026-11-16` and compare the "per app" column with the 5.1 M baseline.

## 5. Second pass (2026-11-18): inline sessions

Since 2026-11-16 everything runs inline (candidate: no subagents), so change 1 no longer applies. Measured over 19 sessions / 90 applications: **4.6 M processed tokens per application**. Tool results that entered the main context (8.7 M chars):

| Source | Share | Fix |
|---|---|---|
| `browser_batch` (mostly with screenshots: 397 images) + 101 standalone screenshots | 47 % + 7 % | `ff.state()` (~300 chars) and `await ff.wait()` replace screenshot / wait chains; local test: submit → confirmation in one call, 1.2 s, ~200 chars instead of a ~6 k-char screenshot |
| Re-typed board-scraping JS (Glassdoor, HelloWork, LinkedIn web, WTTJ) | ~5 % | `tools/board_extract.js` (`jb.run()`), selectors from past working scripts, output feeds `seen.py check`; `seen.py` now also matches Glassdoor `jl=` and HelloWork ids |
| Reading + pasting `form_fill.js` (10.4 k chars each) | ~1 % | `tools/ff_inject.py` prints a minified 8 k line; never Read the source |
| Inline Python to copy/patch CV JSON, then build, archive, tracker add (23+ scripts, ~4 k chars each, written as output tokens) | largest shell cost | `tools/app.py like` + `app.py draft <spec>`: one call, only changed fields travel, output 1-3 lines (`--keep` reruns after an Edit fix) |
| `tracker.py set` + heredoc `submission.md` / queue line per job | ~1 % | `app.py done` / `app.py queue`: one line in, one line out |
| Five separate session-start commands | small | `tools/start.py`: ~6 lines |
| ToolSearch (76 calls, 2.5 k each) | 2 % | playbook gives one canonical select line for all browser tools |

Not projected as a single number: the screenshot share alone is ~40 % of context growth, so per-application cost should drop well below 4.6 M if screenshots stop. Check after the next batch: `python tools/token_report.py --since 2026-11-19`.
Checked: `tests/test_app_tools.py` (8 tests), `app.py` draft → fail → `--keep` → done → queue end to end (test rows removed), helpers in Chrome on a local form, full suite 961 tests with the same 7 pre-existing failures (a stray BOM in `tracker.py` that broke one compile test was removed).
