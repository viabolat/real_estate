"""Photo order lives in the filename prefix and nowhere else.

Guards _rules/photo-order-lives-in-the-filename-prefix.md: "Photo order lives in
the filename prefix and nowhere else",
and the three things that must all stay: the build prints the resolved order, it
warns when nothing authored it, and config.json never gains an order key.

This is the failure that already shipped -- 46_beacon_5 was delivered in CDN-hash
order. Its only symptom was the finished video.
"""
import ast
import io
import contextlib
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers

ORDER_WORDS = ("order", "sequence", "sort_order", "photo_order", "manifest",
               "playlist", "selection", "photos")


class TestOrderComesFromTheFilenames(unittest.TestCase):

    def test_main_sorts_the_photo_glob(self):
        """Sorting the filenames *is* the ordering mechanism."""
        tree = ast.parse(helpers.source())
        main = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.name == "main")
        photos = next(n for n in main.body
                      if isinstance(n, ast.Assign)
                      and getattr(n.targets[0], "id", None) == "photos")
        self.assertIsInstance(photos.value, ast.Call)
        self.assertEqual(photos.value.func.id, "sorted",
                         "the photo list is no longer sorted -- order is now "
                         "whatever the filesystem returned")

    def test_a_numbered_folder_builds_in_prefix_order(self):
        with helpers.listing(config={}) as (m, tmp):
            os.mkdir("photos")
            for name in ("03_kitchen.jpg", "01_front.jpg", "10_yard.jpg",
                         "02_hall.jpg"):
                open(os.path.join("photos", name), "wb").close()
            import glob
            photos = sorted(p for p in glob.glob("photos/*")
                            if os.path.splitext(p)[1].lower() in m.PHOTO_EXTS)
            self.assertEqual([os.path.basename(p) for p in photos],
                             ["01_front.jpg", "02_hall.jpg", "03_kitchen.jpg",
                              "10_yard.jpg"])


class TestUnauthoredOrderIsAnnounced(unittest.TestCase):
    """A folder with no prefixes still builds -- loudly, not silently."""

    def order_output(self, mod, names):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            mod.tour_order([os.path.join("photos", n) for n in names])
        return buf.getvalue()

    def test_the_resolved_order_is_printed_before_the_encode(self):
        with helpers.listing(config={}) as (m, _):
            out = self.order_output(m, ["01_front.jpg", "02_hall.jpg"])
            self.assertIn("01_front.jpg", out)
            self.assertIn("02_hall.jpg", out)

    def test_unprefixed_filenames_raise_a_warning(self):
        with helpers.listing(config={}) as (m, _):
            out = self.order_output(m, ["IMG_8842.jpg", "a3f9c2e1.jpg"])
            self.assertIn("WARNING", out)
            self.assertIn("alphabetical", out)

    def test_a_fully_numbered_folder_raises_no_warning(self):
        with helpers.listing(config={}) as (m, _):
            out = self.order_output(m, ["01_front.jpg", "02_hall.jpg"])
            self.assertNotIn("WARNING", out)

    def test_a_partly_numbered_folder_still_warns(self):
        """One stray unprefixed file is enough to shuffle the tour."""
        with helpers.listing(config={}) as (m, _):
            out = self.order_output(m, ["01_front.jpg", "IMG_8842.jpg"])
            self.assertIn("WARNING", out)


class TestConfigNeverCarriesOrder(unittest.TestCase):
    """config.json carries timing, pacing, asset paths and build state ONLY."""

    def config_keys(self):
        """Every _cfg.get("...") key make_tour reads."""
        tree = ast.parse(helpers.source())
        keys = set()
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "get"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "_cfg"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)):
                keys.add(node.args[0].value)
        return keys

    def test_no_config_key_names_an_order_or_a_selection(self):
        offenders = [k for k in self.config_keys()
                     if any(w in k for w in ORDER_WORDS)]
        self.assertEqual(offenders, [],
                         f"config.json gained an ordering key: {offenders}. "
                         "Order lives in the filename prefix and nowhere else.")

    def test_the_known_config_surface_has_not_silently_grown(self):
        """A new [cfg] key is fine -- undocumented is not. Update CLAUDE.md."""
        documented = {
            "clip_seconds", "xfade_seconds", "brand_persistent", "brand_in",
            "brand_out", "lower_third", "logo", "music", "watermark",
            "address", "agent_name", "agent_phone", "brokerage",
            "output_prefix", "card", "card_seconds", "card_style",
            "card_theme", "accent", "font", "scrim",
        }
        undocumented = self.config_keys() - documented
        self.assertEqual(undocumented, set(),
                         f"undocumented config keys: {sorted(undocumented)}. "
                         "Docs do not go stale -- add them to "
                         "_reference/config-schema.md, STEPS.md and the "
                         "module docstring in this pass.")

    def test_an_order_key_in_config_is_ignored_by_the_build(self):
        """Even if one appears in a listing's config, nothing may read it."""
        with helpers.listing(config={"photo_order": ["z.jpg", "a.jpg"]}) as (m, _):
            self.assertFalse(hasattr(m, "PHOTO_ORDER"))
            with open("config.json") as f:
                self.assertIn("photo_order", json.load(f))


if __name__ == "__main__":
    unittest.main()
