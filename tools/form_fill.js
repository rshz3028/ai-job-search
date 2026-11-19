// Generic application-form helper (any ATS). One javascript_tool call replaces a screenshot + find + click chain.
// Install per site:  localStorage.ff = <this file's text>;  then on each page: eval(localStorage.ff)
// (LinkedIn wipes storage: paste the text directly instead.)  Exposes window.ff. Returns short JSON only.
//
//   ff.scan()                 -> {fields:[[i,label,type,req,filled,options]], errors, buttons, files}
//   ff.fill({"regex": value}) -> {done:[...], miss:[required fields still empty]}  (text, textarea, select, radio, checkbox)
//   ff.consent()              -> ticks REQUIRED privacy/terms boxes only, never marketing / talent-pool boxes
//   ff.file(i)                -> exposes the i-th file input (shadow DOM / hidden) as #ff-file-i for find + file_upload;
//   ff.fileBack()                after file_upload, puts a moved shadow-DOM input back and fires 'change'
//   ff.click("regex")         -> clicks the first visible button/link whose text matches
//   ff.text(n)                -> first n chars of the visible page text (default 600), e.g. to read a confirmation
//   ff.all({"regex": value})  -> fill + consent in one call; returns only what still needs work {miss, nofield, consent, errors}
//   ff.state(okRx)            -> ~300-char page check instead of a screenshot: {url, h1, ok, errors, req_empty, buttons, login, captcha}
//   await ff.wait(rx, ms)     -> polls until page text / URL matches rx (default: success words) or ms pass, then ff.state()
// Values come from 10-screening-answers.md / profile.local.json, passed in by the caller. Nothing is stored here.
// Chrome auto-translate rewrites labels and buttons mid-run (seen in testing 2026-11-15): always write bilingual
// regexes, e.g. {"pr[ée]nom|first name": ..., "dur[ée]e|duration": "6"} and ff.click("envoyer|submit|postuler|apply").
// Tested on a local form: text/email/select/radio/textarea, required-vs-marketing consent, shadow-DOM file upload.
window.ff = (() => {
  const all = (root = document) => {               // walk light DOM, open shadow roots and same-origin iframes
    const out = []; const walk = r => { for (const el of r.querySelectorAll('*')) { out.push(el); if (el.shadowRoot) walk(el.shadowRoot);
      if (el.tagName === 'IFRAME') { try { el.contentDocument && walk(el.contentDocument); } catch (e) {} } } };
    walk(root); return out; };
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const label = el => {
    const doc = el.ownerDocument; let t = '';
    if (el.labels && el.labels.length) t = el.labels[0].innerText;
    if (!t && el.getAttribute('aria-labelledby')) t = el.getAttribute('aria-labelledby').split(' ').map(id => doc.getElementById(id)?.innerText || '').join(' ');
    t = t || el.getAttribute('aria-label') || el.placeholder || '';
    if (!t) { const box = el.closest('fieldset,[role=group],[class*=field],[class*=Field],[class*=question],li,div'); const l = box?.querySelector('legend,label,[class*=label],[class*=Label]'); t = l?.innerText || ''; }
    return clean(t || el.name || el.id).slice(0, 80); };
  const group = el => { const g = el.closest('fieldset,[role=radiogroup],[role=group]'); const l = g && (g.querySelector('legend')?.innerText || g.getAttribute('aria-label'));
    return clean(l || (el.name ? el.ownerDocument.querySelector(`[for="${el.name}"]`)?.innerText : '') || el.name).slice(0, 80); };
  const isField = el => /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName) && !/^(hidden|submit|button|image|reset)$/.test(el.type) && (el.type === 'file' || vis(el));
  const fields = () => all().filter(isField);
  const setVal = (el, v) => { const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : el.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v); for (const e of ['input', 'change']) el.dispatchEvent(new Event(e, { bubbles: true })); el.dispatchEvent(new Event('blur', { bubbles: true })); };
  const req = el => el.required || el.getAttribute('aria-required') === 'true' || /\*\s*$/.test(label(el));
  const filled = el => el.type === 'checkbox' || el.type === 'radio' ? el.checked : el.type === 'file' ? el.files.length > 0 : !!clean(el.value);
  const MARKETING = /newsletter|marketing|promotion|offres? (commerciales|similaires)|talent ?pool|vivier|partenaires|partners|sms|job alerts?|alertes?/i;
  const OK = /merci|thank you|candidature (a (bien )?été |bien )?(envoy|re[çc]u|transmis|enregistr)|application (has been )?(sent|submitted|received)|successfully submitted|confirmation/i;
  const CONSENT = /consent|accept|j.accepte|privacy|confidentialit|donn[ée]es personnelles|rgpd|gdpr|terms|conditions|politique/i;
  return {
    scan() { const fs = fields(); const seen = new Set(); return { fields: fs.map((el, i) => {
        if (el.type === 'radio') { const g = group(el); if (seen.has(g)) return null; seen.add(g);
          const opts = fs.filter(r => r.type === 'radio' && r.name === el.name); return [i, g, 'radio', opts.some(r => r.required) || /\*\s*$/.test(g) ? 1 : 0, opts.some(r => r.checked) ? 1 : 0, opts.map(r => label(r).slice(0, 25))]; }
        return [i, label(el), el.tagName === 'SELECT' ? 'select' : el.type || el.tagName.toLowerCase(), req(el) ? 1 : 0, filled(el) ? 1 : 0,
          el.tagName === 'SELECT' ? [...el.options].slice(0, 8).map(o => clean(o.text).slice(0, 25)) : undefined]; }).filter(Boolean),
      errors: all().filter(e => /error|invalid|alert/i.test(e.className + ' ' + (e.getAttribute('role') || '')) && vis(e) && clean(e.innerText)).slice(0, 5).map(e => clean(e.innerText).slice(0, 80)),
      buttons: all().filter(e => (e.tagName === 'BUTTON' || e.type === 'submit' || e.getAttribute('role') === 'button') && vis(e)).map(e => clean(e.innerText || e.value).slice(0, 30)).filter(Boolean).slice(0, 12),
      files: fs.filter(e => e.type === 'file').length }; },
    fill(map) { const fs = fields(); const done = [];
      for (const [rx, v] of Object.entries(map)) { const re = new RegExp(rx, 'i');
        const radios = fs.filter(el => el.type === 'radio' && re.test(group(el)));
        if (radios.length) { const vr = new RegExp(String(v), 'i'); const r = radios.find(el => vr.test(label(el)) || vr.test(el.value));
          if (r) { r.click(); done.push(rx + '=' + clean(label(r))); } else done.push(rx + ': no option ' + v); continue; }
        const hits = fs.filter(el => el.type !== 'radio' && re.test(label(el)));
        for (const el of hits) {
          if (el.type === 'checkbox') { if (!!v !== el.checked) el.click(); done.push(rx + '=' + !!v); break; }
          if (el.tagName === 'SELECT') { const o = [...el.options].find(o => new RegExp(String(v), 'i').test(o.text)); if (o) { setVal(el, o.value); done.push(rx + '=' + clean(o.text)); } else done.push(rx + ': no option ' + v); break; }
          if (el.type === 'file') continue;
          setVal(el, String(v)); done.push(rx); break; }
        if (!hits.length) done.push(rx + ': no field'); }
      const radioMiss = [...new Set(fs.filter(el => el.type === 'radio' && /\*\s*$/.test(group(el))).map(el => el.name))]
        .filter(n => !fs.some(el => el.type === 'radio' && el.name === n && el.checked)).map(n => group(fs.find(el => el.name === n)));
      return { done, miss: fs.filter(el => req(el) && !filled(el) && el.type !== 'radio').map(label).concat(radioMiss) }; },
    consent() { const out = []; for (const el of fields().filter(e => e.type === 'checkbox')) { const l = label(el);
        if (CONSENT.test(l) && !MARKETING.test(l) && !el.checked) { el.click(); out.push(l.slice(0, 50)); } } return out; },
    file(i = 0) { const f = fields().filter(e => e.type === 'file')[i]; if (!f) return 'no file input ' + i;
      f.id = f.id || 'ff-file-' + i; f.style.display = 'block'; f.style.opacity = 1;
      if (f.getRootNode() !== document) { window.__ffHome = [f, f.parentNode, f.nextSibling]; document.body.appendChild(f); } return '#' + f.id; },
    fileBack() { const h = window.__ffHome; if (!h) return 'nothing moved'; const [f, p, n] = h; p.insertBefore(f, n); f.dispatchEvent(new Event('change', { bubbles: true })); window.__ffHome = null; return 'restored, files=' + f.files.length; },
    click(rx) { const re = new RegExp(rx, 'i');
      const b = all().find(e => (/^(BUTTON|A)$/.test(e.tagName) || e.type === 'submit' || e.getAttribute('role') === 'button') && vis(e) && re.test(clean(e.innerText || e.value)));
      if (!b) return 'no button ' + rx; b.scrollIntoView({ block: 'center' }); b.click(); return 'clicked ' + clean(b.innerText || b.value).slice(0, 30); },
    text(n = 600) { return clean(document.body.innerText).slice(0, n); },
    all(map) { const c = this.consent(); const f = this.fill(map); const s = this.scan();
      return { miss: f.miss, nofield: f.done.filter(d => /: no (field|option)/.test(d)), consent: c, errors: s.errors }; },
    state(okRx) { const ok = okRx ? new RegExp(okRx, 'i') : OK; const t = clean(document.body.innerText); const fs = fields();
      return { url: (location.host + location.pathname).slice(0, 90), h1: clean(document.querySelector('h1,h2')?.innerText).slice(0, 60),
        ok: (t.match(ok) || [null])[0], errors: all().filter(e => /error|invalid|alert/i.test(e.className + ' ' + (e.getAttribute('role') || '')) && vis(e) && clean(e.innerText)).slice(0, 3).map(e => clean(e.innerText).slice(0, 70)),
        req_empty: fs.filter(el => req(el) && !filled(el) && el.type !== 'file').map(label).slice(0, 6),
        buttons: all().filter(e => (e.tagName === 'BUTTON' || e.type === 'submit') && vis(e)).map(e => clean(e.innerText || e.value).slice(0, 25)).filter(Boolean).slice(0, 6),
        login: fs.some(el => el.type === 'password' && vis(el)) ? 1 : 0,
        captcha: document.querySelector('iframe[src*="recaptcha"],iframe[src*="hcaptcha"],iframe[src*="turnstile"],.g-recaptcha,.h-captcha') ? 1 : 0 }; },
    async wait(rx, ms = 8000) { const re = rx ? new RegExp(rx, 'i') : OK; const t0 = Date.now(); const u0 = location.href;
      while (Date.now() - t0 < ms) { if (re.test(document.body.innerText) || (!rx && location.href !== u0)) break; await new Promise(r => setTimeout(r, 400)); }
      return this.state(rx); },
  };
})();
'ff ready';
