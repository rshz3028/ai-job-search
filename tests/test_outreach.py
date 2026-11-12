"""Tests for tools/outreach.py (the /outreach bookkeeping helper)."""
import csv
import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import outreach  # noqa: E402

FIELDS = ["date", "company", "sector", "role", "role_type", "channel", "status", "contact_person",
          "fit_rating", "notes", "cv_file", "cover_letter_file", "source", "deadline"]


class OutreachTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.orig = (outreach.TRACKER, outreach.LOG, outreach.APPS)
        outreach.TRACKER = self.tmp / "tracker.csv"
        outreach.LOG = self.tmp / "outreach" / "log.csv"
        outreach.APPS = self.tmp / "apps"
        outreach.APPS.mkdir()
        d = lambda n: (dt.date.today() - dt.timedelta(days=n)).isoformat()
        rows = [
            dict(date=d(10), company="Acme", role="Stage Electronique H/F", role_type="internship", status="applied", fit_rating="80", notes="a, b"),
            dict(date=d(10), company="Old", role="Intern", role_type="internship", status="applied", fit_rating="90", notes=""),
            dict(date=d(1), company="Fresh", role="Intern", role_type="internship", status="applied", fit_rating="90", notes=""),
            dict(date=d(10), company="Done", role="Intern", role_type="internship", status="rejected", fit_rating="90", notes=""),
            dict(date=d(10), company="Job", role="CDI", role_type="full_time", status="applied", fit_rating="90", notes=""),
            dict(date=d(10), company="Chased", role="Intern", role_type="internship", status="applied", fit_rating="90",
                 notes="followed up 2026-01-01; followed up 2026-01-08"),
        ]
        rows[1]["date"] = d(100)
        with outreach.TRACKER.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, restval="")
            w.writeheader()
            w.writerows(rows)

    def tearDown(self):
        outreach.TRACKER, outreach.LOG, outreach.APPS = self.orig

    def args(self, **kw):
        base = dict(min_days=3, max_days=45, limit=15, company=None, all_types=False)
        base.update(kw)
        return SimpleNamespace(**base)

    def test_only_eligible_rows(self):
        names = [c["company"] for c in outreach.candidates(self.args())]
        self.assertEqual(names, ["Acme"])

    def test_company_filter_ignores_age(self):
        names = [c["company"] for c in outreach.candidates(self.args(company="old"))]
        self.assertEqual(names, ["Old"])

    def test_sent_log_excludes_and_notes_tracker(self):
        acme = outreach.candidates(self.args())[0]
        res = outreach.log(SimpleNamespace(company="Acme", role=acme["role"], date=acme["applied_date"],
                                           status="sent", to="rh@acme.fr", name="", title="",
                                           source="https://acme.fr/contact", lang="fr", notes="x\ny"))
        self.assertTrue(res["tracker_note_added"])
        self.assertEqual(outreach.candidates(self.args()), [])
        with outreach.TRACKER.open(encoding="utf-8", newline="") as f:
            row = next(r for r in csv.DictReader(f) if r["company"] == "Acme")
        self.assertIn("followed up", row["notes"])
        self.assertTrue(row["notes"].startswith("a, b; "))
        self.assertEqual(outreach.stats()["sent_today"], 1)

    def test_subfolder_rule(self):
        self.assertEqual(outreach.subfolder("Novo Nordisk A/S", "ML  Engineer"), "novo_nordisk_as_ml_engineer")

    def test_archive_fuzzy_match(self):
        (outreach.APPS / "acme_stage_electronique").mkdir()
        found = outreach.find_archive("Acme", "Stage Electronique H/F", outreach.APPS)
        self.assertEqual(found.name, "acme_stage_electronique")


if __name__ == "__main__":
    unittest.main()
