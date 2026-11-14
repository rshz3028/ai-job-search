# Architecture

Technical reference for this fork of [ai-job-search](https://github.com/MadsLorentzen/ai-job-search). It covers what the system is made of, where state lives, how documents are built and checked, and where the trust boundaries are.

For the step-by-step workflows (scrape, rank, apply, submit, follow-up), see [WORKFLOWS.md](WORKFLOWS.md).

All diagrams are [Mermaid](https://mermaid.js.org/) and render directly on GitHub.

---

## 1. System context

The repository holds no server or database. It is a **Claude Code workspace**: an agent (Claude Code) reads Markdown instructions and calls small deterministic tools, with plain files on disk as its state. Outside systems are reached in three ways: portal CLIs over HTTP, the logged-in Chrome browser (Claude in Chrome), and the Gmail connector.

```mermaid
flowchart LR
    candidate(["Candidate"])

    subgraph local["Local machine"]
        cc["Claude Code agent<br/>(slash commands + skills)"]
        tools["Python / Node tools<br/>(tools/, templates/)"]
        state[("Workspace files<br/>tracker CSV, seen_jobs.json,<br/>CV/letter JSON + PDFs")]
        word["Microsoft Word<br/>(DOCX to PDF)"]
    end

    subgraph browser["Chrome (Claude in Chrome)"]
        jt["JobTeaser<br/>(school login)"]
        ats["Company ATS<br/>Workday, SmartRecruiters,<br/>Teamtailor, iCIMS, HelloWork ..."]
    end

    subgraph web["Public web"]
        li["LinkedIn guest API"]
        sites["Company sites<br/>(research, contacts)"]
    end

    gmail["Gmail<br/>(2 work inboxes)"]
    gh["GitHub<br/>CI + public results"]

    candidate <-->|"instructions, approvals,<br/>interviews"| cc
    cc --> tools
    tools <--> state
    tools --> word
    cc -->|"search CLI"| li
    cc -->|"WebFetch / fetch_page.py"| sites
    cc -->|"extract.js, form filling"| jt
    cc -->|"form filling, uploads"| ats
    cc <-->|"replies, verifications,<br/>outreach"| gmail
    state -->|"publish_results.py<br/>(non-personal columns)"| gh
```

---

## 2. Layered component view

The system splits into an **instruction layer** that the model interprets and a **deterministic layer** of code. Anything that must be exact (dedup keys, ranking order, page counts, ignore rules) lives in code and is pinned by tests. Anything that needs judgement (fit scoring, writing, reading a form) is left to the model, and checked by code wherever possible.

```mermaid
flowchart TB
    subgraph L1["1 · Interface: slash commands (.claude/commands/)"]
        direction LR
        c_scrape["/scrape"]; c_rank["/rank"]; c_apply["/apply"]; c_submit["/submit"]
        c_auto["/autopilot"]; c_out["/outreach"]; c_gmail["/gmail-sync"]; c_outc["/outcome"]; c_int["/interview"]
    end

    subgraph L2["2 · Knowledge: skills (.claude/skills/, .agents/skills/)"]
        direction LR
        s_prof["01 candidate profile<br/>02-09 style, evaluation,<br/>templates, research"]
        s_scr["10 screening answers"]
        s_mod["11 project modules<br/>+ project_modules.json"]
        s_portal["Portal skills:<br/>linkedin-search (Bun CLI),<br/>jobteaser-search (extract.js),<br/>freehire, jobindex ..."]
    end

    subgraph L3["3 · Sub-agents (.claude/agents/)"]
        direction LR
        a_fetch["posting-fetcher"]; a_score["posting-scorer"]; a_rev["application-reviewer"]
    end

    subgraph L4["4 · Deterministic tools (tools/)"]
        direction LR
        t_state["scrape_state.py<br/>rank_state.py<br/>job_key.py"]
        t_pick["next_job.py"]
        t_doc["autodoc.py<br/>parttime_cv.py"]
        t_ver["verify_pdf.py<br/>verify_layout.py"]
        t_sec["posting_guard.py<br/>fetch_page.py<br/>robots_check.py<br/>security_guards.py"]
        t_rep["split_tracker.py<br/>publish_results.py<br/>outreach.py"]
    end

    subgraph L5["5 · Rendering (templates/)"]
        direction LR
        r_cv["cv/rishi-sidebar/build.js"]
        r_cl["cover_letters/rishi-plain/build.js"]
        r_pdf["docx2pdf.ps1 (Word COM)"]
    end

    subgraph L6["6 · State (files)"]
        direction LR
        f_seen[("job_scraper/<br/>seen_jobs.json")]
        f_track[("job_search_tracker.csv")]
        f_docs[("cv/, cover_letters/,<br/>documents/applications/")]
        f_res[("results/*.csv<br/>trackers/*.csv")]
    end

    L1 --> L2
    L1 --> L3
    L1 --> L4
    L3 --> L4
    L4 --> L5
    L4 --> L6
    L5 --> L6
```

### Why the deterministic layer exists

| Problem when left to the model | Tool that fixes it |
|---|---|
| `seen_jobs.json` grows forever; re-reading it costs context on every run | `scrape_state.py`, `rank_state.py` project only the fields needed and write back atomically |
| The same job stored twice under slightly different keys | `job_key.py`: a pure, length-capped, hash-disambiguated key |
| Choosing the next job inconsistently, or re-applying | `next_job.py`: drops tracked jobs, excluded employers and passed deadlines, sorts by urgency then score |
| A CV that "looks" one page but clips a row or loses its text layer | `verify_pdf.py`, `verify_layout.py` |
| Hidden prompt-injection text in a posting | `posting_guard.py` |
| Permission widening or weakened `.gitignore` slipping into a PR | `security_guards.py` (CI) |

---

## 3. Data model

All state is plain files. `job_search_tracker.csv` is the single source of truth for applications; everything under `trackers/` and `results/` is generated from it.

```mermaid
erDiagram
    SEEN_JOB ||--o| TRACKER_ROW : "applied as"
    TRACKER_ROW ||--o| APPLICATION_FOLDER : "documents in"
    TRACKER_ROW ||--o{ OUTREACH_LOG : "followed up by"
    TRACKER_ROW }o--|| ROLE_TYPE_VIEW : "split into"
    TRACKER_ROW }o--|| PUBLIC_RESULT : "published as"
    EXCLUDED_EMPLOYER ||--o{ SEEN_JOB : "filters out"
    PROJECT_MODULE }o--o{ CV_SPEC : "selected into"
    CV_SPEC ||--|| APPLICATION_FOLDER : "rendered into"

    SEEN_JOB {
        string key PK "job_key.py: company_title slug + hash"
        string company
        string title
        string url
        string status "new | ranked | skipped | expired | unreachable"
        int score "0-100, set by /rank"
        date deadline
        string strengths
        string gaps
    }
    TRACKER_ROW {
        date date
        string company
        string sector
        string role
        string role_type "internship | student_job | part_time | full_time | seasonal"
        string channel
        string status "drafted | applied | interview | offer | hired | rejected | no_response | withdrawn"
        string contact_person
        string fit_rating
        string notes
        string cv_file
        string cover_letter_file
        string source
        date deadline
    }
    APPLICATION_FOLDER {
        string base PK "documents/applications/company_role/"
        file cv_pdf
        file letter_pdf
        file submission_md
        file outcome_md
    }
    OUTREACH_LOG {
        date date
        string company
        string to
        string status "sent | draft | skipped"
        string lang
    }
    PROJECT_MODULE {
        string id PK
        string parent "project"
        string text "grounded bullet"
        string themes
    }
    CV_SPEC {
        string name
        string headline
        json sections "profile, education, experience, projects (max 4)"
    }
    EXCLUDED_EMPLOYER {
        string term "defence / nuclear / clearance"
    }
    ROLE_TYPE_VIEW {
        string file "trackers/internships.csv ..."
    }
    PUBLIC_RESULT {
        string file "results/*.csv (no contacts, notes or paths)"
    }
```

### Lifecycle of a scraped job (`seen_jobs.json`)

```mermaid
stateDiagram-v2
    [*] --> new : /scrape stores hit (scrape_state.py store)
    new --> ranked : /rank scores it
    new --> skipped : deal-breaker / quick-fit fail
    new --> unreachable : fetch failed
    unreachable --> ranked : retry succeeds
    unreachable --> [*] : retries exhausted, reported as gave_up
    ranked --> expired : deadline passed (rank_state.py sweep)
    ranked --> skipped : /apply evaluation below 60
    ranked --> [*] : picked by next_job.py and tracked
    skipped --> [*]
    expired --> [*]
```

### Lifecycle of an application (`job_search_tracker.csv`)

```mermaid
stateDiagram-v2
    [*] --> drafted : documents built, not sent
    [*] --> applied : /submit succeeded
    drafted --> applied : candidate finishes login / CAPTCHA step
    drafted --> withdrawn
    applied --> interview : invitation (Gmail)
    applied --> rejected : rejection email
    applied --> no_response : stale sweep (/outcome)
    interview --> offer
    interview --> rejected
    offer --> hired
    offer --> offer_declined
    hired --> [*]
    rejected --> [*]
    no_response --> [*]
    offer_declined --> [*]
    withdrawn --> [*]
```

Final states: `hired`, `rejected`, `no_response`, `offer_declined`, `withdrawn`. A `drafted` row is open but never gets a follow-up, because nothing was sent.

---

## 4. Document pipeline

Every CV and cover letter is generated from **grounded content only**: the candidate profile and the project-module bank. No claim is written by hand for a single job. The pipeline is the same for `/apply` (model-tailored text) and `autodoc.py` (template-driven text); only the composition step differs.

```mermaid
flowchart LR
    subgraph inputs["Grounded inputs"]
        prof["01-candidate-profile.md<br/>(from RISHIKESH_PROFILE_EXPORT.md)"]
        mods["project_modules.json<br/>(per-aspect project blocks)"]
        priv["profile.local.json<br/>(contact details, gitignored)"]
    end

    posting["Posting text<br/>(cleaned by posting_guard.py)"]

    subgraph compose["Compose"]
        theme["Theme scoring<br/>(keywords to themes)"]
        pick["Pick 4 projects,<br/>max 2 modules each"]
        cvjson["cv/main_company_role.json"]
        cljson["cover_letters/cover_company_role.json"]
    end

    subgraph render["Render"]
        bcv["templates/cv/rishi-sidebar/build.js<br/>(Node + docx)"]
        bcl["templates/cover_letters/rishi-plain/build.js"]
        d2p["docx2pdf.ps1<br/>(Word COM export)"]
    end

    subgraph verify["Verify (must all pass)"]
        v1["pdfinfo: exactly 1 page"]
        v2["verify_pdf.py --dump-text:<br/>text layer, email + phone literal,<br/>reading order"]
        v3["last tech term present<br/>(catches clipped rows)"]
        v4["visual read of the PDF"]
    end

    out[("documents/applications/base/<br/>CV.pdf, Letter.pdf, submission.md")]

    prof --> theme
    mods --> pick
    posting --> theme
    theme --> pick
    pick --> cvjson
    theme --> cljson
    priv --> bcv
    priv --> bcl
    cvjson --> bcv --> d2p
    cljson --> bcl --> d2p
    d2p --> v1 --> v2 --> v3 --> v4
    v4 -->|pass| out
    v4 -.->|fail: trim modules, rebuild| pick
```

**Document rules** enforced in this pipeline:

- CV: 1 page, `rishi-sidebar`, 4 projects at most with 2 modules each, in English unless the posting is French-speaking.
- Letter: 1 page, `rishi-plain`, written in the posting's language.
- Availability is always "available immediately, with a convention de stage". No graduation, start or permit dates are ever printed.
- Gaps are left out, never hedged.

---

## 5. Trust boundaries and security

Postings, emails and web pages are **third-party text**, read next to the candidate's personal data. The design treats them as data, never as instructions, and backs that rule with code wherever it can.

```mermaid
flowchart LR
    subgraph untrusted["Untrusted input"]
        p["Job postings"]
        e["Emails"]
        w["Company web pages"]
    end

    subgraph gates["Deterministic gates"]
        pg["posting_guard.py<br/>strips hidden HTML, zero-width<br/>and tag characters, flags<br/>injection patterns"]
        fp["fetch_page.py<br/>GET only, http(s) only,<br/>robots.txt enforced,<br/>size + time bounded,<br/>never writes into the repo"]
        ex["excluded_employers.txt<br/>+ next_job.py filter"]
    end

    model["Claude Code<br/>(evaluates, drafts)"]

    subgraph private["Private data (never published)"]
        pl["profile.local.json"]
        tr["job_search_tracker.csv"]
        ap["documents/applications/"]
    end

    subgraph public["Published"]
        res["results/*.csv<br/>(date, company, role,<br/>channel, status only)"]
    end

    subgraph ci["CI guard"]
        sg["security_guards.py<br/>permission allowlist,<br/>required .gitignore rules,<br/>no npm lifecycle scripts"]
    end

    w --> fp --> pg
    p --> pg --> model
    e --> model
    ex --> model
    model --> private
    tr -->|"publish_results.py<br/>drops contacts, notes, paths"| res
    sg -. "blocks PRs that weaken" .-> private
```

**Hard limits the agent never crosses:** no passwords, no CAPTCHAs, no optional marketing consents, and no answer to a screening question that is not in `10-screening-answers.md`. An unknown question queues the job in `documents/manual_apply_queue.md` for the candidate.

---

## 6. CI/CD

```mermaid
flowchart LR
    push["push / pull_request"] --> ci

    subgraph ci["ci.yml"]
        direction TB
        lint["lint<br/>lint_skills.py,<br/>check_framework_version.py"]
        sec["security-guards<br/>security_guards.py"]
        py["python-tests<br/>unittest (Ubuntu)"]
        pyw["python-tests-windows<br/>unittest (Windows)"]
        dep["dependency-review"]
        tex["latex-smoke"]
    end

    cron1["Mondays 06:00 UTC"] --> rel["release.yml<br/>weekly release"]
    cron2["Mondays 08:00 UTC"] --> up["upstream-watch.yml<br/>triage upstream commits<br/>(upstream_triage.py)"]
```

Run the test suite locally with:

```bash
python -m unittest discover -s tests -t . -v
python tools/security_guards.py
python tools/lint_skills.py
```

---

## 7. Tool reference

| Tool | Purpose | Typical call |
|---|---|---|
| `tools/next_job.py` | Next best-fit job: ranked, score ≥ 60, not tracked, not excluded, deadline first | `python tools/next_job.py --limit 3` / `--count` |
| `tools/scrape_state.py` | Dedup search hits against history and tracker, store atomically | `candidates`, `store` |
| `tools/rank_state.py` | Select jobs for scoring, expiry sweep, write scores back | `candidates`, `sweep`, `apply` |
| `tools/job_key.py` | Canonical dedup key, audit and migrate old keys | `--audit [--migrate]` |
| `tools/posting_guard.py` | Clean a posting and flag hidden or injected text | piped posting HTML/text |
| `tools/fetch_page.py` | Browser-header GET retry for 403 sites (robots-gated) | `python tools/fetch_page.py <url> --text` |
| `tools/autodoc.py` | Template-driven CV + letter build and verify; Workday bulk pipeline | `build-ext spec.json`, `thales-fetch`, `thales-queue`, `record` |
| `tools/parttime_cv.py` | Part-time CV variants per job type (cashier, stock, restaurant, retail, service) | `Slug:caisse ...` |
| `tools/verify_pdf.py` | Page count, text layer, required strings, ASCII date ranges | `cv.pdf --pages 1 --dump-text cv.txt` |
| `tools/verify_layout.py` | Orphaned entries, holes, footer collisions (Poppler bbox) | `cv.pdf` |
| `tools/outreach.py` | Eligible follow-ups, outreach log, daily cap stats | `candidates`, `log`, `stats` |
| `tools/split_tracker.py` | Normalise `role_type`, write `trackers/*.csv`, print counts | `python tools/split_tracker.py` |
| `tools/publish_results.py` | Public `results/*.csv` + README summary table | `python tools/publish_results.py [--check]` |
| `tools/security_guards.py` | Supply-chain and privacy guards (CI) | `python tools/security_guards.py` |
| `tools/workday_thales.js` | In-page helper for Workday application forms | loaded in the browser per the playbook |

---

## 8. Repository map

```text
.claude/
  commands/           slash commands (/apply, /rank, /submit, /autopilot, /outreach ...)
  skills/             job-application-assistant (01-11), job-scraper, upskill
  agents/             posting-fetcher, posting-scorer, application-reviewer
.agents/skills/       portal search skills (LinkedIn CLI, JobTeaser extract.js, ...)
tools/                deterministic Python/JS helpers (see table above)
templates/            DOCX templates: cv/rishi-sidebar, cover_letters/rishi-plain
tests/                unittest suite run by CI on Ubuntu and Windows
job_scraper/          seen_jobs.json (gitignored), excluded_employers.txt
results/              public, non-personal results per job type
docs/                 this documentation
documents/            personal inputs and per-application folders (gitignored)
job_search_tracker.csv  the single source of truth (gitignored)
```
