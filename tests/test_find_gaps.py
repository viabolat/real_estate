"""find_gaps.py detects two gaps and writes neither.

Guards _rules/find-gaps-detects-and-reports-it-never-writes.md: the module
never opens a file in write mode, never calls json.dump(, never downloads
anything, and reuses photos.slugify() rather than re-deriving a second
folder-naming function. See tests/README.md for the pattern this mirrors
(test_outreach_draft.py's TestDraft.test_nothing_in_publish_sends_mail).
"""
import inspect
import json
import os
import shutil
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
import helpers


class TestNeverWrites(unittest.TestCase):

    def setUp(self):
        self.find_gaps = helpers.scraper_module("find_gaps")

    def test_module_never_writes_a_file(self):
        src = inspect.getsource(self.find_gaps)
        for token in ('"w")', "'w')", '"w",', "'w',", "json.dump(",
                      "urlretrieve", "requests."):
            self.assertNotIn(token, src, f"{token} found -- find_gaps.py must never write")

    def test_open_tabs_only_opens_a_browser_tab(self):
        src = inspect.getsource(self.find_gaps.open_tabs)
        self.assertIn("webbrowser.open", src)
        for token in ("urlretrieve", "requests.", "urllib.request", '"w")', "'w')"):
            self.assertNotIn(token, src)

    def test_email_gaps_never_opens_leads_csv_for_writing(self):
        src = inspect.getsource(self.find_gaps.email_gaps)
        self.assertNotIn('"w"', src)
        self.assertNotIn("'w'", src)

    def test_reuses_photos_slugify_rather_than_a_second_copy(self):
        src = inspect.getsource(self.find_gaps)
        self.assertIn("from photos import", src)
        self.assertNotIn("def slugify(", src)


class TestLogoStatus(unittest.TestCase):

    def setUp(self):
        self.find_gaps = helpers.scraper_module("find_gaps")
        self.tmp = tempfile.mkdtemp(prefix="find_gaps_test_")
        self.agents = os.path.join(self.tmp, "agents")
        self.logos = os.path.join(self.tmp, "global_assets", "logos")
        os.makedirs(self.logos)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _brand(self, slug, logo=""):
        d = os.path.join(self.agents, slug)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "brand.json"), "w", encoding="utf-8") as f:
            json.dump({"logo": logo}, f)

    def _logo_file(self, name):
        with open(os.path.join(self.logos, name), "wb") as f:
            f.write(b"fake-png")

    def test_a_resolved_logo_is_ok(self):
        self._logo_file("acme.png")
        self._brand("acme", logo="global_assets/logos/acme.png")
        self.assertEqual(
            self.find_gaps.logo_status("acme", self.agents, self.logos, self.tmp),
            "ok")

    def test_an_exact_unclaimed_file_is_available(self):
        self._logo_file("insight_realty_group.png")
        self._brand("insight_realty_group")
        self.assertEqual(
            self.find_gaps.logo_status(
                "insight_realty_group", self.agents, self.logos, self.tmp),
            "available")

    def test_a_substring_match_is_a_near_miss(self):
        self._logo_file("coldwell_banker.png")
        self._brand("coldwell_banker_realty_easton")
        self.assertEqual(
            self.find_gaps.logo_status(
                "coldwell_banker_realty_easton", self.agents, self.logos, self.tmp),
            "near_miss")

    def test_an_acronym_match_is_a_near_miss(self):
        self._logo_file("tcc.png")
        self._brand("the_collaborative_companies")
        self.assertEqual(
            self.find_gaps.logo_status(
                "the_collaborative_companies", self.agents, self.logos, self.tmp),
            "near_miss")

    def test_nothing_on_disk_is_a_gap(self):
        self._brand("brand_new_co")
        self.assertEqual(
            self.find_gaps.logo_status("brand_new_co", self.agents, self.logos, self.tmp),
            "gap")

    def test_a_single_word_brand_does_not_get_a_spurious_acronym_hit(self):
        """reason: a one-word brand's "acronym" is one letter -- without the
        >=2-word guard in _acronym(), "compass" would spuriously near-miss
        against any single-letter-prefixed logo file."""
        self._logo_file("c.png")
        self._brand("compass")
        self.assertEqual(
            self.find_gaps.logo_status("compass", self.agents, self.logos, self.tmp),
            "gap")


class TestEmailGaps(unittest.TestCase):

    def setUp(self):
        self.find_gaps = helpers.scraper_module("find_gaps")
        self.tmp = tempfile.mkdtemp(prefix="find_gaps_test_")
        self.agents = os.path.join(self.tmp, "agents")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _row(self, **over):
        r = {"address": "1 Test St", "broker_name": "Acme Realty",
             "agent_name": "Jane Doe", "agent_phone": "1001-2002"}
        r.update(over)
        return r

    def _config(self, key, agent_email=""):
        d = os.path.join(self.agents, *key)
        os.makedirs(d, exist_ok=True)
        cfg = {"agent_name": "Jane Doe", "agent_phone": "1001-2002"}
        if agent_email:
            cfg["agent_email"] = agent_email
        with open(os.path.join(d, "config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        return d

    def test_a_lead_with_no_listing_folder_yet_is_skipped(self):
        gaps = self.find_gaps.email_gaps([self._row()], agents_dir=self.agents)
        self.assertEqual(gaps, [])

    def test_a_blank_agent_email_is_a_gap(self):
        row = self._row()
        key = self.find_gaps.row_key(row)
        self._config(key)
        gaps = self.find_gaps.email_gaps([row], agents_dir=self.agents)
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["agent_name"], "Jane Doe")
        self.assertEqual(gaps[0]["broker_name"], "Acme Realty")

    def test_a_set_agent_email_is_not_a_gap(self):
        # reason: check_pii.py scans every publishable file for anything
        # email-shaped, fixtures included -- see tests/README.md's "Fixtures
        # must not be phone-shaped or email-shaped." A non-email marker
        # exercises the same truthy-string branch without tripping it.
        row = self._row()
        key = self.find_gaps.row_key(row)
        self._config(key, agent_email="address-on-file")
        gaps = self.find_gaps.email_gaps([row], agents_dir=self.agents)
        self.assertEqual(gaps, [])


if __name__ == "__main__":
    unittest.main()
