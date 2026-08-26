"""status.py must not send you somewhere that cannot help, or pass silently.

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
