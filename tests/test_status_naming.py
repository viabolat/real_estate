r"""status.py must not send you somewhere that cannot help, or pass silently.

Guards _rules/the-scrape-names-the-folders.md: "status.py prints the mv when a
folder no longer matches its
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


class TestAContactedRowWithNoScrapedName(unittest.TestCase):
    """orphaned_marks(): a contacted.csv row keyed on a name the scrape does not
    produce records a real send that leads.html can never find.

    That page derives its key from the leads.csv row, so the CONTACTED and
    FOLLOW UP columns stay blank and the lead reads "new" forever -- while rung
    5 offers to mail it again. Three rows sat that way for two weeks and one
    agent got a duplicate. Ids are short and non-phone-shaped: check_pii.py
    matches by shape (tests/README.md).
    """

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="orphan_test_")
        self.addCleanup(shutil.rmtree, self.d, True)
        self.csv = os.path.join(self.d, "contacted.csv")
        real = STATUS._publish
        self.addCleanup(setattr, STATUS, "_publish", real)

        class FakePublish:
            CONTACTED = self.csv
        STATUS._publish = FakePublish()

    def write(self, *keys):
        with open(self.csv, "w", newline="") as f:
            f.write("marked_at,brand,listing,agent\n")
            for k in keys:
                f.write("2026-08-01T00:00:00," + ",".join(k) + "\n")

    def test_a_row_matching_a_scraped_name_is_not_an_orphan(self):
        key = ("compass", "41_worcester_sq", "mary_smith")
        self.write(key)
        self.assertEqual(STATUS.orphaned_marks({key}), [])

    def test_a_row_the_scrape_does_not_name_is_reported(self):
        self.write(("compass", "41_worcester_sq", "mary_smith_and_team"))
        self.assertEqual(STATUS.orphaned_marks({("compass", "41_worcester_sq",
                                                 "mary_smith")}),
                         [("compass", "41_worcester_sq", "mary_smith_and_team")])

    def test_a_placeholder_keyed_row_is_reported(self):
        # reason: the two pre-scraper listings were marked contacted as
        # unknown_brokerage/<listing>/unassigned_agent, then their leads.csv
        # rows gained a real brokerage and agent. The key moved out from under
        # the mark and both leads read "new" for two weeks. Synthetic names --
        # check_pii.py scans fixtures against leads.csv (tests/README.md).
        self.write(("unknown_brokerage", "1_example_st", "unassigned_agent"))
        self.assertEqual(len(STATUS.orphaned_marks(
            {("example_brokerage", "1_example_st", "a_lister")})), 1)

    def test_a_repeated_key_is_reported_once(self):
        # reason: contacted.csv now carries one row per send, so a followed-up
        # orphan has several rows. The report names the folder, not the sends.
        key = ("compass", "41_worcester_sq", "mary_smith_and_team")
        self.write(key, key, key)
        self.assertEqual(STATUS.orphaned_marks(set()), [key])

    def test_a_missing_file_is_no_orphans_not_a_crash(self):
        self.assertEqual(STATUS.orphaned_marks({("a", "b", "c")}), [])

    def test_print_audit_names_the_row_and_says_re_keying_alone_is_not_enough(self):
        lines = []
        STATUS.print_audit([], [], [("compass", "41_worcester_sq", "m_smith")],
                           out=lines.append)
        text = "\n".join(lines)
        self.assertIn("compass/41_worcester_sq/m_smith", text)
        self.assertIn("leads.html", text)
        self.assertIn("rung 5", text)


class TestABlankMusicBedIsNotABlocker(unittest.TestCase):
    """sample_ cuts ship silent, so `music` is blank on every real listing.

    It used to sit in next_action()'s ladder one rung below the logo and return
    "music blank/missing -- add it to brand.json". That matched EVERY listing in
    the ledger -- all eleven already delivered and contacted ones included -- and
    reported the nag in place of the real next action, so the NEXT column said
    nothing useful for the whole table. The asymmetry with the logo is the point:
    a missing logo halts --auto, a missing music bed only adds --no-music.
    """

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="status_test_")
        self.addCleanup(shutil.rmtree, self.d, True)
        for name in ("logo.png", "viabolat.png"):
            open(os.path.join(self.d, name), "wb").close()
        self.cfg = {"logo": "logo.png", "watermark": "viabolat.png"}

    def action(self, *cuts):
        out = os.path.join(self.d, "out")
        os.makedirs(out, exist_ok=True)
        for c in cuts:
            open(os.path.join(out, c), "wb").close()
        real = STATUS.published
        STATUS.published = lambda b, l: False
        self.addCleanup(setattr, STATUS, "published", real)
        return STATUS.next_action(self.d, self.cfg, 17, 2000, 2400)

    def test_no_music_key_still_reads_ready_to_build(self):
        self.assertEqual("ready to build", self.action())

    def test_no_music_key_still_reaches_the_review_link(self):
        self.assertIn("publish", self.action("sample_branded.mp4"))

    def test_an_empty_music_value_is_not_a_blocker_either(self):
        self.cfg["music"] = ""
        self.assertIn("publish", self.action("sample_branded.mp4"))

    def test_a_missing_logo_is_still_a_blocker(self):
        """The whole reason music can go is that the logo check is the real gate."""
        self.cfg.pop("logo")
        self.assertIn("logo", self.action("sample_branded.mp4"))

    def test_no_state_ever_reports_music_as_the_next_action(self):
        """A future edit must not reintroduce the nag under a new wording.

        Asserted on what next_action RETURNS, across every state a blank-music
        listing can be in -- not on the source text, which carries a `# reason:`
        comment naming music on purpose.
        """
        for cuts in ((), ("sample_branded.mp4",),
                     ("sample_branded.mp4", "tour_branded.mp4")):
            with self.subTest(cuts=cuts):
                self.setUp()
                self.assertNotIn("music", self.action(*cuts).lower())


class TestDriftClassification(unittest.TestCase):
    """Three buckets: agrees, drifted, unverifiable. Nothing falls through."""

    TRUTH = {"1001": ("brokerage_one", "11_first_st", "agent_a"),
             "2002": ("brokerage_two", "22_second_st", "agent_b")}
    KNOWN = set(TRUTH.values())

    def classify(self, brand, listing, agent, cfg):
        """The exact expression main() uses, over a synthetic truth table."""
        import re
        want = self.TRUTH.get(re.sub(r"\D", "", cfg.get("agent_phone") or ""))
        if want and (brand, listing, agent) != want:
            return "drift"
        if not want and (brand, listing, agent) not in self.KNOWN:
            return "unverifiable"
        return "agrees"

    def test_a_matching_folder_agrees(self):
        self.assertEqual(self.classify(
            "brokerage_two", "22_second_st", "agent_b", {"agent_phone": "2002"}),
            "agrees")

    def test_a_renamed_folder_drifts(self):
        """The shape of the bug this check was written for."""
        self.assertEqual(self.classify(
            "hand_named", "1_first", "agent_a", {"agent_phone": "1001"}), "drift")

    def test_a_configless_legacy_folder_is_unverifiable_not_silent(self):
        """The bug: this used to classify as 'agrees' by falling through."""
        self.assertEqual(self.classify("brewester", "9_w_cedar", "j_doe", {}),
                         "unverifiable")
        self.assertEqual(self.classify("corcoran", "46_beacon_5", "j_doe", {}),
                         "unverifiable")

    def test_a_right_name_with_a_wrong_phone_still_drifts(self):
        """Name matches one lead row, config points at another. Worse, not less."""
        self.assertEqual(self.classify(
            "brokerage_one", "11_first_st", "agent_a", {"agent_phone": "2002"}),
            "drift")

    def test_a_known_name_with_no_phone_is_not_flagged(self):
        """The scrape named it; a blank phone is not evidence against that."""
        self.assertEqual(self.classify(
            "brokerage_two", "22_second_st", "agent_b", {}), "agrees")

    def test_punctuation_does_not_affect_the_match(self):
        """The match normalizes to digits, which is why it beats address text."""
        for form in ("2002", "20-02", "(20) 02", "+20 02", "20.02", " 2002 "):
            self.assertEqual(self.classify(
                "brokerage_two", "22_second_st", "agent_b", {"agent_phone": form}),
                "agrees", form)

    def test_a_placeholder_agent_drifts_once_the_real_name_is_known(self):
        """The correction path for scraper.photos.UNASSIGNED_AGENT: once the
        config's agent_phone resolves to a lead row, a folder still sitting on
        the placeholder slug drifts against the real agent slug like any other
        mismatch."""
        self.assertEqual(self.classify(
            "brokerage_one", "11_first_st", "unassigned_agent",
            {"agent_phone": "1001"}), "drift")


class TestTheLegacyLayoutIsNamedNotMislabelled(unittest.TestCase):
    """A listing one level off is a migration, not a missing scrape.

    reason: _dirs() cannot tell agents/<brand>/<listing>/<agent> from the
    photos/, clips/ and out/ a build writes inside one. survey() therefore read
    "photos" as the agent slug, looked for a config.json inside photos/, found
    none, and filed the listing under unverifiable -- while the config sat one
    level up, carrying the very agent_phone the drift audit keys on. Eight rows
    read that way. See _rules/an-agent-folder-is-one-that-holds-a-config.md.
    """

    TRUTH = {"1001": ("brokerage_one", "11_first_st", "agent_a")}

    def listing(self, subs=(), config=None):
        d = tempfile.mkdtemp(prefix="status_test_")
        self.addCleanup(shutil.rmtree, d, True)
        for sub in subs:
            os.makedirs(os.path.join(d, sub), exist_ok=True)
        if config is not None:
            import json
            with open(os.path.join(d, "config.json"), "w", encoding="utf-8") as f:
                json.dump(config, f)
        return d

    def test_build_intermediates_are_not_read_as_agents(self):
        d = self.listing(("photos", "clips", "out", "clips_draft", "work_text"),
                         config={"agent_phone": "1001"})
        self.assertEqual(STATUS._agent_dirs(d), [])

    def test_an_agent_folder_is_one_that_holds_a_config_or_photos(self):
        d = self.listing(("agent_a/photos", "agent_b", "out"))
        with open(os.path.join(d, "agent_b", "config.json"), "w") as f:
            f.write("{}")
        self.assertEqual(STATUS._agent_dirs(d), ["agent_a", "agent_b"])

    def test_the_destination_slug_comes_out_of_leads_csv(self):
        """Nothing here names a folder; it reports the name the scrape implies."""
        d = self.listing(("photos",), config={"agent_phone": "10-01"})
        self.assertEqual(STATUS.legacy_target(d, self.TRUTH), "agent_a")

    def test_a_legacy_folder_with_no_lead_row_is_not_hand_named(self):
        d = self.listing(("photos",), config={"agent_phone": "9009"})
        self.assertIsNone(STATUS.legacy_target(d, self.TRUTH))

    def test_a_config_with_no_photos_beside_it_is_not_the_legacy_shape(self):
        d = self.listing(config={"agent_phone": "1001"})
        self.assertIsNone(STATUS.legacy_target(d, self.TRUTH))

    def test_photos_with_no_config_beside_it_is_not_the_legacy_shape(self):
        """That is a folder the scrape never finished, and the existing
        "rerun photos.py" advice is the right one."""
        d = self.listing(("photos",))
        self.assertIsNone(STATUS.legacy_target(d, self.TRUTH))


class TestScrapedNamesReadsTheAuthority(unittest.TestCase):

    def test_it_keys_on_digits_only(self):
        """Address text formatting varies between config and CSV; a phone does not."""
        import inspect
        src = inspect.getsource(STATUS.scraped_names)
        self.assertIn("agent_phone", src)
        self.assertIn("broker_name", src)
        self.assertIn("address", src)
        self.assertIn("agent_name", src)

    def test_a_missing_leads_csv_is_not_an_error(self):
        """status.py is read-only and must run on a clone with no scrape yet."""
        self.assertIsInstance(STATUS.scraped_names(), dict)


if __name__ == "__main__":
    unittest.main()
