"""The card must never reach the MLS cut, and vertical needs two sources.

Guards _rules/the-card-never-rides-in-work-silent.md and
_rules/vertical-takes-two-sources-per-family.md: "The card never rides in
work_silent.mp4", "vertical() takes
two sources per family, and that is not redundancy", and "the watermark is
deliberately not gated on the branded flag".

These read the wiring in main() rather than encoding video, because the wiring
*is* the rule: which stitch each finish() call is handed, and which cut each
vertical() layer comes from. A regression here produces a valid video with an
agent's phone number on the MLS -- no error, no crash.
"""
import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers


def calls_in_main(func_name):
    """[ast.Call] for every func_name(...) inside main()."""
    tree = ast.parse(helpers.source())
    main = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "main")
    return [n for n in ast.walk(main)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name) and n.func.id == func_name]


def kwarg(call, name):
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def cut_name(call):
    """The out= argument of a finish() call, as the cuts[...] key."""
    target = call.args[3]
    if isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant):
        return target.slice.value
    return None


class TestUnbrandedCutsAreClean(unittest.TestCase):
    """The unbranded cuts are the MLS/IDX files. Nothing branded may reach them."""

    def setUp(self):
        self.finishes = {cut_name(c): c for c in calls_in_main("finish")
                         if cut_name(c)}
        self.assertEqual(len(self.finishes), 4,
                         "expected four finish() calls with a cuts[...] target")

    def test_unbranded_cuts_read_the_photos_only_stitch(self):
        """branded_silent carries the card. The MLS cut must not read it."""
        for cut in ("tour_unbranded", "sample_unbranded"):
            src = self.finishes[cut].args[0]
            self.assertIsInstance(src, ast.Name)
            self.assertEqual(src.id, "silent",
                             f"{cut} reads {src.id!r} -- the card-bearing stitch "
                             "would put the agent's details on the MLS")

    def test_branded_cuts_read_the_card_bearing_stitch(self):
        for cut in ("tour_branded", "sample_branded"):
            src = self.finishes[cut].args[0]
            self.assertEqual(src.id, "branded_silent", cut)

    def test_unbranded_cuts_pass_no_branding_and_no_card_span(self):
        for cut in ("tour_unbranded", "sample_unbranded"):
            call = self.finishes[cut]
            self.assertIs(kwarg(call, "branded").value, False, cut)
            self.assertIs(kwarg(call, "logo").value, None, cut)
            self.assertIsNone(kwarg(call, "cards"),
                              f"{cut} was handed a card span; it has no card")
            self.assertIsInstance(call.args[2], ast.Constant)
            self.assertIsNone(call.args[2].value,
                              f"{cut} was handed a brand plate")

    def test_branded_cuts_carry_the_card_span(self):
        """finish() gates branding to the photo body only when given cards=."""
        for cut in ("tour_branded", "sample_branded"):
            self.assertIsNotNone(kwarg(self.finishes[cut], "cards"), cut)


class TestWatermarkIsNotGatedOnBranded(unittest.TestCase):
    """The watermark is the entire reason a sample cut exists."""

    def setUp(self):
        self.finishes = {cut_name(c): c for c in calls_in_main("finish")
                         if cut_name(c)}

    def test_both_sample_cuts_get_the_watermark(self):
        for cut in ("sample_branded", "sample_unbranded"):
            self.assertIsNotNone(kwarg(self.finishes[cut], "watermark"),
                                 f"{cut} lost its proofing watermark")

    def test_neither_delivery_cut_gets_the_watermark(self):
        for cut in ("tour_branded", "tour_unbranded"):
            self.assertIsNone(kwarg(self.finishes[cut], "watermark"),
                              f"{cut} is a deliverable and must be clean")

    def test_the_unbranded_sample_is_watermarked_while_unbranded(self):
        """The exact combination the 'not gated on branded' rule protects."""
        call = self.finishes["sample_unbranded"]
        self.assertIs(kwarg(call, "branded").value, False)
        self.assertIsNotNone(kwarg(call, "watermark"))


class TestVerticalTakesTwoSources(unittest.TestCase):
    """Band from the unbranded cut, centre from the branded one."""

    def setUp(self):
        self.verticals = calls_in_main("vertical")

    def test_one_vertical_per_family(self):
        self.assertEqual(len(self.verticals), 2)

    def test_band_and_centre_come_from_different_cuts(self):
        for call in self.verticals:
            bg, fg = call.args[0], call.args[1]
            self.assertNotEqual(ast.dump(bg), ast.dump(fg),
                                "collapsed to a single input -- the lower third "
                                "reappears in the blurred band, readable")

    def test_band_is_unbranded_and_centre_is_branded(self):
        for call in self.verticals:
            bg, fg, out = (c.slice.value for c in call.args[:3])
            self.assertTrue(bg.endswith("_unbranded"), f"band from {bg}")
            self.assertTrue(fg.endswith("_branded"), f"centre from {fg}")
            self.assertTrue(out.endswith("_vertical"), out)

    def test_families_are_not_crossed(self):
        """A sample band under a tour centre would ship an unwatermarked cut."""
        for call in self.verticals:
            bg, fg, out = (c.slice.value for c in call.args[:3])
            family = out.split("_")[0]
            self.assertTrue(bg.startswith(family) and fg.startswith(family),
                            f"{out} mixes families: {bg} + {fg}")


class TestStitchesAreNamedApart(unittest.TestCase):

    def test_silent_and_branded_work_are_different_files(self):
        with helpers.listing(config={"card": "outro"}) as (m, _):
            self.assertNotEqual(m.SILENT_WORK, m.BRANDED_WORK)

    def test_a_draft_never_touches_the_delivery_stitch(self):
        with helpers.listing(config={}, argv=["make_tour.py", "--draft"]) as (m, _):
            self.assertNotEqual(m.SILENT_WORK, "work_silent.mp4")


if __name__ == "__main__":
    unittest.main()
