"""photo_quality.py scores photos for sharpness so make_tour.py can trim an
oversized photo set down to max_total_seconds. Mirrors test_floorplan.py's
shape for the scoring module itself (synthetic pixel grids, an injectable
extractor, a source-text scan for destructive calls), plus coverage of
make_tour.py's own cap arithmetic and call site.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers


def flat(rgb, grid):
    return bytes(rgb) * (grid * grid)


def checkerboard(grid):
    """A high-contrast, alternating grid -- high edge energy by construction."""
    flat_px = []
    for r in range(grid):
        for c in range(grid):
            v = 240 if (r + c) % 2 == 0 else 10
            flat_px.extend((v, v, v))
    return bytes(flat_px)


class Sharpness(unittest.TestCase):
    def setUp(self):
        self.pq = helpers.photo_quality_module()

    def test_flat_image_scores_zero(self):
        self.assertEqual(self.pq.sharpness(flat((128, 128, 128), 4), grid=4), 0.0)

    def test_checkerboard_scores_higher_than_flat(self):
        sharp = self.pq.sharpness(checkerboard(4), grid=4)
        dull = self.pq.sharpness(flat((128, 128, 128), 4), grid=4)
        self.assertGreater(sharp, dull)

    def test_short_bytes_scores_zero(self):
        raw = flat((240, 240, 240), 4)[:-3]      # one pixel short
        self.assertEqual(self.pq.sharpness(raw, grid=4), 0.0)

    def test_empty_bytes_scores_zero(self):
        self.assertEqual(self.pq.sharpness(b"", grid=4), 0.0)


class Rank(unittest.TestCase):
    def setUp(self):
        self.pq = helpers.photo_quality_module()

    def test_orders_sharpest_first_with_zero_subprocess_calls(self):
        raw_by_path = {
            "/x/sharp.jpg": checkerboard(4),
            "/x/blurry.jpg": flat((128, 128, 128), 4),
        }
        with mock.patch.object(self.pq.subprocess, "run",
                                side_effect=AssertionError("ffmpeg was invoked")):
            ranked = self.pq.rank(list(raw_by_path), grid=4,
                                   extract=lambda path, grid: raw_by_path[path])
        self.assertEqual([p for p, _ in ranked], ["/x/sharp.jpg", "/x/blurry.jpg"])


class Select(unittest.TestCase):
    def setUp(self):
        self.pq = helpers.photo_quality_module()

    def test_at_or_under_the_cap_keeps_everything_and_drops_nothing(self):
        kept, dropped = self.pq.select(["a.jpg", "b.jpg"], keep_n=5,
                                        extract=lambda p, g: b"")
        self.assertEqual(kept, ["a.jpg", "b.jpg"])
        self.assertEqual(dropped, [])

    def test_over_the_cap_keeps_the_sharpest_in_original_order(self):
        order = ["a.jpg", "b.jpg", "c.jpg", "d.jpg"]
        scores = {"a.jpg": 1.0, "b.jpg": 4.0, "c.jpg": 2.0, "d.jpg": 3.0}
        extract = lambda p, g: p.encode()
        with mock.patch.object(self.pq, "sharpness",
                                side_effect=lambda raw, grid: scores[raw.decode()]):
            kept, dropped = self.pq.select(order, keep_n=2, extract=extract)
        # the two sharpest are b (4.0) and d (3.0), restored to original order
        self.assertEqual(kept, ["b.jpg", "d.jpg"])
        # dropped, weakest first
        self.assertEqual([p for p, _ in dropped], ["a.jpg", "c.jpg"])


class NeverWritesRenamesOrDeletes(unittest.TestCase):
    """The promise this module exists to keep, checked in the source text --
    not just asserted in a docstring. Mirrors test_floorplan.py's guard."""

    def test_source_has_no_destructive_call(self):
        src = helpers.repo_source("photo_quality.py")
        for banned in ("os.remove", "os.rename", "os.unlink",
                       "shutil.move", "shutil.rmtree", "open("):
            self.assertNotIn(banned, src, f"{banned!r} found in photo_quality.py")


class MaxPhotosForAgreesWithTourRuntime(unittest.TestCase):
    """make_tour.max_photos_for() duplicates tour.runtime()'s arithmetic on
    purpose (make_tour cannot import tour, which imports make_tour) -- this
    holds the two in agreement instead of a shared import.
    """
    def setUp(self):
        self.tour = helpers.tour_module()

    def _cfg(self, card):
        return {"clip_seconds": 4.0, "xfade_seconds": 0.5,
                "card_seconds": 5.0, "card": card}

    def test_agrees_for_every_card_setting(self):
        for card in ("none", "intro", "outro", "both"):
            with helpers.listing(config={"card": card}) as (mod, _tmp):
                cap = mod.max_photos_for(90.0)
                cfg = self._cfg(card)
                self.assertLessEqual(self.tour.runtime(cap, cfg), 90.0)
                self.assertGreater(self.tour.runtime(cap + 1, cfg), 90.0)


class SelectPhotosCallSite(unittest.TestCase):
    def test_under_the_cap_is_a_no_op_and_never_scores_anything(self):
        with helpers.listing() as (mod, _tmp):
            photos = [f"{i:02d}.jpg" for i in range(1, 4)]
            with mock.patch.object(
                    mod.photo_quality, "select",
                    side_effect=AssertionError("scoring should not run")):
                kept, dropped = mod.select_photos(photos)
        self.assertEqual(kept, photos)
        self.assertEqual(dropped, [])

    def test_over_the_cap_delegates_to_photo_quality_select_with_the_right_cap(self):
        with helpers.listing(config={"max_total_seconds": 10.0}) as (mod, _tmp):
            photos = [f"{i:02d}.jpg" for i in range(1, 21)]
            cap = mod.max_photos_for(10.0)
            self.assertLess(cap, len(photos))
            fake_kept, fake_dropped = photos[:cap], [("weak.jpg", 0.5)]
            with mock.patch.object(mod.photo_quality, "select",
                                    return_value=(fake_kept, fake_dropped)) as sel:
                kept, dropped = mod.select_photos(photos)
            sel.assert_called_once_with(photos, cap)
            self.assertEqual(kept, fake_kept)
            self.assertEqual(dropped, fake_dropped)

    def test_never_yields_a_runtime_over_max_total_seconds(self):
        with helpers.listing(config={"max_total_seconds": 30.0}) as (mod, _tmp):
            photos = [f"{i:02d}.jpg" for i in range(1, 41)]
            with mock.patch.object(
                    mod.photo_quality, "select",
                    side_effect=lambda paths, keep_n: (paths[:keep_n],
                                                        [(p, 0.0) for p in paths[keep_n:]])):
                kept, _dropped = mod.select_photos(photos)
            cfg = {"clip_seconds": mod.CLIP_SECONDS, "xfade_seconds": mod.XFADE_SECONDS,
                   "card_seconds": mod.CARD_SECONDS, "card": mod.CARD}
            self.assertLessEqual(
                helpers.tour_module().runtime(len(kept), cfg), 30.0)


if __name__ == "__main__":
    unittest.main()
