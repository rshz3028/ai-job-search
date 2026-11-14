# Workflows

How a job goes from a search result to a submitted application, then to a follow-up and an outcome. Each section names the command or tool that runs the step. For the components and data model behind these steps, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 1. End-to-end pipeline

```mermaid
flowchart LR
    start(["Session start"]) --> inbox["Check both work inboxes<br/>(Primary, Updates, Promotions)"]
    inbox --> scrape["/scrape<br/>LinkedIn CLI, JobTeaser,<br/>HelloWork, freehire"]
    scrape --> rank["/rank<br/>posting-scorer sub-agents<br/>score 0-100"]
    rank --> pick["next_job.py<br/>best fit first"]
    pick --> apply["/apply<br/>evaluate, draft,<br/>review, build, verify"]
    apply --> submit["/submit<br/>email or web form"]
    submit --> record["Record<br/>tracker row +<br/>submission.md"]
    record --> sync["/gmail-sync<br/>replies to tracker"]
    sync --> outreach["/outreach<br/>recruiter follow-up"]
    outreach --> outcome["/outcome, /interview"]
    record -->|"next job"| pick
```

`/autopilot` runs the `pick → apply → submit → record` loop by itself until a stop condition is hit (section 2).

---

## 2. `/autopilot`: the continuous loop

```mermaid
flowchart TD
    A(["/autopilot [N | until HH:MM | focus | draft]"]) --> P["next_job.py --limit 3"]
    P --> Q{"Any job ≥ 60<br/>not claimed by<br/>another session?"}
    Q -- yes --> AP["/apply on the job URL<br/>(no pause at evaluation)"]
    Q -- no --> C["next_job.py --count"]
    C --> U{"unranked_new > 0?"}
    U -- yes --> R["/rank --limit 10"] --> P
    U -- no --> S{"Already scraped<br/>this run?"}
    S -- no --> SC["/scrape + JobTeaser"] --> R
    S -- yes --> STOP1(["Stop: nothing scores ≥ 60"])

    AP --> E{"Own evaluation ≥ 60<br/>and no deal-breaker?"}
    E -- no --> SK["Mark skipped in<br/>seen_jobs.json"] --> P
    E -- yes --> SQ["Read the site's entry in<br/>docs/site_quirks.md"]
    SQ --> SUB["/submit"]
    SUB --> OK{"Submitted?"}
    OK -- yes --> REC["Append tracker row<br/>+ submission.md<br/>+ finish email verification"]
    OK -- "needs login / CAPTCHA /<br/>unknown answer" --> MQ["Queue in<br/>manual_apply_queue.md"]
    REC --> N{"Every 5 apps"}
    MQ --> P
    N -- yes --> ST["split_tracker.py<br/>status line"] --> LIM
    N -- no --> LIM{"Limit reached or<br/>candidate says stop?"}
    LIM -- no --> P
    LIM -- yes --> STOP2(["Stop and report"])
```

**Selection rules in `next_job.py`:** status `ranked`, score ≥ 60, not already in the tracker (company plus a similar title, on any channel), employer not in `excluded_employers.txt`, deadline not passed. Jobs closing within 7 days come first, then the rest by score.

---

## 3. `/scrape`: finding postings

```mermaid
sequenceDiagram
    autonumber
    participant U as Candidate
    participant CC as Claude Code
    participant CLI as Portal CLIs<br/>(linkedin-search ...)
    participant CH as Chrome<br/>(JobTeaser extract.js)
    participant SS as scrape_state.py
    participant SJ as seen_jobs.json

    U->>CC: /scrape
    CC->>CC: Load search-queries.md
    par CLI portals
        CC->>CLI: search -q QUERY -l France --jobage 14
        CLI-->>CC: JSON hits
    and Browser portals
        CC->>CH: jobteaser([...], {pages: 2})
        CH-->>CC: JSON hits
    end
    CC->>SS: candidates (hits)
    SS->>SJ: read history + tracker
    SS-->>CC: only unseen hits
    CC->>CLI: detail ID (new hits only)
    CC->>CC: Mass-posting detection, quick fit check
    CC->>SS: store (enriched entries, status=new)
    SS->>SJ: atomic write
    CC-->>U: New matches + highlights
```

---

## 4. `/rank`: scoring the shortlist

```mermaid
sequenceDiagram
    autonumber
    participant CC as Claude Code
    participant RS as rank_state.py
    participant PS as posting-scorer<br/>(sub-agents, in parallel)
    participant PG as posting_guard.py
    participant SJ as seen_jobs.json

    CC->>RS: candidates [--limit N] [--focus]
    RS->>SJ: read
    RS-->>CC: projected entries (key, url, title, company)
    loop each batch
        CC->>PS: batch + candidate rubric (inline)
        PS->>PS: fetch posting
        PS->>PG: integrity gate
        PG-->>PS: clean text + flags
        PS-->>CC: score, strengths, gaps, deadline, verdict
    end
    CC->>RS: sweep (expire passed deadlines)
    CC->>RS: apply (results)
    RS->>SJ: write scores, statuses
    RS-->>CC: ranked / vetoed / expired / unreachable rows
    CC-->>CC: Shortlist report
```

**What keeps a job off the shortlist:** a location or language gate `FAIL` (for example, fluent French required), or one of the candidate's deal-breakers: a full-time CDI/CDD, alternance or VIE contract, a defence or nuclear employer, a security clearance or EU nationality requirement, or internship pay below 600 EUR/month. A `FLAG` keeps the job in the ranking with a ⚠ marker for the candidate to judge. A posting that `posting_guard.py` flags is still scored, and the flag is shown to the candidate.

---

## 5. `/apply`: drafter-reviewer loop

```mermaid
sequenceDiagram
    autonumber
    participant U as Candidate
    participant D as Drafter (main agent)
    participant F as posting-fetcher
    participant R as application-reviewer
    participant B as Build + verify<br/>(build.js, docx2pdf, verify_pdf)
    participant T as Tracker

    U->>D: /apply URL or posting text
    D->>F: Step 0 fetch + integrity gate
    F-->>D: clean posting + verdict
    D->>D: Step 1 evaluate fit (score, deal-breakers)
    alt score below 60 or deal-breaker
        D-->>U: Skip with reason
    else fit
        D->>D: Step 2 draft CV (4 projects, ≤ 2 modules each) + letter
        D->>R: Step 3 drafts + posting + profile
        R->>R: research company, grounding audit
        R-->>D: edits + research notes
        D->>D: Step 4 revise
        loop until 1 page and clean
            D->>B: Step 5 build and inspect
            B-->>D: page count, text layer, layout
        end
        D->>T: Step 6b record (status drafted / applied)
        D-->>U: verification checklist + files
    end
```

---

## 6. `/submit`: sending the application

```mermaid
flowchart TD
    A(["/submit application folder"]) --> L["Load posting, CV, letter,<br/>10-screening-answers.md"]
    L --> CH{"Channel?"}

    CH -- email --> EM["Compose from rishiz3028<br/>CV + letter attached"]
    EM --> SENT["Send"]

    CH -- "web form" --> QK["Read the site entry<br/>in docs/site_quirks.md"]
    QK --> OPEN["Open form in Chrome"]
    OPEN --> ACC{"Account, password<br/>or CAPTCHA needed?"}
    ACC -- yes --> MQ["Queue in manual_apply_queue.md<br/>leave tab open"]
    ACC -- no --> FILL["Fill fields from the screening bank<br/>upload CV, paste letter"]
    FILL --> UNK{"Unknown question?"}
    UNK -- yes --> MQ
    UNK -- no --> CONS["Accept required privacy / T&C<br/>never optional marketing"]
    CONS --> SUBMIT["Submit"]
    SUBMIT --> CONF{"Confirmation shown?"}
    CONF -- no --> MQ
    CONF -- yes --> VER["Check inbox for<br/>'verify / finalise' email<br/>and complete it"]

    SENT --> REC["Tracker row status=applied<br/>+ submission.md"]
    VER --> REC
    MQ --> DR["Tracker row status=drafted"]
```

---

## 7. Inbox sync and follow-up

```mermaid
sequenceDiagram
    autonumber
    participant G as Gmail (2 inboxes)
    participant CC as Claude Code
    participant T as job_search_tracker.csv
    participant O as outreach.py
    participant U as Candidate

    Note over CC,G: Session start and /gmail-sync
    CC->>G: newer_than:3d (Primary, Updates, Promotions)
    G-->>CC: threads
    CC->>CC: classify: invitation / rejection / verification / noise
    alt interview invitation or recruiter question
        CC-->>U: tell the candidate first
        CC->>T: status = interview
    else rejection
        CC->>T: status = rejected (+ date in notes)
    else verify / finalise email
        CC->>G: open link, complete application
    end

    Note over CC,O: /outreach (max 10 per day, once per application)
    CC->>O: candidates --min-days 3
    O->>T: read applied rows
    O-->>CC: eligible applications
    CC->>CC: find a published recruiter address
    CC->>G: send short follow-up with the submitted CV
    CC->>O: log --status sent
    O->>T: append "followed up" to notes
```

---

## 8. Reporting

```mermaid
flowchart LR
    T[("job_search_tracker.csv<br/>(private)")] --> S["split_tracker.py"]
    S --> V[("trackers/*.csv<br/>per role_type")]
    S --> C["counts per category<br/>and status (stdout)"]
    T --> P["publish_results.py"]
    P --> R[("results/*.csv<br/>non-personal columns")]
    P --> RM["README.md results table<br/>(between results markers)"]
```

Run at the end of every batch:

```bash
python tools/split_tracker.py
python tools/publish_results.py
```

---

## 9. Daily routine (cheat sheet)

| When | Do | Command |
|---|---|---|
| Session start | Read both work inboxes, update the tracker, report invitations | (manual, mandatory) |
| Queue empty | Refill the job queue | `/scrape` then `/rank` |
| Working | Apply in fit order with tailored documents | `/autopilot` or `/apply` + `/submit` |
| After a batch | Regenerate views and publish | `split_tracker.py`, `publish_results.py` |
| After a batch | Pull replies into the tracker | `/gmail-sync` |
| Daily, ≤ 10 | Recruiter follow-ups | `/outreach` |
| Interview booked | Build a prep pack | `/interview` |
| Result known | Close the application | `/outcome` |
