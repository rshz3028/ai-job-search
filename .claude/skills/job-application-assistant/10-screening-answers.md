---
framework_version: 1.0.0
---

# Screening Answers Bank

Canonical answers for application-form fields, used by `/submit` and `/autopilot`. Every answer is grounded in `01-candidate-profile.md`. **If a form asks something not covered here, do not stop the run and do not ask the candidate: never guess, leave that application unsent, record it in `documents/manual_apply_queue.md` with the unanswered question, and move on to the next job.** See "Unattended runs" at the end of this file. When the candidate later answers, add the answer here so it is reused.

> This public copy is a template. Fill in the `<...>` values in your own (private) fork.

## Identity & contact

| Field | Answer |
|---|---|
| First name / Prénom | `<first name>` |
| Last name / Nom | `<last name>` |
| Email | `<email>` |
| Phone | `<phone, with country code>` |
| Date of birth | `<dd/mm/yyyy>` |
| Address / city | `<street, postcode, city, country>` |
| LinkedIn | `<url>` |
| GitHub / portfolio / website | `<url>` |
| Civility / Civilité | `<M. / Mme>` |

## Status & eligibility

| Question | Answer |
|---|---|
| Nationality | `<nationality>` |
| Work authorization / "Are you authorized to work in <country>?" | `<yes/no, and on what basis>` |
| Do you require visa sponsorship? | `<yes/no>` |
| Security clearance held? | `<yes/no>` |
| Driving licence | `<which licences>` |
| Convention de stage available? | `<yes (school) / no>` |

## Internship logistics

| Question | Answer |
|---|---|
| Contract type sought | `<internship / stage de fin d'études / ...>` |
| Availability / start date | `<date or "immediately">`. If a date field is required: today's date |
| Duration | `<months>` |
| Notice period | `<none / ...>` |
| Remote / hybrid | `<on-site / hybrid / remote>` |
| Willing to relocate | `<yes/no, where>` |
| Gratification / salary expectation | `<minimum>` |

## Education

| Field | Answer |
|---|---|
| Current school | `<school, city>` |
| Degree | `<degree, level>` |
| Dates | `<start - expected end>` |
| Previous degree | `<degree, school, years>` |

## Languages (dropdowns)

| Language | Answer |
|---|---|
| `<language>` | `<level / CEFR>` |

## Diversity / optional questions

Gender, disability, accommodations, ethnicity, etc.: choose "Prefer not to say" / « Je ne souhaite pas répondre » when available; otherwise STOP and ask.

## Form-question history

Check here first, and add every new answer here, so the candidate is never asked twice.

| Form question | Answer |
|---|---|
| Level of education dropdown | `<e.g. BAC + 5>` |
| Geographical mobility with an "all France" option | `<answer>` |
| Talent community / future-opportunities consent | Leave unticked; tick required privacy notices only |

## Source / "How did you hear about us?"

Use the actual channel the posting came from (LinkedIn, Indeed, Welcome to the Jungle, HelloWork, company website, JobTeaser). If unknown, "Company website".

## Free-text fields

Draft per `08-application-forms.md`, grounded against the profile. Never paste claims that are not in the CV or cover letter submitted for the same role.

## Common application-form questions

| Question | Answer |
|---|---|
| Years of professional experience | `<n>` |
| Highest degree obtained | `<degree>` |
| Is this an end-of-studies internship (PFE)? | `<yes/no>` |
| Earliest start date | Immediately; if a date is required, today's date, or the posting's start date if it is later |
| Previously employed by or applied to this company | Employed: `<no>`. Applied: check the tracker |
| Referred by an employee | `<no>` |
| Willing to travel | `<answer>` |
| Eligible for a clearance / requires a specific nationality | `<answer, or "do not apply: skip the job">` |
| Optional marketing, talent-community or SMS opt-ins | Leave unticked |
| Cover letter required as a file, none tailored yet | Use the message box if there is one; otherwise queue the job |

## Unattended runs

**When a site is exhausted, blocked or errors out:** note it in `trackers/session_claims.md`, claim the next site, carry on. Coordinate with the other sessions through that file and never work a site another session has claimed.

**Skip the job and move on (no question to the candidate) when:**
- it fails a hard gate in `04-job-evaluation.md` (eligibility, language, contract type, duration, pay);
- it is CV-mismatched: a core required skill is not in `01-candidate-profile.md`;
- it may duplicate a tracker row (same company and a similar title, any channel).

**Queue in `documents/manual_apply_queue.md` and move on when the form needs:**
- an account, password or login (includes "quick apply" flows that silently create an account);
- a CAPTCHA or bot check;
- an answer not covered in this file;
- a statement that would be untrue.

Queue line format: `date | company | role | url | what is needed from the candidate`.

Report queued items at the end of the run, and never invent an answer to get past a question.
