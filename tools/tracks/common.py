"""Helpers shared by every track: fold text, fetch a posting description (LinkedIn detail cache or the page).

Every description passes posting_guard before it is stored or read: hidden blocks, invisible characters and
mixed-script words are removed, and a posting with instruction-like text starts with a GUARD_MARK line.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import posting_guard  # noqa: E402
import seen  # noqa: E402
from page_decode import decode_page  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
CACHE = ROOT / "job_scraper" / "postings"
CLI = ROOT / ".agents" / "skills" / "linkedin-search" / "cli" / "src" / "cli.ts"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
fold = seen.fold

# Hard rules shared by all tracks (CLAUDE.md rules 2 and 4)
CLEARANCE = (r"habilitation|clearance|secret defense|confidentiel defense|nationalite (francaise|europeenne)|"
             r"eu (citizen|national)|ressortissant", "clearance/nationality")
FLUENT_FR = (r"francais (courant|bilingue|natif|exige|indispensable|obligatoire)|"
             r"(maitrise|excellente maitrise) (parfaite )?du francais|fluent (in )?french|native french|"
             r"french (is )?(mandatory|required)|professional french", "fluent French required")
DEFENCE = (r"defense|militaire|military|nucleaire|nuclear", "defence/nuclear")


def linkedin_detail(jid: str) -> str:
    f = CACHE / f"{jid}.txt"
    if f.exists() and f.stat().st_size > 200:
        return f.read_text(encoding="utf-8", errors="replace")
    try:
        r = subprocess.run([shutil.which("bun") or "bun", "run", str(CLI), "detail", jid, "--format", "plain"],
                           capture_output=True, timeout=60, encoding="utf-8", errors="replace", cwd=ROOT)
        txt = r.stdout or ""
    except Exception:
        txt = ""
    if len(txt) > 200:
        CACHE.mkdir(parents=True, exist_ok=True)
        f.write_text(txt, encoding="utf-8")
    return txt


GUARD_MARK = "⚠ posting_guard:"


def guard_text(raw: str, mode: str = "auto") -> tuple[str, str]:
    """Clean untrusted posting text. Returns (text, alarm); alarm is "" when clean.

    A text that already starts with GUARD_MARK keeps that alarm, so re-guarding a stored description never
    loses a warning found while the raw page (with its hidden HTML) was still available."""
    prior = ""
    if raw.startswith(GUARD_MARK):
        prior, _, raw = raw.partition("\n")
        prior = prior[len(GUARD_MARK):].strip()
    text, findings = posting_guard.guard(raw, mode)
    v = findings["verdict"]
    alarm = v.split("⚠", 1)[1].strip() if "⚠" in v else ""
    return text, "; ".join(a for a in (prior, alarm) if a)


def guarded(raw: str, mode: str = "auto") -> str:
    """guard_text() as one string: the cleaned text, preceded by a GUARD_MARK line when it alarmed."""
    text, alarm = guard_text(raw, mode)
    return f"{GUARD_MARK} {alarm}\n{text}" if alarm and text else text


def fetch_description(row) -> str:
    try:
        if row["portal_id"] and (row["portal"] == "linkedin" or (row["key"] or "").startswith("linkedin:")):
            return guarded(linkedin_detail(row["portal_id"]), "text")
        if (row["url"] or "").startswith("http"):
            req = urllib.request.Request(row["url"], headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                text = guarded(decode_page(r.read(2_000_000)), "html")
            return text[:20000] if len(text) > 300 else ""
    except Exception:
        return ""
    return ""


def handled(row, lk: "seen.Lookup"):
    """Already applied / drafted / skipped / excluded -> a decide() verdict, else None."""
    hit = lk.find(row["company"] or "", row["title"] or "", row["url"] or "")
    if not hit:
        return None
    kind, rec = hit
    st = rec["s"]
    stage = {"applied": "applied", "interview": "applied", "offer": "applied", "hired": "applied",
             "drafted": "drafted"}.get(st, "discarded")
    return stage, None, "", "", f"already {st} [{kind}] {rec['why']}"[:120]
