"""
A dump that has already been scraped -- same company/address/agent -- must be
reported loudly and must not repeat the download or the CSV append. These
tests exercise the pure detection/formatting functions directly rather than
scraper/lead.py's or scraper/photos.py's main(), because main() in both
scripts writes into real, gitignored, PII-bearing paths (the repo's actual
agents/ tree and scraper/leads.csv) that a test must never touch.
"""
import csv
import os
import tempfile
import unittest
from unittest import mock

import helpers


class TestPhotosAlreadyScraped(unittest.TestCase):
    def setUp(self):
        self.photos = helpers.scraper_module("photos")

    def test_no_folder_yet_is_not_a_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "photos")
            self.assertEqual(
                self.photos.already_scraped(out_dir, ["u1", "u2", "u3"]), 0)

    def test_fewer_on_disk_than_urls_is_a_partial_run_not_a_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "photos")
            os.makedirs(out_dir)
            open(os.path.join(out_dir, "01.jpg"), "w").close()
            self.assertEqual(
                self.photos.already_scraped(out_dir, ["u1", "u2", "u3"]), 0)

    def test_at_least_as_many_on_disk_as_urls_is_a_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "photos")
            os.makedirs(out_dir)
            for name in ("01.jpg", "02.jpg", "03.jpg"):
                open(os.path.join(out_dir, name), "w").close()
            self.assertEqual(
                self.photos.already_scraped(out_dir, ["u1", "u2"]), 3)

    def test_no_urls_is_never_a_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "photos")
            os.makedirs(out_dir)
            open(os.path.join(out_dir, "01.jpg"), "w").close()
            self.assertEqual(self.photos.already_scraped(out_dir, []), 0)

    def test_non_jpg_files_do_not_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = os.path.join(tmp, "photos")
            os.makedirs(out_dir)
            open(os.path.join(out_dir, "notes.txt"), "w").close()
            self.assertEqual(
                self.photos.already_scraped(out_dir, ["u1"]), 0)


class TestLeadDuplicateBanner(unittest.TestCase):
    def setUp(self):
        self.lead = helpers.scraper_module("lead")

    def _row(self, **overrides):
        row = {
            "address": "11 First St", "zip": "10001", "city": "Anytown",
            "state": "NY", "price": "500000", "beds": "3", "baths": "2",
            "zpid": "1001", "status": "FOR_SALE", "type": "SINGLE_FAMILY",
            "agent_name": "Agent A", "agent_email": "a@example.com",
            "agent_phone": "1001", "broker_name": "Brokerage One",
            "mls_id": "M1", "contact_role": "Listing Agent",
            "contact_name": "Agent A",
        }
        row.update(overrides)
        return row

    def test_find_duplicate_matches_on_zpid_and_phone(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "leads.csv")
            existing = self._row()
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.lead.CSV_FIELDS)
                writer.writeheader()
                writer.writerow(existing)

            dup = self.lead.find_duplicate(csv_path, self._row())
            self.assertIsNotNone(dup)

    def test_new_zpid_is_not_a_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "leads.csv")
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.lead.CSV_FIELDS)
                writer.writeheader()
                writer.writerow(self._row())

            dup = self.lead.find_duplicate(csv_path, self._row(zpid="2002"))
            self.assertIsNone(dup)

    def test_duplicate_banner_names_the_address_and_csv_path(self):
        row = self._row()
        banner = self.lead.duplicate_banner("/tmp/leads.csv", row)
        self.assertIn("DUPLICATE -- SKIPPED", banner)
        self.assertIn(row["address"], banner)
        self.assertIn(row["agent_name"], banner)
        self.assertIn(row["zpid"], banner)
        self.assertIn("Nothing appended", banner)


class TestLeadHtmlContactedColumn(unittest.TestCase):
    """leads.html's derived CONTACTED column, and the guard that lead.py
    borrowing photos.py's slugify() (a lazy, function-scoped load -- see
    lead._load_photos()) never re-enters this same file. Loading it eagerly
    at module scope would crash the very first run: photos.py imports FROM
    lead.py, so an eager load re-executes lead.py under the name "lead"
    before field()/extract_zip_city_state() exist on it yet, and this test
    is what would catch that regression -- a RecursionError or ImportError,
    not a wrong column.
    """
    def setUp(self):
        self.lead = helpers.scraper_module("lead")

    def _row(self, **overrides):
        row = {
            "address": "46 Beacon St #5", "zip": "02116", "city": "Boston",
            "state": "MA", "price": "500000", "beds": "2", "baths": "1",
            "zpid": "1001", "status": "FOR_SALE", "type": "CONDO",
            "agent_name": "Sean O'Brien", "agent_email": "",
            "agent_phone": "1001", "broker_name": "Corcoran",
            "mls_id": "", "contact_role": "", "contact_name": "",
        }
        row.update(overrides)
        return row

    def _write_leads(self, path, rows):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=self.lead.CSV_FIELDS)
            w.writeheader()
            for r in rows:
                w.writerow(r)

    def test_the_table_gets_a_contacted_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "leads.csv")
            html_path = os.path.join(tmp, "leads.html")
            self._write_leads(csv_path, [self._row()])
            self.lead.write_html_table(csv_path, html_path)
            with open(html_path, encoding="utf-8") as f:
                page = f.read()
        self.assertIn("<th>contacted</th>", page)

    def test_a_row_in_contacted_csv_is_marked_contacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "leads.csv")
            html_path = os.path.join(tmp, "leads.html")
            contacted_csv = os.path.join(tmp, "contacted.csv")
            self._write_leads(csv_path, [self._row()])
            with open(contacted_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["marked_at", "brand",
                                                   "listing", "agent"])
                w.writeheader()
                w.writerow({"marked_at": "t", "brand": "corcoran",
                            "listing": "46_beacon_st_5",
                            "agent": "sean_obrien"})
            with mock.patch.object(self.lead, "CONTACTED_CSV", contacted_csv):
                self.lead.write_html_table(csv_path, html_path)
            with open(html_path, encoding="utf-8") as f:
                page = f.read()
        row_line = next(l for l in page.splitlines() if "Corcoran" in l)
        self.assertTrue(row_line.lstrip().startswith("<tr><td>contacted</td>"),
                         row_line)

    def test_a_lead_absent_from_contacted_csv_is_new(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "leads.csv")
            html_path = os.path.join(tmp, "leads.html")
            contacted_csv = os.path.join(tmp, "contacted.csv")  # never written
            self._write_leads(csv_path, [self._row()])
            with mock.patch.object(self.lead, "CONTACTED_CSV", contacted_csv):
                self.lead.write_html_table(csv_path, html_path)
            with open(html_path, encoding="utf-8") as f:
                page = f.read()
        row_line = next(l for l in page.splitlines() if "Corcoran" in l)
        self.assertTrue(row_line.lstrip().startswith("<tr><td>new</td>"), row_line)


class TestRunOneClassification(unittest.TestCase):
    def setUp(self):
        self.run = helpers.scraper_module("run")

    def test_both_succeed_is_new(self):
        self.assertEqual(self._classify(0, 0), "new")

    def test_either_side_duplicate_is_duplicate(self):
        self.assertEqual(self._classify(3, 0), "duplicate")
        self.assertEqual(self._classify(0, 3), "duplicate")
        self.assertEqual(self._classify(3, 3), "duplicate")

    def test_any_other_nonzero_is_failed(self):
        self.assertEqual(self._classify(2, 0), "failed")
        self.assertEqual(self._classify(0, 1), "failed")
        self.assertEqual(self._classify(2, 3), "failed")

    def _classify(self, lead_code, photos_code):
        """run_one() without shelling out -- fake subprocess.run() results."""
        class FakeResult:
            def __init__(self, returncode):
                self.returncode = returncode

        real_run = self.run.subprocess.run
        calls = iter([FakeResult(lead_code), FakeResult(photos_code)])
        self.run.subprocess.run = lambda *a, **k: next(calls)
        try:
            return self.run.run_one("dump.txt", "lead.py", "photos.py")
        finally:
            self.run.subprocess.run = real_run


if __name__ == "__main__":
    unittest.main()
