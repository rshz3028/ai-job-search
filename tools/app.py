#!/usr/bin/env python3
"""One-call application steps: replaces the inline Python / heredoc scripts written per job.

  python tools/app.py like "<keywords>" [--lang fr|en]   # 3 closest past applied documents (base names)
  python tools/app.py draft <spec.json> [--keep]         # copy + patch + build_verify + archive + tracker add
                                                         # --keep: reuse the already-written JSONs (after Edit fixes)
  python tools/app.py done <row> <site> "<confirmation>" [--form "<answers given>"] [--url <apply url>]
  python tools/app.py queue <row> "<reason>"             # manual_apply_queue.md + tracker note

draft spec (JSON; every key except base/company/role/from optional):
  {"base": "acme_stage_embedded", "company": "Acme", "role": "<posting title>", "from": "<past base>",
   "url": "<posting url>", "site": "<ATS / channel>", "fit": 75, "role_type": "internship",
   "cv":     {"headline": "...", "sections.0.text": "...", "sidebar.1.bullets": ["..."]},
   "letter": {"subject": "...", "salutation": "...", "paragraphs.0": "...", "paragraphs": [...]},
   "replace": [["old text", "new text"]],          # applied to both documents, each must occur
   "posting": "<posting text>" | "posting_file": "<path>"}
Dotted keys address dicts by name and lists by index. The CV/letter JSON of `from` is copied to
cv/main_<base>.json and cover_letters/cover_<base>.json, then patched, so only changed fields travel.
Output: FAIL lines (if any) + one result line. Exit 1 on a failed check (fix with Edit, then rerun with
--keep; the tracker row is added only when every check passes).
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import re
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import tracker  # noqa: E402

APPS = ROOT / "documents" / "applications"
QUEUE = ROOT / "documents" / "manual_apply_queue.md"


def die(msg):
    print("ERROR", msg)
    sys.exit(2)


def set_path(doc, dotted, value):
    keys = dotted.split(".")
    cur = doc
    for k in keys[:-1]:
        cur = cur[int(k)] if isinstance(cur, list) else cur.setdefault(k, {})
    last = keys[-1]
    if isinstance(cur, list):
        i = int(last)
        if i == len(cur):
            cur.append(value)
        else:
            cur[i] = value
    else:
        cur[last] = value


def src_paths(frm):
    """Accept a base name, a cv/main_<base>.json path or a cover path."""
    b = Path(frm).name
    b = re.sub(r"^(main_|cover_)", "", b)
    b = re.sub(r"\.(json|pdf|docx)$", "", b)
    return ROOT / "cv" / f"main_{b}.json", ROOT / "cover_letters" / f"cover_{b}.json"


def cmd_like(args):
    lang = None
    if "--lang" in args:
        i = args.index("--lang")
        lang = args[i + 1]
        del args[i:i + 2]
    words = [tracker.norm(w) for w in " ".join(args).split() if len(w) > 2]
    h, recs, _, _ = tracker.load()
    scored = []
    for n, r in enumerate(recs[1:], 1):
        g = dict(zip(h, r + [""] * (len(h) - len(r))))
        if g["status"] not in ("applied", "interview", "rejected") or not g["cv_file"]:
            continue
        cvp, cop = ROOT / g["cv_file"], ROOT / (g["cover_letter_file"] or "-")
        if not cvp.exists() or not cop.is_file():
            continue
        if lang:
            fr = "Sincèrement" in cop.read_text(encoding="utf-8", errors="ignore")
            if fr != (lang == "fr"):
                continue
        hay = tracker.norm(g["role"] + " " + g["company"] + " " + g["sector"])
        s = sum(1 for w in words if w in hay)
        if s:
            scored.append((s, g["date"], n, g))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    for s, _, n, g in scored[:3]:
        base = Path(g["cv_file"]).stem.removeprefix("main_")
        print(f"{base} | row {n} | {g['company'][:24]} | {g['role'][:60]} | hits {s}")
    if not scored:
        print("no similar applied document; start from autodoc build-ext or the closest past CV by hand")


def cmd_draft(args):
    if not args:
        die("usage: draft <spec.json>")
    keep = "--keep" in args
    args = [a for a in args if a != "--keep"]
    spec = json.loads(Path(args[0]).read_text(encoding="utf-8-sig"))
    for k in ("base", "company", "role", "from"):
        if not spec.get(k):
            die(f"spec needs {k!r}")
    base = re.sub(r"[^a-z0-9_]+", "_", spec["base"].lower()).strip("_")
    d_cv, d_co = ROOT / "cv" / f"main_{base}.json", ROOT / "cover_letters" / f"cover_{base}.json"
    s_cv, s_co = (d_cv, d_co) if keep else src_paths(spec["from"])
    for p in (s_cv, s_co):
        if not p.exists():
            die(f"missing source {p.relative_to(ROOT)}")
    cv = json.loads(s_cv.read_text(encoding="utf-8"))
    co = json.loads(s_co.read_text(encoding="utf-8"))
    for doc, patch in () if keep else ((cv, spec.get("cv") or {}), (co, spec.get("letter") or {})):
        for k, v in patch.items():
            try:
                set_path(doc, k, v)
            except (KeyError, IndexError, ValueError, TypeError) as exc:
                die(f"bad path {k!r}: {exc}")
    cv_t, co_t = json.dumps(cv, ensure_ascii=False, indent=1), json.dumps(co, ensure_ascii=False, indent=1)
    for old, new in [] if keep else spec.get("replace") or []:
        if old not in cv_t and old not in co_t:
            die(f"replace: text not found: {old[:60]!r}")
        o, n = json.dumps(old, ensure_ascii=False)[1:-1], json.dumps(new, ensure_ascii=False)[1:-1]
        cv_t, co_t = cv_t.replace(o, n), co_t.replace(o, n)
    d_cv.write_text(cv_t + "\n", encoding="utf-8")
    d_co.write_text(co_t + "\n", encoding="utf-8")

    # posting archive
    app = APPS / base
    app.mkdir(parents=True, exist_ok=True)
    post = spec.get("posting")
    if spec.get("posting_file"):
        post = Path(spec["posting_file"]).read_text(encoding="utf-8-sig")
    jp = app / "job_posting.md"
    if post and not jp.exists():
        jp.write_text(f"# {spec['role']}\n- Company: {spec['company']}\n- Source: {spec.get('url', '')}\n"
                      f"- Saved: {dt.date.today().isoformat()}\n\n{post.strip()}\n", encoding="utf-8")

    rel = lambda p: p.relative_to(ROOT).as_posix()  # noqa: E731
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "build_verify.py"), rel(d_cv), rel(d_co),
                        "--company", spec["company"]], cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = r.stdout.strip().splitlines()
    fails = [l for l in out if l.startswith("FAIL")]
    deliv = next((l for l in out if l.startswith("delivery:")), "")
    for l in fails:
        print(l)
    if r.returncode or not any(l.startswith("RESULT ok") for l in out):
        tail = "" if fails else " | " + (r.stderr.strip().splitlines() or ["?"])[-1][:200]
        print(f"DRAFT FAIL {base}: fix {rel(d_cv)} / {rel(d_co)} with Edit, then "
              f"python tools/app.py draft {args[0]} --keep{tail}")
        sys.exit(1)
    # A rebuild (--keep, or a rerun) must not add a second row for the same CV file.
    h, recs, _, _ = tracker.load()
    ci = h.index("cv_file") if "cv_file" in h else -1
    existing = next((i for i in range(1, len(recs)) if ci >= 0 and len(recs[i]) > ci
                     and recs[i][ci].replace("\\", "/") == rel(d_cv).replace("\\", "/")), None)
    if existing:
        print(f"DRAFTED {spec['company']} | row {existing} (rebuilt) | {deliv.removeprefix('delivery: ').replace(chr(92), '/')} "
              f"| PDFs: Read once for layout")
        return
    buf = io.StringIO()
    with redirect_stdout(buf):
        tracker.cmd_add([f"company={spec['company']}", f"role={spec['role']}",
                         f"role_type={spec.get('role_type', 'internship')}", "status=drafted",
                         f"fit_rating={spec.get('fit', '')}", f"channel={spec.get('site', '')}",
                         f"cv_file={rel(d_cv)}", f"cover_letter_file={rel(d_co)}", f"source={spec.get('url', '')}"])
    row = re.search(r"^\s*added\s+(\d+)", buf.getvalue())
    print(f"DRAFTED {spec['company']} | row {row.group(1) if row else '?'} | {deliv.removeprefix('delivery: ').replace(chr(92), '/')} "
          f"| PDFs: Read once for layout")


def row_dict(n):
    h, recs, _, _ = tracker.load()
    if not 1 <= n < len(recs):
        die(f"row {n} out of range")
    return dict(zip(h, recs[n] + [""] * (len(h) - len(recs[n]))))


def app_dir(g):
    if g["cv_file"]:
        return APPS / Path(g["cv_file"]).stem.removeprefix("main_")
    return APPS / re.sub(r"[^a-z0-9]+", "_", tracker.norm(g["company"] + " " + g["role"])[:60]).strip("_")


def cmd_done(args):
    form = url = None
    for flag in ("--form", "--url"):
        if flag in args:
            i = args.index(flag)
            if flag == "--form":
                form = args[i + 1]
            else:
                url = args[i + 1]
            del args[i:i + 2]
    if len(args) < 3 or not args[0].isdigit():
        die('usage: done <row> <site> "<confirmation>" [--form "..."] [--url URL]')
    n, site, conf = int(args[0]), args[1], args[2]
    g = row_dict(n)
    today = dt.date.today().isoformat()
    buf = io.StringIO()
    with redirect_stdout(buf):
        tracker.cmd_set([str(n), "status=applied", f"channel={site}", f"note=submitted via {site}; {conf[:120]}"])
    d = app_dir(g)
    d.mkdir(parents=True, exist_ok=True)
    files = ", ".join(sorted(p.name for p in d.glob("*.pdf"))) or "(none in folder)"
    (d / "submission.md").write_text(
        f"# Submission: {g['company']}, {g['role']}\n- Date: {today}\n- Channel: {site}\n"
        f"- URL: {url or g['source']}\n- Files: {files}\n- Form: {form or 'standard fields from profile.local.json'}\n"
        f"- Confirmation: {conf}\n", encoding="utf-8")
    print(f"SUBMITTED row {n} | {g['company'][:30]} | {site} | {d.relative_to(ROOT).as_posix()}/submission.md")


def cmd_queue(args):
    if len(args) < 2 or not args[0].isdigit():
        die('usage: queue <row> "<reason>"')
    n, reason = int(args[0]), " ".join(args[1:])
    g = row_dict(n)
    d = app_dir(g)
    with QUEUE.open("a", encoding="utf-8") as f:
        f.write(f"- {dt.date.today().isoformat()} | {g['company']} {n} ({g['role'][:70]}): documents ready in "
                f"{d.relative_to(ROOT).as_posix()}; {reason}\n")
    buf = io.StringIO()
    with redirect_stdout(buf):
        tracker.cmd_set([str(n), f"note=queued: {reason[:120]}"])
    print(f"QUEUED row {n} | {g['company'][:30]} | {reason[:80]}")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return
    cmd, args = sys.argv[1], sys.argv[2:]
    {"like": cmd_like, "draft": cmd_draft, "done": cmd_done, "queue": cmd_queue}.get(
        cmd, lambda _: die(f"unknown command {cmd}"))(args)


if __name__ == "__main__":
    main()
