#!/usr/bin/env python3
"""Print a browser helper as one compact JS line to paste into javascript_tool (no Read of the commented source).

  python tools/ff_inject.py            # form_fill.js  -> localStorage.ff=...;eval(localStorage.ff)
  python tools/ff_inject.py boards     # board_extract.js -> eval'd directly (window.jb)
  python tools/ff_inject.py --check    # syntax-check both minified helpers with node, print sizes

Strips comment lines, trailing ` // ` comments and indentation (about 40 % smaller than the source).
The source files stay the documented, editable versions.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
FILES = {"ff": TOOLS / "form_fill.js", "boards": TOOLS / "board_extract.js"}


def minify(src: str) -> str:
    out = []
    for line in src.splitlines():
        s = line.strip()
        if not s or s.startswith("//"):
            continue
        s = re.sub(r"\s+//\s.*$", "", s)  # trailing comment (code never contains ' // ')
        out.append(s)
    return "\n".join(out)


def snippet(name: str) -> str:
    code = minify(FILES[name].read_text(encoding="utf-8"))
    if name == "ff":  # stored per origin so later pages only need eval(localStorage.ff)
        return f"localStorage.ff={json.dumps(code, ensure_ascii=False)};eval(localStorage.ff)"
    return code


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "--check" in argv:
        ok = True
        for name, f in FILES.items():
            code = minify(f.read_text(encoding="utf-8"))
            r = subprocess.run(["node", "-e", "new Function(require('fs').readFileSync(0,'utf8'))"],
                               input=code, capture_output=True, text=True, encoding="utf-8")
            ok &= r.returncode == 0
            print(f"{name}: {f.stat().st_size} -> {len(code)} chars, syntax {'ok' if r.returncode == 0 else 'ERROR ' + r.stderr.strip().splitlines()[-1][:120]}")
        return 0 if ok else 1
    name = argv[0] if argv else "ff"
    if name not in FILES:
        print(__doc__)
        return 2
    print(snippet(name))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
