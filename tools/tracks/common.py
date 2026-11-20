"""Helpers shared by every track: fold text, fetch a posting description (LinkedIn detail cache or the page)."""
from __future__ import annotations

import html
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import seen  # noqa: E402

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


def _strip(markup: str) -> str:
    markup = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", markup)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", markup))).strip()


def fetch_description(row) -> str:
    try:
        if row["portal_id"] and (row["portal"] == "linkedin" or (row["key"] or "").startswith("linkedin:")):
            return linkedin_detail(row["portal_id"])
        if (row["url"] or "").startswith("http"):
            req = urllib.request.Request(row["url"], headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                text = _strip(r.read(2_000_000).decode("utf-8", "replace"))
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
