"""The front door: derived state, and a roll-up that cannot block a build.

Guards CLAUDE.md's "Photo order lives in the filename prefix and nowhere else"
generalised one level up -- unimported dumps are detected by whether the folder
exists, never by a marker file -- and the project's warn-vs-refuse asymmetry: a
broken cosmetic layer drops out, only a broken watermark stops a build.
"""
import ast
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers

DUMP = """
"streetAddress":"12 Example St Unit 3","zpid":"111","homeStatus":"FOR_SALE"
"brokerName":"Example Brokerage LLC","agentName":"A Person"
"""


class TestUnimportedDumps(unittest.TestCase):
    """Derived from folder existence. No manifest, no marker, ever."""

    def setUp(self):
        self.tour = helpers.tour_module()
        self.tmp = tempfile.mkdtemp(prefix="home_dumps_")
        self.dumps = os.path.join(self.tmp, "dumps")
        self.agents = os.path.join(self.tmp, "agents")
        os.makedirs(self.dumps)
        os.makedirs(self.agents)
        with open(os.path.join(self.dumps, "paste1.txt"), "w") as f:
            f.write(DUMP)
        self.prev = (self.tour.DUMPS, self.tour.LISTINGS_ROOT)
        self.tour.DUMPS, self.tour.LISTINGS_ROOT = self.dumps, self.agents

    def tearDown(self):
        self.tour.DUMPS, self.tour.LISTINGS_ROOT = self.prev
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_dump_with_no_folder_is_pending(self):
        pending = self.tour.unimported_dumps()
        self.assertEqual([p[0] for p in pending], ["paste1.txt"])
        self.assertEqual(pending[0][1:],
                         ("example_brokerage_llc", "12_example_st_unit_3"))

    def test_the_folder_existing_is_the_whole_test(self):
        """No import is recorded anywhere -- the folder IS the record."""
        _n, brand, listing = self.tour.unimported_dumps()[0]
        os.makedirs(os.path.join(self.agents, brand, listing))
        self.assertEqual(self.tour.unimported_dumps(), [])

    def test_detection_writes_nothing(self):
        """A marker file or manifest would drift out of sync with the folders."""
        before = sorted(os.listdir(self.dumps))
        self.tour.unimported_dumps()
        self.tour.unimported_dumps()
        self.assertEqual(sorted(os.listdir(self.dumps)), before,
                         "unimported_dumps() wrote into scraper/dumps/. State "
                         "is derived from folder existence and nowhere else.")
        self.assertEqual(os.listdir(self.agents), [],
                         "unimported_dumps() is read-only.")

    def test_deleting_the_folder_re_offers_the_dump(self):
        """The failure a .processed marker would produce, asserted directly."""
        _n, brand, listing = self.tour.unimported_dumps()[0]
        made = os.path.join(self.agents, brand, listing)
        os.makedirs(made)
        self.assertEqual(self.tour.unimported_dumps(), [])
        shutil.rmtree(made)
        self.assertEqual(len(self.tour.unimported_dumps()), 1)

    def test_a_dump_that_is_not_a_listing_is_not_offered(self):
        """Mirrors photos.py's own refusal -- no urls and no address."""
        with open(os.path.join(self.dumps, "junk.txt"), "w") as f:
            f.write("this is just some text with no listing in it at all\n")
        self.assertEqual([p[0] for p in self.tour.unimported_dumps()],
                         ["paste1.txt"])

    def test_no_source_file_records_processed_dumps(self):
        """A guard on the shape, not just on this implementation.

        reason: read the CODE, not the comments. Every one of these files
        explains in prose why there is no processed-dumps record, so a plain
        text search matches the documentation of the rule and fails on the
        files that follow it -- which is what the first version of this test
        did. ast.unparse() on a tree with the docstrings removed leaves the
        code and drops every comment.
        """
        for name in ("tour.py", "status.py", os.path.join("scraper",
                                                          "run.py")):
            with open(os.path.join(helpers.REPO, name)) as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                body = getattr(node, "body", None)
                if not isinstance(body, list) or not body:
                    continue
                first = body[0]
                if (isinstance(first, ast.Expr)
                        and isinstance(first.value, ast.Constant)
                        and isinstance(first.value.value, str)):
                    body.pop(0)
            code = ast.unparse(tree).lower()
            for word in (".processed", "processed.json", "imported.json",
                         "dumps_seen", "manifest.json", ".imported"):
                self.assertNotIn(word, code,
                                 f"{name} records which dumps were processed. "
                                 "Derive it from the folder -- a record kept "
                                 "beside the artifacts drifts out of sync with "
                                 "them, and then it is wrong silently.")


class TestRollUpDegrades(unittest.TestCase):
    """A missing roll-up is cosmetic. It must not take a build down."""

    def test_load_status_returns_a_reason_instead_of_raising(self):
        tour = helpers.tour_module()
        prev_root, prev_cache = tour.ROOT, tour._STATUS
        try:
            tour.ROOT = tempfile.mkdtemp(prefix="no_status_")
            tour._STATUS = ()
            mod, why = tour.load_status()
        finally:
            shutil.rmtree(tour.ROOT, ignore_errors=True)
            tour.ROOT, tour._STATUS = prev_root, prev_cache
        self.assertIsNone(mod)
        self.assertTrue(why, "a failed roll-up import must say why.")

    def test_dump_detection_degrades_with_it(self):
        tour = helpers.tour_module()
        prev_root, prev_cache = tour.ROOT, tour._STATUS
        try:
            tour.ROOT = tempfile.mkdtemp(prefix="no_status_")
            tour._STATUS = ()
            self.assertEqual(tour.unimported_dumps(), [])
        finally:
            shutil.rmtree(tour.ROOT, ignore_errors=True)
            tour.ROOT, tour._STATUS = prev_root, prev_cache

    def test_home_reaches_the_menu_without_a_roll_up(self):
        """The screen still renders and the build route is still offered."""
        import contextlib
        import io
        tour = helpers.tour_module()
        prev = (tour.ROOT, tour._STATUS, tour.ask, tour.gate_banner)
        buf = io.StringIO()
        try:
            tour.ROOT = tempfile.mkdtemp(prefix="no_status_")
            tour._STATUS = ()
            tour.ask = lambda *a, **k: "q"
            tour.gate_banner = lambda: None
            with contextlib.redirect_stdout(buf):
                tour.home()
        finally:
            shutil.rmtree(tour.ROOT, ignore_errors=True)
            tour.ROOT, tour._STATUS, tour.ask, tour.gate_banner = prev
        out = buf.getvalue()
        self.assertIn("roll-up is unavailable", out)
        self.assertIn("1. Build a tour", out,
                      "the build route must survive a broken roll-up.")


class TestGateBanner(unittest.TestCase):

    def test_hook_state_reports_an_unwired_clone(self):
        """The file being committed says nothing about this clone."""
        tour = helpers.tour_module()
        prev = tour.ROOT
        try:
            tour.ROOT = tempfile.mkdtemp(prefix="no_hook_")
            wired, why = tour.hook_state()
        finally:
            shutil.rmtree(tour.ROOT, ignore_errors=True)
            tour.ROOT = prev
        self.assertFalse(wired)
        self.assertIn("pre-push", why)


if __name__ == "__main__":
    unittest.main()
