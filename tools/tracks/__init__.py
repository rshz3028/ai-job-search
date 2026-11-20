"""Pipeline tracks: one module per job situation, each a self-contained "function" the pipeline calls.

A track is two files:
  config/tracks/<name>.json   what to search for and where: location, jobage_days, portals, keyword families
  tools/tracks/<name>.py      how to judge a posting: DEFAULT_MIN, TITLE_ONLY_SLACK and
                              decide(row, desc, lk, min_score) -> (stage, score, hits, flags, reason)

Every pipeline command takes --track <name> (default: internship). To add a situation, copy the closest
track's two files, change them, and register the module in TRACKS below. Nothing else changes.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import internship, parttime

ROOT = Path(__file__).resolve().parent.parent.parent
TRACKS = {"internship": internship, "parttime": parttime}
DEFAULT = "internship"


def names() -> list[str]:
    return list(TRACKS)


def get(name: str):
    if name not in TRACKS:
        raise SystemExit(f"unknown track {name!r}; tracks: {', '.join(TRACKS)}")
    return TRACKS[name]


def config(name: str) -> dict:
    get(name)
    return json.loads((ROOT / "config" / "tracks" / f"{name}.json").read_text(encoding="utf-8"))


def from_argv(argv: list[str]) -> str:
    """--track <name> from a command line (removed from argv in place); default internship."""
    if "--track" in argv:
        i = argv.index("--track")
        name = argv[i + 1]
        del argv[i:i + 2]
        get(name)
        return name
    return DEFAULT
