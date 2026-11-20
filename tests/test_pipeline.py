"""The job pipeline core (docs/PIPELINE.md): db identity and intake, track verdicts, pipeline commands, bulk sources.

Everything runs on a temporary SQLite file and fake tracker lookups: no network, no real tracker or db.
"""
from __future__ import annotations

import io
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import bulk  # noqa: E402
import jobsdb  # noqa: E402
import pipeline  # noqa: E402
import seen  # noqa: E402
from bulk import workday  # noqa: E402
from tracks import internship, parttime  # noqa: E402


class FakeLookup:
    """seen.Lookup stand-in: {fold(company): status}; status 'excluded' mimics excluded_employers.txt."""

    def __init__(self, by_company=None):
        self.by_company = {seen.fold(k): v for k, v in (by_company or {}).items()}

    def find(self, company, title, url=""):
        st = self.by_company.get(seen.fold(company))
        if not st:
            return None
        if st == "excluded":
            return "excluded", {"s": "excluded", "why": f"excluded employer '{company}'", "lbl": company}
        return "co+title", {"s": st, "why": "test match", "lbl": f"{company} | {title}"}


def gate_with(lookup):
    return jobsdb.IntakeGate(lookup)


class DbCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.con = jobsdb.connect(Path(self.tmp.name) / "jobs.db")

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def add(self, **kw):
        base = {"company": "Acme", "title": "Stage systèmes embarqués", "url": "https://example.com/j/1"}
        base.update(kw)
        return jobsdb.upsert(self.con, **base)

    def row(self, key=None):
        q = "SELECT * FROM postings" + (" WHERE key=?" if key else " ORDER BY id DESC LIMIT 1")
        return self.con.execute(q, (key,) if key else ()).fetchone()


# ---------------------------------------------------------------- identity
class PostingIdentity(unittest.TestCase):
    def test_linkedin_id_from_view_url(self):
        self.assertEqual(jobsdb.portal_id("https://www.linkedin.com/jobs/view/stage-embarque-at-acme-4312345678/"),
                         ("linkedin", "4312345678"))

    def test_workday_key_holds_tenant_and_requisition(self):
        url = "https://thales.wd3.myworkdayjobs.com/Careers/job/Toulouse/Stage-Logiciel-Embarqu_R0281234"
        self.assertEqual(jobsdb.portal_id(url), ("workday", "thales/r0281234"))

    def test_workday_key_ignores_apply_suffix_and_locale(self):
        a = "https://alliancewd.wd3.myworkdayjobs.com/renault-group-careers/job/Lardy/Stage-IA_JOBREQ_50286977"
        b = "https://alliancewd.wd3.myworkdayjobs.com/fr-FR/renault-group-careers/job/Lardy/Stage-IA_JOBREQ_50286977/apply/useMyLastApplication"
        self.assertEqual(jobsdb.make_key("x", "y", a), jobsdb.make_key("other", "z", b))
        self.assertEqual(jobsdb.make_key("x", "y", a), "workday:alliancewd/50286977")

    def test_same_requisition_on_two_tenants_differs(self):
        a = "https://acme.wd3.myworkdayjobs.com/Careers/job/Paris/Intern_R1"
        b = "https://other.wd5.myworkdayjobs.com/Careers/job/Paris/Intern_R1"
        self.assertNotEqual(jobsdb.make_key("", "", a), jobsdb.make_key("", "", b))

    def test_without_portal_id_key_is_company_and_title_folded(self):
        k1 = jobsdb.make_key("Société Générale", "Stage Embarqué (H/F)", "https://careers.example.com/123")
        k2 = jobsdb.make_key("societe generale", "stage embarque h f", "https://other.example.com/9")
        self.assertEqual(k1, k2)
        self.assertTrue(k1.startswith("ct:"))


# ---------------------------------------------------------------- intake
class Upsert(DbCase):
    def test_new_posting_is_found_and_returns_true(self):
        self.assertTrue(self.add())
        r = self.row()
        self.assertEqual((r["stage"], r["track"]), ("found", "internship"))

    def test_second_sighting_is_not_new_and_fills_missing_description(self):
        self.add(description="")
        self.assertFalse(self.add(description="full text"))
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM postings").fetchone()[0], 1)
        self.assertEqual(self.row()["description"], "full text")

    def test_second_sighting_keeps_existing_description(self):
        self.add(description="first")
        self.add(description="second")
        self.assertEqual(self.row()["description"], "first")

    def test_track_is_stored(self):
        self.add(track="parttime")
        self.assertEqual(self.row()["track"], "parttime")

    def test_gate_discards_a_posting_already_submitted(self):
        g = gate_with(FakeLookup({"Acme": "applied"}))
        self.assertFalse(self.add(gate=g))
        r = self.row()
        self.assertEqual(r["stage"], "discarded")
        self.assertIn("already submitted: applied", r["reason"])
        self.assertEqual(g.dropped, 1)

    def test_gate_lets_drafted_but_unsent_through(self):
        g = gate_with(FakeLookup({"Acme": "drafted"}))
        self.assertTrue(self.add(gate=g))
        self.assertEqual(self.row()["stage"], "found")

    def test_dedupe_only_touches_waiting_postings(self):
        self.add(url="https://example.com/a", title="Stage A")
        self.add(url="https://example.com/b", title="Stage B")
        self.con.execute("UPDATE postings SET stage='applied' WHERE title='Stage B'")
        n = jobsdb.dedupe(self.con, gate_with(FakeLookup({"Acme": "rejected"})))
        self.assertEqual(n, 1)
        stages = dict(self.con.execute("SELECT title, stage FROM postings").fetchall())
        self.assertEqual(stages, {"Stage A": "discarded", "Stage B": "applied"})


# ---------------------------------------------------------------- tracks
def posting(title, location="Paris", company="Acme", url="https://example.com/j"):
    return {"title": title, "location": location, "company": company, "url": url}


class InternshipDecide(unittest.TestCase):
    lk = FakeLookup()
    EMB = ("Stage firmware embarqué STM32: développement en C sur microcontrôleur, bus CAN et UART, "
           "banc de test et validation, capteurs, Python pour l'automatisation. 6 mois.")

    def decide(self, title, desc, lk=None):
        return internship.decide(posting(title), desc, lk or self.lk, internship.DEFAULT_MIN)

    def test_embedded_internship_is_fit(self):
        st, score, hits, _, _ = self.decide("Stage - Ingénieur logiciel embarqué (F/H)", self.EMB)
        self.assertEqual(st, "fit")
        self.assertGreaterEqual(score, internship.DEFAULT_MIN)
        self.assertIn("EMBEDDED", hits)

    def test_non_internship_title_is_discarded(self):
        self.assertEqual(self.decide("Ingénieur logiciel embarqué", self.EMB)[4], "not an internship title")

    def test_non_engineering_title_is_discarded(self):
        self.assertEqual(self.decide("Stage marketing digital", self.EMB)[4], "non-engineering title")

    def test_deal_breakers(self):
        for extra, why in [("Contrat en alternance.", "alternance"),
                           ("Poste soumis à habilitation secret défense.", "clearance/nationality"),
                           ("Français courant exigé.", "fluent French required"),
                           ("Stage de 2 mois.", "duration/level"),
                           ("CDI temps plein.", "not an internship contract")]:
            with self.subTest(why=why):
                st, _, _, _, reason = self.decide("Stage systèmes embarqués", self.EMB + " " + extra)
                self.assertEqual((st, reason), ("discarded", "deal-breaker: " + why))

    def test_single_defence_mention_in_body_is_tolerated(self):
        st = self.decide("Stage systèmes embarqués", self.EMB + " Clients: automobile, défense.")[0]
        self.assertEqual(st, "fit")

    def test_defence_in_title_is_a_deal_breaker(self):
        self.assertEqual(self.decide("Stage embarqué systèmes de défense", self.EMB)[4], "deal-breaker: defence/nuclear")

    def test_never_claim_skills_are_penalised(self):
        plain = self.decide("Stage systèmes embarqués", self.EMB)
        hdl = self.decide("Stage systèmes embarqués", self.EMB + " VHDL, FPGA, Verilog, RTL requis.")
        self.assertLess(hdl[1], plain[1])
        self.assertIn("HDL", hdl[3])

    def test_title_only_passes_at_a_lower_bar_and_is_flagged(self):
        st, score, _, flags, _ = self.decide("Stage firmware embarqué", "")
        self.assertEqual(st, "fit")
        self.assertIn("title-only", flags)

    def test_already_applied_short_circuits(self):
        st, _, _, _, reason = self.decide("Stage systèmes embarqués", self.EMB, FakeLookup({"Acme": "applied"}))
        self.assertEqual(st, "applied")
        self.assertIn("already applied", reason)

    def test_excluded_employer_is_discarded(self):
        st, _, _, _, reason = self.decide("Stage systèmes embarqués", self.EMB, FakeLookup({"Acme": "excluded"}))
        self.assertEqual(st, "discarded")
        self.assertIn("excluded", reason)


class ParttimeDecide(unittest.TestCase):
    lk = FakeLookup()
    EN = ("We are looking for a part-time receptionist, 16 hours per week, to welcome our guests at the front desk. "
          "You will check in guests and answer their questions. Our team works in English. Basic French is a plus.")

    def decide(self, title, desc, location="Paris"):
        return parttime.decide(posting(title, location), desc, self.lk, parttime.DEFAULT_MIN)

    def test_english_part_time_reception_is_fit(self):
        self.assertEqual(self.decide("Part-time Receptionist", self.EN)[0], "fit")

    def test_too_many_hours_is_discarded(self):
        desc = self.EN.replace("16 hours per week", "30 hours per week")
        self.assertEqual(self.decide("Part-time Receptionist", desc)[4], "deal-breaker: 30 h/week")

    def test_outside_paris_is_discarded(self):
        self.assertEqual(self.decide("Part-time Receptionist", self.EN, "Lyon")[4],
                         "deal-breaker: outside the Paris region")

    def test_childcare_is_discarded(self):
        self.assertEqual(self.decide("Hôte d'accueil", self.EN + " Babysitting after school.")[4],
                         "deal-breaker: teaching/childcare")

    def test_french_above_basic_is_discarded(self):
        desc = self.EN.replace("Basic French is a plus.", "Fluent French and English required.")
        self.assertEqual(self.decide("Part-time Receptionist", desc)[0], "discarded")

    def test_internship_or_manager_title_is_discarded(self):
        for t in ("Stage réception hôtel", "Front Office Manager"):
            with self.subTest(t=t):
                self.assertEqual(self.decide(t, self.EN)[4], "management/technical/internship title")


# ---------------------------------------------------------------- pipeline commands
class PipelineCommands(DbCase):
    def run_cmd(self, fn, *a, **kw):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = fn(*a, **kw)
        return rc, out.getvalue()

    def test_next_lists_fit_postings_of_the_track_best_first(self):
        for i, (sc, tr) in enumerate([(60, "internship"), (80, "internship"), (90, "parttime")]):
            self.add(url=f"https://example.com/{i}", title=f"Stage {i}", track=tr)
            self.con.execute("UPDATE postings SET stage='fit', score=? WHERE url=?", (sc, f"https://example.com/{i}"))
        with mock.patch.object(seen, "Lookup", lambda: FakeLookup()):
            _, out = self.run_cmd(pipeline.nxt, self.con, 5, "internship")
        lines = out.strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("| 80 |", lines[0])

    def test_sync_copies_tracker_status_onto_postings(self):
        self.add(company="Acme")
        self.add(company="Beta", url="https://example.com/2")
        self.con.execute("UPDATE postings SET stage='fit'")
        with mock.patch.object(seen, "Lookup", lambda: FakeLookup({"Acme": "interview", "Beta": "rejected"})):
            n = pipeline.sync(self.con)
        self.assertEqual(n, 2)
        stages = dict(self.con.execute("SELECT company, stage FROM postings").fetchall())
        self.assertEqual(stages, {"Acme": "applied", "Beta": "closed"})

    def test_sync_keeps_queued_over_drafted(self):
        self.add()
        self.con.execute("UPDATE postings SET stage='queued'")
        with mock.patch.object(seen, "Lookup", lambda: FakeLookup({"Acme": "drafted"})):
            self.assertEqual(pipeline.sync(self.con), 0)

    def test_mark_skipped_discards_and_writes_the_skip_log(self):
        self.add()
        pid = self.row()["id"]
        skips = Path(self.tmp.name) / "skipped.tsv"
        with mock.patch.object(seen, "SKIPS", skips):
            rc, _ = self.run_cmd(pipeline.mark, self.con, pid, "skipped", "needs PLC")
        self.assertEqual(rc, 0)
        r = self.row()
        self.assertEqual((r["stage"], r["reason"]), ("discarded", "skipped: needs PLC"))
        self.assertIn("needs PLC", skips.read_text(encoding="utf-8"))

    def test_mark_rejects_an_unknown_stage(self):
        self.add()
        rc, out = self.run_cmd(pipeline.mark, self.con, self.row()["id"], "sent", "")
        self.assertEqual(rc, 1)
        self.assertEqual(self.row()["stage"], "found")

    def test_add_records_an_outside_application(self):
        rc, out = self.run_cmd(pipeline.add, self.con, "parttime",
                               ["--company", "Hostel X", "--title", "Night receptionist", "--url", "mailto:jobs@x.example"])
        self.assertEqual(rc, 0)
        r = self.row()
        self.assertEqual((r["stage"], r["track"], r["company"]), ("applied", "parttime", "Hostel X"))


# ---------------------------------------------------------------- bulk sources
WD_CFG = {"name": "acme", "adapter": "workday", "company": "Acme", "track": "internship",
          "endpoint": "https://acme.wd3.myworkdayjobs.com/wday/cxs/acme/Careers", "facets": {"x": ["1"]}}


def fake_workday(n_postings, page_total=None):
    """A Workday tenant with n postings: list pages of 20 (total only on page 1) + detail per path."""
    calls = []

    def get(url, body=None):
        calls.append((url, body))
        if url.endswith("/jobs"):
            off = body["offset"]
            page = [{"externalPath": f"/job/Paris/Stage-{i}_R{i:04d}"} for i in range(off, min(off + 20, n_postings))]
            return {"total": (page_total or n_postings) if off == 0 else 0, "jobPostings": page}
        i = int(url.rsplit("_R", 1)[1])
        return {"jobPostingInfo": {"title": f"Stage embarqué {i}", "location": "Paris",
                                   "jobDescription": "<p>Firmware&nbsp;C</p><ul><li>CAN</li></ul>",
                                   "externalUrl": f"https://acme.wd3.myworkdayjobs.com/Careers/job/Paris/Stage-{i}_R{i:04d}",
                                   "startDate": "2026-11-01"}}
    return get, calls


class WorkdayAdapter(unittest.TestCase):
    def test_pages_through_the_list_and_fetches_every_detail(self):
        get, calls = fake_workday(45)
        out = workday.fetch(WD_CFG, get=get)
        self.assertEqual(len(out), 45)
        list_calls = [b for u, b in calls if u.endswith("/jobs")]
        self.assertEqual([b["offset"] for b in list_calls], [0, 20, 40])
        self.assertEqual(list_calls[0]["appliedFacets"], {"x": ["1"]})

    def test_maps_detail_to_a_posting_and_cleans_html(self):
        get, _ = fake_workday(1)
        p = workday.fetch(WD_CFG, get=get)[0]
        self.assertEqual(p["company"], "Acme")
        self.assertEqual(p["title"], "Stage embarqué 0")
        self.assertEqual(p["description"], "Firmware C\nCAN")
        self.assertTrue(p["url"].endswith("_R0000"))

    def test_respects_max(self):
        get, _ = fake_workday(100)
        self.assertEqual(len(workday.fetch({**WD_CFG, "max": 30}, get=get)), 30)

    def test_failed_list_call_returns_nothing(self):
        self.assertEqual(workday.fetch(WD_CFG, get=lambda u, b=None: None), [])

    def test_failed_detail_is_skipped(self):
        get, _ = fake_workday(3)
        flaky = lambda u, b=None: None if u.endswith("_R0001") else get(u, b)  # noqa: E731
        self.assertEqual(len(workday.fetch(WD_CFG, get=flaky)), 2)


class BulkConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "bulk.json"

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, employers):
        self.path.write_text(json.dumps({"employers": employers}), encoding="utf-8")

    def test_get_validates_adapter_and_required_keys(self):
        self.write({"a": {"adapter": "nope", "company": "A", "track": "internship"},
                    "b": {"adapter": "workday", "track": "internship"}})
        for name in ("a", "b", "missing"):
            with self.subTest(name=name), self.assertRaises(SystemExit):
                bulk.get(name, self.path)

    def test_shipped_config_is_valid(self):
        for name in bulk.employers():
            with self.subTest(name=name):
                cfg = bulk.get(name)
                self.assertIn(cfg["track"], ("internship", "parttime"))

    def test_fetch_normalises_and_drops_incomplete_postings(self):
        rows = [{"title": " T ", "url": "u", "company": ""}, {"title": "", "url": "u2"}, {"title": "x"}]
        with mock.patch.dict(bulk.ADAPTERS, {"workday": lambda cfg: rows}):
            out = bulk.fetch(WD_CFG)
        self.assertEqual(out, [{"company": "Acme", "title": "T", "url": "u", "location": "", "description": "", "posted": ""}])


class BulkCommand(DbCase):
    def bulk(self, cfg, rest, postings=(), lookup=None):
        out = io.StringIO()
        with mock.patch.object(bulk, "get", lambda name: dict(cfg)), redirect_stdout(out):
            rc = pipeline.bulk(self.con, [cfg["name"], *rest], fetcher=lambda c: list(postings),
                               lookup=lookup or FakeLookup())
        return rc, out.getvalue()

    def postings(self, n):
        get, _ = fake_workday(n)
        return [{k: str(v) for k, v in p.items()} for p in workday.fetch(WD_CFG, get=get)]

    def test_stores_postings_as_found_in_the_employer_track(self):
        rc, out = self.bulk(WD_CFG, [], self.postings(3))
        self.assertEqual(rc, 0)
        rows = self.con.execute("SELECT stage, track, portal, query, key FROM postings").fetchall()
        self.assertEqual(len(rows), 3)
        self.assertEqual({(r[0], r[1], r[2], r[3]) for r in rows}, {("found", "internship", "acme", "bulk:acme")})
        self.assertTrue(all(r[4].startswith("workday:acme/") for r in rows))
        self.assertEqual(self.con.execute("SELECT found, new FROM search_runs").fetchone()[:], (3, 3))

    def test_rerun_adds_nothing_new(self):
        self.bulk(WD_CFG, [], self.postings(3))
        _, out = self.bulk(WD_CFG, [], self.postings(4))
        self.assertIn("4 postings, 1 new", out)

    def test_disabled_employer_is_not_fetched(self):
        rc, out = self.bulk({**WD_CFG, "enabled": False, "disabled_reason": "paused"}, [], self.postings(2))
        self.assertEqual(rc, 1)
        self.assertIn("paused", out)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM postings").fetchone()[0], 0)

    def test_excluded_employer_is_not_fetched(self):
        rc, out = self.bulk(WD_CFG, [], self.postings(2), lookup=FakeLookup({"Acme": "excluded"}))
        self.assertEqual(rc, 1)
        self.assertIn("excluded", out)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM postings").fetchone()[0], 0)

    def test_dry_run_stores_nothing(self):
        rc, out = self.bulk(WD_CFG, ["--dry-run"], self.postings(2))
        self.assertEqual(rc, 0)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM postings").fetchone()[0], 0)

    def test_list_without_a_name(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(pipeline.bulk(self.con, []), 0)
        self.assertIn("thales", out.getvalue())


if __name__ == "__main__":
    unittest.main()
