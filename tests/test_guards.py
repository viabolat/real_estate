"""Guards against the crashes and hangs found in the 2026-08-24 audit.

reason: every case here was confirmed by running it, not by reading the source.
Each one is a failure the operator could not act on -- a hang with no output, a
ZeroDivisionError minutes into a build, a report that dies on one bad file, or a
PII gate that prints "Safe to push" because it scanned nothing at all.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests.helpers import REPO, listing, status_module


class TestMusicLoopTerminates(unittest.TestCase):
    """prepare_music's loop is length = length*2 - d, fixed point at d.

    With d pinned to MUSIC_XFADE (2.0), a body of exactly 2.0s never grew and
    anything shorter ran negative, so `while length < need` never exited. The
    build hung with no error and no output. music_span() floors body at 1.0s, so
    any track under ~2s of real music reached it.
    """

    def _run(self, body, need=60.0):
        """prepare_music with ffmpeg stubbed; returns (passes, final length)."""
        with listing(config={}) as (mod, tmp):
            passes = []
            mod.run = lambda cmd: passes.append(cmd)
            mod.music_span = lambda src: (0.0, body)
            mod.duration = lambda src: body
            with contextlib.redirect_stdout(io.StringIO()):
                mod.prepare_music("music.mp3", need)
            # first run() is the trim; the rest are loop passes
            return len(passes) - 1

    def test_a_two_second_track_terminates(self):
        """body == MUSIC_XFADE was the exact fixed point: 2.0 -> 2.0 forever."""
        self.assertLess(self._run(2.0), 40,
                        "a 2.0s body did not converge -- the loop is hanging again")

    def test_a_one_second_track_terminates(self):
        """Below the fixed point the length went negative and never recovered."""
        self.assertLess(self._run(1.0), 40,
                        "a 1.0s body did not converge -- the loop is hanging again")

    def test_a_normal_track_is_unchanged(self):
        """The clamp must be invisible for any real music.

        d = min(MUSIC_XFADE, body/2), so any body >= 2*MUSIC_XFADE keeps the full
        2.0s seam. If this fails the fix has changed delivered audio.
        """
        with listing(config={}) as (mod, tmp):
            cmds = []
            mod.run = lambda cmd: cmds.append(cmd)
            mod.music_span = lambda src: (0.0, 30.0)
            mod.duration = lambda src: 30.0
            with contextlib.redirect_stdout(io.StringIO()):
                mod.prepare_music("music.mp3", 120.0)
            seams = [c for c in cmds if "-filter_complex" in c]
            self.assertTrue(seams, "a 30s track should still need looping to 120s")
            for c in seams:
                self.assertIn(f"acrossfade=d={mod.MUSIC_XFADE}",
                              c[c.index("-filter_complex") + 1],
                              "a normal track no longer uses the full crossfade")

    def test_the_loop_has_a_backstop(self):
        with open(os.path.join(REPO, "make_tour.py")) as f:
            self.assertIn("MUSIC_LOOP_MAX", f.read(),
                          "the loop lost its iteration ceiling")


class TestZeroDimensionAssets(unittest.TestCase):
    """Every fit box is min(BOX_W / aw, BOX_H / ah). A 0-byte or truncated PNG
    passes os.path.exists(), makes dimensions() return (0, 0), and divides by
    zero inside finish() -- i.e. after every clip has already been rendered."""

    def test_image_ok_rejects_what_exists_but_cannot_be_read(self):
        with listing(config={}) as (mod, tmp):
            empty = os.path.join(tmp, "empty.png")
            open(empty, "wb").close()
            self.assertTrue(os.path.exists(empty))
            self.assertFalse(mod.image_ok(empty),
                             "a 0-byte file must not count as a usable image")
            self.assertFalse(mod.image_ok(None))
            self.assertFalse(mod.image_ok("does_not_exist.png"))

    def test_image_ok_rejects_zero_dimensions(self):
        with listing(config={}) as (mod, tmp):
            p = os.path.join(tmp, "corrupt.png")
            with open(p, "wb") as f:
                f.write(b"not really a png")
            mod.dimensions = lambda path: (0, 0)
            self.assertFalse(mod.image_ok(p),
                             "dimensions() of (0, 0) must not reach a fit box")

    def test_a_broken_logo_is_skipped_not_fatal(self):
        """Branding is cosmetic: warn and drop it rather than kill the build."""
        with listing(config={}, assets=("logo.png",)) as (mod, tmp):
            cmds = []
            mod.run = lambda cmd: cmds.append(cmd)
            mod.duration = lambda path: 60.0
            mod.image_ok = lambda path: False
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                mod.finish("work_silent.mp4", None, None, "out/x.mp4",
                           branded=True, logo="logo.png")
            self.assertIn("WARNING", buf.getvalue())
            self.assertTrue(cmds, "the build should have continued without the logo")

    def test_a_broken_watermark_stops_the_build(self):
        """NOT cosmetic. Skipping it writes an unmarked sample_ cut -- the one
        file _rules/a-missing-watermark-stops-the-build.md forbids. Refuse, not degrade."""
        with listing(config={}, assets=("viabolat.png",)) as (mod, tmp):
            mod.run = lambda cmd: None
            mod.duration = lambda path: 60.0
            mod.image_ok = lambda path: False
            with self.assertRaises(SystemExit) as cm:
                with contextlib.redirect_stdout(io.StringIO()):
                    mod.finish("work_silent.mp4", None, None, "out/x.mp4",
                               branded=False, watermark="viabolat.png")
            self.assertIn("watermark", str(cm.exception).lower())

    def test_a_missing_watermark_stops_the_build_too(self):
        """A watermark that is not there is a watermark that will not render.

        reason: this used to be `use_wm = bool(watermark and exists(watermark))`
        -- a present-but-unreadable file refused, an ABSENT one was skipped in
        silence. Every config.json the scraper writes pins the path, so the hole
        only opened on folders that were never scraped: exactly the hand-placed
        ones tour.py now admits, and the bare "viabolat.png" fallback does not
        resolve from a listing folder. The result was an unwatermarked
        sample_ cut that publish.py then uploaded on the strength of its name.
        """
        with listing(config={}) as (mod, tmp):
            mod.run = lambda cmd: None
            mod.duration = lambda path: 60.0
            self.assertFalse(os.path.exists(os.path.join(tmp, "viabolat.png")))
            with self.assertRaises(SystemExit) as cm:
                with contextlib.redirect_stdout(io.StringIO()):
                    mod.finish("work_silent.mp4", None, None, "out/x.mp4",
                               branded=False, watermark="viabolat.png")
            self.assertIn("watermark", str(cm.exception).lower())

    def test_a_cut_that_asks_for_no_watermark_is_unaffected(self):
        """The refusal is scoped to the sample family. A --delivery-only run
        passes watermark=None and must build exactly as it always has."""
        with listing(config={}) as (mod, tmp):
            cmds = []
            mod.run = lambda cmd: cmds.append(cmd)
            mod.duration = lambda path: 60.0
            with contextlib.redirect_stdout(io.StringIO()):
                mod.finish("work_silent.mp4", None, None, "out/x.mp4",
                           branded=False, logo=None)
            self.assertTrue(cmds, "a delivery cut needs no watermark to build")


class TestTheWatermarkRefusalIsCheap(unittest.TestCase):
    """Knowing at second one and refusing at minute five is the repo's own
    stated failure shape -- it is what the resolution gate was fixed for.

    So the watermark is checked at preflight, before the lock, the clips and the
    stitch. finish() keeps its own check as the last gate before the pixels.
    """

    def build(self, *flags, watermark="does_not_exist.png"):
        d = tempfile.mkdtemp(prefix="wm_gate_")
        self.addCleanup(shutil.rmtree, d, True)
        os.mkdir(os.path.join(d, "photos"))
        for i in range(2):
            # reason: a real jpeg is not needed -- the refusal must land before
            # anything tries to decode these.
            open(os.path.join(d, "photos", f"0{i}_a.jpg"), "wb").close()
        with open(os.path.join(d, "config.json"), "w") as f:
            json.dump({"watermark": watermark}, f)
        r = subprocess.run(
            [sys.executable, os.path.join(REPO, "make_tour.py"),
             "--720p", "--allow-lowres", "--no-music", *flags],
            cwd=d, capture_output=True, text=True, timeout=120)
        return r, d

    def test_a_sample_build_refuses_before_taking_the_lock(self):
        r, d = self.build("--samples-only")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("REFUSING TO BUILD", r.stdout + r.stderr)
        self.assertFalse(os.path.exists(os.path.join(d, ".build.lock")),
                         "the lock was taken before the refusal")

    def test_the_refusal_leaves_no_intermediates_behind(self):
        _r, d = self.build("--samples-only")
        for leftover in ("out", "clips", "work_silent.mp4"):
            self.assertFalse(os.path.exists(os.path.join(d, leftover)),
                             f"{leftover} was written before the refusal")

    def test_a_default_build_refuses_too(self):
        """A bare run writes the sample family, so it needs the watermark."""
        r, _d = self.build()
        self.assertNotEqual(r.returncode, 0)

    def test_a_delivery_only_build_needs_no_watermark(self):
        """The scope of the refusal. Run 2 applies no watermark at all, so a
        broken one must not stop the client's paid deliverable from building."""
        r, d = self.build("--delivery-only")
        self.assertNotIn("REFUSING TO BUILD", r.stdout + r.stderr)

    def test_the_message_names_the_way_out(self):
        r, _d = self.build("--samples-only")
        out = r.stdout + r.stderr
        self.assertIn("does_not_exist.png", out)
        self.assertIn("global_assets/logos/viabolat.png", out)


class TestPhotoListingSurvivesBadEntries(unittest.TestCase):
    """A directory named 01_front.jpg was picked up by the extension filter.
    make_tour handed it to ffmpeg; status.py opened it and raised
    IsADirectoryError, killing the whole report over one bad entry."""

    def test_status_photo_stats_ignores_a_directory(self):
        st = status_module()
        with tempfile.TemporaryDirectory() as tmp:
            photos = os.path.join(tmp, "photos")
            os.makedirs(os.path.join(photos, "01_front.jpg"))
            with open(os.path.join(photos, "02_real.jpg"), "wb") as f:
                f.write(b"\xff\xd8not-a-real-jpeg")
            n, worst, best = st.photo_stats(tmp)      # must not raise
            self.assertEqual(n, 0, "unreadable entries should not be counted")

    def test_status_size_swallows_an_unreadable_path(self):
        st = status_module()
        with tempfile.TemporaryDirectory() as tmp:
            d = os.path.join(tmp, "a_directory.jpg")
            os.makedirs(d)
            self.assertIsNone(st._size(d), "_size must return None, not raise")

    def test_make_tour_filters_directories_out_of_the_order(self):
        with open(os.path.join(REPO, "make_tour.py")) as f:
            src = f.read()
        block = src[src.index('glob.glob("photos/*")'):][:400]
        self.assertIn("os.path.isfile", block,
                      "photos/* glob no longer filters out directories")


class TestPiiGateFailsClosed(unittest.TestCase):
    """The gate enumerates files via git. git() swallows a failed subprocess and
    returns [], so outside a repository it scanned nothing and printed
    'Safe to push' with exit 0 -- over a folder that may hold the lead list."""

    def test_it_refuses_outside_a_git_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            import shutil
            shutil.copy(os.path.join(REPO, "check_pii.py"), tmp)
            os.makedirs(os.path.join(tmp, "scraper"))
            with open(os.path.join(tmp, "LEAK.txt"), "w") as f:
                f.write("stand-in for a file the gate must not miss\n")
            r = subprocess.run([sys.executable, "check_pii.py"], cwd=tmp,
                               capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0,
                                "the gate passed outside a git repo")
            self.assertNotIn("Safe to push", r.stdout)

    def test_it_does_not_fail_closed_inside_the_repository(self):
        """The fail-closed guards must not fire on the real repo.

        reason: this deliberately checks for exit 2 / REFUSING TO PASS -- the new
        behaviour -- and NOT for exit 0. Asserting the repo is PII-clean here would
        make the whole unit suite red whenever a lead value legitimately turns up
        in a working file, which is check_pii.py's own job to report, loudly, on
        its own run before a push. What this guards is the opposite failure: a
        gate that refuses everything is as useless as one that passes everything.
        """
        r = subprocess.run([sys.executable, "check_pii.py"], cwd=REPO,
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 2, r.stdout)
        self.assertNotIn("REFUSING TO PASS", r.stdout)


class TestResolutionGatesDoNotDrift(unittest.TestCase):
    """status.py and scraper/photos.py hardcode the gate that
    make_tour.py derives as int(OUT_W * ZOOM_MAX). Nothing linked them, so
    changing ZOOM_MAX silently made both report a threshold the build no longer
    applies. Importing across would make the scraper depend on the builder, so
    the redundancy stays and this test is what holds it together."""

    def test_status_gates_match_make_tour(self):
        st = status_module()
        with listing(config={}) as (mod, tmp):
            self.assertEqual(st.GATE_1080P, mod.gate_min(1920),
                             "status.py's 1080p gate has drifted from make_tour")
            self.assertEqual(st.GATE_720P, mod.gate_min(1280),
                             "status.py's 720p gate has drifted from make_tour")

    def test_scraper_gates_match_make_tour(self):
        from tests.helpers import scraper_module
        zp = scraper_module("photos")
        with listing(config={}) as (mod, tmp):
            for name, out_w in (("GATE_1080P", 1920), ("GATE_720P", 1280)):
                if hasattr(zp, name):
                    self.assertEqual(getattr(zp, name), mod.gate_min(out_w),
                                     f"photos.{name} has drifted")


if __name__ == "__main__":
    unittest.main()
