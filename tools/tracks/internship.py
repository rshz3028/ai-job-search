"""Track: internship (4-6 months, engineering, France). Config: config/tracks/internship.json.

decide(): already handled -> internship title -> engineering title -> deal-breakers -> keyword fit score.
"""
from __future__ import annotations

import re

from .common import CLEARANCE, DEFENCE, FLUENT_FR, fold, handled

DEFAULT_MIN = 50
TITLE_ONLY_SLACK = 15  # no description fetched: pass at a lower bar, flagged, so the posting is read

TITLE_OK = re.compile(r"\b(stage|stagiaire|intern|internship|trainee|pfe|fin d.?etudes)\b")
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
    CLEARANCE,
    FLUENT_FR,
    (r"stage de [123] mois|duree ?: ?[123] mois|\b[23] months\b|2(e|eme|nd) annee|1(ere|st) annee|\bbts\b|\bbut\b|licence pro", "duration/level"),
    DEFENCE,
]
PEN = [  # skills the profile must never claim: penalty, not a hard skip (may be nice-to-have)
    (r"verilog|vhdl|fpga|\brtl\b|asic", 20, "HDL"), (r"labview", 15, "LabVIEW"), (r"\bhil\b|hardware.in.the.loop", 8, "HIL"),
    (r"\bmpc\b|commande predictive", 15, "MPC"), (r"scada|\bplc\b|automate programmable|tia portal|grafcet", 15, "PLC/SCADA"),
    (r"iso ?26262|autosar|a-spice|aspice", 6, "ISO26262/AUTOSAR"), (r"\brf\b|radiofrequen|hyperfrequen|antenn", 8, "RF"),
    (r"catia|solidworks|mecanique|mechanical", 6, "mechanical"), (r"java\b|javascript|react|angular|\.net|c#", 8, "web/Java"),
]


def score(title: str, body: str):
    ft, fb = fold(title), fold(body)
    if re.search(r"status: (closed|expired)", fb):
        return 0, [], ["expired"], True
    for rx, why in DEAL:
        m = re.search(rx, fb) or re.search(rx, ft)  # the title counts too ("Stage ... défense", "Alternance ...")
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


def decide(row, desc: str, lk, min_score: int):
    """Return (stage, score, hits, flags, reason)."""
    v = handled(row, lk)
    if v:
        return v
    t = row["title"] or ""
    ft = fold(t)
    if not TITLE_OK.search(ft):
        return "discarded", None, "", "", "not an internship title"
    if TITLE_KILL.search(ft):
        return "discarded", None, "", "", "non-engineering title"
    s, hits, flags, dead = score(t, desc or t)
    if dead:
        return "discarded", 0, "", ",".join(flags), "deal-breaker: " + (flags[0] if flags else "?")
    flag_txt = ",".join(flags + ([] if desc else ["title-only"]))
    if s < (min_score if desc else min_score - TITLE_ONLY_SLACK):
        return "discarded", s, ",".join(hits), flag_txt, f"low fit {s}"
    return "fit", s, ",".join(hits), flag_txt, ""
