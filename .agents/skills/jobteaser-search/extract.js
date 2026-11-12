// JobTeaser (ESIGELEC school portal) search extractor.
// Run inside a logged-in Chrome tab on https://esigelec.jobteaser.com via
// mcp__claude-in-chrome__javascript_tool. Paste this file, then call e.g.
//   await jobteaser(['systèmes embarqués', 'linux embarqué'], {pages: 2, maxAgeDays: 14})
// Returns [{title, company, contract, location, date, url, partner}] (deduped by URL).
async function jobteaser(queries, {pages = 1, maxAgeDays = 14} = {}) {
  const today = new Date();
  const iso = (d) => d.toISOString().slice(0, 10);
  const parseDate = (s) => {
    s = (s || '').toLowerCase().trim();
    const d = new Date(today);
    if (/aujourd|heure|minute|today|hour|minute/.test(s)) return iso(d);
    if (/^hier|yesterday/.test(s)) { d.setDate(d.getDate() - 1); return iso(d); }
    if (/avant-hier/.test(s)) { d.setDate(d.getDate() - 2); return iso(d); }
    let m = s.match(/(\d+)\s*(jour|day)/); if (m) { d.setDate(d.getDate() - +m[1]); return iso(d); }
    m = s.match(/(\d+)\s*(semaine|week)/); if (m) { d.setDate(d.getDate() - 7 * m[1]); return iso(d); }
    m = s.match(/(\d+)\s*(mois|month)/); if (m) { d.setMonth(d.getMonth() - +m[1]); return iso(d); }
    return null;
  };
  const out = new Map();
  for (const q of queries) {
    for (let page = 1; page <= pages; page++) {
      const r = await fetch('/fr/job-offers?contract=internship&q=' + encodeURIComponent(q) + '&page=' + page);
      if (!r.ok) break;
      const doc = new DOMParser().parseFromString(await r.text(), 'text/html');
      const links = [...doc.querySelectorAll('a[href*="/fr/job-offers/"]')]
        .filter((a) => /\/job-offers\/[0-9a-f-]{36}/.test(a.getAttribute('href')));
      if (!links.length) break;
      for (const a of links) {
        const url = location.origin + a.getAttribute('href').split('?')[0];
        if (out.has(url)) continue;
        let card = a;
        for (let i = 0; i < 8 && card.parentElement; i++) {
          card = card.parentElement;
          if (card.querySelector('time')) break;
        }
        const time = card.querySelector('time');
        const parts = [...new Set([...card.querySelectorAll('p,span,h3')]
          .map((e) => e.textContent.trim()).filter(Boolean))];
        const title = a.textContent.trim();
        const rest = parts.filter((p) => p !== title && p !== (time && time.textContent.trim()));
        const date = time ? parseDate(time.textContent) : null; // "Offre de la semaine" cards have no <time>
        out.set(url, {
          title,
          company: rest[0] || null,
          contract: rest.find((p) => /^(stage|internship)/i.test(p)) || null,
          location: rest.find((p) => /,\s*[A-ZÉ][\w\s-]+$/.test(p) && !/^(stage|internship)/i.test(p)) || null,
          date,
          partner: /Offre partenaire|Partner offer/i.test(card.textContent),
          url,
          query: q,
        });
      }
    }
  }
  const cutoff = new Date(today); cutoff.setDate(cutoff.getDate() - maxAgeDays);
  return [...out.values()].filter((j) => !j.date || j.date >= iso(cutoff));
}
