"""The output filename is a boundary that survives being emailed.

Guards CLAUDE.md: "Never send a sample_ file as a deliverable, and never send a
tour_ file before sign-off", "the shortfall rides in the filename", and
"draft.mp4 is not a deliverable and does not go in out/".
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers

CUTS = ("tour_branded", "tour_unbranded", "tour_vertical",
        "sample_branded", "sample_unbranded", "sample_vertical")


class TestOutputNaming(unittest.TestCase):

    def test_family_token_survives_the_agent_prefix(self):
        """tour_/sample_ is what keeps a proof from being sent as a delivery."""
        with helpers.listing(config={"agent_name": "Jane Doe"}) as (m, _):
            for cut in CUTS:
                path = m.out_path(cut)
                self.assertIn(cut, os.path.basename(path),
                              f"{cut} lost its family token: {path}")

    def test_all_six_cuts_are_distinct_and_live_in_out(self):
        with helpers.listing(config={"agent_name": "Jane Doe"}) as (m, _):
            paths = [m.out_path(c) for c in CUTS]
            self.assertEqual(len(set(paths)), 6, "two cuts collide on one name")
            for path in paths:
                self.assertTrue(path.startswith("out/"), path)

    def test_lowres_is_a_suffix_and_only_when_asked(self):
        with helpers.listing(config={"agent_name": "Jane Doe"}) as (m, _):
            self.assertTrue(m.out_path("tour_branded", True).endswith(
                "_lowres.mp4"))
            self.assertNotIn("_lowres", m.out_path("tour_branded", False))

    def test_lowres_tag_cannot_be_dropped_by_config(self):
        """No config key may suppress the tag -- it is the warning, not a flag."""
        with helpers.listing(config={"agent_name": "Jane Doe",
                                     "output_prefix": "custom"}) as (m, _):
            self.assertTrue(m.out_path("sample_vertical", True).endswith(
                "_lowres.mp4"))

    def test_output_prefix_overrides_agent_name(self):
        with helpers.listing(config={"agent_name": "Jane Doe",
                                     "output_prefix": "corcoran"}) as (m, _):
            self.assertEqual(m.out_path("tour_branded"),
                             "out/corcoran_tour_branded.mp4")

    def test_both_blank_leaves_the_bare_names(self):
        """A pre-existing CLI folder must build exactly what it always did."""
        with helpers.listing(config={}) as (m, _):
            self.assertEqual(m.out_path("tour_branded"), "out/tour_branded.mp4")

    def test_draft_is_not_a_deliverable_and_not_in_out(self):
        with helpers.listing(config={}, argv=["make_tour.py", "--draft"]) as (m, _):
            self.assertFalse(m.DRAFT_OUT.startswith("out/"), m.DRAFT_OUT)
            self.assertNotIn("/", m.DRAFT_OUT)

    def test_draft_intermediates_are_named_apart_from_delivery_ones(self):
        """A draft-quality stitch must never be able to feed a delivery build."""
        with helpers.listing(config={}, argv=["make_tour.py", "--draft"]) as (m, _):
            draft_work, draft_clips = m.SILENT_WORK, m.CLIPS_DIR
        with helpers.listing(config={}) as (m, _):
            self.assertNotEqual(draft_work, m.SILENT_WORK)
            self.assertNotEqual(draft_clips, m.CLIPS_DIR)


class TestSlug(unittest.TestCase):
    """Two slug functions exist, and they must agree on the apostrophe rule.

    scraper/zillow_photos.slugify names agents/<brand>/<listing> and is the
    naming authority. make_tour._slug names the output files from agent_name.
    They are separate functions on purpose -- make_tour runs from a listing
    folder with nothing but ffmpeg on the path, so importing the scraper would
    make a build depend on the scrape -- and they differ on the empty case on
    purpose too. On apostrophes they must not differ, or one name gets two
    spellings: sean_obrien/ holding sean_o_brien_tour_branded.mp4.
    """

    def both(self):
        return helpers.scraper_module("zillow_photos").slugify

    def test_scraper_slug_drops_apostrophes_rather_than_separating(self):
        """The folder-naming authority. CLAUDE.md documents exactly this."""
        slugify = self.both()
        self.assertEqual(slugify("Gibson Sotheby's International Realty"),
                         "gibson_sothebys_international_realty")
        self.assertEqual(slugify("Gibson Sotheby\u2019s International Realty"),
                         "gibson_sothebys_international_realty")

    def test_output_slug_drops_apostrophes_too(self):
        """The fix: make_tour._slug no longer separates on an apostrophe."""
        with helpers.listing(config={}) as (m, _):
            self.assertEqual(m._slug("Gibson Sotheby's International Realty"),
                             "gibson_sothebys_international_realty")
            self.assertEqual(m._slug("Sean O'Brien"), "sean_obrien")

    def test_both_apostrophe_glyphs_are_handled(self):
        """A scrape yields the typographic quote as often as the straight one."""
        slugify = self.both()
        with helpers.listing(config={}) as (m, _):
            for text in ("Sean O'Brien", "Sean O\u2019Brien"):
                self.assertEqual(m._slug(text), "sean_obrien", repr(text))
                self.assertEqual(slugify(text), "sean_obrien", repr(text))

    def test_the_two_sluggers_agree_on_every_non_empty_case(self):
        """The drift guard. A folder and the files inside it spell one name."""
        slugify = self.both()
        cases = ["Gibson Sotheby's International Realty",
                 "Gibson Sotheby\u2019s International Realty",
                 "Coldwell Banker Realty - Boston",
                 "Coldwell Banker Realty - Waltham",
                 "260-262 Commonwealth Ave #1B",
                 "335 W 2nd St UNIT 8",
                 "Sean O'Brien", "Boston Advanced Realty", "Compass"]
        with helpers.listing(config={}) as (m, _):
            for text in cases:
                self.assertEqual(m._slug(text), slugify(text),
                                 f"the two sluggers disagree on {text!r}")

    def test_output_slug_is_idempotent_on_an_already_slugged_value(self):
        """tour.py feeds _slug the brand folder, which the scraper produced."""
        slugify = self.both()
        brand = slugify("Gibson Sotheby's International Realty")
        with helpers.listing(config={}) as (m, _):
            self.assertEqual(m._slug(brand), brand)

    def test_the_empty_case_differs_on_purpose(self):
        """A folder cannot be called ""; a filename prefix must be able to be."""
        slugify = self.both()
        self.assertEqual(slugify("---"), "listing")
        self.assertEqual(slugify("", default="unknown_brokerage"),
                         "unknown_brokerage")
        with helpers.listing(config={}) as (m, _):
            self.assertEqual(m._slug("---"), "")
            self.assertEqual(m._slug(""), "")

    def test_an_empty_agent_name_still_leaves_the_bare_output_names(self):
        """The empty difference exists to protect exactly this."""
        with helpers.listing(config={"agent_name": "---"}) as (m, _):
            self.assertEqual(m.out_path("tour_branded"), "out/tour_branded.mp4")


if __name__ == "__main__":
    unittest.main()
