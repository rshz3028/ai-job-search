---
name: jobteaser-search
version: 1.0.0
description: >
  Search internship offers on JobTeaser through the candidate's ESIGELEC school portal
  (esigelec.jobteaser.com). Login-only, so it runs in the user's logged-in Chrome via
  Claude in Chrome, not with bun. Trigger: /scrape, JobTeaser, job teaser, school job board.
context: fork
enabled: true  # set to false to keep this portal installed but have /scrape skip it
runner: chrome  # NOT a bun CLI: /scrape must run it via mcp__claude-in-chrome__javascript_tool
---

# JobTeaser Search (ESIGELEC portal, Chrome-based)

JobTeaser needs the candidate's school login, so there is **no `cli/`**. Searches run
inside the user's logged-in Chrome session with `extract.js` (this directory).

## How to run

1. Load the Claude in Chrome tools (`tabs_context_mcp`, `tabs_create_mcp`, `navigate`,
   `javascript_tool`, `get_page_text`) in one ToolSearch call.
2. Open a tab on `https://www.jobteaser.com/fr/job-offers`. It redirects to
   `https://esigelec.jobteaser.com/fr/job-offers` when logged in. If it lands on a login
   page instead, stop and ask the user to log in. Never type the password.
3. In `javascript_tool`, paste the full contents of `extract.js` followed by one call:
   ```js
   await jobteaser(['systèmes embarqués', 'logiciel embarqué', 'linux embarqué',
                    'validation embarqué', 'électronique de puissance', 'firmware'],
                   {pages: 2, maxAgeDays: 14})
   ```
   Each query fetches the server-rendered search HTML (`?contract=internship&q=…&page=N`,
   20 offers per page) and parses the cards. Results are already internships only.
4. Output per result: `title, company, contract, location, date (ISO, converted from
   "hier" / "il y a N jours"), partner (bool), url, query`. Tag results
   `portal: "jobteaser-search"`, `source: "cli"` for `seen_jobs.json`.

## Detail

`navigate` to a result `url`, then `get_page_text` for the full description, requirements
and apply method. Some offers apply on JobTeaser itself ("Candidature simplifiée"). Others
("Offre partenaire") send you to the company's own ATS.

## Notes

- Sponsored "Offre de la semaine" cards are pinned at the top of every search, whatever
  the query. Ignore them unless the title matches.
- Chrome auto-translate may show English text in the tab, but fetched HTML stays French.
- Many results are defence (Thales, Naval Group, MBDA, Safran). Defence companies are
  fine (candidate rule, 2026-10-28). Drop an offer only when its own description requires
  habilitation/clearance or EU/French nationality, so read the detail before ranking.
- Keep volume low (a few queries × 2 pages per run).
