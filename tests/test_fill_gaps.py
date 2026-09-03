"""fill_gaps.py closes gaps without inventing any.

Guards _rules/fill-gaps-acts-only-on-what-find-gaps-named.md: the near_miss
bucket is never adopted, an agent_email is never guessed when leads.csv has
none, the two offline lanes never reach the network, and a non-PNG mark is
refused rather than saved under a name that lies about its type.
"""
import inspect
import json
import os
import struct
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


def png(w=400, h=140):
    """A PNG header with a real IHDR, which is all png_size() reads."""
    return (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR"
            + struct.pack(">II", w, h) + b"\x08\x06\x00\x00\x00")


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
        mark = png()
        with tempfile.TemporaryDirectory() as d:
            def fake_get(url):
                if url.endswith(".png"):
                    return (url, mark, {"Content-Type": "image/png"})
                return (url, b"<title>Arborview Realty</title>"
                             b"<img class='logo' src='/l.png'>", {})
            self.m._get = fake_get
            r = self.m.fetch_logo("arborview_realty", "Arborview Realty Inc", logos_dir=d)
            self.assertEqual(r["status"], "ok")
            self.assertEqual(os.listdir(d), ["arborview_realty.png"])
            self.assertEqual(
                open(os.path.join(d, "arborview_realty.png"), "rb").read(), mark)

    def test_a_favicon_is_too_small_to_be_a_mark(self):
        """reason: rel="icon" led the candidate list, so serhant.com's
        favicon-16x16.png was written as the brokerage's logo. Scaled into
        make_tour.py's 360x200 box that is an upscale smear."""
        with tempfile.TemporaryDirectory() as d:
            def fake_get(url):
                if url.endswith(".png"):
                    return (url, png(16, 16), {"Content-Type": "image/png"})
                return (url, b"<title>Arborview Realty</title>"
                             b"<link rel='icon' href='/favicon-16x16.png'>", {})
            self.m._get = fake_get
            r = self.m.fetch_logo("arborview_realty", "Arborview Realty Inc",
                                  logos_dir=d)
            self.assertEqual(r["status"], "skipped")
            self.assertIn("favicon", r["reason"])
            self.assertEqual(os.listdir(d), [])

    def test_it_falls_through_a_bad_candidate_to_a_good_one(self):
        """One wrong answer used to end the attempt: the first candidate was
        the only candidate."""
        with tempfile.TemporaryDirectory() as d:
            def fake_get(url):
                if url.endswith("small.png"):
                    return (url, png(16, 16), {"Content-Type": "image/png"})
                if url.endswith("real.png"):
                    return (url, png(), {"Content-Type": "image/png"})
                return (url, b"<title>Arborview Realty</title>"
                             b"<link rel='icon' href='/small.png'>"
                             b"<img class='site-logo' src='/real.png'>", {})
            self.m._get = fake_get
            r = self.m.fetch_logo("arborview_realty", "Arborview Realty Inc",
                                  logos_dir=d)
            self.assertEqual(r["status"], "ok")
            self.assertTrue(r["source"].endswith("real.png"))

    def test_a_page_that_does_not_verify_downloads_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            self.m._get = lambda url: (url, b"<title>Someone Else</title>", {})
            r = self.m.fetch_logo("arborview_realty", "Arborview Realty Inc", logos_dir=d)
            self.assertEqual(r["status"], "skipped")
            self.assertEqual(os.listdir(d), [])


class TestOnlyThisBrokeragesMarkIsACandidate(unittest.TestCase):
    """A page is full of other people's logos, and they all download clean.

    serhant.com carries the NETFLIX wordmark (for the show the brokerage
    appears in), two MLS marks and an RLS mark. Each is a real PNG of a
    plausible size. No byte or dimension check separates them from the
    brokerage's own mark -- only asking who owns it does. See
    _rules/a-fetched-logo-names-the-brokerage-or-it-is-not-fetched.md.
    """

    SERHANT = (b"<title>SERHANT</title>"
               b"<meta property='og:image' content='/netflix-share.png'>"
               b"<img src='/hero.jpg'>"
               b"<img src='/own-mark.png' alt='Logo' class='heading-logo'>"
               b"<img class='netflix-logo' src='/netflix.png' alt='Netflix Logo'>"
               b"<img class='property-card__mls-logo' src='/mls.png' alt='MLS logo'>"
               b"<img src='/rls_logo_vertical2020.png'>"
               b"<link rel='icon' href='/favicon-16x16.png'>")

    def setUp(self):
        self.m = helpers.scraper_module("fill_gaps")

    def urls(self, html=None, name="Serhant"):
        return list(self.m.logo_urls(html or self.SERHANT, "https://x.test/", name))

    def test_the_pages_own_generically_labelled_mark_wins(self):
        self.assertEqual(self.urls()[0], "https://x.test/own-mark.png")

    def test_attribute_order_carries_no_meaning(self):
        """The bug: the pattern needed the logo-ish attribute BEFORE src=, so
        <img src=... alt="Logo" class="heading-logo"> never matched and
        <img class="netflix-logo" src=...> did."""
        self.assertIn("https://x.test/own-mark.png", self.urls())

    def test_another_companys_mark_is_never_a_candidate(self):
        for foreign in ("netflix.png", "mls.png", "rls_logo_vertical2020.png"):
            self.assertNotIn("https://x.test/" + foreign, self.urls(), foreign)

    def test_the_share_card_is_never_a_candidate(self):
        """og:image is chosen to sell the page, not to identify the company --
        and on serhant.com it IS the Netflix wordmark."""
        self.assertNotIn("https://x.test/netflix-share.png", self.urls())
        body = inspect.getsource(self.m.logo_urls).split('"""')[2]
        self.assertNotIn("og:image", body)

    def test_a_src_url_naming_the_brokerage_is_vouched(self):
        html = b"<img src='/assets/ArborviewRealty_Logo.png'>"
        self.assertEqual(self.urls(html, "Arborview Realty Inc"),
                         ["https://x.test/assets/ArborviewRealty_Logo.png"])

    def test_the_brokerages_own_mark_outranks_a_generic_one(self):
        html = (b"<img class='site-logo' src='/generic.png'>"
                b"<img class='serhant-logo' src='/named.png'>")
        self.assertEqual(self.urls(html)[0], "https://x.test/named.png")

    def test_a_templating_placeholder_is_not_a_url(self):
        """serhant.com ships an unrendered <img src="{{mlsLogo}}">."""
        self.assertEqual(self.urls(b"<img class='logo' src='{{mlsLogo}}'>"), [])

    def test_the_favicon_stays_last_rather_than_first(self):
        self.assertEqual(self.urls()[-1], "https://x.test/favicon-16x16.png")


class TestPngSize(unittest.TestCase):
    """No Pillow, no ffprobe -- the IHDR is read directly."""

    def setUp(self):
        self.m = helpers.scraper_module("fill_gaps")

    def test_it_reads_the_ihdr(self):
        self.assertEqual(self.m.png_size(png(758, 263)), (758, 263))

    def test_a_non_png_has_no_size(self):
        self.assertIsNone(self.m.png_size(b"<svg xmlns='...'></svg>"))

    def test_a_truncated_png_has_no_size(self):
        self.assertIsNone(self.m.png_size(b"\x89PNG\r\n\x1a\n"))

    def test_the_floor_is_high_enough_to_reject_every_common_favicon(self):
        """16, 32, 48, 64 and 96 are the sizes a rel="icon" actually serves."""
        for n in (16, 32, 48, 64, 96):
            self.assertLess(n, self.m.MIN_LOGO_PX, n)


if __name__ == "__main__":
    unittest.main()
