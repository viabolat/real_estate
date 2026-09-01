"""The recorded link stays a link, and the draft quotes the watermarked cut.

Guards three things publish.py now owns:

  * outreach/links.csv puts url LAST and uploaded_at FIRST, with \n endings. The
    link used to sit mid-row, so anything that grabbed it took the timestamp with
    it and the URL 404'd. Nothing may be appended after url again.
  * the email draft quotes the sample_branded cut and never a tour_ file --
    _rules/never-cross-the-sample-tour-boundary.md, one layer up from the
    upload gate that tests/test_publish_gate.py covers.
  * outreach/contacted.csv is append-only, by header name, and never rewrites
    leads.csv itself -- the same shape links.csv already holds.

No network: record_links(), record_contacted() and the draft renderer are pure
file work.
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
import helpers

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


class TestContactedRecord(unittest.TestCase):
    """outreach/contacted.csv -- byte-for-byte the same append-by-header-name
    shape record_links() already uses for links.csv."""

    def test_columns_are_marked_at_brand_listing_agent(self):
        self.assertEqual(publish.CONTACTED_COLUMNS,
                          ["marked_at", "brand", "listing", "agent"])

    def test_record_then_lookup_round_trips(self):
        with tempfile.TemporaryDirectory() as d:
            contacted = os.path.join(d, "outreach", "contacted.csv")
            with mock.patch.object(publish, "CONTACTED", contacted), \
                 mock.patch.object(publish, "LEADS_CSV", os.path.join(d, "leads.csv")):
                self.assertFalse(publish.contacted("corcoran", "46_beacon_5",
                                                    "sean_obrien"))
                publish.record_contacted("corcoran", "46_beacon_5", "sean_obrien")
                self.assertTrue(publish.contacted("corcoran", "46_beacon_5",
                                                   "sean_obrien"))
                self.assertFalse(publish.contacted("corcoran", "46_beacon_5",
                                                    "someone_else"))

    def test_a_missing_file_reads_as_not_contacted(self):
        with mock.patch.object(publish, "CONTACTED", "/no/such/file.csv"):
            self.assertFalse(publish.contacted("corcoran", "46_beacon_5",
                                                "sean_obrien"))

    def test_appending_twice_keeps_one_header_and_two_rows(self):
        with tempfile.TemporaryDirectory() as d:
            contacted = os.path.join(d, "outreach", "contacted.csv")
            with mock.patch.object(publish, "CONTACTED", contacted), \
                 mock.patch.object(publish, "LEADS_CSV", os.path.join(d, "leads.csv")):
                publish.record_contacted("corcoran", "46_beacon_5", "sean_obrien")
                publish.record_contacted("corcoran", "9_oak_st", "jane_doe")
            with open(contacted, newline="", encoding="utf-8") as f:
                raw = f.read()
                f.seek(0)
                rows = list(csv.DictReader(f))
        self.assertEqual(raw.count("marked_at"), 1, "the header was written twice")
        self.assertEqual(len(rows), 2)

    def test_never_touches_links_csv(self):
        """reason: publish.py's other record file must not gain a side effect
        from marking a lead contacted -- the two are independent facts."""
        with tempfile.TemporaryDirectory() as d:
            links = os.path.join(d, "links.csv")
            contacted = os.path.join(d, "contacted.csv")
            with mock.patch.object(publish, "LINKS", links), \
                 mock.patch.object(publish, "CONTACTED", contacted), \
                 mock.patch.object(publish, "LEADS_CSV", os.path.join(d, "leads.csv")):
                publish.record_contacted("corcoran", "46_beacon_5", "sean_obrien")
            self.assertFalse(os.path.isfile(links))

    def test_never_touches_the_real_leads_html(self):
        """reason: _refresh_leads_html() reads module-level LEADS_CSV/LEADS_HTML
        directly, not whatever CONTACTED was patched to -- a test that isolates
        CONTACTED alone still lets record_contacted() write the real
        scraper/leads.html, joined against this test's own throwaway contacted
        row, clobbering every real lead's CONTACTED/FOLLOW UP columns to blank.
        Every test in this class that calls record_contacted() must also patch
        LEADS_CSV (or LEADS_HTML) so _refresh_leads_html()'s own
        os.path.isfile(LEADS_CSV) guard no-ops it."""
        def _read(path):
            if not os.path.isfile(path):
                return None
            with open(path, encoding="utf-8") as f:
                return f.read()

        with tempfile.TemporaryDirectory() as d:
            contacted = os.path.join(d, "outreach", "contacted.csv")
            real_leads_html = publish.LEADS_HTML
            before = _read(real_leads_html)
            with mock.patch.object(publish, "CONTACTED", contacted), \
                 mock.patch.object(publish, "LEADS_CSV", os.path.join(d, "leads.csv")):
                publish.record_contacted("corcoran", "46_beacon_5", "sean_obrien")
            after = _read(real_leads_html)
        self.assertEqual(before, after, "record_contacted() touched the real "
                          "scraper/leads.html")

    def test_marking_contacted_refreshes_leads_html(self):
        """reason: leads.html's CONTACTED column used to go stale the moment a
        lead was marked contacted from anywhere but a fresh scrape -- nothing
        called write_html_table() again. record_contacted() now refreshes it
        itself, so every caller (the publish rung, the bulk mark-contacted
        action, or a one-off script) gets a correct page for free."""
        with tempfile.TemporaryDirectory() as d:
            contacted = os.path.join(d, "contacted.csv")
            leads_csv = os.path.join(d, "leads.csv")
            leads_html = os.path.join(d, "leads.html")
            lead = helpers.scraper_module("lead")
            with open(leads_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=lead.CSV_FIELDS)
                w.writeheader()
                w.writerow({
                    "address": "46 Beacon St #5", "zip": "02116",
                    "city": "Boston", "state": "MA", "price": "500000",
                    "beds": "2", "baths": "1", "zpid": "1001",
                    "status": "FOR_SALE", "type": "CONDO",
                    "agent_name": "Sean O'Brien", "agent_email": "",
                    "agent_phone": "1001", "broker_name": "Corcoran",
                    "mls_id": "", "contact_role": "", "contact_name": "",
                })
            with mock.patch.object(publish, "CONTACTED", contacted), \
                 mock.patch.object(publish, "LEADS_CSV", leads_csv), \
                 mock.patch.object(publish, "LEADS_HTML", leads_html):
                self.assertFalse(os.path.isfile(leads_html))
                publish.record_contacted("corcoran", "46_beacon_st_5", "sean_obrien")
                self.assertTrue(os.path.isfile(leads_html))
                with open(leads_html, encoding="utf-8") as f:
                    page = f.read()
            row_line = next(l for l in page.splitlines() if "Corcoran" in l)
            self.assertTrue(row_line.lstrip().startswith("<tr><td>contacted</td>"),
                             row_line)


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

    def test_the_draft_lands_inside_the_listing_agent_folder(self):
        """reason: the draft used to land in a flat outreach/drafts/ tree, apart
        from the out/ cuts that produced it. It now lands right beside them, so
        agents/<brand>/<listing>/<agent>/ holds everything for that property."""
        d = self.listing(agent_name="Sean O'Brien", address="46 Beacon St #5")
        path, _ = publish.write_draft(d, URL)
        self.assertEqual(path, os.path.join(d, publish.DRAFT_FILENAME))
        self.assertEqual(os.path.basename(path), "outreach_draft.txt")
        self.assertTrue(os.path.isfile(path))

    def test_nothing_in_publish_sends_mail(self):
        """PROGRESS.md 5.1: drafting is automatic, sending never is."""
        import inspect
        src = inspect.getsource(publish)
        for token in ("smtplib", "sendmail", "SMTP(", "starttls"):
            self.assertNotIn(token, src, f"{token} puts a send path in the repo")


if __name__ == "__main__":
    unittest.main()
