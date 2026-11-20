"""Bulk employer sources: one big employer's own careers API, fetched in full and fed into data/jobs.db.

Why a separate place: a large employer (hundreds of openings on one ATS) is cheaper to pull straight from
its careers API than through keyword searches on the job boards, and its application form is identical
for every posting, so a form helper and a playbook pay for themselves after a few applications.

A bulk source is:
  config/bulk.json  "employers": {<name>: {adapter, company, track, enabled, ...adapter settings}}
  an adapter        tools/bulk/<adapter>.py with fetch(cfg) -> list of posting dicts (keys below)
  optional extras   tools/bulk/<name>/: PLAYBOOK.md (form walk-through), form.js (in-page helper)

Posting dict keys: company, title, url, location, description, posted (all str; description may be "").

`python tools/pipeline.py bulk <name>` stores the postings as `found` in the employer's track, through the
same intake gate as the blanket search. They are then ranked by `pipeline.py rank` like any other posting
(excluded employers, deal-breakers and fit score all apply) and appear in `pipeline.py next`.
To add an employer on an ATS that already has an adapter (e.g. another Workday tenant), add a config entry
only. A new ATS = one new adapter module registered in ADAPTERS.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import workday

ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG = ROOT / "config" / "bulk.json"
ADAPTERS = {"workday": workday.fetch}
KEYS = ("company", "title", "url", "location", "description", "posted")


def employers(path: Path = CONFIG) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("employers", {})


def get(name: str, path: Path = CONFIG) -> dict:
    emp = employers(path)
    if name not in emp:
        raise SystemExit(f"unknown bulk employer {name!r}; configured: {', '.join(emp) or 'none'} ({path})")
    cfg = dict(emp[name])
    cfg.setdefault("name", name)
    if cfg.get("adapter") not in ADAPTERS:
        raise SystemExit(f"{name}: adapter {cfg.get('adapter')!r} unknown; adapters: {', '.join(ADAPTERS)}")
    for k in ("company", "track"):
        if not cfg.get(k):
            raise SystemExit(f"{name}: config needs {k!r}")
    return cfg


def fetch(cfg: dict) -> list[dict]:
    """Run the employer's adapter and normalise its output to the posting dict keys."""
    out = []
    for p in ADAPTERS[cfg["adapter"]](cfg):
        row = {k: str(p.get(k) or "").strip() for k in KEYS}
        row["company"] = row["company"] or cfg["company"]
        if row["title"] and row["url"]:
            out.append(row)
    return out
