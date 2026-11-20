#!/usr/bin/env python3
"""Build a hand-tailored CV and/or letter JSON and run every mechanical check, printing one line per check.

  python tools/build_verify.py cv/main_<base>.json [cover_letters/cover_<base>.json] [--company Name]

Builds DOCX -> PDF with the rishi-sidebar / rishi-plain templates (same toolchain as autodoc.py),
then checks: page count = 1, email and phone as literal text, last tech term present (clipping),
no garbage glyphs, letter closing present, no banned terms, no dashes in letter prose, and that the
CV and letter carry no graduation or end date but do say 'available immediately' (CLAUDE.md rule 3).
With --company, copies the delivery files into documents/applications/<base>/ like autodoc build-ext.

Output: `PASS check` / `FAIL check: detail`, then `RESULT ok|fail`. Exit 1 on any failure.
The visual Read of each PDF stays a separate, manual step.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import autodoc  # noqa: E402  (reuses CONTACT, BANNED, norm, run, build_one)

ROOT = autodoc.ROOT
AVAIL_RX = re.compile(r"available immediately|immediately available|disponible imm[ée]diatement|disponible d[èe]s maintenant", re.I)
DATE_RX = re.compile(r"(graduation|graduating|graduate in|fin d.études|date de fin|end date|jusqu.au|until)\D{0,25}(202[6-9])", re.I)


def pages(pdf):
    return int(re.search(r"Pages:\s+(\d+)", autodoc.run(f'pdfinfo "{pdf}"')).group(1))


def text_of(pdf):
    return autodoc.run(f'pdftotext -layout -enc UTF-8 "{pdf}" -')


def last_tech(cv):
    for sec in reversed(cv.get("sections", [])):
        for e in reversed(sec.get("entries", []) or []):
            if e.get("tech"):  # last term long enough to be distinctive ("C" or "Go" is everywhere)
                terms = [t.strip() for t in re.split(r"[,;]", e["tech"]) if t.strip()]
                for t in reversed(terms):
                    w = max(t.split(), key=len)
                    if len(w) >= 3:
                        return w.strip("()")
    for blk in reversed(cv.get("sidebar", [])):
        for b in reversed(blk.get("bullets", []) or []):
            return re.split(r"[,(]", b)[-1].strip().split()[0] if b.strip() else None
    return None


def main(argv):
    company = None
    if "--company" in argv:
        i = argv.index("--company")
        company = argv[i + 1]
        del argv[i:i + 2]
    if not argv:
        print(__doc__)
        return 2
    results, docs = [], {}
    for path in argv:
        p = os.path.abspath(path)
        d, name = os.path.split(p)
        kind = "cv" if os.path.basename(d) == "cv" else "letter"
        tpl = "cv/rishi-sidebar" if kind == "cv" else "cover_letters/rishi-plain"
        data = json.load(open(p, encoding="utf-8"))
        try:
            pdf = autodoc.build_one(os.path.relpath(d, ROOT), name[:-5], tpl)
        except Exception as exc:  # build error: one line, tail only
            results.append((False, f"build {kind}", str(exc).strip().splitlines()[-1][:160]))
            continue
        docs[kind] = (data, pdf)
        n = pages(pdf)
        results.append((n == 1, f"{kind} 1 page", f"{n} pages"))
        t = text_of(pdf)
        if kind == "cv":
            for s in (autodoc.CONTACT["email"], autodoc.CONTACT["phone"].split()[-1]):
                results.append((s in t, f"cv text has {'email' if '@' in s else 'phone'}", "missing (icon-only?)"))
            lt = last_tech(data)
            results.append((bool(lt) and lt in t, f"cv last tech term '{lt}'", "missing: bottom row clipped"))
            results.append(("(cid:" not in t and "�" not in t, "cv text layer clean", "garbage glyphs"))
        else:
            closing = data.get("closing", "Sincerely,").rstrip(",")
            results.append((closing in t, f"letter closing '{closing}'", "missing: letter clipped"))
            dash = [p for p in data.get("paragraphs", []) if "—" in p or "–" in p]
            results.append((not dash, "letter prose has no long dashes", f"{len(dash)} paragraph(s)"))
        alltext = autodoc.norm(json.dumps(data, ensure_ascii=False))
        banned = [rx for rx in autodoc.BANNED if re.search(autodoc.norm(rx), alltext)]
        results.append((not banned, f"{kind} no banned/unclaimed terms", ", ".join(banned)))
        m = DATE_RX.search(json.dumps(data, ensure_ascii=False))
        results.append((not m, f"{kind} no end/graduation date", m.group(0) if m else ""))
        av = AVAIL_RX.search(json.dumps(data, ensure_ascii=False))
        results.append((bool(av), f"{kind} states availability", "add 'available immediately' / 'disponible immédiatement'"))
    if company and "cv" in docs:
        base = os.path.basename(docs["cv"][1])[5:-4]  # main_<base>.pdf
        app = os.path.join(ROOT, "documents", "applications", base)
        os.makedirs(app, exist_ok=True)
        C = re.sub(r"[^A-Za-z0-9]+", "_", company).strip("_")
        fr = "letter" in docs and docs["letter"][0].get("closing", "").startswith("Sincèrement")
        pairs = [(docs["cv"][1], f"Rishikesh_Sudheer_Resume_{C}.pdf")]
        if "letter" in docs:
            pairs.append((docs["letter"][1], f"{'Lettre_Motivation' if fr else 'Cover_Letter'}_{C}.pdf"))
        for src, dst in pairs:
            shutil.copy(src, os.path.join(app, dst))
            shutil.copy(src[:-4] + ".docx", os.path.join(app, dst[:-4] + ".docx"))
        print("delivery:", os.path.relpath(app, ROOT), "|", ", ".join(d for _, d in pairs))
    ok = all(r[0] for r in results)
    for passed, name, detail in results:
        print(f"PASS {name}" if passed else f"FAIL {name}: {detail}")
    print("RESULT", "ok" if ok else "fail", "| next: Read each PDF once to check the layout visually")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
