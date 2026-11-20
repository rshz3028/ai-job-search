#!/usr/bin/env python3
"""PreToolUse wrapper: forward to `graphify hook-guard <kind>` only when the call targets code.

The stock graphify hook nudges on every Grep and every shell grep, including lookups in the
tracker CSV, site notes and application documents, where the code graph cannot help. Each nudge
adds ~250 tokens that are then re-read on every later turn. This wrapper keeps the nudge for code
(tools/, tests/, .agents/, templates/, job_scraper/*.py and source extensions) and stays silent
otherwise. Fails open: any error prints nothing and exits 0.
"""
import json
import re
import subprocess
import sys

CODE = re.compile(r"(^|[\\/\s\"'])(tools|tests|\.agents|templates)[\\/]|\.(py|ts|tsx|js|mjs|cjs|ps1|sh)\b", re.I)


def main():
    kind = sys.argv[1] if len(sys.argv) > 1 else "search"
    raw = sys.stdin.buffer.read()
    try:
        d = json.loads(raw.decode("utf-8", "replace"))
        t = d.get("tool_input") or {}
        target = " ".join(str(t.get(k) or "") for k in ("command", "pattern", "path", "glob", "file_path"))
        if not CODE.search(target):
            return 0
        r = subprocess.run(["graphify", "hook-guard", kind], input=raw, capture_output=True, timeout=9)
        sys.stdout.buffer.write(r.stdout)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
