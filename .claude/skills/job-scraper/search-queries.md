# Search Queries for Job Scraper

<!-- SETUP: Customize these queries based on your skills, target roles, and location -->

## Installed portal CLIs (primary for `/scrape`)

`/scrape` discovers every portal skill under `.agents/skills/*/SKILL.md` and runs its CLI first. Shipped country-agnostic CLIs include `linkedin-search` and `freehire-search`; Danish demos and any skill you add with `/add-portal` are included the same way. You do **not** need a matching `site:` line below for those CLIs to run.

The `site:` query templates in this file are the **WebSearch fallback** — for portals without a CLI, company career pages, or when a CLI fails.

**Language scope:** write every query category in every language listed in your CLAUDE.md Languages table (typically 1-2, sometimes more). A posting requiring a language you have *not* declared, as a job condition, is excluded before scoring; a posting requiring a *higher level* than you declared in a language you *do* work in is flagged for your own judgment, not excluded — see `04-job-evaluation.md`'s Language Gate, the single source of truth for this rule. Translate each category's keywords rather than machine-translating word-for-word (e.g. "Frontend Developer" -> "Desarrollador Frontend", not a literal word-for-word translation) if you work in more than one language.

## Search Sites

Market: **France** (internships / stages, 4-6 months, on-site). Languages: write queries in **English and French**.

Primary:
- **linkedin.com/jobs** - `linkedin-search` CLI (location: France / Île-de-France)
- **welcometothejungle.com** - major French tech/startup board (WebSearch fallback until a CLI is added with `/add-portal`)
- **hellowork.com** - large French general board
- **fr.indeed.com** - Indeed France
- **apec.fr** - engineering/cadre roles (mostly jobs, some internships)
- **jobteaser.com** - school-linked internships (ESIGELEC portal, esigelec.jobteaser.com). `jobteaser-search` skill, run in logged-in Chrome (`runner: chrome`). Use French queries: systèmes embarqués, logiciel embarqué, linux embarqué, validation embarqué, électronique de puissance, firmware

Secondary (company career pages via Google):
- Valeo, NXP, Stellantis, Safran, Thales, Parrot, Sagemcom, Schneider Electric, EDF, Socomec, Expleo, Renault/Ampere, Forvia, Continental, Bosch France, Alstom, Nexans, Legrand, Saft, Verkor, Hager

## Query Categories

All queries target internships: add `stage` / `stagiaire` / `internship` / `stage de fin d'études` / `PFE` to each.

### Priority 1: Embedded systems / firmware

```
site:welcometothejungle.com stage "systèmes embarqués" OR "logiciel embarqué"
site:linkedin.com/jobs "embedded software intern" France
site:linkedin.com/jobs "stage logiciel embarqué" Île-de-France
site:hellowork.com stage "ingénieur systèmes embarqués"
site:fr.indeed.com stage "firmware" "STM32" OR "C embarqué"
site:welcometothejungle.com internship "embedded" "C/C++"
```

Title variants: Embedded Software Intern, Firmware Engineer Intern, Stagiaire Ingénieur Logiciel Embarqué, Stage Systèmes Embarqués, Stage Électronique Embarquée, Embedded Systems Intern (Automotive), Stage Intégration Capteurs.

### Priority 2: Test & validation

```
site:linkedin.com/jobs "stage validation" "systèmes embarqués" France
site:welcometothejungle.com stage "test et validation" embarqué
site:hellowork.com stage "ingénieur validation" électronique
site:fr.indeed.com stage "banc de test" OR "test automatisé" embarqué
site:linkedin.com/jobs "validation engineer intern" automotive France
```

Title variants: Stage Ingénieur Test et Validation, Stage V&V, Validation Engineer Intern, Stage Ingénieur Essais, Test Automation Intern (embedded), Stage Validation Système.

### Priority 2b: EMC / CEM (candidate interest, 2026-11-14)

```
site:linkedin.com/jobs stage "CEM" OR "compatibilité électromagnétique" France
site:linkedin.com/jobs "EMC intern" OR "EMC internship" France
site:hellowork.com stage "compatibilité électromagnétique"
site:welcometothejungle.com stage "CEM" électronique
```

Title variants: Stage Ingénieur CEM, Stage Compatibilité Électromagnétique, EMC Test Engineer Intern, Stage Essais CEM, Stage Simulation CEM. Skip defence/nuclear labs and anything requiring habilitation (rule 2).

### Priority 3: Energy (with embedded in support)

```
site:linkedin.com/jobs stage "électronique de puissance" France
site:welcometothejungle.com stage énergie "embarqué" OR "BMS" OR "convertisseur"
site:hellowork.com stage "réseaux électriques" OR "smart grid" ingénieur
site:fr.indeed.com stage "BMS" OR "MPPT" OR "borne de recharge"
site:linkedin.com/jobs "power electronics intern" France
```

Title variants: Stage Électronique de Puissance, Stage BMS, Stage Énergie / Smart Grid, Stage Recharge Véhicule Électrique, Stage Contrôle-Commande, Power Electronics Intern.

### Priority 4: Embedded Linux

```
site:linkedin.com/jobs stage "Linux embarqué" OR "Yocto" France
site:welcometothejungle.com stage "Linux embarqué"
site:fr.indeed.com stage "Yocto" OR "BSP" OR "drivers Linux"
```

Title variants: Stage Linux Embarqué, Embedded Linux Intern, Stage BSP / Drivers, Stage Yocto.

### Also consider (adjacent, suggested)
- Sensor fusion / perception / robotics internships (ROS2, Kalman, OpenCV) - strong project evidence
- Hardware/electronics design internships (KiCad, prototyping)
- Automotive diagnostics (CAN/OBD/UDS) internships

## Location Filter

Home: Neuilly-Plaisance (93), east Paris suburbs. Relocation within France is acceptable.
- **Ideal:** Paris and Île-de-France (Paris, Saclay, Vélizy, Guyancourt, Massy, Cergy, Marne-la-Vallée, Créteil, Bobigny, Poissy)
- **Acceptable:** anywhere else in France (Toulouse, Grenoble, Lyon, Rouen, Orléans, Rennes, Sophia-Antipolis, Alsace, Annemasse)
- **Borderline (FLAG):** outside France (Switzerland, Belgium, Germany, Netherlands, Sweden) - separate permit needed
- **Exclude:** fully remote internships

**Contract filter:** internships (stage / stage de fin d'études) only. Drop CDI, CDD, alternance, VIE.
**Clearance filter:** drop postings mentioning « habilitation », « secret de la défense nationale », « IGI 1300 » or nationality requirements.

**Pay filter:** exclude internships stating < 600 EUR/month. Unstated pay: include and note.

## Language Filter

Your working languages and levels are in CLAUDE.md's Languages table. When filtering scraped results, apply `04-job-evaluation.md`'s Language Gate: a posting requiring a language you haven't declared at all is excluded; a posting requiring a higher level than you declared in a language you do work in is not excluded, flag it clearly instead (see `job-scraper/SKILL.md`'s Step 3 "Quick Fit Assessment" for how the flag surfaces in `/scrape` output). Postings simply *written* in a language you don't work in, that don't require it on the job, are fine.

## Date Filter

Only include jobs posted within the last 14 days, or with an application deadline that has not yet passed. If a posting date cannot be determined, include it but flag as "date unknown".

## Adapting Queries

If the user specifies a focus area, select queries from the matching category and also generate 2-3 custom queries for that focus. For example:
- "/scrape [focus_area]" -> relevant category queries + custom focus-specific queries
