// Job-board listing extractor: one javascript_tool call on a search-results page returns compact lines
//   "company | title | url | location"   (the format `python tools/seen.py check` reads from stdin).
// Inject: `python tools/ff_inject.py boards` -> paste the printed code (defines window.jb), then `await jb.run()`.
// Selectors come from extraction scripts that worked in past sessions (2026-11-16..18):
//   glassdoor  li[data-jobid] / [data-test=jobListing] cards            (glassdoor.fr search pages)
//   hellowork  a[href*="/emplois/<id>"] inside li cards; APPLIED flag    (hellowork.com search pages)
//   linkedin   a[href*="/jobs/view/<id>"] or currentJobId=<id>          (linkedin.com/jobs/search, logged in)
//   wttj       a[href*="/jobs/"] inside article/li cards                 (welcometothejungle.com, logged in)
// jb.run() picks the extractor by host and scrolls first to load lazy cards. Never pass the whole output to
// the model twice: pick the interesting lines, then pipe only those to `seen.py check`.
window.jb = (() => {
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const cut = (s, n) => clean(s).replace(/\|/g, '/').slice(0, n);
  const scroll = async (n = 5, ms = 600) => { for (let i = 0; i < n; i++) { window.scrollTo(0, document.body.scrollHeight); await new Promise(r => setTimeout(r, ms)); } window.scrollTo(0, 0); };
  const uniq = rows => [...new Map(rows.filter(r => r[1]).map(r => [r[2], r])).values()];
  const fmt = rows => uniq(rows).map(r => r.map((x, i) => cut(x, [30, 90, 110, 25][i])).join(' | '));
  const X = {
    glassdoor() {
      const cards = [...document.querySelectorAll('[data-test="jobListing"], li[data-jobid]')];
      return cards.map(c => { const a = c.querySelector('a[data-test="job-title"]') || c.querySelector('a[href*="job-listing"]');
        const id = c.getAttribute('data-jobid') || (a && new URL(a.href).searchParams.get('jl')) || '';
        const u = a ? new URL(a.href) : null;
        return [c.querySelector('[class*="EmployerProfile"] span, [class*="employer"]')?.innerText, a?.innerText,
          u ? u.origin + u.pathname + (id ? '?jl=' + id : '') : '', c.querySelector('[data-test="emp-location"]')?.innerText]; });
    },
    hellowork() {
      return [...document.querySelectorAll('a[href*="/emplois/"]')].map(a => { const m = a.href.match(/emplois\/(\d+)/); if (!m) return [];
        const c = a.closest('li') || a.parentElement; const t = clean(c.innerText);
        const applied = /Application tracking|Suivi de candidature|D[ée]j[àa] postul[ée]|Candidature envoy[ée]e/i.test(t);
        const ps = [...c.querySelectorAll('h3 p, h3 span, p')].map(e => clean(e.innerText)).filter(Boolean);
        return [ps[1] || '', (applied ? 'APPLIED ' : '') + (ps[0] || t.replace(/^Add the .*? (offer )?to your favorites /, '')),
          'https://www.hellowork.com/fr-fr/emplois/' + m[1] + '.html', ps.find(p => /\d{2}|[A-Z][a-z]+ - \d/.test(p)) || '']; });
    },
    linkedin() {
      return [...document.querySelectorAll('a[href*="/jobs/view/"], a[href*="currentJobId="]')].map(a => {
        const m = a.href.match(/jobs\/view\/(?:[^/?]*-)?(\d{8,})|currentJobId=(\d{8,})/); if (!m) return [];
        const c = a.closest('li') || a.parentElement;
        return [c.querySelector('.artdeco-entity-lockup__subtitle, .base-search-card__subtitle, [class*="company"]')?.innerText,
          a.getAttribute('aria-label') || a.innerText, 'https://www.linkedin.com/jobs/view/' + (m[1] || m[2]),
          c.querySelector('.artdeco-entity-lockup__caption, .job-search-card__location, [class*="location"]')?.innerText]; });
    },
    wttj() {
      return [...document.querySelectorAll('a[href*="/jobs/"]')].map(a => { const h = a.getAttribute('href') || '';
        if (!/\/companies\/[^/]+\/jobs\/[^/?#]+/.test(h)) return [];
        const c = a.closest('article,li,[data-testid]') || a.parentElement.parentElement; const p = (c.innerText || '').split('\n').map(clean).filter(Boolean);
        const co = h.match(/companies\/([^/]+)/)[1];
        return [p.find(x => x.toLowerCase().replace(/[^a-z0-9]/g, '').startsWith(co.split('-')[0])) || co, clean(a.innerText) || p[0],
          location.origin + h.split('?')[0], p.find(x => /^[A-ZÉ][\w\s'-]+$/.test(x) && x.length < 25 && x !== p[0]) || '']; });
    },
  };
  const pick = () => /glassdoor/.test(location.host) ? 'glassdoor' : /hellowork/.test(location.host) ? 'hellowork'
    : /linkedin/.test(location.host) ? 'linkedin' : /welcometothejungle/.test(location.host) ? 'wttj' : null;
  return {
    async run(site, { scrollTimes = 4 } = {}) { site = site || pick(); if (!X[site]) return 'no extractor for ' + location.host;
      await scroll(scrollTimes); const rows = fmt(X[site]());
      return (document.querySelector('h1')?.innerText || '').slice(0, 60) + ' | ' + rows.length + ' rows\n' + rows.join('\n'); },
    rows(site) { return fmt(X[site || pick()]()); },
  };
})();
'jb ready';
