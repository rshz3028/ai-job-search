# Template: rishi-plain

- **Type:** Cover letter
- **Source extension:** .json
- **Engine/toolchain:** node + docx-js (DOCX), Microsoft Word (DOCX -> PDF)
- **Page limit:** 1 page(s)
- **Fonts:** Calibri 10.5pt (system font)
- **Class/packages:** `docx@9.5.1` in `templates/node_modules`; `build.js` + `docx2pdf.ps1` (needs Microsoft Word)

## Compile command

    cd cover_letters && rm -f <file>.pdf <file>.docx && node ../templates/cover_letters/rishi-plain/build.js <file>.json && powershell -NoProfile -ExecutionPolicy Bypass -File ../templates/cover_letters/rishi-plain/docx2pdf.ps1 <file>.docx

## Content file

Copy `template.json` to `cover_letters/cover_<company>_<role>.json`. Fields: `name`, `contactLine`, `date` (optional, empty = omitted), `subject`, `salutation`, `paragraphs[]` (3-4 plain paragraphs, no bullets), `closing`.

## Style rules

- Plain letter: name in navy bold, one contact line, bold subject line ("Subject: Application — <Role> (<ref>), <Company> <Site>" / "Objet : Candidature — ..."), salutation, 3-4 paragraphs, closing, bold name. No header graphics, no signature image.
- Closing is a single line: "Sincerely," (English) or "Sincèrement," (French), followed only by the plain name.
- French letters: salutation "Madame, Monsieur," when no name is known.
- 250-350 words of body text. Never mention gaps (03-writing-style.md candidate rule 1).
- Delivery naming: also copy to `Cover_Letter_<Company>.pdf/.docx` (English) or `Lettre_Motivation_<Company>.pdf/.docx` (French).

## Known pitfalls

- None recorded. One page fits ~400 words at this size; the content limit (not the layout) is the constraint.
