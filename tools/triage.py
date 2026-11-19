#!/usr/bin/env python3
"""Fast internship triage: search output -> NEW postings -> fetched text -> fit score, one line each.

  python tools/triage.py <search.json ...> [--top N] [--min S] [--log] [--no-fetch]
  python tools/triage.py --ids 4488545259 4480444976 ...

Steps (no model tokens spent on reading postings):
  1. tools/seen.py lookup drops anything applied/drafted/rejected/skipped/excluded.
  2. Non-engineering titles (marketing, finance, sales, HR, legal...) are dropped.
  3. LinkedIn details are fetched in parallel (8 at a time) and cached in job_scraper/postings/<id>.txt.
  4. Keyword score against the candidate profile; deal-breakers (hard rules) force 0 with a reason.
  --log writes every deal-breaker skip to the seen.py skip log so it is never fetched again.

Output: score | id | company | title | location | +matched keywords | -flags   (sorted, best first)
The score is a pre-filter, not a verdict: read the top postings, write tailored documents, apply.
"""
from __future__ import annotations

import concurrent.futures as cf
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import seen  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "job_scraper" / "postings"
CLI = ROOT / ".agents" / "skills" / "linkedin-search" / "cli" / "src" / "cli.ts"

# (regex on folded text, weight, label). Title hits count triple.
POS = [
    (r"embedded|embarque", 8, "embedded"), (r"firmware|micrologiciel", 8, "firmware"),
    (r"microcontr|\bmcu\b|stm32|esp32|\barm\b|cortex", 7, "MCU"), (r"can bus|bus can|\bcan fd|obd|\buds\b|diagnost", 6, "CAN/diag"),
    (r"uart|\bspi\b|i2c", 4, "buses"), (r"\bc\+\+|\bc\b(?! level)|langage c\b", 5, "C/C++"), (r"python", 4, "Python"),
    (r"linux|yocto", 4, "Linux"), (r"ros ?2|\bros\b|robot", 5, "robotics"), (r"capteur|sensor|imu|lidar|radar", 5, "sensors"),
    (r"kalman|fusion", 6, "fusion"), (r"opencv|vision|perception|yolo", 4, "vision"),
    (r"matlab|simulink", 5, "Simulink"), (r"electroniqu|electronic|\bpcb\b|carte electronique|schemat", 6, "electronics"),
    (r"puissance|power electronic|convertisseur|converter|onduleur|inverter|mppt|dc ?dc", 5, "power-elec"),
    (r"batter|bms", 3, "battery"), (r"automobile|automotive|vehicul|vehicle|adas|powertrain|ev\b|electrique", 4, "automotive"),
    (r"banc|test bench|validation|verification|essai", 5, "test/validation"), (r"automatisation des tests|test automation|automated test", 5, "test-auto"),
    (r"oscillo|multimet|instrumentation|acquisition|mesure", 4, "lab/acq"), (r"traitement du signal|signal processing", 4, "signal"),
    (r"controle commande|commande moteur|motor control|regulation|asservissement|control law|loi de commande", 5, "control"),
    (r"iot|connected|connecte", 3, "IoT"), (r"git\b|docker|ci/cd|gitlab", 2, "tooling"),
    (r"medical|dispositif medical|medtech", 3, "medtech"), (r"aero|avion|drone|spatial|space|satellite", 2, "aero/space"),
    (r"machine learning|deep learning|\bia\b|\bai\b|pytorch|llm|agent", 2, "AI"),
]
TITLE_KILL = re.compile(r"marketing|commercial|business develop|sales|vente|finance|comptab|account|audit|juriste|droit|legal|"
                        r"\brh\b|ressources humaines|recrut|talent|communication|design(er)? (studio|assist)|achat|purchas|"
                        r"supply chain|logisti|consultant (en )?(strat|finance)|controle de gestion|crm|product owner|"
                        r"data analyst|bdr|sdr|assistant\.?e? |chef de projet marketing|merchandis|immobilier")
DEAL = [
    (r"alternance|apprentissage|apprenti\b|work[- ]study", "alternance"),
    (r"\bcdi\b|\bcdd\b|\bvie\b|v\.i\.e|interim", "not an internship contract"),
    (r"habilitation|clearance|secret defense|confidentiel defense|nationalite (francaise|europeenne)|eu (citizen|national)|"
     r"ressortissant", "clearance/nationality"),
    (r"francais (courant|bilingue|natif|exige|indispensable|obligatoire)|(maitrise|excellente maitrise) (parfaite )?du francais|"
     r"fluent (in )?french|native french|french (is )?(mandatory|required)|professional french", "fluent French required"),
    (r"stage de [123] mois|duree ?: ?[123] mois|\b[23] months\b|2(e|eme|nd) annee|1(ere|st) annee|\bbts\b|\bbut\b|licence pro", "duration/level"),
    (r"defense|militaire|military|nucleaire|nuclear", "defence/nuclear"),
]
PEN = [  # skills the profile must never claim: penalty, not a hard skip (may be nice-to-have)
    (r"verilog|vhdl|fpga|\brtl\b|asic", 20, "HDL"), (r"labview", 15, "LabVIEW"), (r"\bhil\b|hardware.in.the.loop", 8, "HIL"),
    (r"\bmpc\b|commande predictive", 15, "MPC"), (r"scada|\bplc\b|automate programmable|tia portal|grafcet", 15, "PLC/SCADA"),
    (r"iso ?26262|autosar|a-spice|aspice", 6, "ISO26262/AUTOSAR"), (r"\brf\b|radiofrequen|hyperfrequen|antenn", 8, "RF"),
    (r"catia|solidworks|mecanique|mechanical", 6, "mechanical"), (r"java\b|javascript|react|angular|\.net|c#", 8, "web/Java"),
]


def fetch(jid: str) -> str:
    f = CACHE / f"{jid}.txt"
    if f.exists() and f.stat().st_size > 200:
        return f.read_text(encoding="utf-8", errors="replace")
    try:
        r = subprocess.run([shutil.which("bun") or "bun", "run", str(CLI), "detail", jid, "--format", "plain"], capture_output=True,
                           timeout=60, encoding="utf-8", errors="replace", cwd=ROOT)
        txt = r.stdout or ""
    except Exception:
        txt = ""
    if len(txt) > 200:
        CACHE.mkdir(parents=True, exist_ok=True)
        f.write_text(txt, encoding="utf-8")
    return txt


def score(title: str, body: str):
    ft, fb = seen.fold(title), seen.fold(body)
    if re.search(r"status: (closed|expired)", fb):
        return 0, [], ["expired"], True
    for rx, why in DEAL:
        m = re.search(rx, fb)
        if m and not (why == "defence/nuclear" and not re.search(rx, ft) and len(re.findall(rx, fb)) < 2):
            return 0, [], [why], True
    s, hits = 20, []
    for rx, w, lab in POS:
        if re.search(rx, ft):
            s += 3 * w
            hits.append(lab.upper())
        elif re.search(rx, fb):
            s += w
            hits.append(lab)
    flags = []
    for rx, w, lab in PEN:
        n = len(re.findall(rx, fb)) + 2 * len(re.findall(rx, ft))
        if n:
            s -= w if n < 3 else int(w * 1.5)
            flags.append(lab)
    return max(0, min(100, s)), hits, flags, False


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    top = int(argv[argv.index("--top") + 1]) if "--top" in argv else 40
    mn = int(argv[argv.index("--min") + 1]) if "--min" in argv else 0
    log, nofetch = "--log" in argv, "--no-fetch" in argv
    lk = seen.Lookup()
    items = []
    if "--ids" in argv:
        for jid in argv[argv.index("--ids") + 1:]:
            if jid.isdigit():
                items.append(("", "", f"https://www.linkedin.com/jobs/view/{jid}", ""))
    else:
        import glob
        files = [f for a in argv if not a.startswith("--") and not a.isdigit() for f in (sorted(glob.glob(a)) or [a])]
        texts = [Path(f).read_text(encoding="utf-8-sig") for f in files]
        items = list(seen.parse_inputs(texts))
    todo, done, cnt = [], set(), {"seen": 0, "title": 0, "dup": 0}
    for c, t, u, loc in items:
        ids = sorted(seen.ids_in(u))
        jid = next((i for i in ids if i.isdigit()), "")
        key = jid or (seen.co_key(c), tuple(seen.t_toks(t)))
        if key in done:
            cnt["dup"] += 1
            continue
        done.add(key)
        if c and (lk.find(c, t, u) or not seen.INTERN_RE.search(seen.fold(t))):
            cnt["seen"] += 1
            continue
        if c and TITLE_KILL.search(seen.fold(t)):
            cnt["title"] += 1
            continue
        todo.append((c, t, u, loc, jid))
    with cf.ThreadPoolExecutor(8) as ex:
        bodies = list(ex.map(lambda x: "" if nofetch or not x[4] else fetch(x[4]), todo))
    rows, skipped = [], 0
    for (c, t, u, loc, jid), body in zip(todo, bodies):
        if not c and body:  # --ids mode: take company/title from the detail header
            lines = body.splitlines()
            t = lines[0].strip() if lines else ""
            c = lines[1].split("·")[0].strip() if len(lines) > 1 else ""
            loc = lines[1].split("·")[1].strip()[:25] if len(lines) > 1 and "·" in lines[1] else ""
            if lk.find(c, t, u):
                cnt["seen"] += 1
                continue
        s, hits, flags, dead = score(t, body or t)
        if dead:
            skipped += 1
            if log:
                with seen.SKIPS.open("a", encoding="utf-8") as f:
                    f.write("\t".join([seen.date.today().isoformat(), c, t, u, "triage: " + flags[0]]) + "\n")
            continue
        rows.append((s, jid, c, t, loc, hits, flags))
    rows.sort(key=lambda r: -r[0])
    for s, jid, c, t, loc, hits, flags in [r for r in rows if r[0] >= mn][:top]:
        print(f"{s:>3} | {jid} | {c[:24]} | {t[:70]} | {loc[:18]} | +{','.join(hits[:7])}" + (f" | -{','.join(flags)}" if flags else ""))
    print(f"-- {len(rows)} scored, {skipped} deal-breakers{' (logged)' if log else ''}, "
          f"{cnt['seen']} already seen/non-internship, {cnt['title']} non-engineering titles, {cnt['dup']} dups")


if __name__ == "__main__":
    main(sys.argv[1:])
