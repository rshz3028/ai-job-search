#!/usr/bin/env python3
"""Automated job-portal logins in the dedicated "job Chrome" that Claude in Chrome also drives.

Why: login-gated portals (Workday, SuccessFactors, Talentsoft, WTTJ, ...) used to stop every run until the
candidate signed in by hand. This script signs in by itself, inside the same Chrome profile Claude applies
from, so the session is there when Claude opens the apply page.

Credentials: Windows Credential Manager (python `keyring`, service "ai-job-search"). The candidate stores them
once with `set`; the script reads them only at fill time and never prints, logs or returns them. Claude never
sees a password. Login names come from profile.local.json (config/portals.json -> "account").

One-time setup (candidate):
  pip install playwright keyring
  python tools/portal_login.py chrome          # starts the job Chrome (own profile, debugging port 9222)
      in that window: install / connect the Claude in Chrome extension, sign in to both Gmail accounts
  python tools/portal_login.py set <portal>    # prompts for the password (hidden), saves it to Credential Manager
                                               # (in Claude Code type: ! python tools/portal_login.py set linkedin)
Use:
  python tools/portal_login.py list                    # portals, credential stored?, last result
  python tools/portal_login.py login <portal> [...]    # sign in (opens a tab, fills, submits, reports)
  python tools/portal_login.py all                     # every portal with a stored credential
  python tools/portal_login.py status [<portal> ...]   # signed in? (no credential use, no submit)
  python tools/portal_login.py test <portal>           # opens the login URL, reports which fields it finds
  python tools/portal_login.py otp <portal> <code>     # type an emailed one-time code into the waiting tab
  python tools/portal_login.py forget <portal>         # delete the stored credential
  python tools/portal_login.py reset <portal> [...]    # forgot-password -> reset mail in Gmail (job Chrome) ->
                                                       # new generated password saved to Credential Manager -> login
                                                       # (candidate-authorised 2026-11-19; password never printed)

Result per portal (one line; also saved in data/jobs.db portal_logins):
  ok | already | captcha (tab left open for the candidate) | code (emailed code needed: read it from Gmail,
  then `otp`) | no-credential | error: <short text> | form-not-found
Never solves CAPTCHAs, never ticks consents, never creates accounts.
"""
from __future__ import annotations

import getpass
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobsdb  # noqa: E402

ROOT = jobsdb.ROOT
CFG_PATH = ROOT / "config" / "portals.json"
PROFILE = ROOT / "profile.local.json"
SERVICE = "ai-job-search"

USER_SEL = ("input[type=email], input[autocomplete=username], input[autocomplete=email], input[name*=email i], "
            "input[id*=email i], input[name*=user i], input[id*=user i], input[name*=login i], input[id*=login i], "
            "input[name*=identifiant i]")
PASS_SEL = "input[type=password]"
OTP_SEL = ("input[autocomplete=one-time-code], input[name*=otp i], input[id*=otp i], input[name*=code i]:not([type=hidden]), "
           "input[id*=code i]:not([type=hidden])")
SUBMIT_RX = re.compile(r"^\s*(sign ?in|log ?in|connexion|se connecter|me connecter|connect|valider|submit|s['’]identifier|continuer|continue)\s*$", re.I)
NEXT_RX = re.compile(r"^\s*(next|continue|continuer|suivant|continuer avec (l'|un )?e-?mail|continue with email)\s*$", re.I)
COOKIE_RX = re.compile(r"^\s*(tout refuser|refuser|reject all|decline|only necessary|necessary only|"
                       r"continuer sans accepter|continue without accepting|continue without agreeing|disagree( and close)?|je refuse|refuser et fermer|refuser tout|use necessary cookies only|accept only essential|reject optional cookies|refuser les cookies optionnels)\s*$", re.I)
CAPTCHA_RX = re.compile(r"recaptcha|hcaptcha|turnstile|challenges\.cloudflare|arkoselabs|funcaptcha|captcha-delivery", re.I)
ERROR_RX = re.compile(r"incorrect|invalid|n'est pas valide|erron|wrong password|mot de passe (est )?incorrect|"
                      r"try again|réessayer|locked|verrouill", re.I)
LOGIN_URL_RX = re.compile(r"login|log-in|signin|sign-in|sign_in|connexion|/auth|authwall|checkpoint", re.I)

PRESETS = {
    "generic": {},
    "workday": {
        "user": "input[data-automation-id=email]", "password": "input[data-automation-id=password]",
        # the submit button is covered by a transparent click_filter div that takes the click
        "submit": "[data-automation-id=click_filter][aria-label*='Sign In' i], [data-automation-id=click_filter][aria-label*='Soumettre' i], "
                  "[data-automation-id=click_filter][aria-label*='Submit' i], [data-automation-id=click_filter][aria-label*='Connexion' i], "
                  "[data-automation-id=signInSubmitButton]",
        # the /login route first shows a chooser (Apple / Google / e-mail): pick e-mail
        "open": "[data-automation-id=SignInWithEmailButton], [data-automation-id=utilityButtonSignIn], "
                "[data-automation-id=signInLink]",
        "logged_out": "[data-automation-id=utilityButtonSignIn], [data-automation-id=SignInWithEmailButton]",
        "newpass_submit": "[data-automation-id=click_filter][aria-label*='Submit' i], [data-automation-id=click_filter][aria-label*='Soumettre' i], "
                          "[data-automation-id=click_filter][aria-label*='Reset' i], [data-automation-id=click_filter][aria-label*='initialiser' i]",
    },
    "successfactors": {"user": "input[name=username], input#username, " + USER_SEL, "password": "input[name=password], " + PASS_SEL},
    # login page = sign-in form (tbxIdentifiant/tbxPassword) + a create-account form: target the sign-in one
    # some Talentsoft sites have a header login box (Login/Password/btnConnexion) and an in-page one
    # (tbxIdentifiant/tbxPassword/btnConnexionViaPage): prefer the in-page form, all three from the same form
    "talentsoft": {"user": "input[name$=tbxIdentifiant], input[name$=Login]", "password": "input[name$=tbxPassword], input[name$=Password]",
                   "submit": "input[name$=btnConnexionViaPage], input[name$=btnConnexion]",
                   "newpass_submit": "input[name$=btnModifyPassword]",
                   # the reset page also carries the header login box: target the reset form itself
                   "reset_user": "input[name$=Identifiant]", "reset_submit": "input[name$=btnRetrievePassword]"},
    "icims_linkedin": {"sso": r"linkedin"},
}


# ---------------------------------------------------------------- config / credentials
def load_cfg() -> dict:
    return json.loads(CFG_PATH.read_text(encoding="utf-8"))


def portal_cfg(cfg: dict, name: str) -> dict:
    if name not in cfg["portals"]:
        sys.exit(f"unknown portal '{name}'. Known: {', '.join(cfg['portals'])}")
    p = dict(PRESETS.get(cfg["portals"][name].get("preset", "generic"), {}))
    p.update(cfg["portals"][name])
    p.setdefault("credential", name)
    return p


def account(p: dict) -> str:
    acc = p.get("account", "email")
    if "@" in acc:
        return acc
    try:
        return json.loads(PROFILE.read_text(encoding="utf-8")).get(acc, "")
    except (OSError, ValueError):
        return ""


def _keyring():
    try:
        import keyring
        return keyring
    except ImportError:
        sys.exit("missing package: pip install keyring")


def has_secret(p: dict) -> bool:
    return bool(_keyring().get_password(SERVICE, p["credential"]))


def secret(p: dict) -> str:
    return _keyring().get_password(SERVICE, p["credential"]) or ""


# ---------------------------------------------------------------- the job Chrome
def chrome_exe(cfg: dict) -> str:
    cands = [cfg["chrome"].get("exe") or "",
             os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
             os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
             os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")]
    for c in cands:
        if c and Path(c).exists():
            return c
    sys.exit("Chrome not found; set chrome.exe in config/portals.json")


def port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def ensure_chrome(cfg: dict) -> int:
    port = int(cfg["chrome"].get("port", 9222))
    if port_open(port):
        return port
    udd = os.path.expandvars(cfg["chrome"]["user_data_dir"])
    Path(udd).mkdir(parents=True, exist_ok=True)
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([chrome_exe(cfg), f"--user-data-dir={udd}", f"--remote-debugging-port={port}",
                      "--remote-debugging-address=127.0.0.1", "--no-first-run", "--no-default-browser-check"],
                     creationflags=flags, close_fds=True)
    for _ in range(40):
        if port_open(port):
            return port
        time.sleep(0.25)
    sys.exit(f"job Chrome did not open the debugging port {port}. Close other Chrome windows using that profile and retry.")


class Browser:
    """Playwright attached over CDP to the job Chrome (it stays open when the script ends)."""

    def __init__(self, cfg: dict):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            sys.exit("missing package: pip install playwright   (no `playwright install` needed: it uses your Chrome)")
        self.port = ensure_chrome(cfg)
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.connect_over_cdp(f"http://127.0.0.1:{self.port}")
        self.ctx = self.browser.contexts[0] if self.browser.contexts else self.browser.new_context()

    def stop(self):
        try:
            self.pw.stop()  # disconnects only; Chrome and its tabs stay open
        except Exception:
            pass


# ---------------------------------------------------------------- page helpers
def frames(page):
    return [page.main_frame] + [f for f in page.frames if f != page.main_frame]


def visible(page, sel: str):
    """First visible element for a CSS selector list in any frame, or None.
    The comma-separated parts are tried in the order written (a preference list), so a preset can
    point user, password and submit at the same form even when the page has two login forms."""
    for part in [x.strip() for x in re.split(r",(?![^()]*\))", sel) if x.strip()]:
        for fr in frames(page):
            try:
                loc = fr.locator(part)
                for i in range(min(loc.count(), 12)):
                    el = loc.nth(i)
                    if el.is_visible():
                        return el
            except Exception:
                continue
    return None


def button(page, rx: re.Pattern):
    for fr in frames(page):
        try:
            loc = fr.get_by_role("button", name=rx)
            for i in range(min(loc.count(), 6)):
                if loc.nth(i).is_visible():
                    return loc.nth(i)
            loc = fr.get_by_role("link", name=rx)
            for i in range(min(loc.count(), 6)):
                if loc.nth(i).is_visible():
                    return loc.nth(i)
        except Exception:
            continue
    return None


def wait_for(fn, seconds: float, step: float = 0.4):
    end = time.time() + seconds
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(step)
    return None


def captcha(page) -> bool:
    """A captcha the user must solve: a visible checkbox/challenge, not an invisible reCAPTCHA badge."""
    for fr in page.frames:
        u = fr.url or ""
        if not CAPTCHA_RX.search(u) or "size=invisible" in u:
            continue
        try:
            box = fr.frame_element().bounding_box()
        except Exception:
            continue
        if not box or box["width"] < 60 or box["height"] < 40:
            continue
        if "recaptcha" in u and "bframe" in u and box["height"] < 200:
            continue  # challenge frame present but not opened
        return True
    return False


def otp_waiting(page) -> bool:
    if visible(page, OTP_SEL):
        return True
    try:
        body = page.inner_text("body", timeout=2000)[:4000]
    except Exception:
        return False
    return bool(re.search(r"verification code|code de v[ée]rification|enter the code|saisissez le code|"
                          r"code (à|a) 6 chiffres|6-digit code|we sent you a code|nous vous avons envoy", body, re.I))


def error_text(page) -> str:
    el = visible(page, "[role=alert], .error, .errorMessage, [data-automation-id=errorMessage], .alert-danger")
    try:
        t = (el.inner_text(timeout=1000) if el else "").strip()
    except Exception:
        t = ""
    return t[:90] if t and ERROR_RX.search(t) else ""


def signed_in(page, p: dict) -> bool:
    url = page.url or ""
    if re.search(r"/userHome", url):  # Workday's signed-in landing page
        return True
    if p.get("ok_url"):
        return bool(re.search(p["ok_url"], url))
    if p.get("ok"):
        return visible(page, p["ok"]) is not None
    if p.get("logged_out") and visible(page, p["logged_out"]):
        return False
    if visible(page, p.get("password", PASS_SEL)) or visible(page, p.get("user", USER_SEL)):
        return False
    if p.get("logged_out"):
        return True
    return not LOGIN_URL_RX.search(url)


COOKIE_SEL = ("#didomi-notice-disagree-button, #onetrust-reject-all-handler, #CybotCookiebotDialogBodyButtonDecline, "
              "button[data-testid=uc-deny-all-button], #axeptio_btn_dismiss, button#tarteaucitronAllDenied2, "
              "#cookie-reject, button[data-cookiefirst-action=reject], #cookie-bar-reject")


def decline_cookies(page) -> None:
    el = visible(page, COOKIE_SEL)
    if el:
        try:
            el.click(timeout=3000)
            time.sleep(0.7)
            return
        except Exception:
            pass
    b = button(page, COOKIE_RX)
    if b:
        try:
            b.click(timeout=3000)
            time.sleep(0.5)
        except Exception:
            pass


def prepare(page, p: dict, open_form: bool) -> None:
    """Let a slow SPA render (Workday takes ~5-10 s), decline cookies, and optionally open the sign-in form."""
    user_sel = p.get("user", USER_SEL)
    marks = ", ".join(s for s in (user_sel, p.get("password", PASS_SEL), p.get("open"), p.get("ok"), p.get("logged_out")) if s)
    page.wait_for_timeout(1500)
    decline_cookies(page)
    wait_for(lambda: visible(page, marks), 15)
    decline_cookies(page)
    if open_form and p.get("open") and not visible(page, user_sel):
        el = visible(page, p["open"])
        if el:
            el.click()
            wait_for(lambda: visible(page, user_sel), 12)


def record(portal: str, result: str, detail: str = "") -> None:
    con = jobsdb.connect()
    con.execute("INSERT INTO portal_logins(portal, last_try, result, detail) VALUES (?,?,?,?) "
                "ON CONFLICT(portal) DO UPDATE SET last_try=excluded.last_try, result=excluded.result, detail=excluded.detail",
                (portal, jobsdb.now(), result, detail[:200]))
    con.commit()


# ---------------------------------------------------------------- actions
def do_login(br: Browser, name: str, p: dict) -> tuple[str, str]:
    page = br.ctx.new_page()
    try:
        page.goto(p["login_url"], wait_until="domcontentloaded", timeout=45000)
    except Exception as e:
        return "error", f"page did not load: {str(e)[:80]}"
    prepare(page, p, open_form=False)
    if signed_in(page, p) and not visible(page, p.get("user", USER_SEL)):
        page.close()
        return "already", ""
    if captcha(page):
        return "captcha", "before login form"
    prepare(page, p, open_form=True)
    if p.get("sso"):  # sign in through another provider (e.g. iCIMS -> LinkedIn); the provider must be signed in
        user = visible(page, p.get("user", USER_SEL))
        if user and account(p):  # some forms ask for the e-mail before offering the provider button
            user.fill(account(p))
            nb = button(page, NEXT_RX) or button(page, SUBMIT_RX)
            nb.click() if nb else user.press("Enter")
        b = wait_for(lambda: button(page, re.compile(p["sso"], re.I)), 12)
        if not b:
            return "form-not-found", "SSO button not found"
        b.click()
        ok = wait_for(lambda: signed_in(page, p) and not re.search(p["sso"], page.url, re.I), 25)
        return ("ok", "") if ok else ("error", "SSO did not complete (sign in to the provider first)")
    login_name = account(p)
    if not login_name:
        return "error", f"no login name: set '{p.get('account')}' in profile.local.json"
    pw = "" if p.get("passwordless") else secret(p)
    if not pw and not p.get("passwordless"):
        page.close()
        return "no-credential", f"run: python tools/portal_login.py set {name}"
    user = wait_for(lambda: visible(page, p.get("user", USER_SEL)), 12)
    if not user:
        return "form-not-found", f"no login field on {page.url[:80]}"
    user.click()
    user.fill(login_name)
    pwd = visible(page, p.get("password", PASS_SEL))
    if not pwd:  # two-step forms: email first, then password (Glassdoor, Microsoft, Workday variants)
        nb = button(page, NEXT_RX) or button(page, SUBMIT_RX)
        if nb:
            nb.click()
        else:
            user.press("Enter")
        if p.get("passwordless"):
            page.wait_for_timeout(4000)
            return ("captcha", "after email") if captcha(page) else ("code", "emailed code expected: read it from Gmail, then `otp`")
        pwd = wait_for(lambda: visible(page, p.get("password", PASS_SEL)), 15)
        if not pwd:
            if captcha(page):
                return "captcha", "after email step"
            if otp_waiting(page):
                return "code", "emailed code expected"
            return "form-not-found", "password field did not appear"
    pwd.click()
    pwd.fill(pw)
    pw = ""  # drop the reference as soon as it is typed
    sb = visible(page, p["submit"]) if p.get("submit") else None
    sb = sb or button(page, SUBMIT_RX)
    if sb:
        sb.click()
    else:
        pwd.press("Enter")

    def settled():
        if captcha(page):
            return "captcha"
        if otp_waiting(page):
            return "code"
        if error_text(page):
            return "error"
        if signed_in(page, p):
            return "ok"
        return None

    res = wait_for(settled, 25) or "error"
    if res == "ok":
        page.close()
        return "ok", ""
    if res == "error":
        return "error", error_text(page) or f"still on the login page ({page.url[:70]})"
    return res, "tab left open" if res == "captcha" else "emailed code expected: read it from Gmail, then `otp`"


def do_status(br: Browser, name: str, p: dict) -> tuple[str, str]:
    page = br.ctx.new_page()
    try:
        page.goto(p.get("check_url") or p["login_url"], wait_until="domcontentloaded", timeout=45000)
        prepare(page, p, open_form=False)
        ok = signed_in(page, p) and not visible(page, p.get("user", USER_SEL))
        return ("already" if ok else "signed-out"), ""
    except Exception as e:
        return "error", str(e)[:80]
    finally:
        page.close()


def do_test(br: Browser, name: str, p: dict) -> str:
    page = br.ctx.new_page()
    page.goto(p["login_url"], wait_until="domcontentloaded", timeout=45000)
    prepare(page, p, open_form=True)
    found = {"user": bool(visible(page, p.get("user", USER_SEL))), "password": bool(visible(page, p.get("password", PASS_SEL))),
             "next": bool(button(page, NEXT_RX)), "submit": bool((p.get("submit") and visible(page, p["submit"])) or button(page, SUBMIT_RX)),
             "captcha": captcha(page), "signed_in": signed_in(page, p)}
    return f"{page.url[:90]} | " + " ".join(f"{k}={'y' if v else 'n'}" for k, v in found.items())


def do_otp(br: Browser, name: str, p: dict, code: str) -> tuple[str, str]:
    host = re.sub(r"^https?://([^/]+).*", r"\1", p["login_url"]).split(".", 1)[-1]
    pages = [pg for pg in br.ctx.pages if host in (pg.url or "")]
    if not pages:
        return "error", f"no open tab on {host}; run login first"
    page = pages[-1]
    boxes = [b for b in (page.locator("input[maxlength='1']").all() if page.locator("input[maxlength='1']").count() >= 4 else [])
             if b.is_visible()]
    if len(boxes) >= len(code):
        for b, ch in zip(boxes, code):
            b.click()
            b.type(ch)
    else:
        el = visible(page, OTP_SEL) or visible(page, "input[type=text], input[type=tel], input[inputmode=numeric]")
        if not el:
            return "form-not-found", "no code field"
        el.click()
        el.fill(code)
    b = button(page, re.compile(r"verify|v[ée]rifier|confirm|valider|continue|continuer|submit|sign ?in|connexion", re.I))
    if b:
        b.click()
    res = wait_for(lambda: "ok" if signed_in(page, p) and not otp_waiting(page) else None, 20)
    return ("ok", "") if res else ("error", error_text(page) or "code not accepted (expired?)")


# ---------------------------------------------------------------- password reset through Gmail
# Candidate, 2026-11-19: "if there is a password reset needed just use the gmails to reset it and save the login
# credentials". The new password is generated here, saved to Credential Manager before submitting, typed into the
# reset form, and never printed. The previous one (if any) is kept as <credential>.prev.
FORGOT_RX = re.compile(r"forgot|oubli|reset|r[ée]initialis|mot de passe perdu|lost password|trouble signing", re.I)
SEND_RX = re.compile(r"^\s*(send|envoyer|reset|r[ée]initialiser|submit|soumettre|valider|continue|continuer|next|suivant|"
                     r"confirm|confirmer|request|demander|recover|r[ée]cup[ée]rer|recevoir|ok)\b.*", re.I)
SAVE_RX = re.compile(r"^\s*(save|enregistrer|submit|soumettre|valider|confirm|confirmer|change|changer|modifier|update|"
                     r"mettre à jour|reset|r[ée]initialiser|set password|d[ée]finir|continue|continuer|envoyer|send|ok)\b.*", re.I)
MAIL_RX = re.compile(r"reset|password|passwd|pwd|mot.?de.?passe|motdepasse|forgot|oubli|recover|token|activat|"
                     r"changepassword|verify|confirm", re.I)
GMAIL = {}  # address -> /mail/u/<n>


def new_password() -> str:
    import secrets
    import string
    sym = "!#%*?@"
    while True:
        pw = "".join(secrets.choice(string.ascii_letters + string.digits + sym) for _ in range(16))  # SuccessFactors caps at 18
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw) and any(c.isdigit() for c in pw)
                and any(c in sym for c in pw)):
            return pw


def gmail_index(br: Browser, address: str) -> int | None:
    if not GMAIL:
        for i in range(4):
            pg = br.ctx.new_page()
            try:
                pg.goto(f"https://mail.google.com/mail/u/{i}/#inbox", wait_until="domcontentloaded", timeout=45000)
                wait_for(lambda: "@" in pg.title(), 15)
                m = re.search(r"[\w.+-]+@[\w.-]+", pg.title())
                if m and m.group(0).lower() not in GMAIL:
                    GMAIL[m.group(0).lower()] = i
            finally:
                pg.close()
    return GMAIL.get(address.lower())


def mail_links(br: Browser, address: str, query: str, host_hint: str, max_threads: int = 3) -> list[str]:
    """Links in the newest Gmail threads matching the query that look like reset/verify links (host hint first)."""
    import urllib.parse
    idx = gmail_index(br, address)
    if idx is None:
        return []
    pg = br.ctx.new_page()
    out: list[str] = []
    try:
        pg.goto(f"https://mail.google.com/mail/u/{idx}/#search/{urllib.parse.quote(query)}",
                wait_until="domcontentloaded", timeout=45000)
        pg.wait_for_timeout(4000)
        rows = pg.locator("tr.zA:visible")
        for i in range(min(rows.count(), max_threads)):
            rows.nth(i).click()
            pg.wait_for_timeout(2500)
            hrefs = pg.eval_on_selector_all("div.a3s a[href]", "els => els.map(a => a.href)")
            # a conversation lists its messages oldest first: reverse so the newest reset link comes first
            good = [h for h in reversed(hrefs) if h.startswith("http") and MAIL_RX.search(h) and "google.com" not in h]
            good.sort(key=lambda h: host_hint not in h)  # stable: keeps newest-first within each group
            out += [h for h in good if h not in out]
            pg.go_back()
            pg.wait_for_timeout(2000)
    finally:
        pg.close()
    return out


def request_reset(br: Browser, p: dict, email: str) -> tuple[str, str]:
    page = br.ctx.new_page()
    try:
        page.goto(p["login_url"], wait_until="domcontentloaded", timeout=45000)
        prepare(page, p, open_form=True)
        link = wait_for(lambda: visible(page, "[data-automation-id=forgotPasswordLink]") or button(page, FORGOT_RX)
                        or visible(page, "a:has-text('oubli'), a:has-text('Forgot'), a:has-text('forgot')"), 10)
        if not link:
            return "form-not-found", "no forgot-password link"
        try:
            link.click(timeout=8000)
        except Exception:  # an overlay still intercepts: follow the link's address instead
            href = link.get_attribute("href") or ""
            if not href:
                raise
            page.goto(urllib.parse.urljoin(page.url, href), wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        user = wait_for(lambda: (p.get("reset_user") and visible(page, p["reset_user"])) or visible(page, p.get("user", USER_SEL))
                        or visible(page, USER_SEL), 15)
        if not user:
            return "form-not-found", "no e-mail field on the reset page"
        user.click()
        user.fill(email)
        if captcha(page):
            return "captcha", "on the reset form"
        b = ((visible(page, p["reset_submit"]) if p.get("reset_submit") else None)
             or (visible(page, p["submit"]) if p.get("submit") else None) or button(page, SEND_RX))
        b.click() if b else user.press("Enter")
        page.wait_for_timeout(5000)
        if captcha(page):
            return "captcha", "after sending the reset form"
        err = error_text(page)
        return ("error", err) if err else ("sent", "")
    except Exception as e:
        return "error", str(e).splitlines()[0][:100]
    finally:
        try:
            page.close()
        except Exception:
            pass


def set_password_from_link(br: Browser, p: dict, url: str) -> tuple[str, str]:
    kr = _keyring()
    page = br.ctx.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(3000)
        decline_cookies(page)
        first = wait_for(lambda: visible(page, PASS_SEL), 20)
        if not first:
            return "form-not-found", f"no password field at the reset link ({page.url[:60]})"
        fields = [f for fr in frames(page) for f in fr.locator(PASS_SEL).all() if f.is_visible()]
        # pages that also carry a header login box (Talentsoft): keep only the new/confirm fields
        named = [f for f in fields if re.search(r"new|nouveau|confirm|retype|verify|repeat|again|password2|pwd2",
                                                (f.get_attribute("name") or "") + " " + (f.get_attribute("id") or ""), re.I)]
        if len(named) >= 1:
            fields = named
        old = kr.get_password(SERVICE, p["credential"])
        if old:
            kr.set_password(SERVICE, p["credential"] + ".prev", old)
        pw = new_password()
        kr.set_password(SERVICE, p["credential"], pw)  # saved before submit, so it cannot be lost
        for f in fields:  # real key presses: some forms (SuccessFactors) validate on keyup and keep Submit disabled otherwise
            f.click()
            f.fill("")
            f.press_sequentially(pw, delay=30)
        pw = ""
        b = (visible(page, p["newpass_submit"]) if p.get("newpass_submit") else None)             or button(page, SAVE_RX)             or visible(page, "form:has(input[type=password]) button[type=submit], form:has(input[type=password]) input[type=submit]")
        b.click() if b else fields[-1].press("Enter")
        page.wait_for_timeout(6000)
        try:
            body = page.inner_text("body", timeout=3000)
        except Exception:
            body = ""
        if re.search(r"success|r[ée]ussi|has been (reset|changed|updated)|a [ée]t[ée] (modifi|r[ée]initialis|chang)|"
                     r"password (was )?(changed|updated|reset)", body, re.I) and not error_text(page):
            page.close()
            return "ok", ""
        if captcha(page):
            return "captcha", "on the new-password form (tab left open)"
        err = error_text(page)

        def still_shown(f) -> bool:
            try:
                return f.is_visible()
            except Exception:  # detached after navigation
                return False

        if err:  # the site refused it explicitly: the old password is still the valid one
            if old:
                kr.set_password(SERVICE, p["credential"], old)
            return "error", err
        if any(still_shown(f) for f in fields):
            # same new/confirm fields still on screen: probably not accepted, but keep the new password stored
            # (rolling back on a guess lost a working password once); the login check that follows decides
            return "error", "new-password form still shown (policy?); new password kept, previous in .prev"
        page.close()
        return "ok", ""
    except Exception as e:
        return "error", str(e).splitlines()[0][:100]


def do_reset(br: Browser, name: str, p: dict, emails: list[str]) -> tuple[str, str]:
    host = re.sub(r"^https?://([^/]+).*", r"\1", p["login_url"])
    hint = ".".join(host.split(".")[-2:]) if "myworkdayjobs" not in host and "successfactors" not in host else host.split(".")[0]
    query = "newer_than:1h"
    before = {e: set(mail_links(br, e, query, hint)) for e in emails}
    tried = []
    for e in emails:
        res, detail = request_reset(br, p, e)
        tried.append(f"{e.split('@')[0]}:{res}")
        if res != "sent":
            continue
        link = wait_for(lambda: next((l for em in emails for l in mail_links(br, em, query, hint)
                                      if l not in before.get(em, set()) and hint.split(".")[0] in l), None), 180, step=15)
        if not link:
            continue
        res, detail = set_password_from_link(br, p, link)
        if res != "ok" and "kept" not in detail:
            return res, detail
        detail = ""  # uncertain or ok: the login below is the real test
        if e != account(p):
            detail = f"account e-mail is {e}: set \"account\" in config/portals.json"
        lres, ldetail = do_login(br, name, dict(p, account=e))
        if lres not in ("ok", "already"):  # sites often need a few seconds after a reset
            for pg in [x for x in br.ctx.pages if host in (x.url or "")]:
                pg.close()
            time.sleep(8)
            lres, ldetail = do_login(br, name, dict(p, account=e))
        return ("ok" if lres in ("ok", "already") else "reset-ok-login-" + lres), (detail + " " + ldetail).strip()
    return "no-reset-mail", " ".join(tried) + " (no account with these e-mails, or the mail is slow)"


def main(argv: list[str]) -> int:
    jobsdb.utf8_out()
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cfg = load_cfg()
    cmd, names = argv[0], argv[1:]

    if cmd == "reset":
        prof = json.loads(PROFILE.read_text(encoding="utf-8"))
        both = [prof.get("email", ""), prof.get("workday_account", "")]
        br = Browser(cfg)
        try:
            for n in names:
                p = portal_cfg(cfg, n)
                emails = [account(p)] + [e for e in both if e and e != account(p)]
                try:
                    res, detail = do_reset(br, n, p, emails)
                except Exception as e:
                    res, detail = "error", str(e).splitlines()[0][:100]
                record(n, res, "reset: " + detail)
                print(f"{n}: reset {res}" + (f" ({detail})" if detail else ""))
        finally:
            br.stop()
        return 0
    if cmd == "chrome":
        port = ensure_chrome(cfg)
        print(f"job Chrome running on 127.0.0.1:{port}, profile {os.path.expandvars(cfg['chrome']['user_data_dir'])}")
        return 0
    if cmd == "set":
        for n in names:
            p = portal_cfg(cfg, n)
            pw = getpass.getpass(f"password for {n} ({account(p) or p.get('account')}): ")
            if pw:
                _keyring().set_password(SERVICE, p["credential"], pw)
                print(f"{n}: saved to Windows Credential Manager as {SERVICE}/{p['credential']}")
        return 0
    if cmd == "forget":
        for n in names:
            p = portal_cfg(cfg, n)
            try:
                _keyring().delete_password(SERVICE, p["credential"])
                print(f"{n}: credential deleted")
            except Exception:
                print(f"{n}: nothing stored")
        return 0
    if cmd == "list":
        con = jobsdb.connect()
        last = {r["portal"]: r for r in con.execute("SELECT * FROM portal_logins")}
        for n in cfg["portals"]:
            p = portal_cfg(cfg, n)
            stored = "pwless" if p.get("passwordless") else ("cred" if has_secret(p) else "no-cred")
            r = last.get(n)
            print(f"{n:<22} {p.get('preset', 'generic'):<15} {stored:<7} {'verify-url' if p.get('verify') else '':<10} "
                  f"{(r['result'] + ' ' + r['last_try'][5:16]) if r else ''}")
        return 0
    if cmd == "all":
        names = [n for n in cfg["portals"] if (lambda p: p.get("passwordless") is not True and has_secret(p))(portal_cfg(cfg, n))]
        if not names:
            print("no stored credentials yet: python tools/portal_login.py set <portal>")
            return 0
        cmd = "login"
    if cmd in ("login", "status", "test", "otp"):
        if not names:
            print(f"usage: portal_login.py {cmd} <portal> ...")
            return 1
        br = Browser(cfg)
        try:
            if cmd == "otp":
                p = portal_cfg(cfg, names[0])
                res, detail = do_otp(br, names[0], p, names[1] if len(names) > 1 else "")
                record(names[0], res, detail)
                print(f"{names[0]}: {res}" + (f" ({detail})" if detail else ""))
                return 0 if res == "ok" else 2
            worst = 0
            for n in names:
                p = portal_cfg(cfg, n)
                if cmd == "test":
                    print(f"{n}: {do_test(br, n, p)}")
                    continue
                try:
                    res, detail = (do_login if cmd == "login" else do_status)(br, n, p)
                except Exception as e:  # one portal failing must not stop the others
                    res, detail = "error", str(e).splitlines()[0][:100]
                record(n, "ok" if res == "already" else res, detail)
                if res in ("ok", "already") and p.get("verify") and cmd == "login":
                    detail = (detail + " login URL works: set verify false in config/portals.json").strip()
                print(f"{n}: {res}" + (f" ({detail})" if detail else ""))
                worst = max(worst, 0 if res in ("ok", "already") else 2)
            return worst
        finally:
            br.stop()
    print(f"unknown command {cmd}; see --help")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
