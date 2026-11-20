"""Workday adapter: every posting on one Workday tenant's public careers API (the "cxs" JSON endpoints).

Config keys (config/bulk.json):
  endpoint   https://<tenant>.wd<N>.myworkdayjobs.com/wday/cxs/<tenant>/<site>
  facets     {"workerSubType": [...], "locationCountry": [...]}: ids copied from the site's filter URL
             (open the careers site, apply the filters, read appliedFacets in the jobs POST in DevTools)
  search     optional free-text search ("" = everything under the facets)
  max        optional cap on postings fetched (default 2000)

List: POST <endpoint>/jobs {appliedFacets, limit 20, offset, searchText}; `total` is only on page 1.
Detail: GET <endpoint><externalPath> -> jobPostingInfo {title, location, jobDescription, externalUrl, startDate}.
"""
from __future__ import annotations

import concurrent.futures as cf
import html
import json
import re
import time
import urllib.request

PAGE = 20


def http(url: str, body: dict | None = None, tries: int = 4):
    for a in range(tries):
        try:
            req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                         headers={"Content-Type": "application/json", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:
            if a + 1 < tries:
                time.sleep(2 + 3 * a)
    return None


def clean(markup: str) -> str:
    t = html.unescape(markup or "")
    t = re.sub(r"<(br|/p|/li|/h\d)[^>]*>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"[ \t ]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n", t).strip()


def list_paths(cfg: dict, get=http) -> list[str]:
    ep, cap = cfg["endpoint"].rstrip("/"), int(cfg.get("max", 2000))
    paths, off, total = [], 0, None
    while off < cap:
        d = get(ep + "/jobs", {"appliedFacets": cfg.get("facets", {}), "limit": PAGE, "offset": off,
                               "searchText": cfg.get("search", "")})
        if not d:
            break
        total = total or d.get("total") or 0
        page = d.get("jobPostings") or []
        paths += [j["externalPath"] for j in page if j.get("externalPath") and j["externalPath"] not in paths]
        off += PAGE
        if not page or off >= total:
            break
    return paths[:cap]


def to_posting(info: dict, company: str) -> dict:
    return {"company": company, "title": info.get("title", ""), "url": info.get("externalUrl", ""),
            "location": info.get("location", ""), "description": clean(info.get("jobDescription", "")),
            "posted": info.get("startDate", "")}


def fetch(cfg: dict, get=http) -> list[dict]:
    ep = cfg["endpoint"].rstrip("/")
    paths = list_paths(cfg, get)
    with cf.ThreadPoolExecutor(6) as ex:
        details = list(ex.map(lambda p: get(ep + p), paths))
    return [to_posting(d["jobPostingInfo"], cfg["company"]) for d in details if d and d.get("jobPostingInfo")]
