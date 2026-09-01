"""tour.py --publish-pending: the batch entry for publish_action()'s rung 4.

Guards the same confirm-per-listing bar publish_rung() already holds --
this only walks every listing with an unpublished sample_ cut in out/ instead
of picking one from the home screen, and must never answer its own "Publish
the sample cuts?" prompt or open a second cut for a listing that has none.
"""
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
import publish


class TestPublishPending(unittest.TestCase):

    def setUp(self):
        self.tour = helpers.tour_module()
        self.env = mock.patch.dict(os.environ, {
            "SUPABASE_URL": "https://x.supabase.co",
            "SUPABASE_SERVICE_KEY": "key"}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.dotenv = mock.patch.object(publish, "load_dotenv", lambda *a: None)
        self.dotenv.start()
        self.addCleanup(self.dotenv.stop)

    def _listing(self, root, brand, listing, agent, files):
        d = os.path.join(root, brand, listing, agent)
        out = os.path.join(d, "out")
        os.makedirs(out)
        for name in files:
            open(os.path.join(out, name), "wb").close()
        return d

    def test_a_listing_with_no_out_dir_is_not_a_candidate(self):
        with tempfile.TemporaryDirectory() as root:
            d = os.path.join(root, "acme", "1_main_st", "jane")
            os.makedirs(d)  # no out/ at all
            with mock.patch.object(self.tour, "LISTINGS_ROOT", root), \
                 mock.patch.object(publish, "LINKS", "/no/such/file.csv"):
                buf = []
                with mock.patch.object(self.tour, "say", buf.append):
                    self.tour.publish_pending()
        self.assertTrue(any("Nothing waiting" in line for line in buf))

    def test_a_delivered_listing_with_no_sample_cut_is_skipped(self):
        with tempfile.TemporaryDirectory() as root:
            self._listing(root, "acme", "1_main_st", "jane",
                          ["tour_branded.mp4"])
            with mock.patch.object(self.tour, "LISTINGS_ROOT", root), \
                 mock.patch.object(publish, "LINKS", "/no/such/file.csv"), \
                 mock.patch.object(self.tour, "publish_rung") as rung:
                self.tour.publish_pending()
        rung.assert_not_called()

    def test_an_already_published_and_swept_listing_is_skipped(self):
        with tempfile.TemporaryDirectory() as root:
            self._listing(root, "acme", "1_main_st", "jane", [])
            links = os.path.join(root, "links.csv")
            with open(links, "w") as f:
                f.write("uploaded_at,brand,listing,cut,url\n"
                        "t,acme,1_main_st,sample_branded.mp4,https://x/1\n")
            with mock.patch.object(self.tour, "LISTINGS_ROOT", root), \
                 mock.patch.object(publish, "LINKS", links), \
                 mock.patch.object(self.tour, "publish_rung") as rung:
                self.tour.publish_pending()
        rung.assert_not_called()

    def test_an_unpublished_sample_cut_is_offered_and_opens_the_branded_one(self):
        with tempfile.TemporaryDirectory() as root:
            d = self._listing(root, "acme", "1_main_st", "jane",
                              ["jane_sample_unbranded.mp4",
                               "jane_sample_branded.mp4",
                               "jane_sample_vertical.mp4"])
            opened = []
            with mock.patch.object(self.tour, "LISTINGS_ROOT", root), \
                 mock.patch.object(publish, "LINKS", "/no/such/file.csv"), \
                 mock.patch.object(self.tour.shutil, "which",
                                   lambda name: "/usr/bin/open"), \
                 mock.patch.object(self.tour.subprocess, "run",
                                   lambda cmd, **k: opened.append(cmd)), \
                 mock.patch.object(self.tour, "confirm", lambda *a, **k: False):
                self.tour.publish_pending()
        self.assertEqual(len(opened), 1)
        self.assertTrue(opened[0][-1].endswith("jane_sample_branded.mp4"),
                        opened[0])

    def test_a_no_answer_uploads_nothing(self):
        """publish_rung() still runs; declining its prompt calls publish.py
        for none of the candidates."""
        with tempfile.TemporaryDirectory() as root:
            self._listing(root, "acme", "1_main_st", "jane",
                          ["sample_branded.mp4"])
            with mock.patch.object(self.tour, "LISTINGS_ROOT", root), \
                 mock.patch.object(publish, "LINKS", "/no/such/file.csv"), \
                 mock.patch.object(self.tour, "shutil") as fake_shutil, \
                 mock.patch.object(self.tour, "confirm", lambda *a, **k: False), \
                 mock.patch.object(self.tour.subprocess, "run") as run:
                fake_shutil.which.return_value = None
                self.tour.publish_pending()
        for call in run.call_args_list:
            self.assertNotIn(self.tour.PUBLISH, call.args[0],
                             "declining the prompt must never reach publish.py")

    def test_no_hardcoded_confirm_bypass(self):
        """reason: this is the one prompt standing between a batch loop and an
        upload -- a --yes/--force here would make it a keystroke, not a rule,
        the same failure test_publish_gate.py's own gate test guards against."""
        import inspect
        src = inspect.getsource(self.tour.publish_pending)
        for flag in ("--yes", "--force", "confirm(", ):
            if flag == "confirm(":
                self.assertNotIn(flag, src,
                                 "publish_pending() must not answer the "
                                 "publish prompt itself -- publish_rung() "
                                 "owns confirm().")
            else:
                self.assertNotIn(flag, src, f"{flag} bypasses the per-listing ask")


if __name__ == "__main__":
    unittest.main()
