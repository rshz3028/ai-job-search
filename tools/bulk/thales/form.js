// Thales Workday apply helper. Install once per browser profile on thales.wd3.myworkdayjobs.com:
//   localStorage.wdThales = <this file's text>;  then on every page: eval(localStorage.wdThales)
// Exposes window.wd. Only does what script clicks can do reliably; real clicks are listed in the playbook.
window.wd = (() => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const step = () => $('[data-automation-id="progressBarActiveStep"]')?.innerText.replace(/\n/g, ' | ');
  const xy = el => { el.scrollIntoView({ block: 'center' }); const r = el.getBoundingClientRect(); return [Math.round(r.x + r.width / 2), Math.round(r.y + r.height / 2)]; };
  const setText = (el, v) => { const p = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(p, 'value').set.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); el.blur(); };
  async function pick(btn, txt) { if (btn.innerText.trim() === txt) return true; btn.click(); await sleep(700);
    const o = $$('[role=option]').find(o => o.textContent.trim() === txt); if (!o) { btn.click(); return 'missing:' + txt; } o.click(); await sleep(500); return btn.innerText.trim() === txt; }
  // Answers for the "Questions de candidature" step (from 10-screening-answers.md).
  const ANSWERS = [
    [/durée de stage/i, 'sel', '6 mois'],
    [/niveau d.études/i, 'sel', 'Master M2 / MBA / Ingénieur / Commerce'],
    [/dernière année/i, 'sel', 'Oui'],
    [/quelle école/i, 'txt', 'ESIGELEC (Rouen)'],
    [/titre du diplôme/i, 'txt', 'Master of Science (MSc) Automotive Embedded Systems / Master Systèmes Embarqués Automobile, ESIGELEC'],
  ];
  return {
    step,
    // state summary of the current page
    state() { return { step: step(), err: $('[data-automation-id="errorBanner"]')?.innerText,
      sel: $$('[data-automation-id="selectedItem"]').map(e => e.textContent), cbs: $$('main input[type=checkbox]').map(c => c.checked),
      files: $$('[data-automation-id="file-upload-item"]').map(e => e.innerText.split('\n').slice(0, 2).join(' ')), source: $('#source--source') ? true : undefined }; },
    async next() { const s = step(); $('[data-automation-id="pageFooterNextButton"]').click(); for (let i = 0; i < 20 && step() === s; i++) await sleep(300); await sleep(600); return this.state(); },
    async clearFiles() { let n = 0; for (let k = 0; k < 6; k++) { const b = $('[data-automation-id="delete-file"]'); if (!b) break; b.click(); n++; await sleep(900); } return n; },
    sourceXY() { return $('#source--source') ? xy($('#source--source')) : null; },
    consentXY() { const c = $('main input[type=checkbox]'); return c ? xy(c) : null; },
    async questions() { const out = [];
      for (const lab of $$('main label, main legend')) { const q = lab.innerText.trim(); const box = lab.closest('[data-automation-id^="formField"]') || lab.parentElement.parentElement;
        const a = ANSWERS.find(([rx]) => rx.test(q)); if (!a) continue;
        if (a[1] === 'sel') out.push([q.slice(0, 30), await pick(box.querySelector('button[aria-haspopup=listbox]'), a[2])]);
        else { const t = box.querySelector('textarea,input'); setText(t, a[2]); out.push([q.slice(0, 30), !!t.value]); } }
      const known = ANSWERS.map(a => a[0]); const unknown = $$('main label, main legend').map(l => l.innerText.trim()).filter(q => q.endsWith('*') && !known.some(rx => rx.test(q)) && !/mobilité|date doit débuter/i.test(q));
      return { out, unknown, hasMobility: /mobilité/i.test($('main').innerText), hasDate: /date doit débuter/i.test($('main').innerText) }; },
    review() { const t = $('main').innerText; return { step: step(), files: t.match(/[\w_]+\.pdf\n[\d,]+ KB/g), src: t.includes('Site institutionnel Thales'), gender: t.includes('Préfère ne pas répondre'), terms: /conditions générales\nOui/.test(t) }; },
    submit() { const b = $('[data-automation-id="pageFooterNextButton"]'); if (b.innerText !== 'Soumettre') return 'not on review'; setTimeout(() => b.click(), 50); return 'clicked'; },
    done() { return document.body.innerText.includes('Candidature soumise'); },
  };
})();
'wd ready';
