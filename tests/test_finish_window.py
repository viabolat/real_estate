"""Branding is held off wherever the card is on screen; the watermark is not.

Guards _rules/branding-is-held-off-under-the-card.md: "Branding is held off
wherever the card is on screen, and the
watermark is not", and "a no-card build is byte-identical to one from before
cards existed".

These run the real finish() with ffmpeg stubbed and assert on the filtergraph it
builds -- the enable= window on each overlay layer is the whole of the rule.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers

ASSETS = ("lower_third.png", "logo.png", "viabolat.png")


def layers(graph):
    """{label: enable-window-or-None} for every overlay in the filtergraph."""
    found = {}
    # reason: the enable= expression contains commas of its own -- between(t,a,b)
    # -- so the scan has to run to the next chained label or the fade, not to the
    # next comma.
    for label, rest in re.findall(
            r"\[(bp|lg|wm)\]overlay=(.*?)(?=\[ov\d|,fade)", graph):
        m = re.search(r"enable='between\(t,([\d.]+),([\d.]+)\)'", rest)
        found[label] = (float(m.group(1)), float(m.group(2))) if m else None
    return found


class TestNoCardIsUnchanged(unittest.TestCase):
    """The no-card path must produce exactly what it did before cards existed."""

    def test_persistent_branding_gets_no_window_at_all(self):
        with helpers.listing(config={}, assets=ASSETS) as (m, _):
            graph = helpers.filtergraph(helpers.capture_finish(
                m, brand="lower_third.png", logo="logo.png"))
            found = layers(graph)
            self.assertIsNone(found["bp"], "lower third gained a window")
            self.assertIsNone(found["lg"], "logo gained a window")

    def test_a_zero_card_span_is_the_same_as_no_span(self):
        with helpers.listing(config={}, assets=ASSETS) as (m, _):
            without = helpers.filtergraph(helpers.capture_finish(
                m, brand="lower_third.png", logo="logo.png"))
            with_zero = helpers.filtergraph(helpers.capture_finish(
                m, brand="lower_third.png", logo="logo.png", cards=(0.0, 0.0)))
            self.assertEqual(without, with_zero)

    def test_non_persistent_branding_uses_the_configured_window(self):
        with helpers.listing(config={"brand_persistent": False, "brand_in": 0.8,
                                     "brand_out": 6.5}, assets=ASSETS) as (m, _):
            found = layers(helpers.filtergraph(helpers.capture_finish(
                m, brand="lower_third.png")))
            self.assertEqual(found["bp"], (0.8, 6.5))


class TestBrandingIsGatedToThePhotoBody(unittest.TestCase):

    def test_persistent_branding_stops_at_the_cards(self):
        """60s cut, 5s intro + 5s outro -> branding runs 5.0 to 55.0."""
        with helpers.listing(config={}, assets=ASSETS) as (m, _):
            found = layers(helpers.filtergraph(helpers.capture_finish(
                m, brand="lower_third.png", logo="logo.png", cards=(5.0, 5.0))))
            self.assertEqual(found["bp"], (5.0, 55.0))
            self.assertEqual(found["lg"], (5.0, 55.0),
                             "the logo prints over the card's own mark")

    def test_an_intro_only_card_gates_the_head_not_the_tail(self):
        with helpers.listing(config={}, assets=ASSETS) as (m, _):
            found = layers(helpers.filtergraph(helpers.capture_finish(
                m, brand="lower_third.png", cards=(5.0, 0.0))))
            self.assertEqual(found["bp"], (5.0, 60.0))

    def test_an_outro_only_card_gates_the_tail_not_the_head(self):
        with helpers.listing(config={}, assets=ASSETS) as (m, _):
            found = layers(helpers.filtergraph(helpers.capture_finish(
                m, brand="lower_third.png", cards=(0.0, 5.0))))
            self.assertEqual(found["bp"], (0.0, 55.0))

    def test_a_non_persistent_window_is_relative_to_the_photos(self):
        """brand_in 0.8 means 0.8s into the photos, not into the video."""
        with helpers.listing(config={"brand_persistent": False, "brand_in": 0.8,
                                     "brand_out": 6.5}, assets=ASSETS) as (m, _):
            found = layers(helpers.filtergraph(helpers.capture_finish(
                m, brand="lower_third.png", cards=(5.0, 5.0))))
            self.assertEqual(found["bp"], (5.8, 11.5))

    def test_a_window_running_past_the_body_is_clamped_to_the_card(self):
        with helpers.listing(config={"brand_persistent": False, "brand_in": 0.8,
                                     "brand_out": 90.0}, assets=ASSETS) as (m, _):
            found = layers(helpers.filtergraph(helpers.capture_finish(
                m, brand="lower_third.png", cards=(5.0, 5.0))))
            self.assertEqual(found["bp"], (5.8, 55.0),
                             "the lower third ran over the outro card")


class TestWatermarkIsExemptFromTheCardGate(unittest.TestCase):
    """An unwatermarked outro card is the frame a proof gets screenshot from."""

    def test_the_watermark_has_no_window_with_a_card(self):
        with helpers.listing(config={}, assets=ASSETS) as (m, _):
            found = layers(helpers.filtergraph(helpers.capture_finish(
                m, brand="lower_third.png", logo="logo.png",
                watermark="viabolat.png", cards=(5.0, 5.0))))
            self.assertIsNone(found["wm"], "the card frames are unwatermarked")

    def test_the_watermark_survives_onto_the_unbranded_sample(self):
        with helpers.listing(config={}, assets=ASSETS) as (m, _):
            found = layers(helpers.filtergraph(helpers.capture_finish(
                m, brand="lower_third.png", logo="logo.png",
                watermark="viabolat.png", branded=False)))
            self.assertIn("wm", found)
            self.assertNotIn("bp", found, "branding leaked onto an MLS cut")
            self.assertNotIn("lg", found, "the logo leaked onto an MLS cut")

    def test_the_watermark_is_the_topmost_layer(self):
        """It must not be croppable or coverable by the lower third."""
        with helpers.listing(config={}, assets=ASSETS) as (m, _):
            graph = helpers.filtergraph(helpers.capture_finish(
                m, brand="lower_third.png", logo="logo.png",
                watermark="viabolat.png"))
            order = re.findall(r"\[(bp|lg|wm)\]overlay=", graph)
            self.assertEqual(order[-1], "wm", f"stacking order was {order}")


if __name__ == "__main__":
    unittest.main()
