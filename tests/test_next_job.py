"""Tests for tools/next_job.py (the /autopilot picker)."""
import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from next_job import pick, score_of  # noqa: E402

TODAY = dt.date(2026, 11, 10)


class NextJobTests(unittest.TestCase):
    def test_order_filters_and_dedupe(self):
        seen = {
            "a": {"status": "ranked", "company": "Acme", "title": "Power Electronics Intern", "fit": "medium"},
            "b": {"status": "ranked", "company": "Beta", "title": "Embedded Intern", "score": 90},
            "c": {"status": "ranked", "company": "Gamma", "title": "Test Intern", "score": 70, "deadline": "2026-11-14"},
            "d": {"status": "ranked", "company": "Delta", "title": "X", "score": 95, "deadline": "2026-11-01"},
            "e": {"status": "new", "company": "Eps", "title": "Y", "score": 99},
            "f": {"status": "ranked", "company": "Low", "title": "Z", "fit": "low"},
            "g": {"status": "ranked", "company": "Acme SAS", "title": "Stage Power Electronics H/F", "score": 85},
        }
        tracker = [{"company": "Acme SAS", "role": "Power Electronics Internship"}]
        keys = [j["key"] for j in pick(seen, tracker, 60, TODAY)]
        self.assertEqual(keys, ["c", "b"])

    def test_score_fallbacks(self):
        self.assertEqual(score_of({"fit": "High"}), 80)
        self.assertEqual(score_of({"score": 72, "fit": "low"}), 72)
        self.assertEqual(score_of({}), 0)


if __name__ == "__main__":
    unittest.main()
