"""autodoc: template-driven CV + cover letter (no hand writing per job), for any company.

posting text -> theme scoring -> CV json + letter json (from grounded snippets only)
-> docx/pdf build (rishi-sidebar / rishi-plain) -> automatic verification -> application folder.

Usage
  python tools/autodoc.py build-ext <spec.json> ...    # spec: {company,title,location,id,url,description[,theme,hook,extra,slug]}
  python tools/autodoc.py build-db <id> ...            # a data/jobs.db posting (e.g. from `pipeline.py bulk`)

Bulk employers (one ATS, hundreds of postings) are fetched by `pipeline.py bulk` (tools/bulk/); this file
only writes the documents. All text comes from SNIPPETS below, which are grounded in
documents/RISHIKESH_PROFILE_EXPORT.md and project_modules.json. Add a theme or snippet here; never write
per-job claims by hand. build_verify.py reuses CONTACT, BANNED, norm, run and build_one.
"""
import html, json, os, re, shutil, subprocess, sys, unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, ".claude", "skills", "job-application-assistant")

# ---------------------------------------------------------------- grounded content
MOD = {m["id"]: m for m in json.load(open(os.path.join(SKILL, "project_modules.json"), encoding="utf-8"))["modules"]}
PAR = json.load(open(os.path.join(SKILL, "project_modules.json"), encoding="utf-8"))["parents"]

SIDEBAR = {
    "emb": ("Embarqué", ["C/C++ embarqué, Python", "STM32 (ARM Cortex-M), ESP32, Arduino, K210", "FreeRTOS, interruptions, ADC, GPIO"]),
    "bus": ("Interfaces & bus", ["CAN, OBD-II/UDS, UART, SPI, I²C", "Acquisition et journalisation temps réel"]),
    "linux": ("Linux embarqué", ["BeagleBone, Yocto", "Pilotes et code noyau (Master)", "Docker, Git, GitLab CI"]),
    "test": ("Test & mesure", ["Oscilloscope, multimètre", "Tests automatisés, injection de défauts", "Analyse statistique (RMSE, MAE)"]),
    "algo": ("Algorithmes & simulation", ["Filtre de Kalman, fusion de capteurs", "MATLAB/Simulink", "Filtres numériques (DSP)"]),
    "ai": ("IA & vision", ["PyTorch, scikit-learn, pandas", "OpenCV, YOLOv8", "MLP quantifié 8 bits sur K210"]),
    "robot": ("Robotique", ["ROS2 (Python, C++)", "Gazebo, Unity", "LiDAR (RTMaps)"]),
    "hw": ("Électronique", ["KiCad, Proteus, PCB", "Électronique de puissance (SEPIC, MPPT)", "Oscilloscope, multimètre"]),
    "sw": ("Logiciel", ["C++, Python, C", "Git, GitLab CI, Docker", "OpenGL, Vulkan, SQL"]),
}
LANG = ("Langues", ["Anglais — Bilingue", "Français — Basique (A2)", "Hindi — B2", "Malayalam — Courant (C2)"])
# Private contact details live in profile.local.json at the repo root (gitignored), so this file
# can be published as is. Placeholders are used when the file is missing.
_LOCAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profile.local.json")
PRIVATE = json.load(open(_LOCAL, encoding="utf-8")) if os.path.exists(_LOCAL) else {}
CONTACT = {"phone": PRIVATE.get("phone", "<phone>"), "email": PRIVATE.get("email", "<email>"),
           "location": PRIVATE.get("location", "<city>, France"),
           "linkedin": {"text": "linkedin.com/in/rishikesh-sudheer-31977522a", "url": "https://www.linkedin.com/in/rishikesh-sudheer-31977522a"},
           "github": {"text": "github.com/rshz3028", "url": "https://github.com/rshz3028"}}
EDU = {"heading": "Formation", "entries": [
    {"title": "Master en Systèmes Embarqués Automobile", "dates": "2025 - Présent", "sub": "ESIGELEC, Rouen, France · convention de stage fournie · R&D 20/20 (1er sur 11)"},
    {"title": "Bachelor of Technology, Electrical & Computer Engineering", "dates": "2021 - 2025", "sub": "Amrita Vishwa Vidyapeetham, Kollam, Inde"}]}
INNSPARK = {"title": "Stagiaire Systèmes Embarqués — Innspark", "dates": "Août 2024 - Nov. 2024", "sub": "Prototype de lecteur OBD-II · Inde", "bullets": [
    "Conception d'un prototype de lecteur OBD-II : circuit électronique et firmware embarqué en C pour lire les données de diagnostic du véhicule.",
    "Mise en œuvre de la communication CAN bus et des requêtes OBD-II/PID pour collecter des données en temps réel.",
    "Débogage des défauts de circuit et de communication à l'oscilloscope et au multimètre, jusqu'à un prototype fonctionnel."]}
INTRO = "Étudiant en dernière année de Master Systèmes Embarqués Automobile (ESIGELEC), à la recherche d'un stage de six mois, disponible immédiatement."

# Evidence sentences for the letter body, keyed by id (all grounded).
EVID = {
    "innspark": "Chez Innspark, j'ai conçu un prototype de lecteur OBD-II : circuit, firmware en C, communication CAN et requêtes OBD-II/PID, avec un débogage à l'oscilloscope jusqu'au prototype fonctionnel.",
    "bbw_test": "Sur mon projet Brake-by-Wire, j'ai mis en place l'acquisition multi-capteurs, la journalisation temps réel et des tests automatisés et reproductibles par injection de défauts.",
    "bbw_ml": "J'ai entraîné un classifieur MLP sur des séries temporelles capteurs, je l'ai quantifié en 8 bits et déployé sur un Kendryte K210 pour détecter des défauts en temps réel.",
    "imu": "Mon projet R&D, noté 20/20 et classé premier sur onze, portait sur l'estimation d'orientation par fusion de deux IMU : filtres de Kalman en C++, affichage 3D temps réel et comparaison des algorithmes par RMSE, MAE et dérive.",
    "imu_app": "J'ai développé une application C++ qui reçoit des données capteurs par liaison série et les affiche en 3D et en graphiques en temps réel, avec journalisation.",
    "ros": "En robotique, j'ai développé sous ROS2 (Python, C++) la navigation autonome d'un robot DJI RoboMaster EP, avec détection d'obstacles par OpenCV et YOLOv8, testée sous Gazebo et Unity.",
    "mppt": "Pour mon projet de fin d'études, j'ai conçu un chargeur solaire à convertisseur SEPIC avec commande MPPT Perturb & Observe, modélisé sous MATLAB/Simulink, puis passé de la carte prototype à un PCB sur mesure sous KiCad.",
    "mcu": "Je programme en C/C++ sur STM32 (ARM Cortex-M), ESP32 avec FreeRTOS, Arduino et K210 : GPIO, ADC, interruptions, UART, SPI, I²C et CAN.",
    "linux": "Je travaille sous Linux embarqué (BeagleBone, Yocto), avec Git, GitLab CI et Docker.",
    "py": "J'utilise Python pour l'analyse de données et l'apprentissage automatique (pandas, scikit-learn, PyTorch).",
}

# Themes: keyword weights (regex), CV layout, profile, letter pieces.
THEMES = {
    "bus_test": {
        "kw": {r"\bcan\b|bus de terrain|canopen": 6, r"banc|test|essai|validation|ivvq|v[ée]rification": 2, r"automatis": 3, r"uart|spi|i2c|ethernet": 2, r"diagnostic": 2},
        "headline": "bus CAN, tests automatisés & bancs de validation", "sidebar": ["bus", "emb", "linux", "test"],
        "modules": ["Communication Buses", "Embedded C", "Linux", "Safety systems"],
        "projects": ["bbw-testbench", "imu-app", "bbw-ml", "ros-nav"],
        "profile": "J'ai développé la communication CAN et les requêtes OBD-II d'un prototype en C embarqué chez Innspark. Je programme en C, C++ et Python sur STM32, ESP32 (FreeRTOS) et K210, je travaille sous Linux embarqué (BeagleBone, Yocto) et je conçois des outils de test : banc d'injection de défauts, acquisition et visualisation temps réel en C++.",
        "hook": "les bancs de test, les bus de communication et le logiciel qui fait fonctionner du vrai matériel",
        "evid": ["bbw_test", "innspark", "linux", "imu_app"]},
    "embedded_sw": {
        "kw": {r"embarqu|embedded": 3, r"firmware|micrologiciel|microcontr|stm32|esp32|arduino": 5, r"rtos|temps r[ée]el|zephyr": 4, r"linux|yocto|driver|pilote": 3, r"\bc\b|c\+\+|langage c": 2, r"[ée]mulat|ex[ée]cutable|x86|\barm\b|cible": 3},
        "headline": "C/C++ embarqué, temps réel & Linux", "sidebar": ["emb", "linux", "bus", "test"],
        "modules": ["Embedded C", "Linux", "Communication Buses", "Safety systems"],
        "projects": ["bbw-testbench", "imu-app", "imu-fusion", "bbw-ml"],
        "profile": "Je développe du firmware en C/C++ sur STM32 (ARM Cortex-M), ESP32 (FreeRTOS), Arduino et K210 : GPIO, ADC, interruptions, UART, SPI, I²C et CAN. Je travaille sous Linux embarqué (BeagleBone, Yocto) avec Git, GitLab CI et Docker, et j'ai développé chez Innspark le firmware et la communication CAN d'un prototype OBD-II.",
        "hook": "le logiciel embarqué au plus près du matériel, du firmware jusqu'à l'intégration sur cible",
        "evid": ["mcu", "innspark", "linux", "bbw_test"]},
    "nav_fusion": {
        "kw": {r"gnss|inertiel|centrale inertielle|\bimu\b|filtre de navigation|navigation (temps|autonome|automatique)": 6, r"navigation": 1, r"kalman|fusion de|filtre de navigation|filtrage|estimation d": 6, r"capteur|sensor": 2, r"algorithm": 2, r"mod[ée]lisation|matlab|simulink": 4},
        "headline": "fusion de capteurs, Kalman & C++", "sidebar": ["algo", "emb", "linux", "sw"],
        "modules": ["Robotics & localization", "Embedded C", "Linux", "AI for Automotive"],
        "projects": ["imu-fusion", "imu-app", "ros-nav", "bbw-testbench"],
        "profile": "Mon projet R&D, noté 20/20 (1er sur 11), portait sur l'estimation d'orientation par fusion de deux IMU avec des filtres de Kalman en C++, évaluée par RMSE, MAE et dérive. Je programme en C/C++ et Python sur STM32, ESP32 et K210, sous Linux embarqué (BeagleBone, Yocto), et j'ai développé la navigation autonome d'un robot sous ROS2.",
        "hook": "l'estimation de position et d'attitude à partir de capteurs, et son intégration en logiciel embarqué",
        "evid": ["imu", "ros", "mcu", "linux"]},
    "ai_vision": {
        "kw": {r"intelligence artificielle|\bia\b|machine learning|deep learning|apprentissage|neuron|\bml\b": 5, r"vision|image|cam[ée]ra|d[ée]tection|yolo|opencv": 4, r"donn[ée]es|data|dataset": 2, r"python|pytorch": 2},
        "headline": "IA embarquée, vision & Python", "sidebar": ["ai", "emb", "robot", "sw"],
        "modules": ["AI for Automotive", "Computer Vision", "Embedded C", "Robotics & localization"],
        "projects": ["bbw-ml", "ros-vision", "imu-fusion", "bbw-testbench"],
        "profile": "J'ai entraîné un classifieur MLP sur des séries temporelles capteurs, quantifié en 8 bits et déployé sur Kendryte K210 pour la détection de défauts en temps réel. En vision, j'ai utilisé OpenCV et YOLOv8 pour la détection d'obstacles d'un robot ROS2. Je programme en Python (PyTorch, scikit-learn, pandas), C et C++.",
        "hook": "l'IA appliquée à des systèmes réels, de l'entraînement du modèle jusqu'à son exécution embarquée",
        "evid": ["bbw_ml", "ros", "py", "imu"]},
    "robotics_sim": {
        "kw": {r"robot|drone|autonom": 5, r"simulat|simulateur|jumeau num|digital twin": 4, r"ros\b|gazebo|unity": 5, r"c\+\+|python": 1},
        "headline": "simulation, robotique & logiciel C++/Python", "sidebar": ["robot", "sw", "algo", "emb"],
        "modules": ["Robotics & localization", "Computer Vision", "Embedded C", "Linux"],
        "projects": ["ros-nav", "imu-app", "imu-fusion", "bbw-testbench"],
        "profile": "J'ai développé sous ROS2 (Python, C++) la navigation autonome d'un robot mobile testée en simulation Gazebo et Unity, et une application C++ d'acquisition et de visualisation 3D temps réel (projet R&D noté 20/20). Je programme aussi sur microcontrôleurs (STM32, ESP32, K210) et sous Linux embarqué.",
        "hook": "la simulation et le logiciel qui permettent de tester des systèmes complexes avant le terrain",
        "evid": ["ros", "imu_app", "imu", "bbw_test"]},
    "hardware": {
        "kw": {r"[ée]lectronique|carte|pcb|sch[ée]ma|composant": 4, r"puissance|convertisseur|alimentation|[ée]nergie|batter": 5, r"mesure|oscillo|instrument": 3, r"fpga|soc": 2},
        "headline": "électronique, prototypage & firmware", "sidebar": ["hw", "emb", "bus", "test"],
        "modules": ["Embedded C", "Communication Buses", "Safety systems", "Linux"],
        "projects": [["mppt-converter", 0], ["mppt-pcb", 1], "bbw-testbench", "imu-app"],
        "profile": "J'ai conçu un convertisseur SEPIC avec commande MPPT, modélisé sous MATLAB/Simulink et passé de la carte prototype à un PCB sur mesure sous KiCad, avec tests au banc des protections. Chez Innspark, j'ai réalisé le circuit et le firmware C d'un prototype OBD-II, débogué à l'oscilloscope. Je programme sur STM32, ESP32 et K210.",
        "hook": "l'électronique concrète, de la conception de carte jusqu'aux mesures au banc",
        "evid": ["mppt", "innspark", "mcu", "bbw_test"]},
    "software_tools": {
        "kw": {r"logiciel|software|d[ée]velopp": 2, r"ci/cd|int[ée]gration continue|devops|docker|git": 4, r"python|c\+\+|java": 2, r"outil|ihm|interface": 2, r"donn[ée]es|data": 1},
        "headline": "développement logiciel C++/Python & CI", "sidebar": ["sw", "linux", "emb", "test"],
        "modules": ["Linux", "Embedded C", "AI for Automotive", "Communication Buses"],
        "projects": ["imu-app", "bbw-testbench", "ros-nav", "bbw-ml"],
        "profile": "Je développe en C++, Python et C, sous Linux, avec Git, GitLab CI et Docker. J'ai réalisé une application C++ d'acquisition et de visualisation 3D temps réel (projet R&D noté 20/20), un logiciel ROS2 de navigation autonome et une chaîne de tests automatisés par injection de défauts.",
        "hook": "le développement d'outils logiciels fiables qui servent directement les équipes d'ingénierie",
        "evid": ["imu_app", "linux", "bbw_test", "ros"]},
}

# Skills the posting may ask for that the profile genuinely supports -> French label for the letter.
SUPPORTED = [(r"\bc\+\+", "C++"), (r"\bpython\b", "Python"), (r"\blangage c\b|\ben c\b|\bc,|\bc/|\bc et\b", "C"), (r"\blinux\b", "Linux"),
             (r"\bcan\b", "le bus CAN"), (r"\bgit\b", "Git"), (r"matlab|simulink", "MATLAB/Simulink"), (r"docker", "Docker"),
             (r"freertos|rtos", "FreeRTOS"), (r"stm32", "STM32"), (r"arduino|esp32", "Arduino/ESP32"), (r"\bros\b|ros2", "ROS2"),
             (r"opencv", "OpenCV"), (r"pytorch", "PyTorch"), (r"kalman", "le filtrage de Kalman"), (r"ci/cd|int[ée]gration continue|gitlab", "l'intégration continue"),
             (r"uart|spi|i2c|i²c", "les liaisons série (UART, SPI, I²C)"), (r"yocto", "Yocto"), (r"kicad", "KiCad")]
BANNED = [r"raspberry", r"canoe", r"vector\b", r"modbus", r"mqtt", r"labview", r"\blin\b", r"tcp/ip", r"doors", r"\bhil\b", r"a-spice", r"\bslam\b",
          r"javascript", r"\brust\b", r"\bc#", r"iso 26262", r"\bbms\b", r"gestion de batterie", r"habilitation", r"nouveau pour moi", r"pas encore", r"je n'ai pas", r"débutant", r"\(c1\)", r"(english|anglais)\W{0,5}(fluent|courant)?\W{0,5}\(?c1\b"]


def norm(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def slugify(s, n=60):
    s = re.sub(r"^(stage|internship)\s*[-–:]*\s*", "", norm(s)); s = re.sub(r"\b(f/h|h/f|f / h|m/f|6 mois|ingenieur)\b", " ", s)
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")[:n].strip("_")


def clean_desc(j):
    t = html.unescape(j["jobDescription"]); t = re.sub(r"<(br|/p|/li)[^>]*>", "\n", t); t = re.sub("<[^>]+>", "", t)
    t = re.sub(r"[ \t ]+", " ", t); return re.sub(r"\n\s*\n+", "\n", t)


def core(t):
    i = t.find("Votre quotidien"); t = t[i if i > 0 else 0:]
    return re.sub(r"Thales, entreprise Handi.*", "", t, flags=re.S)


def clean_title(t):
    t = re.sub(r"^\s*stage\s*[-–—:]*\s*", "", t, flags=re.I); t = re.sub(r"\s*[-–(]*\s*(F\s*/\s*H|H\s*/\s*F|F\s*/\s*M)\s*\)?.*$", "", t, flags=re.I)
    t = re.sub(r"\bde nos\b", "des", t); t = re.sub(r"\bnos\b", "les", t); t = re.sub(r"\bnotre\b", "la", t)
    t = re.sub(r"\s+[–—]\s+", ", ", t)
    return t.strip(" -–—,")


def is_french(t):
    return len(re.findall(r"\b(vous|les|des|et|pour|une|dans)\b", t.lower())) > len(re.findall(r"\b(you|the|and|for|with|our)\b", t.lower()))


# ---------------------------------------------------------------- theme scoring
def theme_scores(text):
    t = text.lower(); return {k: sum(w * min(len(re.findall(rx, t)), 3) for rx, w in th["kw"].items()) for k, th in THEMES.items()}


# ---------------------------------------------------------------- compose
def project(spec):
    mid, idx = (spec if isinstance(spec, list) else [spec, 0]); m = MOD[mid]; p = PAR[m["parent"]]
    return {"title": f'{m["titles_fr"][idx]} — {p["context_fr"]}', "dates": p["dates_fr"], "text": m["text_fr"], "tech": m["tech_fr"]}


def compose(j):
    desc = core(clean_desc(j)); sc = theme_scores((j["title"] + " ") * 4 + desc)
    theme = j.get("theme") or max(sc, key=sc.get); th = THEMES[theme]
    title = clean_title(j["title"]); site = j["location"].split(",")[0]
    entity = j.get("company") or ""
    asked = []
    for rx, lab in SUPPORTED:
        if re.search(rx, desc, re.I) and lab not in asked: asked.append(lab)
    asked = asked[:5]
    cv = {"photo": "../documents/cv/photo.JPG", "name": "Rishikesh Sudheer", "headline": "Étudiant systèmes embarqués — " + th["headline"],
          "labels": {"contact": "Contact", "techUsed": "Technologies utilisées : "}, "contact": CONTACT,
          "sidebar": [{"heading": SIDEBAR[k][0], "bullets": SIDEBAR[k][1]} for k in th["sidebar"]] + [{"heading": "Modules du Master", "bullets": th["modules"]}, {"heading": LANG[0], "lines": LANG[1]}],
          "sections": [{"heading": "Profil", "text": INTRO + " " + th["profile"]}, EDU, {"heading": "Expérience Professionnelle", "entries": [INNSPARK]},
                       {"heading": "Projets", "entries": [project(p) for p in th["projects"]]}]}
    p1 = (f"Je vous adresse ma candidature pour le stage « {title} » chez {entity} à {site}. Ce sujet rejoint ce qui me motive le plus : {j.get('hook') or th['hook']}. "
          "Je suis étudiant en dernière année de Master Systèmes Embarqués Automobile à l'ESIGELEC et je suis disponible immédiatement pour un stage de six mois, sous convention de stage ESIGELEC.")
    body = " ".join(EVID[e] for e in th["evid"][:3])
    if j.get("extra"): body += " " + j["extra"]
    if asked:
        lst = ", ".join(asked[:-1]) + (" et " + asked[-1] if len(asked) > 1 else asked[0])
        body += f" Je pourrai ainsi mettre à profit {lst} dès mon arrivée et contribuer rapidement aux missions de votre équipe."
    else:
        body += " Je pourrai ainsi contribuer rapidement aux missions de votre équipe."
    p3 = (""
          "Rigoureux, curieux et force de proposition, je serais heureux de vous présenter mes projets lors d'un entretien.")
    cl = {"name": "Rishikesh Sudheer", "contactLine": f"{CONTACT['location']} · {CONTACT['phone']} · {CONTACT['email']}", "date": "",
          "subject": f"Objet : Candidature — Stage {title}, {entity} {site} ({j['jobReqId']})", "salutation": "Madame, Monsieur,",
          "paragraphs": [p1, body, p3], "closing": "Sincèrement,"}
    return theme, sc, cv, cl


# ---------------------------------------------------------------- build + verify
def run(cmd, cwd=ROOT):
    r = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode: raise RuntimeError(cmd + "\n" + (r.stdout + r.stderr)[-800:])
    return r.stdout


def build_one(d, name, tpl):
    cwd = os.path.join(ROOT, d)
    for ext in (".pdf", ".docx"):
        try: os.remove(os.path.join(cwd, name + ext))
        except FileNotFoundError: pass
    run(f"node ../templates/{tpl}/build.js {name}.json", cwd)
    run(f"powershell -NoProfile -ExecutionPolicy Bypass -File ../templates/{tpl}/docx2pdf.ps1 {name}.docx", cwd)
    return os.path.join(cwd, name + ".pdf")


def verify(cv, cl, cvpdf, clpdf):
    fails = []
    pages = lambda p: int(re.search(r"Pages:\s+(\d+)", run(f'pdfinfo "{p}"')).group(1))
    if pages(cvpdf) != 1: fails.append("CV not 1 page")
    if pages(clpdf) != 1: fails.append("letter not 1 page")
    ct = run(f'pdftotext -layout -enc UTF-8 "{cvpdf}" -'); lt = run(f'pdftotext -layout -enc UTF-8 "{clpdf}" -')
    for s in (CONTACT["email"], CONTACT["phone"].split()[-1]):
        if s not in ct: fails.append(f"CV text layer missing {s}")
    last = cv["sections"][-1]["entries"][-1]["tech"].split(",")[-1].strip().split()[0]
    if last not in ct: fails.append("CV clipped (last tech term missing)")
    if "(cid:" in ct or "�" in ct: fails.append("CV text layer garbage")
    if "Sincèrement" not in lt: fails.append("letter clipped (closing missing)")
    alltext = norm(json.dumps(cv, ensure_ascii=False) + json.dumps(cl, ensure_ascii=False))
    for rx in BANNED:
        if re.search(norm(rx), alltext): fails.append(f"banned term: {rx}")
    if any("—" in p or "–" in p for p in cl["paragraphs"]): fails.append("dash in letter prose")
    return fails


def build_ext(specf):
    """Generic posting (any company): spec json path or dict {company, title, location, id, url, description, slug?}."""
    sp = dict(specf) if isinstance(specf, dict) else json.load(open(specf, encoding="utf-8"))
    # strip campaign prefixes such as "CS27 Bac+5 - Stage" so the subject line reads naturally
    sp["title"] = re.sub(r"^\s*(CS\d+\s*[-–]?\s*)?(BAC\s*\+\s*\d\s*[-–]?\s*)?(Stage\s*[-–:]?\s*)?", "", sp["title"], flags=re.I).strip() or sp["title"]
    sp["title"] = re.sub(r"\s*\(?\b[HF]\s*/\s*[HF]\)?\s*$", "", sp["title"]).strip()
    j = {"title": sp["title"], "location": sp["location"], "jobReqId": sp["id"], "jobDescription": html.escape(sp["description"]),
         "externalUrl": sp["url"], "company": sp["company"], "theme": sp.get("theme"), "hook": sp.get("hook"), "extra": sp.get("extra")}
    theme, sc, cv, cl = compose(j)
    co = slugify(sp["company"], 20); base = sp.get("slug") or f"{co}_{slugify(sp['title'], 45)}"
    cvn, cln = f"main_{base}", f"cover_{base}"
    json.dump(cv, open(os.path.join(ROOT, "cv", cvn + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(cl, open(os.path.join(ROOT, "cover_letters", cln + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    cvpdf = build_one("cv", cvn, "cv/rishi-sidebar"); clpdf = build_one("cover_letters", cln, "cover_letters/rishi-plain")
    fails = verify(cv, cl, cvpdf, clpdf)
    app = os.path.join(ROOT, "documents", "applications", base); os.makedirs(app, exist_ok=True)
    C = re.sub(r"[^A-Za-z0-9]+", "_", sp["company"]).strip("_")
    out = {}
    for src, dst in ((cvpdf, f"Rishikesh_Sudheer_Resume_{C}.pdf"), (cvpdf[:-4] + ".docx", f"Rishikesh_Sudheer_Resume_{C}.docx"),
                     (clpdf, f"Lettre_Motivation_{C}.pdf"), (clpdf[:-4] + ".docx", f"Lettre_Motivation_{C}.docx")):
        shutil.copy(src, os.path.join(app, dst)); out[dst] = os.path.join(app, dst)
    open(os.path.join(app, "job_posting.md"), "w", encoding="utf-8").write(
        f"# {sp['title']}\n\n- Company: {sp['company']}\n- Location: {sp['location']}\n- Id: {sp['id']}\n- URL: {sp['url']}\n- Theme: {theme} {sc}\n\n{sp['description']}\n")
    print(json.dumps({"id": sp["id"], "theme": theme, "ok": not fails, "fails": fails, "dir": app, "cv_file": f"cv/{cvn}.json", "cl_file": f"cover_letters/{cln}.json"}, ensure_ascii=False))



def spec_from_db(pid):
    """A jobs.db posting -> build_ext spec (description falls back to the title when none was fetched)."""
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import jobsdb
    r = jobsdb.connect().execute("SELECT * FROM postings WHERE id=?", (int(pid),)).fetchone()
    if not r:
        raise SystemExit(f"no posting {pid} in data/jobs.db")
    return {"company": r["company"] or "", "title": r["title"] or "", "location": r["location"] or "",
            "id": r["portal_id"] or str(r["id"]), "url": r["url"] or "", "description": r["description"] or r["title"] or ""}


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a: print(__doc__); sys.exit()
    if a[0] == "build-ext": [build_ext(f) for f in a[1:]]
    elif a[0] == "build-db": [build_ext(spec_from_db(i)) for i in a[1:]]
    else: print(__doc__); sys.exit(1)
