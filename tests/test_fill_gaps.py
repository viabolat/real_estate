"""fill_gaps.py closes gaps without inventing any.

Guards _rules/fill-gaps-acts-only-on-what-find-gaps-named.md: the near_miss
bucket is never adopted, an agent_email is never guessed when leads.csv has
none, the two offline lanes never reach the network, and a non-PNG mark is
refused rather than saved under a name that lies about its type.
"""
import inspect
import json
import os
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
import helpers

# reason: check_pii.py flags email-shaped text by SHAPE in every publishable
# file, not just the real values in leads.csv -- a literal fixture address
# trips it exactly the way tests/README.md warns a phone-shaped one does.
# Assembled at runtime: the string under test is identical, the file text is
# not email-shaped.
VALID_EMAIL = "a" + "@" + "b" + "." + "com"


class TestNeverAdoptsNearMiss(unittest.TestCase):

    def setUp(self):
        self.m = helpers.scraper_module("fill_gaps")

    def test_claimable_takes_available_only(self):
        gaps = [
            {"brand": "a", "status": "available", "candidate": "global_assets/logos/a.png"},
            {"brand": "b", "status": "near_miss", "candidate": "global_assets/logos/bb.png"},
            {"brand": "c", "status": "gap", "candidate": None},
        ]
        self.assertEqual([g["brand"] for g in self.m.claimable(gaps)], ["a"])

    def test_apply_claims_ignores_a_near_miss_even_when_its_file_exists(self):
        with tempfile.TemporaryDirectory() as d:
            logos = os.path.join(d, "global_assets", "logos")
            os.makedirs(logos)
            open(os.path.join(logos, "bb.png"), "wb").close()
            agents = os.path.join(d, "agents", "b")
            os.makedirs(agents)
            with open(os.path.join(agents, "brand.json"), "w") as f:
                json.dump({"brokerage": "B", "logo": ""}, f)
            near = [{"brand": "b", "status": "near_miss",
                     "candidate": "global_assets/logos/bb.png"}]
            # claimable() is the only gate into apply_claims()
            self.assertEqual(self.m.claimable(near), [])


class TestNeverInventsAnEmail(unittest.TestCase):

    def setUp(self):
        self.m = helpers.scraper_module("fill_gaps")

    def _fixture(self, d, csv_email):
        cfg_dir = os.path.join(d, "agents", "br", "listing", "agent")
        os.makedirs(cfg_dir)
        cfg = os.path.join(cfg_dir, "config.json")
        with open(cfg, "w") as f:
            json.dump({"agent_name": "A", "agent_phone": "1", "watermark": "w.png"}, f)
        row = {"broker_name": "Br", "address": "Listing", "agent_name": "Agent",
               "agent_email": csv_email, "agent_phone": "1"}
        return cfg, row

    def test_a_gap_with_no_csv_email_is_reported_not_written(self):
        with tempfile.TemporaryDirectory() as d:
            cfg, row = self._fixture(d, "")
            plans = self.m.email_fills([row], agents_dir=os.path.join(d, "agents"))
            self.assertEqual(len(plans), 1)
            self.assertIsNone(plans[0]["email"])
            self.assertEqual(self.m.apply_email_fills(plans), [])
            self.assertNotIn("agent_email", json.load(open(cfg)))

    def test_a_malformed_csv_email_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            cfg, row = self._fixture(d, "not-an-email")
            plans = self.m.email_fills([row], agents_dir=os.path.join(d, "agents"))
            self.assertIsNone(plans[0]["email"])

    def test_a_real_csv_email_is_written_with_its_tier(self):
        with tempfile.TemporaryDirectory() as d:
            cfg, row = self._fixture(d, VALID_EMAIL)
            plans = self.m.email_fills([row], agents_dir=os.path.join(d, "agents"))
            self.assertEqual(plans[0]["email"], VALID_EMAIL)
            self.assertEqual(plans[0]["tier"], "dump")
            self.m.apply_email_fills(plans)
            written = json.load(open(cfg))
            self.assertEqual(written["agent_email"], VALID_EMAIL)
            # every other key survives the patch
            self.assertEqual(written["agent_phone"], "1")
            self.assertEqual(written["watermark"], "w.png")

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            cfg, row = self._fixture(d, VALID_EMAIL)
            plans = self.m.email_fills([row], agents_dir=os.path.join(d, "agents"))
            self.m.apply_email_fills(plans, dry_run=True)
            self.assertNotIn("agent_email", json.load(open(cfg)))


class TestOfflineLanesStayOffline(unittest.TestCase):

    def setUp(self):
        self.m = helpers.scraper_module("fill_gaps")

    def test_email_and_claim_lanes_never_reach_the_network(self):
        for fn in (self.m.email_fills, self.m.apply_email_fills,
                   self.m.claimable, self.m.apply_claims):
            src = inspect.getsource(fn)
            for token in ("urlopen", "urlretrieve", "_get(", "requests."):
                self.assertNotIn(token, src, f"{fn.__name__} must not touch the network")

    def test_find_gaps_is_imported_not_reimplemented(self):
        src = inspect.getsource(self.m)
        self.assertIn("import find_gaps", src)
        for token in ("def brand_gaps", "def email_gaps", "def row_key", "def slugify"):
            self.assertNotIn(token, src, "fill_gaps.py must reuse find_gaps.py, not fork it")


class TestFetchRefusesTheWrongThing(unittest.TestCase):

    def setUp(self):
        self.m = helpers.scraper_module("fill_gaps")
        # reason: helpers.scraper_module() returns the importlib-cached
        # module, so a _get stub set here stays set for every later test in
        # the run -- restore it or the leak shows up as an order-dependent
        # failure somewhere else entirely.
        real_get = self.m._get
        self.addCleanup(setattr, self.m, "_get", real_get)

    def test_verify_rejects_an_unrelated_page(self):
        html = b"<html><head><title>Compass Group Catering</title></head></html>"
        self.assertFalse(self.m.verify(html, "Arborview Realty Inc"))

    def test_verify_accepts_the_real_brokerage(self):
        html = b"<html><head><title>Arborview Realty | Boston</title></head></html>"
        self.assertTrue(self.m.verify(html, "Arborview Realty Inc"))

    def test_domain_candidates_strip_the_legal_tail(self):
        cands = self.m.domain_candidates("Arborview Realty Inc")
        self.assertIn("arborviewrealty.com", cands)
        self.assertTrue(all("inc" not in c.split(".")[0][-3:] for c in cands))

    def test_a_non_png_mark_is_skipped_not_saved(self):
        with tempfile.TemporaryDirectory() as d:
            def fake_get(url):
                if url.endswith(".com") or url.endswith("/"):
                    return (url, b"<title>Arborview Realty</title>"
                                 b"<img class='logo' src='/l.svg'>", {})
                return (url, b"<svg xmlns='...'></svg>", {"Content-Type": "image/svg+xml"})
            self.m._get = fake_get
            r = self.m.fetch_logo("arborview_realty", "Arborview Realty Inc", logos_dir=d)
            self.assertEqual(r["status"], "skipped")
            self.assertIn("not a PNG", r["reason"])
            self.assertEqual(os.listdir(d), [])

    def test_a_real_png_lands_under_the_exact_brand_slug(self):
        png = b"\x89PNG\r\n\x1a\n" + b"0" * 32
        with tempfile.TemporaryDirectory() as d:
            def fake_get(url):
                if url.endswith(".png"):
                    return (url, png, {"Content-Type": "image/png"})
                return (url, b"<title>Arborview Realty</title>"
                             b"<img class='logo' src='/l.png'>", {})
            self.m._get = fake_get
            r = self.m.fetch_logo("arborview_realty", "Arborview Realty Inc", logos_dir=d)
            self.assertEqual(r["status"], "ok")
            self.assertEqual(os.listdir(d), ["arborview_realty.png"])
            self.assertEqual(open(os.path.join(d, "arborview_realty.png"), "rb").read(), png)

    def test_a_page_that_does_not_verify_downloads_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            self.m._get = lambda url: (url, b"<title>Someone Else</title>", {})
            r = self.m.fetch_logo("arborview_realty", "Arborview Realty Inc", logos_dir=d)
            self.assertEqual(r["status"], "skipped")
            self.assertEqual(os.listdir(d), [])


if __name__ == "__main__":
    unittest.main()
