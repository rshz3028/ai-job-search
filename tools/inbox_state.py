#!/usr/bin/env python3
"""Inbox-check state for the session-start rule: when was the last check, and what to search.

  python tools/inbox_state.py status   # "fresh" (checked < 4 h ago, skip) or "due", plus the last check time
  python tools/inbox_state.py query    # Gmail query covering everything since the last check (1 h overlap)
  python tools/inbox_state.py url      # the same search as a Chrome URL for /mail/u/0 (rshz3028)
  python tools/inbox_state.py mark     # record a completed check of both inboxes (now)

The query drops pure-noise senders (job-alert digests, social networks). Application
acknowledgements, rejections and recruiter mail are never excluded. Edit NOISE to tune.
"""
from __future__ import annotations

import json
import urllib.parse
import sys
import time
from pathlib import Path

STATE = Path(__file__).resolve().parent.parent / "trackers" / "inbox_state.json"
FRESH_HOURS = 4
DEFAULT_LOOKBACK_H = 72
NOISE = [  # bare words match any address or domain containing them (glassdoor.com and glassdoor.fr alike)
    "jobalerts-noreply@linkedin.com", "messages-noreply@linkedin.com", "notifications-noreply@linkedin.com",
    "facebookmail", "instagram", "glassdoor", "toogoodtogo", "codeforces", "iziwork",
    "noreply-accounts@google.com", "revolut", "bnpparibas", "samsung",
]


def last():
    try:
        return float(json.loads(STATE.read_text(encoding="utf-8"))["last_check_epoch"])
    except (OSError, ValueError, KeyError):
        return None


def main(cmd):
    t = last()
    now = time.time()
    if cmd == "status":
        if t and now - t < FRESH_HOURS * 3600:
            print(f"fresh: last check {time.strftime('%Y-%m-%d %H:%M', time.localtime(t))} ({(now - t) / 3600:.1f} h ago), skip")
        else:
            print("due" + (f": last check {time.strftime('%Y-%m-%d %H:%M', time.localtime(t))}" if t else ": never checked"))
    elif cmd in ("query", "url"):
        since = int((t - 3600) if t else now - DEFAULT_LOOKBACK_H * 3600)
        q = f"after:{since} -in:sent -in:drafts -category:social -from:({' OR '.join(NOISE)})"
        print(q if cmd == "query" else "https://mail.google.com/mail/u/0/#search/" + urllib.parse.quote(q, safe=""))
    elif cmd == "mark":
        STATE.write_text(json.dumps({"last_check_epoch": int(now), "last_check": time.strftime("%Y-%m-%d %H:%M")}) + "\n", encoding="utf-8")
        print("marked", time.strftime("%Y-%m-%d %H:%M"))
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
