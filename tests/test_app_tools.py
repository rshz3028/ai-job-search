"""Tests for the token-saving batch tools: app.py (patching), ff_inject.py (minify), seen.py portal ids."""
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import app  # noqa: E402
import ff_inject  # noqa: E402
import seen  # noqa: E402
import build_verify  # noqa: E402


class SetPath(unittest.TestCase):
    def test_dict_list_and_append(self):
        d = {"headline": "a", "sections": [{"text": "x"}], "paragraphs": ["p0"]}
        app.set_path(d, "headline", "b")
        app.set_path(d, "sections.0.text", "y")
        app.set_path(d, "paragraphs.1", "p1")  # index == len appends
        app.set_path(d, "labels.contact", "Contact")  # missing dict is created
        self.assertEqual(d, {"headline": "b", "sections": [{"text": "y"}], "paragraphs": ["p0", "p1"],
                             "labels": {"contact": "Contact"}})

    def test_bad_index_raises(self):
        with self.assertRaises(IndexError):
            app.set_path({"p": ["a"]}, "p.5", "z")


class SrcPaths(unittest.TestCase):
    def test_accepts_base_or_paths(self):
        for frm in ("acme_x", "cv/main_acme_x.json", "cover_letters/cover_acme_x.json", "main_acme_x.pdf"):
            cv, co = app.src_paths(frm)
            self.assertEqual(cv.name, "main_acme_x.json")
            self.assertEqual(co.name, "cover_acme_x.json")


class Minify(unittest.TestCase):
    def test_strips_comments_keeps_urls(self):
        src = "// header\n  const a = 1;  // trailing note\n  const u = 'https://x.y/z';\n\n"
        self.assertEqual(ff_inject.minify(src), "const a = 1;\nconst u = 'https://x.y/z';")

    def test_ff_snippet_stores_in_localstorage(self):
        self.assertTrue(ff_inject.snippet("ff").startswith("localStorage.ff="))
        self.assertTrue(ff_inject.snippet("ff").endswith(";eval(localStorage.ff)"))

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_helpers_parse(self):
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "ff_inject.py"), "--check"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class PortalIds(unittest.TestCase):
    def test_glassdoor_and_hellowork_ids(self):
        self.assertIn("1010318963038", seen.ids_in("https://www.glassdoor.fr/job-listing/a.htm?jl=1010318963038"))
        self.assertIn("85471579", seen.ids_in("https://www.hellowork.com/fr-fr/emplois/85471579.html"))

    def test_existing_ids_unchanged(self):
        self.assertIn("4480444976", seen.ids_in("https://www.linkedin.com/jobs/view/4480444976"))


class Availability(unittest.TestCase):
    def test_phrases(self):
        for t in ("MSc student, available immediately.", "Disponible immédiatement pour un stage", "disponible dès maintenant"):
            self.assertTrue(build_verify.AVAIL_RX.search(t), t)
        self.assertIsNone(build_verify.AVAIL_RX.search("MSc student seeking a six-month internship."))


if __name__ == "__main__":
    unittest.main()
