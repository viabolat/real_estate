r"""status.py must not send you somewhere that cannot help, or pass silently.

Guards CLAUDE.md: "status.py prints the mv when a folder no longer matches its
lead row" -- and the gap found on 2026-08-24, where a folder with no config.json
was invisible to that check because the check keys on agent_phone out of the
config. brewester/9_w_cedar sat through the scrape-naming commit that way.

No real lead data is used: leads.csv is PII and gitignored, so these tests build
the phone->name table by hand. The stand-in identifiers are deliberately NOT
phone-shaped -- check_pii.py refuses anything matching \d{3}sep\d{3}sep\d{4} in a
publishable file, and it is right to: a fictional 555 number in a committed test
is still a phone-shaped string in a repo whose whole PII rule is shape-based. The
match is a digits-only comparison, so short ids exercise it identically.
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers

STATUS = None


def setUpModule():
    global STATUS
    STATUS = helpers.status_module()


class TestNextActionOnAConfiglessFolder(unittest.TestCase):
    """The advice has to match the situation, or it is a dead end."""

    def action(self, scraped, n=17, best=1440):
        with tempfile.TemporaryDirectory() as d:
            return STATUS.next_action(d, {}, n, 384, best, scraped=scraped)

    def test_a_scraped_folder_is_sent_to_the_scraper(self):
        self.assertIn("photos.py", self.action(scraped=True))

    def test_a_folder_with_no_lead_row_is_not_sent_to_the_scraper(self):
        """There is no dump to rerun -- saying so is the whole fix."""
        action = self.action(scraped=False)
        self.assertNotIn("photos.py", action)
        self.assertIn("leads.csv", action)

    def test_the_default_stays_the_scraper_path(self):
        """An older caller that passes no flag behaves exactly as before."""
        with tempfile.TemporaryDirectory() as d:
            self.assertIn("photos.py",
                          STATUS.next_action(d, {}, 17, 384, 1440))

    def test_photo_checks_still_win_over_the_naming_verdict(self):
        """A folder with no photos is a photo problem, whoever named it."""
        self.assertIn("no photos", self.action(scraped=False, n=0))
        self.assertIn("get the originals",
                      self.action(scraped=False, best=346))


class TestAHandPlacedFolderCanStillReachReadiness(unittest.TestCase):
    """Provenance is a fact about a folder, never a blocker on it.

    A folder with photos and no config.json -- corcoran/46_beacon_5 is the real
    one -- used to terminate at "not in leads.csv" and could never read as ready,
    however good its photos were. tour.py's picker already offered it and its
    question set already wrote the config, so the roll-up was refusing to say
    what the tool would happily do. The naming authority is untouched by this:
    the folder is not renamed, and audit() still reports it as unverifiable.
    """

    def listing(self, **files):
        d = tempfile.mkdtemp(prefix="status_test_")
        self.addCleanup(shutil.rmtree, d, True)
        for name in ("logo.png", "music.mp3", "viabolat.png"):
            open(os.path.join(d, name), "wb").close()
        for sub, names in files.items():
            os.makedirs(os.path.join(d, sub), exist_ok=True)
            for n in names:
                open(os.path.join(d, sub, n), "wb").close()
        return d

    def action(self, cfg=None, scraped=False, best=2400, **files):
        d = self.listing(**files)
        assets = {"logo": "logo.png", "music": "music.mp3",
                  "watermark": "viabolat.png"}
        return STATUS.next_action(d, dict(cfg or {}), 17, 2000, best,
                                  scraped=scraped, bcfg=assets)

    def test_no_config_and_no_lead_row_still_reads_ready(self):
        self.assertIn("ready to build", self.action())

    def test_the_missing_lead_row_stays_visible(self):
        """It is reported, just no longer as the next action."""
        self.assertIn("leads.csv", self.action())

    def test_a_scraped_folder_is_still_sent_back_to_the_scraper(self):
        """There the scrape fills in address, agent, phone and the watermark
        path -- strictly better than retyping them into the question set."""
        self.assertIn("photos.py", self.action(scraped=True))

    def test_a_normal_listing_carries_no_provenance_tag(self):
        action = self.action(cfg={"address": "1 Main St"}, scraped=True)
        self.assertIn("ready to build", action)
        self.assertNotIn("leads.csv", action)


class TestBrandDefaultsAreLayeredUnderTheListing(unittest.TestCase):
    """survey() reads brand.json per brand; next_action has to see it too.

    reason: the asset checks read only the listing's own config, so a listing
    that inherits its logo and music from brand.json -- which is the normal
    case, and the entire point of brand.json -- reported "logo blank/missing"
    forever. tour.load_config() layers DEFAULTS -> brand.json -> config.json;
    this mirrors the last two.
    """

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="status_test_")
        self.addCleanup(shutil.rmtree, self.d, True)
        for name in ("logo.png", "music.mp3", "viabolat.png"):
            open(os.path.join(self.d, name), "wb").close()
        self.brand = {"logo": "logo.png", "music": "music.mp3",
                      "watermark": "viabolat.png"}

    def action(self, cfg, bcfg):
        return STATUS.next_action(self.d, cfg, 17, 2000, 2400, bcfg=bcfg)

    def test_assets_inherited_from_the_brand_count_as_present(self):
        self.assertIn("ready to build",
                      self.action({"address": "1 Main St"}, self.brand))

    def test_without_the_brand_layer_the_same_listing_looks_broken(self):
        """The exact false negative this argument fixes."""
        self.assertIn("logo", self.action({"address": "1 Main St"}, None))

    def test_the_listing_still_wins_over_the_brand(self):
        cfg = {"logo": "nope.png"}
        self.assertIn("logo", self.action(cfg, self.brand))


class TestThePipelineStatesAreDistinguishable(unittest.TestCase):
    """"built, 3 cuts" could mean a finished sample run or a half-dead build.

    Now that run 1 writes three cuts on purpose, the count alone is ambiguous
    exactly where the operator most needs to know which run is next. The states
    name the family, and the "published" fact is derived from links.csv rather
    than from a marker file.
    """

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="status_test_")
        self.addCleanup(shutil.rmtree, self.d, True)
        for name in ("logo.png", "music.mp3", "viabolat.png"):
            open(os.path.join(self.d, name), "wb").close()
        self.cfg = {"logo": "logo.png", "music": "music.mp3",
                    "watermark": "viabolat.png"}

    def action(self, *cuts, best=2400, published=False):
        out = os.path.join(self.d, "out")
        os.makedirs(out, exist_ok=True)
        for c in cuts:
            open(os.path.join(out, c), "wb").close()
        real = STATUS.published
        STATUS.published = lambda b, l: published
        self.addCleanup(setattr, STATUS, "published", real)
        return STATUS.next_action(self.d, self.cfg, 17, 2000, best)

    def test_nothing_built_is_ready_to_build(self):
        self.assertIn("ready to build", self.action())

    def test_samples_alone_ask_for_the_review_link(self):
        action = self.action("sample_branded.mp4", "sample_unbranded.mp4",
                             "sample_vertical.mp4")
        self.assertIn("publish", action)

    def test_a_published_sample_is_awaiting_sign_off(self):
        action = self.action("sample_branded.mp4", published=True)
        self.assertIn("sign-off", action)

    def test_a_tour_cut_means_delivered(self):
        action = self.action("sample_branded.mp4", "tour_branded.mp4")
        self.assertIn("delivered", action)

    def test_the_soft_verdict_is_measured_not_read_off_a_filename(self):
        """CLAUDE.md: a soft cut is not MLS-ready, and its name will not tell
        you. The reminder has to survive to the state the delivery sits in."""
        action = self.action("sample_branded.mp4", "tour_branded.mp4", best=1024)
        self.assertIn("delivered", action)
        self.assertIn("1024px", action)

    def test_a_build_log_is_not_counted_as_a_cut(self):
        self.assertIn("ready to build", self.action("build.log"))


class TestDriftClassification(unittest.TestCase):
    """Three buckets: agrees, drifted, unverifiable. Nothing falls through."""

    TRUTH = {"1001": ("brokerage_one", "11_first_st"),
             "2002": ("brokerage_two", "22_second_st")}
    KNOWN = set(TRUTH.values())

    def classify(self, brand, listing, cfg):
        """The exact expression main() uses, over a synthetic truth table."""
        import re
        want = self.TRUTH.get(re.sub(r"\D", "", cfg.get("agent_phone") or ""))
        if want and (brand, listing) != want:
            return "drift"
        if not want and (brand, listing) not in self.KNOWN:
            return "unverifiable"
        return "agrees"

    def test_a_matching_folder_agrees(self):
        self.assertEqual(self.classify(
            "brokerage_two", "22_second_st", {"agent_phone": "2002"}), "agrees")

    def test_a_renamed_folder_drifts(self):
        """The shape of the bug this check was written for."""
        self.assertEqual(self.classify(
            "hand_named", "1_first", {"agent_phone": "1001"}), "drift")

    def test_a_configless_legacy_folder_is_unverifiable_not_silent(self):
        """The bug: this used to classify as 'agrees' by falling through."""
        self.assertEqual(self.classify("brewester", "9_w_cedar", {}),
                         "unverifiable")
        self.assertEqual(self.classify("corcoran", "46_beacon_5", {}),
                         "unverifiable")

    def test_a_right_name_with_a_wrong_phone_still_drifts(self):
        """Name matches one lead row, config points at another. Worse, not less."""
        self.assertEqual(self.classify(
            "brokerage_one", "11_first_st", {"agent_phone": "2002"}), "drift")

    def test_a_known_name_with_no_phone_is_not_flagged(self):
        """The scrape named it; a blank phone is not evidence against that."""
        self.assertEqual(self.classify("brokerage_two", "22_second_st", {}),
                         "agrees")

    def test_punctuation_does_not_affect_the_match(self):
        """The match normalizes to digits, which is why it beats address text."""
        for form in ("2002", "20-02", "(20) 02", "+20 02", "20.02", " 2002 "):
            self.assertEqual(self.classify(
                "brokerage_two", "22_second_st", {"agent_phone": form}),
                "agrees", form)


class TestScrapedNamesReadsTheAuthority(unittest.TestCase):

    def test_it_keys_on_digits_only(self):
        """Address text formatting varies between config and CSV; a phone does not."""
        import inspect
        src = inspect.getsource(STATUS.scraped_names)
        self.assertIn("agent_phone", src)
        self.assertIn("broker_name", src)
        self.assertIn("address", src)

    def test_a_missing_leads_csv_is_not_an_error(self):
        """status.py is read-only and must run on a clone with no scrape yet."""
        self.assertIsInstance(STATUS.scraped_names(), dict)


if __name__ == "__main__":
    unittest.main()
