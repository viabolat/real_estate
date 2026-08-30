"""floorplan.py flags a likely floor plan or site map; it never acts on one.

reason: PROGRESS.md 4.2 approved this half of "flag-only photo order review"
on the strength of one promise -- "print them as candidates, and never
reorder or delete". These guard the scoring math AND that promise: a
source-text scan for any deletion/rename call, and a real-tempdir check that
detect() leaves the folder exactly as it found it.
"""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers


def pixels(rgb, grid):
    return bytes(rgb) * (grid * grid)


class LooksLikeFloorPlan(unittest.TestCase):

    def setUp(self):
        self.floorplan = helpers.floorplan_module()

    def test_white_low_chroma_flags(self):
        raw = pixels((250, 250, 250), 4)
        hit, (white, chroma) = self.floorplan.looks_like_floor_plan(raw, grid=4)
        self.assertTrue(hit)
        self.assertEqual(white, 1.0)
        self.assertEqual(chroma, 1.0)

    def test_high_chroma_real_room_does_not_flag(self):
        raw = pixels((200, 50, 30), 4)
        hit, _ = self.floorplan.looks_like_floor_plan(raw, grid=4)
        self.assertFalse(hit)

    def test_white_but_high_chroma_alone_does_not_flag(self):
        # every channel clears the near-white threshold, but the spread between
        # them still clears LOW_CHROMA -- confirms the AND, not an OR.
        raw = pixels((250, 235, 255), 4)
        white, chroma = self.floorplan.score(raw, grid=4)
        self.assertEqual(white, 1.0)
        self.assertLess(chroma, 1.0)
        hit, _ = self.floorplan.looks_like_floor_plan(raw, grid=4)
        self.assertFalse(hit)

    def test_short_bytes_never_flags(self):
        raw = pixels((250, 250, 250), 4)[:-3]      # one pixel short
        hit, (white, chroma) = self.floorplan.looks_like_floor_plan(raw, grid=4)
        self.assertFalse(hit)
        self.assertEqual((white, chroma), (0.0, 0.0))

    def test_empty_bytes_never_flags(self):
        hit, _ = self.floorplan.looks_like_floor_plan(b"", grid=4)
        self.assertFalse(hit)


class Detect(unittest.TestCase):

    def setUp(self):
        self.floorplan = helpers.floorplan_module()

    def test_flags_only_the_matching_photo_with_zero_subprocess_calls(self):
        raw_by_path = {
            "/x/floorplan.jpg": pixels((250, 250, 250), 4),
            "/x/kitchen.jpg": pixels((30, 140, 90), 4),
        }
        with mock.patch.object(self.floorplan.subprocess, "run",
                                side_effect=AssertionError("ffmpeg was invoked")):
            flagged = self.floorplan.detect(
                list(raw_by_path), grid=4,
                extract=lambda path, grid: raw_by_path[path])
        self.assertEqual([name for name, _reason in flagged], ["floorplan.jpg"])

    def test_no_hits_returns_empty(self):
        raw_by_path = {"/x/kitchen.jpg": pixels((30, 140, 90), 4)}
        flagged = self.floorplan.detect(
            list(raw_by_path), grid=4, extract=lambda path, grid: raw_by_path[path])
        self.assertEqual(flagged, [])

    def test_never_touches_the_folder_it_scores(self):
        tmp = tempfile.mkdtemp(prefix="floorplan_test_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        paths = [os.path.join(tmp, n) for n in ("a.jpg", "b.jpg")]
        for p in paths:
            with open(p, "wb") as f:
                f.write(b"placeholder")
        before = sorted(os.listdir(tmp))
        self.floorplan.detect(
            paths, grid=4,
            extract=lambda path, grid: pixels((250, 250, 250), grid))
        self.assertEqual(sorted(os.listdir(tmp)), before)


class ExtractRgb(unittest.TestCase):

    def setUp(self):
        self.floorplan = helpers.floorplan_module()

    def test_ffmpeg_command_shape(self):
        grid = self.floorplan.GRID
        captured = {}

        def fake_run(cmd, capture_output):
            captured["cmd"] = cmd
            return mock.Mock(returncode=0, stdout=b"\x00" * (grid * grid * 3))

        with mock.patch.object(self.floorplan.subprocess, "run", side_effect=fake_run):
            raw = self.floorplan.extract_rgb("/x/photo.jpg")
        self.assertEqual(len(raw), grid * grid * 3)
        cmd = captured["cmd"]
        self.assertIn("/x/photo.jpg", cmd)
        self.assertIn("rgb24", cmd)
        self.assertTrue(any(f"scale={grid}:{grid}:flags=neighbor" in a for a in cmd))

    def test_nonzero_returncode_yields_empty_bytes(self):
        with mock.patch.object(
                self.floorplan.subprocess, "run",
                return_value=mock.Mock(returncode=1, stdout=b"")):
            self.assertEqual(self.floorplan.extract_rgb("/x/photo.jpg"), b"")


class NeverWritesRenamesOrDeletes(unittest.TestCase):
    """The promise this module exists to keep, checked in the source text --
    not just asserted in a docstring."""

    def test_source_has_no_destructive_call(self):
        src = helpers.repo_source("floorplan.py")
        for banned in ("os.remove", "os.rename", "os.unlink",
                       "shutil.move", "shutil.rmtree", "open("):
            self.assertNotIn(banned, src, f"{banned!r} found in floorplan.py")


if __name__ == "__main__":
    unittest.main()
