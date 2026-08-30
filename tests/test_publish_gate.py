"""Only a watermarked cut leaves the machine.

Guards _rules/never-cross-the-sample-tour-boundary.md and
_rules/only-sample-cuts-publish.md: "Never send a sample_ file as a deliverable,
and never send a
tour_ file before sign-off." The bucket behind /preview/ is public, so the
filename gate in publish.py is the only thing standing between an unwatermarked
deliverable and a guessable URL. Also guards the remote-path collision that
the output_prefix rule already solved locally (_reference/layout.md).

No network: the gate and the path builder are pure, the HTTP call is behind them.
"""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
import publish

AGENTS = os.path.join(REPO, "agents")


class TestTheGate(unittest.TestCase):

    def test_every_tour_cut_is_refused(self):
        for name in ("tour_branded.mp4", "tour_unbranded.mp4",
                     "tour_vertical.mp4", "sean_obrien_tour_branded.mp4",
                     "sean_obrien_tour_vertical.mp4"):
            ok, why = publish.publishable(name)
            self.assertFalse(ok, f"{name} would have been published")
            self.assertIn("signed-off", why)

    def test_every_sample_cut_is_allowed(self):
        for name in ("sample_branded.mp4", "sample_unbranded.mp4",
                     "sample_vertical.mp4", "sean_obrien_sample_branded.mp4",
                     "sean_obrien_sample_vertical.mp4"):
            self.assertTrue(publish.publishable(name)[0], name)

    def test_anything_unrecognised_is_refused(self):
        """Fails closed: a name the gate does not understand does not travel."""
        for name in ("draft.mp4", "work_silent.mp4", "work_branded.mp4",
                     "contact_sheet.png", "config.json", "photos"):
            self.assertFalse(publish.publishable(name)[0], name)

    def test_the_gate_takes_no_override(self):
        """reason: a --force would make the boundary a keystroke, not a rule."""
        import inspect
        sig = inspect.signature(publish.publishable)
        self.assertEqual(len(sig.parameters), 1,
                         "publishable() grew an argument -- if that is an "
                         "override, the public bucket has no gate left")
        src = inspect.getsource(publish)
        for flag in ("--force", "--allow-tour", "--unwatermarked"):
            self.assertNotIn(flag, src, f"{flag} lifts the one rule this file has")

    def test_nothing_in_publish_deletes_a_local_file(self):
        """A public bucket must never become the only copy of a deliverable."""
        import inspect
        src = inspect.getsource(publish)
        for call in ("os.remove", "os.unlink", "shutil.rmtree"):
            self.assertNotIn(call, src, f"{call} would delete the delivery")


class TestRemotePath(unittest.TestCase):

    def test_path_is_nested_under_brand_and_listing(self):
        d = os.path.join(AGENTS, "corcoran", "46_beacon_5")
        self.assertEqual(publish.remote_path(d, "x.mp4"),
                         "corcoran/46_beacon_5/x.mp4")

    def test_two_listings_by_one_agent_do_not_collide(self):
        """reason: the flat filename is identical -- only the folder separates them."""
        name = "sean_obrien_sample_branded.mp4"
        a = publish.remote_path(os.path.join(AGENTS, "corcoran", "46_beacon_5"), name)
        b = publish.remote_path(os.path.join(AGENTS, "corcoran", "9_w_cedar"), name)
        self.assertNotEqual(a, b)

    def test_a_bare_cut_name_still_does_not_collide(self):
        """A blank agent_name leaves bare sample_branded.mp4 in every listing."""
        a = publish.remote_path(os.path.join(AGENTS, "brand_a", "l1"), "sample_branded.mp4")
        b = publish.remote_path(os.path.join(AGENTS, "brand_b", "l1"), "sample_branded.mp4")
        self.assertNotEqual(a, b)

    def test_a_folder_outside_agents_is_refused(self):
        for bad in (REPO, os.path.join(REPO, "global_assets"),
                    os.path.join(AGENTS, "corcoran")):
            with self.assertRaises(ValueError, msg=bad):
                publish.remote_path(bad, "x.mp4")

    def test_preview_url_is_absolute_and_drops_the_extension(self):
        """reason: the link is pasted into a cold email and written to links.csv,
        so it must carry the host. The .mp4 comes back from vercel.json's rewrite."""
        url = publish.preview_url("corcoran/46_beacon_5/sample_branded.mp4")
        self.assertEqual(
            url,
            "https://real-estate.viabolat.com/preview/corcoran/46_beacon_5/"
            "sample_branded")


class TestCredentials(unittest.TestCase):

    def test_missing_credentials_exit_2_not_0(self):
        """reason: check_pii.py's rule -- a gate that cannot run fails closed.
        A publish that quietly does nothing reads exactly like one that worked.
        """
        env = {k: v for k, v in os.environ.items()
               if k not in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY")}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(publish, "DOTENV", "/nonexistent/.env"), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                publish.credentials()
        self.assertEqual(cm.exception.code, 2)


    def test_the_example_placeholder_is_not_configuration(self):
        """reason: copying .env.example and filling in only the key left
        SUPABASE_URL=https://your-project-ref.supabase.co in place. It is a
        non-empty string, so it passed, and the run uploaded 90 MB at a hostname
        that cannot resolve before anything noticed.
        """
        for url, key in (
                ("https://your-project-ref.supabase.co", "realkey123"),
                ("https://real.supabase.co", "<the service_role key>"),
                ("https://YOUR-PROJECT-REF.supabase.co", "realkey123")):
            with mock.patch.dict(os.environ, {"SUPABASE_URL": url,
                                              "SUPABASE_SERVICE_KEY": key},
                                 clear=True), \
                    mock.patch.object(publish, "DOTENV", "/nonexistent/.env"), \
                    contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit, msg=url) as cm:
                    publish.credentials()
            self.assertEqual(cm.exception.code, 2)

    def test_a_real_looking_pair_is_accepted(self):
        with mock.patch.dict(os.environ, {
                "SUPABASE_URL": "https://hmfdjqebkdtkackdshta.supabase.co/",
                "SUPABASE_SERVICE_KEY": "eyJhbGciOiJIUzI1NiJ9.abc.def"},
                clear=True), \
                mock.patch.object(publish, "DOTENV", "/nonexistent/.env"):
            url, key = publish.credentials()
        self.assertEqual(url, "https://hmfdjqebkdtkackdshta.supabase.co")


class TestTooLarge(unittest.TestCase):
    """Guards _rules/an-oversized-upload-compresses-a-review-copy.md: only a
    genuine 413 EntityTooLarge is worth retrying with a smaller file."""

    def test_the_real_supabase_413_is_detected(self):
        detail = ('HTTP 400 {"statusCode":"413","error":"Payload too large",'
                   '"message":"The object exceeded the maximum allowed size",'
                   '"code":"EntityTooLarge"}')
        self.assertTrue(publish._too_large(detail))

    def test_an_auth_or_path_error_is_not_retried_as_too_large(self):
        for detail in ("HTTP 403 {\"message\":\"Invalid key\"}",
                       "HTTP 404 {\"message\":\"Bucket not found\"}",
                       "HTTP 500 internal error"):
            self.assertFalse(publish._too_large(detail), detail)


class TestCompressedCopy(unittest.TestCase):
    """No real ffmpeg here -- these check the contract around it: a missing
    binary or a failed encode reports cleanly and yields no path, and the
    context manager never leaves a file behind."""

    def test_a_missing_ffmpeg_yields_none_and_a_message(self):
        with mock.patch.object(publish.subprocess, "run",
                                side_effect=FileNotFoundError):
            with publish._compressed_copy("in.mp4", 23) as (path, detail):
                self.assertIsNone(path)
                self.assertIn("PATH", detail)

    def test_a_failed_encode_yields_none_and_the_stderr(self):
        err = subprocess.CalledProcessError(1, ["ffmpeg"], stderr="bad input\n")
        with mock.patch.object(publish.subprocess, "run", side_effect=err):
            with publish._compressed_copy("in.mp4", 23) as (path, detail):
                self.assertIsNone(path)
                self.assertIn("bad input", detail)

    def test_the_temp_file_is_gone_after_the_block_exits(self):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["path"] = cmd[-1]
            with open(cmd[-1], "wb") as f:
                f.write(b"fake mp4 bytes")

        with mock.patch.object(publish.subprocess, "run", side_effect=fake_run):
            with publish._compressed_copy("in.mp4", 23) as (path, size):
                self.assertTrue(os.path.exists(path))
                self.assertEqual(size, len(b"fake mp4 bytes"))
        self.assertFalse(os.path.exists(captured["path"]))


class TestDotenv(unittest.TestCase):

    def _write(self, body):
        f = tempfile.NamedTemporaryFile("w", suffix=".env", delete=False)
        f.write(body)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_parses_plain_quoted_and_skips_comments(self):
        path = self._write(
            "# a comment\n"
            "\n"
            "PLAIN=one\n"
            'QUOTED="two"\n'
            "SINGLE='three'\n"
            "no_equals_here\n"
            "  SPACED  =  four  \n")
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertTrue(publish.load_dotenv(path))
            self.assertEqual(os.environ["PLAIN"], "one")
            self.assertEqual(os.environ["QUOTED"], "two")
            self.assertEqual(os.environ["SINGLE"], "three")
            self.assertEqual(os.environ["SPACED"], "four")
            self.assertNotIn("no_equals_here", os.environ)

    def test_an_exported_variable_always_wins(self):
        """reason: otherwise a stale .env silently overrides the key you just set."""
        path = self._write("SUPABASE_SERVICE_KEY=from_file\n")
        with mock.patch.dict(os.environ, {"SUPABASE_SERVICE_KEY": "from_env"},
                             clear=True):
            publish.load_dotenv(path)
            self.assertEqual(os.environ["SUPABASE_SERVICE_KEY"], "from_env")

    def test_a_missing_file_is_not_an_error(self):
        self.assertFalse(publish.load_dotenv("/nonexistent/.env"))


if __name__ == "__main__":
    unittest.main()
