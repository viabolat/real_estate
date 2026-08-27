"""The recorded link stays a link, and the draft quotes the watermarked cut.

Guards two things publish.py now owns:

  * outreach/links.csv puts url LAST and uploaded_at FIRST, with \n endings. The
    link used to sit mid-row, so anything that grabbed it took the timestamp with
    it and the URL 404'd. Nothing may be appended after url again.
  * the email draft quotes the sample_branded cut and never a tour_ file --
    _rules/never-cross-the-sample-tour-boundary.md, one layer up from the
    upload gate that tests/test_publish_gate.py covers.

No network: record_links() and the draft renderer are pure file work.
"""
import csv
import os
import sys
import tempfile
import unittest
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
import publish

URL = ("https://real-estate.viabolat.com/preview/corcoran/46_beacon_5/"
       "sean_obrien_sample_branded")


def row(**over):
    r = {"uploaded_at": "2026-08-26T16:58:12", "brand": "corcoran",
         "listing": "46_beacon_5", "cut": "sean_obrien_sample_branded.mp4",
         "url": URL}
    r.update(over)
    return r


class TestLinkRecord(unittest.TestCase):

    def test_url_is_the_last_column_and_uploaded_at_the_first(self):
        """reason: a field after the url is a field that gets swallowed into it."""
        self.assertEqual(publish.LINK_COLUMNS[-1], "url")
        self.assertEqual(publish.LINK_COLUMNS[0], "uploaded_at")

    def test_a_written_row_ends_at_the_url(self):
        with tempfile.TemporaryDirectory() as d:
            links = os.path.join(d, "outreach", "links.csv")
            with mock.patch.object(publish, "LINKS", links):
                publish.record_links([row()])
            with open(links, encoding="utf-8", newline="") as f:
                raw = f.read()
        self.assertNotIn("\r", raw, "a \\r rides on the last field")
        last = raw.splitlines()[-1]
        self.assertTrue(last.endswith(URL), last)

    def test_an_old_file_is_migrated_not_appended_to(self):
        """A links.csv written before the reorder must not keep both shapes."""
        with tempfile.TemporaryDirectory() as d:
            links = os.path.join(d, "outreach", "links.csv")
            os.makedirs(os.path.dirname(links))
            with open(links, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["brand", "listing", "cut",
                                                  "url", "uploaded_at"])
                w.writeheader()
                w.writerow({"brand": "corcoran", "listing": "46_beacon_5",
                            "cut": "old.mp4", "url": URL,
                            "uploaded_at": "2026-08-01T10:00:00"})
            with mock.patch.object(publish, "LINKS", links):
                publish.record_links([row()])
            with open(links, encoding="utf-8", newline="") as f:
                raw = f.read()
            with open(links, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        self.assertNotIn("\r", raw)
        self.assertEqual(list(rows[0].keys()), publish.LINK_COLUMNS)
        self.assertEqual(len(rows), 2, "the old row was dropped or duplicated")
        for r in rows:
            self.assertEqual(r["url"], URL)
            self.assertEqual(r["brand"], "corcoran")


class TestDraft(unittest.TestCase):

    def listing(self, **cfg):
        d = tempfile.mkdtemp()
        import json
        with open(os.path.join(d, "config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        return d

    def test_the_draft_carries_the_name_address_and_link(self):
        d = self.listing(agent_name="Sean O'Brien", address="46 Beacon St #5")
        text, missing = publish.draft_text(d, URL)
        self.assertEqual(missing, [])
        self.assertIn("Hi Sean,", text)
        self.assertIn("46 Beacon St #5", text)
        self.assertIn(URL, text)
        self.assertNotIn("{", text, "a placeholder was left unrendered")

    def test_the_link_line_holds_the_url_alone(self):
        """reason: the whole point of moving url last in the csv -- the draft must
        not reintroduce a trailing anything on the line someone copies."""
        d = self.listing(agent_name="Sean O'Brien", address="46 Beacon St #5")
        text, _ = publish.draft_text(d, URL)
        line = next(l for l in text.splitlines() if URL in l)
        self.assertEqual(line.strip(), URL)

    def test_a_tour_url_never_reaches_the_draft(self):
        """The outreach link is the watermarked cut. A tour_ file is the sale.

        reason: scoped to the two functions that produce a draft, not the whole
        module -- the docstring names tour_branded to explain why it is refused,
        and a test that cannot tell an explanation from a code path is a test
        that gets deleted the next time someone edits a comment.
        """
        import inspect
        self.assertEqual(publish.PRIMARY_CUT, "sample_branded")
        for fn in (publish.draft_text, publish.write_draft):
            src = inspect.getsource(fn)
            self.assertNotIn("tour_", src,
                             f"{fn.__name__} names a tour_ cut")
        d = self.listing(agent_name="Sean O'Brien", address="46 Beacon St #5")
        text, _ = publish.draft_text(d, URL)
        self.assertNotIn("tour_", text)
        self.assertIn("sample_branded", text)

    def test_a_blank_name_leaves_the_placeholder_visible(self):
        """reason: 'Hi ,' ships; an unfilled {agent_first} gets noticed."""
        d = self.listing(agent_name="", address="46 Beacon St #5")
        text, missing = publish.draft_text(d, URL)
        self.assertIn("agent_first", missing)
        self.assertIn("{agent_first}", text)

    def test_the_draft_lands_in_outreach_and_never_in_a_listing(self):
        d = self.listing(agent_name="Sean O'Brien", address="46 Beacon St #5")
        with tempfile.TemporaryDirectory() as out:
            with mock.patch.object(publish, "DRAFTS", os.path.join(out, "drafts")):
                path, _ = publish.write_draft(d, "corcoran", "46_beacon_5", URL)
            self.assertTrue(path.startswith(out), path)
            self.assertEqual(os.path.basename(path), "corcoran__46_beacon_5.txt")
        self.assertNotIn(os.path.join("agents", ""), publish.DRAFTS)
        self.assertTrue(publish.DRAFTS.endswith(os.path.join("outreach", "drafts")))

    def test_nothing_in_publish_sends_mail(self):
        """PROGRESS.md 5.1: drafting is automatic, sending never is."""
        import inspect
        src = inspect.getsource(publish)
        for token in ("smtplib", "sendmail", "SMTP(", "starttls"):
            self.assertNotIn(token, src, f"{token} puts a send path in the repo")


if __name__ == "__main__":
    unittest.main()
