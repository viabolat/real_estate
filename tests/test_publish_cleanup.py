"""A confirmed sample publish clears its own out/ copies -- and the listings
that lose theirs must not look unbuilt to stage()/next_action().

Guards _rules/a-confirmed-sample-publish-clears-its-own-cuts.md: publish.py
itself still deletes nothing (tests/test_publish_gate.py already holds that
line); this file covers the new layer in tour.py -- publish.published_cuts(),
tour.clear_published_cuts(), tour.sweep_published_samples() -- and the
cross-module agreement between tour.stage() and status.next_action() once
out/ has been swept.
"""
import csv
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers

REPO = helpers.REPO
if REPO not in sys.path:
    sys.path.insert(0, REPO)
import publish  # the same singleton tour.py and status.py both import


def _write_links(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=publish.LINK_COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r)


class TestPublishedCuts(unittest.TestCase):
    """publish.published_cuts(brand, listing) -- the row-level lookup
    clear_published_cuts() cross-checks before deleting anything."""

    def test_reads_only_this_listings_confirmed_cuts(self):
        with tempfile.TemporaryDirectory() as root:
            links = os.path.join(root, "links.csv")
            _write_links(links, [
                {"uploaded_at": "t", "brand": "acme", "listing": "1_main_st",
                 "cut": "sample_branded.mp4", "url": "https://x/1"},
                {"uploaded_at": "t", "brand": "acme", "listing": "2_oak_st",
                 "cut": "sample_branded.mp4", "url": "https://x/2"},
            ])
            with mock.patch.object(publish, "LINKS", links):
                self.assertEqual(publish.published_cuts("acme", "1_main_st"),
                                 {"sample_branded.mp4"})
                self.assertEqual(publish.published_cuts("acme", "nope"), set())

    def test_missing_file_is_empty(self):
        with mock.patch.object(publish, "LINKS", "/no/such/file.csv"):
            self.assertEqual(publish.published_cuts("acme", "1_main_st"), set())


class TestClearPublishedCuts(unittest.TestCase):
    """tour.clear_published_cuts() -- the one place allowed to delete a local
    sample_ cut, and only once links.csv names that exact file."""

    def setUp(self):
        self.tour = helpers.tour_module()

    def _listing_dir(self, root, brand="acme", listing="1_main_st", agent="jane"):
        d = os.path.join(root, "agents", brand, listing, agent)
        os.makedirs(os.path.join(d, "out"))
        return d

    def test_deletes_only_the_confirmed_cut(self):
        with tempfile.TemporaryDirectory() as root:
            listing_dir = self._listing_dir(root)
            out = os.path.join(listing_dir, "out")
            for name in ("sample_branded.mp4", "sample_unbranded.mp4"):
                open(os.path.join(out, name), "wb").close()
            links = os.path.join(root, "links.csv")
            _write_links(links, [{"uploaded_at": "t", "brand": "acme",
                                   "listing": "1_main_st",
                                   "cut": "sample_branded.mp4", "url": "u"}])
            with mock.patch.object(publish, "LINKS", links):
                removed = self.tour.clear_published_cuts(listing_dir)
            self.assertEqual(removed, ["sample_branded.mp4"])
            self.assertEqual(sorted(os.listdir(out)), ["sample_unbranded.mp4"])

    def test_never_deletes_a_tour_cut_even_if_named_in_links_csv(self):
        with tempfile.TemporaryDirectory() as root:
            listing_dir = self._listing_dir(root)
            out = os.path.join(listing_dir, "out")
            open(os.path.join(out, "tour_branded.mp4"), "wb").close()
            links = os.path.join(root, "links.csv")
            # a hand-edited or replayed links.csv naming a tour_ cut -- must
            # never be trusted to delete a deliverable
            _write_links(links, [{"uploaded_at": "t", "brand": "acme",
                                   "listing": "1_main_st",
                                   "cut": "tour_branded.mp4", "url": "u"}])
            with mock.patch.object(publish, "LINKS", links):
                removed = self.tour.clear_published_cuts(listing_dir)
            self.assertEqual(removed, [])
            self.assertEqual(os.listdir(out), ["tour_branded.mp4"])

    def test_dry_run_reports_without_deleting(self):
        with tempfile.TemporaryDirectory() as root:
            listing_dir = self._listing_dir(root)
            out = os.path.join(listing_dir, "out")
            open(os.path.join(out, "sample_branded.mp4"), "wb").close()
            links = os.path.join(root, "links.csv")
            _write_links(links, [{"uploaded_at": "t", "brand": "acme",
                                   "listing": "1_main_st",
                                   "cut": "sample_branded.mp4", "url": "u"}])
            with mock.patch.object(publish, "LINKS", links):
                removed = self.tour.clear_published_cuts(listing_dir, dry_run=True)
            self.assertEqual(removed, ["sample_branded.mp4"])
            self.assertEqual(os.listdir(out), ["sample_branded.mp4"])

    def test_a_row_naming_a_file_not_on_disk_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as root:
            listing_dir = self._listing_dir(root)
            links = os.path.join(root, "links.csv")
            _write_links(links, [{"uploaded_at": "t", "brand": "acme",
                                   "listing": "1_main_st",
                                   "cut": "sample_branded.mp4", "url": "u"}])
            with mock.patch.object(publish, "LINKS", links):
                removed = self.tour.clear_published_cuts(listing_dir)
            self.assertEqual(removed, [])


class TestSweepPublishedSamples(unittest.TestCase):
    """tour.py --sweep-published-samples: defaults to dry-run, deletes with
    dry_run=False."""

    def setUp(self):
        self.tour = helpers.tour_module()

    def _fixture(self, root):
        listing_dir = os.path.join(root, "acme", "1_main_st", "jane")
        out = os.path.join(listing_dir, "out")
        os.makedirs(out)
        open(os.path.join(out, "sample_branded.mp4"), "wb").close()
        links = os.path.join(root, "links.csv")
        _write_links(links, [{"uploaded_at": "t", "brand": "acme",
                               "listing": "1_main_st",
                               "cut": "sample_branded.mp4", "url": "u"}])
        return out, links

    def test_defaults_to_dry_run_and_deletes_nothing(self):
        with tempfile.TemporaryDirectory() as root:
            out, links = self._fixture(root)
            with mock.patch.object(publish, "LINKS", links), \
                 mock.patch.object(self.tour, "LISTINGS_ROOT", root):
                self.tour.sweep_published_samples()
            self.assertEqual(os.listdir(out), ["sample_branded.mp4"])

    def test_dry_run_false_actually_deletes(self):
        with tempfile.TemporaryDirectory() as root:
            out, links = self._fixture(root)
            with mock.patch.object(publish, "LINKS", links), \
                 mock.patch.object(self.tour, "LISTINGS_ROOT", root):
                self.tour.sweep_published_samples(dry_run=False)
            self.assertEqual(os.listdir(out), [])


class TestStageAndNextActionAgreeAfterCleanup(unittest.TestCase):
    """The gap a-confirmed-sample-publish-clears-its-own-cuts.md exists to
    close: out/ with neither cut family must not read as "never built" once
    a links.csv row proves a sample_ cut was already confirmed and swept.
    """

    def setUp(self):
        self.tour = helpers.tour_module()
        self.status = helpers.status_module()

    def _listing(self, root, brand="acme", listing="1_main_st", agent="jane"):
        d = os.path.join(root, brand, listing, agent)
        os.makedirs(os.path.join(d, "out"))
        for name in ("logo.png", "music.mp3", "wm.png"):
            open(os.path.join(d, name), "wb").close()
        return d

    def _cfg(self):
        return {"logo": "logo.png", "music": "music.mp3", "watermark": "wm.png"}

    def test_a_cleaned_up_but_published_listing_reads_as_delivery(self):
        with tempfile.TemporaryDirectory() as root:
            listing_dir = self._listing(root)
            links = os.path.join(root, "links.csv")
            _write_links(links, [{"uploaded_at": "t", "brand": "acme",
                                   "listing": "1_main_st",
                                   "cut": "sample_branded.mp4", "url": "u"}])
            with mock.patch.object(publish, "LINKS", links):
                self.assertEqual(self.tour.stage(listing_dir), "delivery")
                verdict = self.status.next_action(
                    listing_dir, self._cfg(), n=10, worst=2160, best=2160)
            self.assertTrue(verdict.startswith("sample published"), verdict)

    def test_never_built_and_never_published_is_still_ready_to_build(self):
        with tempfile.TemporaryDirectory() as root:
            listing_dir = self._listing(root)
            links = os.path.join(root, "links.csv")  # never written
            with mock.patch.object(publish, "LINKS", links):
                self.assertEqual(self.tour.stage(listing_dir), "sample")
                verdict = self.status.next_action(
                    listing_dir, self._cfg(), n=10, worst=2160, best=2160)
            self.assertTrue(verdict.startswith("ready to build"), verdict)


if __name__ == "__main__":
    unittest.main()
