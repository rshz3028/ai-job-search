"""Track: part-time student job, Paris region, English-speaking first (hotels and hostels especially).
Config: config/tracks/parttime.json. CV: python tools/parttime_cv.py <Slug>:hotel|hotel_night|hotel_service[:headline].

Hard rules (CLAUDE.md rule 1 and 4, candidate 2026-11-14 / 2026-11-19):
  <= 20 h/week (up to ~24 accepted), no full-time, no internship/alternance, no teaching or childcare,
  on site in the Paris region.
Language gate (candidate, 2026-11-20): the job must work in English, or need very little French. A posting passes
only if it is written in English / names an English-speaking team, or says basic French is enough; any French
requirement above basic (bilingual, English + French, good/fluent French, B2+) is a deal-breaker.
decide(): already handled -> guest-facing title -> deal-breakers -> language gate -> part-time / hotel score.
"""
from __future__ import annotations

import re

from .common import CLEARANCE, DEFENCE, FLUENT_FR, fold, handled

DEFAULT_MIN = 45
TITLE_ONLY_SLACK = 15
MAX_HOURS = 24

TITLE_OK = re.compile(
    r"recep|front (office|desk|of house)|night (audit|porter|crew|host|agent)|veilleur|\bhote|\bhost\b|hostess|"
    r"guest|concierge|room service|accueil|hostel|auberge|hotel|bagagiste|porter|lobby|petit.?dejeuner|breakfast|"
    r"\bextra\b|polyvalent|allrounder|all.rounder|sidekick|crew|welcom|chambre|housekeep|valet")
TITLE_KILL = re.compile(
    r"manager|directeur|director|responsable|chef de (reception|cuisine|partie|brigade)|premier de reception|sous.?chef|"
    r"superviseur|supervisor|gouvernant|comptab|controleur|controller|commercial|sales|revenue|credit|"
    r"\bstage\b|stagiaire|intern\b|internship|alternan|apprenti|securite|security|infirm|aide.?soignant|\basv\b|"
    r"cuisinier|spa|praticien|maintenance|technique|chauffeur|driver|conducteur|marketing|\bcdi\b.*temps plein|"
    r"analyst|analyste|business|developer|developpeur|engineer|ingenieur|consultant|it support|software|"
    r"secretaire|administrati|hotel social|educat")
# explicit part-time evidence only ("week-end" alone is not: full-time hotel jobs list weekend shifts)
PART_TIME = re.compile(r"part[- ]?time|temps partiel|mi-temps|\bextra(s)?\b|job etudiant|student job|"
                       r"contrat (d.?)?extra|vacation")
NO_PT_PENALTY = 25  # no part-time evidence and no hours stated: keep only strong English/hotel matches, flagged
FULL_TIME = re.compile(r"temps (plein|complet)|full[- ]time|\b(35|37|39) ?h(eures)?\b|35 hours|40 hours")
HOURS = re.compile(r"\b(\d{1,2}) ?(?:h|heures|hours|hrs)\b ?(?:/|par|per|a la|a|each|every)? ?(?:semaine|week|hebdo)")
DEAL = [
    (r"alternance|apprentissage|apprenti\b|work[- ]study|convention de stage", "not a job (alternance/internship)"),
    (r"baby.?sit|garde d.?enfants?|nounou|creche|petite enfance|childcare|nanny|professeur|enseignant|teacher|"
     r"teaching|tutor|soutien scolaire|ecole bilingue|animat\w* (enfants|periscolaire)", "teaching/childcare"),
    (r"permis b (exige|obligatoire|indispensable|requis)|vehicule (personnel|indispensable)|driving licen[cs]e required",
     "car/licence required"),
    CLEARANCE,
    FLUENT_FR,
    (r"maitris\w* (imperativement |parfaitement )?(le |du |de la langue )?francais|"
     r"(bonne|parfaite|excellente) maitrise (du|de la langue) francais|parler couramment (le )?francais",
     "fluent French required"),
    (r"carte (professionnelle )?cnaps|\bssiap\b", "security card required"),
    DEFENCE,
]
# French above basic level (checked only when FR_LITTLE does not match)
FR_NEED = re.compile(
    r"(english|anglais)\W+(and |et |& )?(french|francais)|(french|francais)\W+(and |et |& )?(english|anglais)|"
    r"bilingu|(good|strong|excellent|very good|professional|fluent|perfect|working|native)( command| knowledge| level)?"
    r"( of| in)?( spoken| written)? (french|francais)|(bon|tres bon|excellent|parfait) niveau (de |d.)?francais|"
    r"francais (courant|exige|requis|obligatoire|indispensable|imperatif|parle et ecrit|lu.? ecrit)|"
    r"(french|francais)( level)? ?:? ?(b2|c1|c2)|\b(b2|c1|c2) (in |en )?(french|francais)|"
    r"maitris\w* (du |de la langue |le )?francais|french (is )?(mandatory|required|essential|needed)|"
    r"(must|should|need to) speak french|french[- ]speaking (required|candidate|profile)|francophone (exige|requis)")
# French basic / optional / either-or: allowed
FR_LITTLE = re.compile(
    r"(basic|some|conversational|elementary|beginner|limited|notions? (of|de))( level of| knowledge of)? (french|francais)|"
    r"(french|francais) (is |would be )?(a plus|an asset|a bonus|helpful|appreciated|optional|not (required|necessary|mandatory)|"
    r"apprecie|souhaite|un plus|un atout|n.est pas (obligatoire|necessaire|requis|exige))|"
    r"no french (required|needed|necessary)|(without|sans) (speaking )?(french|parler francais)|"
    r"(french|francais) (a1|a2)|\b(a1|a2) (in |en )?(french|francais)|"
    r"(english|anglais) (or|ou) (french|francais)|(french|francais) (or|ou) (english|anglais)")
EN_TEAM = re.compile(r"english[- ]speaking|anglophone|working language is english|(team|we) (works?|speaks?) (in )?english|"
                     r"(work|travail\w*) (in|en) (english|anglais)|english only|non.?french speakers?")
# "anglais courant" in a French-written posting is not enough: the job still runs in French
EN_WORDS = re.compile(r"\b(the|and|you|your|with|our|we|will|for|guests?)\b")
FR_WORDS = re.compile(r"\b(le|la|les|et|vous|votre|nous|des|pour|avec|clients?)\b")
POS = [  # (regex, weight, label) on folded description
    (r"english[- ]speaking|anglophone|working language is english|team works in english", 15, "English team"),
    (r"english|anglais", 5, "English"),
    (r"international (guests|clientele|team|travell)|clientele internationale|from all over the world|nationalities", 5, "international"),
    (r"hotel|hostel|auberge|aparthotel|hospitality|hotellerie", 10, "hotel"),
    (r"recep|front (office|desk)|check.?in|guest", 8, "front desk"),
    (r"night|nuit", 3, "night"),
    (r"\bextra(s)?\b|flexible|weekend|week-end", 3, "flexible"),
    (r"no experience|sans experience|debutant|beginners? welcome|we will train|formation assuree", 5, "no exp needed"),
]
PEN = [
    (r"([2-9]|\d{2}) ?(ans|years|year|an)s? (d.?experience|of experience|minimum)|experience (de |of )?([2-9]) (ans|years)", 8, "2+ yrs exp"),
    (r"opera|protel|fidelio|mews|apaleo", 2, "PMS named"),
]
PARIS = re.compile(r"paris|ile.?de.?france|greater paris|hauts.?de.?seine|seine.?saint.?denis|val.?de.?marne|"
                   r"\b(75|77|78|91|92|93|94|95)\d{3}\b|la defense|neuilly|vincennes|montreuil|saint.?denis|boulogne|"
                   r"issy|levallois|clichy|pantin|ivry|nanterre|courbevoie|rueil|noisy|marne.?la.?vallee|roissy|orly")


def _desc_body(desc: str) -> str:
    """Drop LinkedIn's metadata lines ('Employment: Full-time' is often wrong for part-time posts)."""
    return "\n".join(l for l in desc.splitlines() if not re.match(r"\s*(Employment|Seniority|Industries|Status):", l))


def score(title: str, desc: str, location: str, lang_gate: bool = True):
    ft, fb, fl = fold(title), fold(_desc_body(desc)), fold(location)
    if re.search(r"status: (closed|expired)", fold(desc)):
        return 0, [], ["expired"], True
    if fl and not PARIS.search(fl) and not PARIS.search(ft):
        return 0, [], ["outside the Paris region"], True
    for rx, why in DEAL:
        if re.search(rx, fb) or re.search(rx, ft):
            if why == "defence/nuclear" and len(re.findall(rx, fb)) < 2 and not re.search(rx, ft):
                continue
            return 0, [], [why], True
    en_posting = len(EN_WORDS.findall(fb)) > 1.5 * max(1, len(FR_WORDS.findall(fb)))
    little = FR_LITTLE.search(fb) or FR_LITTLE.search(ft)
    if lang_gate and not little and (FR_NEED.search(fb) or FR_NEED.search(ft)):
        return 0, [], ["French above basic required"], True
    if lang_gate and not (en_posting or little or EN_TEAM.search(fb) or EN_TEAM.search(ft)):
        return 0, [], ["French-language job, no English signal"], True
    hours = [int(h) for h in HOURS.findall(fb + " " + ft)]
    pt = PART_TIME.search(ft) or PART_TIME.search(fb) or (hours and min(hours) <= MAX_HOURS)
    if hours and min(hours) > MAX_HOURS:
        return 0, [], [f"{min(hours)} h/week"], True
    if not pt and FULL_TIME.search(fb + " " + ft):
        return 0, [], ["full-time"], True
    s, hits, flags = 40, [], []
    if pt:
        s += 15
        hits.append("part-time" + (f" {min(hours)}h" if hours else ""))
    else:
        s -= NO_PT_PENALTY
        flags.append("hours unknown")
    if en_posting:
        s += 15
        hits.append("posting in English")
    for rx, w, lab in POS:
        if re.search(rx, fb) or re.search(rx, ft):
            s += w
            hits.append(lab)
    for rx, w, lab in PEN:
        if re.search(rx, fb):
            s -= w
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
        return "discarded", None, "", "", "not a guest-facing part-time title"
    if TITLE_KILL.search(ft):
        return "discarded", None, "", "", "management/technical/internship title"
    s, hits, flags, dead = score(t, desc or t, row["location"] or "", lang_gate=bool(desc))
    if dead:
        return "discarded", 0, "", ",".join(flags), "deal-breaker: " + (flags[0] if flags else "?")
    flag_txt = ",".join(flags + ([] if desc else ["title-only"]))
    if not desc:
        flag_txt = ",".join(filter(None, [flag_txt, "language unchecked"]))
    if s < (min_score if desc else min_score - TITLE_ONLY_SLACK):
        return "discarded", s, ",".join(hits), flag_txt, f"low fit {s}"
    return "fit", s, ",".join(hits), flag_txt, ""
