"""Photo URL extraction against two real Zillow dumps, one of each listing shape.

reason: URL extraction was the one part of the scraper with no test at all --
`grep zillowstatic tests/` returned nothing -- and it is where a silent 40%
failure lived for as long as Zillow has served Showcase listings. Every other
test here builds its input; these two read a dump, because the bug was never in
the logic. It was in what the payload actually contains, and a hand-written
fixture would have been written from the same wrong assumption as the regex.

The fixtures are the real dumps with PII removed and nothing else touched:
anything phone- or email-shaped, plus every `leads.csv` identifier value, was
replaced (`agentName`, `agentPhoneNumber`). Every `zillowstatic` URL,
`photoCount`, `brokerName`, `streetAddress` and `zpid` is verbatim from the
scrape, and the redaction was applied only after asserting it left
`extract_photo_urls()`'s output unchanged. `check_pii.py` is the gate on that.

Guards _rules/a-second-listing-shape-is-a-fallback-never-a-replacement.md.
"""
import os
import unittest

import helpers

photos = helpers.scraper_module("photos")

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
REGULAR = os.path.join(FIXTURES, "59126324_regular.json")
SHOWCASE = os.path.join(FIXTURES, "464857207_showcase.json")


def read(path):
    with open(path, encoding="utf-8", errors="ignore") as f:
        return f.read()


class TestRegularListing(unittest.TestCase):
    """A regular listing must extract exactly what it did before cc_ft existed."""

    def setUp(self):
        self.urls = photos.extract_photo_urls(read(REGULAR))

    def test_every_photo_is_found(self):
        self.assertEqual(len(self.urls), 32)

    def test_photoCount_agrees(self):
        from lead import field
        self.assertEqual(str(len(self.urls)), field(read(REGULAR), "photoCount"))

    def test_every_url_is_the_uncropped_variant(self):
        # reason: this is the whole point of the fallback being a second pass.
        # Both families exist on this listing at width 1536, so a single regex
        # ranked by width would tie and could hand back cropped variants for
        # photos that have an uncropped original. Not one cc_ft URL may appear
        # here.
        for url in self.urls:
            self.assertIn("-uncropped_scaled_within_", url)
            self.assertNotIn("-cc_ft_", url)

    def test_no_duplicate_hashes(self):
        self.assertEqual(len(set(self.urls)), len(self.urls))


class TestShowcaseListing(unittest.TestCase):
    """A Showcase listing has no uncropped variant at all -- cc_ft or nothing."""

    def setUp(self):
        self.urls = photos.extract_photo_urls(read(SHOWCASE))

    def test_every_photo_is_found(self):
        # Before the fallback this was 0, and the dump was set aside as failed
        # while holding all 33 URLs.
        self.assertEqual(len(self.urls), 33)

    def test_photoCount_agrees(self):
        from lead import field
        self.assertEqual(str(len(self.urls)), field(read(SHOWCASE), "photoCount"))

    def test_every_url_is_cc_ft_at_the_largest_width(self):
        for url in self.urls:
            self.assertIn("-cc_ft_1536.jpg", url)

    def test_the_uncropped_pattern_alone_finds_nothing(self):
        # The premise of the whole change: it is not that the old regex ranked
        # these badly, it is that they are absent.
        self.assertEqual(photos.PHOTO_PATTERN.findall(read(SHOWCASE)), [])

    def test_the_narrow_families_are_not_swept_in(self):
        # sc_/sr_ are present on Showcase and over-collect -- they include
        # images that are not gallery photos. Widening to them would pass the
        # count test above by accident and ship a gallery with junk in it.
        for url in self.urls:
            self.assertNotIn("-sc_", url)
            self.assertNotIn("-sr_", url)

    def test_no_duplicate_hashes(self):
        self.assertEqual(len(set(self.urls)), len(self.urls))


class TestBothShapesScaffoldAFolder(unittest.TestCase):
    """target_for() is the second caller, and its refusal must not change."""

    def test_a_showcase_dump_is_no_longer_carried_by_its_address_alone(self):
        # reason: before the fallback, a Showcase dump cleared target_for()'s
        # refusal only because streetAddress happened to be present -- the photo
        # half of `not urls and not address` was always true. Same verdict now,
        # but on the real reason.
        text = read(SHOWCASE)
        self.assertTrue(photos.extract_photo_urls(text))
        self.assertIsNotNone(photos.target_for(text))

    def test_a_dump_that_is_neither_is_still_refused(self):
        self.assertIsNone(photos.target_for("nothing to see here"))


class TestBrokerNameAcrossBothShapes(unittest.TestCase):
    """The same two-shapes split renames attribution, not just photos."""

    def test_a_regular_listing_reads_brokerName(self):
        from lead import broker_name, field
        text = read(REGULAR)
        self.assertEqual(broker_name(text), field(text, "brokerName"))
        self.assertIsNotNone(broker_name(text))

    def test_a_showcase_listing_falls_back_to_brokerageName(self):
        from lead import broker_name, field
        text = read(SHOWCASE)
        # The key the old reader looked for is simply not there.
        self.assertIsNone(field(text, "brokerName"))
        self.assertEqual(broker_name(text), "Coldwell Banker Realty - Newton")

    def test_the_two_keys_are_disjoint_so_the_fallback_cannot_move_a_folder(self):
        # reason: this is why the fallback is safe on a regular listing, and it
        # is the same argument CC_FT_PATTERN rests on. A broker slug is a folder
        # name; if a regular dump ever carried both keys with different values,
        # this fallback could silently rename an existing listing's folder.
        from lead import field
        for path in (REGULAR, SHOWCASE):
            text = read(path)
            present = [k for k in ("brokerName", "brokerageName")
                       if field(text, k) is not None]
            self.assertEqual(len(present), 1, os.path.basename(path))

    def test_a_showcase_listing_no_longer_slugs_to_unknown_brokerage(self):
        # Before the fallback all four parked Showcase dumps produced
        # unknown_brokerage/<address>/unassigned_agent -- and one such tree was
        # actually written to disk, with zero photos in it.
        brand, listing, agent = photos.target_for(read(SHOWCASE))
        self.assertEqual(brand, "coldwell_banker_realty_newton")
        self.assertEqual(listing, "32_34_ditson_st_2")
        # agentName genuinely is absent on a Showcase payload
        # (listingAgentAttributionContact is null), so the placeholder is right.
        self.assertEqual(agent, photos.UNASSIGNED_AGENT)

    def test_a_dump_with_neither_key_still_gets_the_placeholder(self):
        from lead import broker_name
        self.assertIsNone(broker_name("streetAddress: 1 Nowhere St"))
        self.assertEqual(
            photos.slugify(broker_name("streetAddress: x"), "unknown_brokerage"),
            "unknown_brokerage")


class TestPhotoCountVerdict(unittest.TestCase):
    """Zero URLs on a listing that says it has photos is a failure, not a print."""

    def test_none_found_when_some_expected_fails(self):
        self.assertEqual(photos.photo_count_verdict(0, "33"), "fail")

    def test_fewer_than_expected_warns(self):
        self.assertEqual(photos.photo_count_verdict(30, "33"), "warn")

    def test_more_than_expected_also_warns(self):
        # Over-collection is what a too-broad pattern looks like; it must not go
        # quiet just because the zero case now shouts.
        self.assertEqual(photos.photo_count_verdict(40, "33"), "warn")

    def test_agreement_is_silent(self):
        self.assertIsNone(photos.photo_count_verdict(33, "33"))

    def test_a_listing_with_no_photoCount_is_not_this_bug(self):
        self.assertIsNone(photos.photo_count_verdict(0, None))
        self.assertIsNone(photos.photo_count_verdict(0, "0"))
        self.assertIsNone(photos.photo_count_verdict(0, "not a number"))


class TestFixturesCarryNoContactDetails(unittest.TestCase):
    """The fixtures are committed, so they are inside the PII boundary.

    reason: check_pii.py is the real gate, but it only runs before a push and
    only knows the names currently in leads.csv. These two files are the first
    real scrape output ever committed to this repo, and a later re-redaction
    that missed a field would sit in the tree until someone ran the hook.
    """

    def test_no_phone_or_email_shaped_text(self):
        import re
        phone = re.compile(r'\b\d{3}[-.\s)]\s?\d{3}[-.\s]\d{4}\b')
        email = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')
        allow = re.compile(r'@example\.|noreply@')
        for path in (REGULAR, SHOWCASE):
            text = read(path)
            self.assertEqual(phone.findall(text), [], os.path.basename(path))
            for hit in email.findall(text):
                self.assertRegex(hit, allow, os.path.basename(path))


if __name__ == "__main__":
    unittest.main()
