# Template: rishi-sidebar

- **Type:** CV
- **Source extension:** .json
- **Engine/toolchain:** node + docx-js (DOCX), Microsoft Word (DOCX -> PDF)
- **Page limit:** 1 page(s)
- **Fonts:** Calibri (system font - ships with Windows/Office)
- **Class/packages:** `docx@9.5.1` npm package in `templates/node_modules` (run `npm install` in `templates/` if missing); `build.js` renderer + `docx2pdf.ps1` (needs Microsoft Word installed)

## Compile command

    cd cv && rm -f <file>.pdf <file>.docx && node ../templates/cv/rishi-sidebar/build.js <file>.json && powershell -NoProfile -ExecutionPolicy Bypass -File ../templates/cv/rishi-sidebar/docx2pdf.ps1 <file>.docx

Produces `<file>.docx` AND `<file>.pdf` - the candidate always gets both. Check page count with `pdfinfo <file>.pdf`.

## Content file

Copy `template.json` to `cv/main_<company>_<role>.json` and fill it. `photo` is relative to the JSON file: from `cv/` use `"../documents/cv/photo.JPG"`. The renderer reads: `name`, `headline`, `labels` (`contact`, `techUsed` - translate for French CVs, e.g. `"Coordonnées"`, `"Technologies utilisées : "`), `contact`, `sidebar[]` (`heading` + `bullets[]` or `lines[]`), `sections[]` (`heading` + optional `text` + `entries[]` with `title`, `dates`, `sub`, `text`, `bullets[]`, `tech`).

## Style rules

- Two columns: medium-blue sidebar `#2F5D8A` with white text (photo top, Contact, 4 skill groups, Master Modules, Languages); main column with navy `#1B4F72` headings, Calibri. Do not change colors, sizes or widths in `build.js` per application.
- Exactly **1 page**, A4. Main column order: Profile, Education, Professional Experience, Projects.
- **4 project entries chosen from the module library** (`.claude/skills/job-application-assistant/project_modules.json`, rules in `11-project-modules.md`): pick per-aspect modules that fit the posting (e.g. the SEPIC converter and its PCB/protections as two entries; the BMS is left out), drop irrelevant projects, use at most 2 modules per project. Each entry has the project's dates, context tag and a "Technologies used" line.
- Headline: `EMBEDDED SYSTEMS STUDENT — <2-3 posting-specific focus areas>` (rendered uppercase).
- Sidebar skill groups are retitled per posting (e.g. "Vision & AI", "Interfaces & Communication", "Embedded & Tools"); Master Modules lists 3-5 modules relevant to the posting; Languages always lists all four with honest levels.
- French postings: translate every heading and label (Profil, Formation, Expérience professionnelle, Projets, Langues, Modules du Master).
- Em-dashes are part of the layout in titles/headline ("Embedded Systems Intern — Innspark"); keep prose free of em-dashes per 03-writing-style.md.
- Delivery naming: after verification, also copy to `Rishikesh_Sudheer_Resume_<Company>.pdf` / `.docx` in `cv/` (the candidate's established file names).

## Known pitfalls

- **Overflow is silent.** Word does not shrink content: if the main column is too long, the table row is clipped or a 2nd page appears. Always run `pdfinfo` and Read the PDF. Fix by cutting words (profile 5-6 lines max, Innspark 3 bullets, project text 2-4 lines), never by changing font sizes.
- The table row has an exact height of `PAGE_H - 600` twips. Anything taller makes Word push its mandatory trailing paragraph onto a blank page 2 (zero margins + table). Do not edit it.
- Dates: prefer ASCII ` - ` in the `dates` fields (e.g. `Aug 2024 - Nov 2024`) for ATS parsing; en-dashes reach the text layer as U+2013 (see 05-cv-templates.md "Date fields must be ASCII ranges").
- ATS reading order: sidebar text extracts before the main column. Contact details extract as literal text. Acceptable for single-candidate PDFs.
- `docx2pdf.ps1` drives Word through COM: if Word is open with a modal dialog, the conversion can hang. Close Word dialogs first.
