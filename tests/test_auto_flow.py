"""tour.py --auto: the same interactive wizard, with auto=True answering from
config.json/brand.json alone, plus the floor-plan halt and its resume.

Guards the two constraints from CLAUDE.md this feature was built under: no
listing's sample cuts may ever exist in more than one place, and no automation
may ever delete or move a photo. Concretely:

  * auto=True on ask/confirm/pick/number must never call input() -- and
    auto=False (every existing call site) must be byte-for-byte unchanged.
  * the logo and music picks are skipped outright under auto, never guessed.
  * auto_targets() is derived from out/ on every call, the same as stage() --
    a halted listing writes nothing, so it stays a target with no state kept
    anywhere between runs.
  * auto_flow()/_auto_build_one() must never reach publish_rung() or pass
    "--draft" -- the sample_ cuts are the reviewed artifact, and publishing
    stays a manual, by-hand step.
  * --ignore-floorplan-check is read once from argv and must never land in
    what save_config()/save_state() write to disk.
"""
import ast
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers


def calls_in(fn_name, call_name):
    tree = ast.parse(helpers.repo_source("tour.py"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == fn_name)
    return [n for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name) and n.func.id == call_name]


def constants_in(fn_name):
    tree = ast.parse(helpers.repo_source("tour.py"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == fn_name)
    return {n.value for n in ast.walk(fn) if isinstance(n, ast.Constant)}


class InputPrimitivesUnderAuto(unittest.TestCase):
    """auto=True is a hard bypass -- never reaches input()."""

    def setUp(self):
        self.tour = helpers.tour_module()
        patcher = mock.patch(
            "builtins.input",
            side_effect=AssertionError("input() was called under auto=True"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_ask_returns_the_default(self):
        self.assertEqual(self.tour.ask("Q", "the default", auto=True), "the default")

    def test_confirm_returns_the_default(self):
        self.assertIs(self.tour.confirm("Q", False, auto=True), False)
        self.assertIs(self.tour.confirm("Q", True, auto=True), True)

    def test_pick_returns_the_default_item(self):
        got = self.tour.pick("Q", [("a", "A"), ("b", "B")], default=1, auto=True)
        self.assertEqual(got, "b")

    def test_number_returns_the_default(self):
        self.assertEqual(self.tour.number("Q", 4.0, 1.0, 10.0, auto=True), 4.0)


class InputPrimitivesWithoutAutoAreUnchanged(unittest.TestCase):
    """Every existing call site omits auto -- it must still read input()."""

    def setUp(self):
        self.tour = helpers.tour_module()

    def test_ask_reads_input(self):
        with mock.patch("builtins.input", return_value="typed"):
            self.assertEqual(self.tour.ask("Q", "default"), "typed")

    def test_ask_falls_back_to_default_on_blank_input(self):
        with mock.patch("builtins.input", return_value=""):
            self.assertEqual(self.tour.ask("Q", "default"), "default")

    def test_confirm_reads_input(self):
        with mock.patch("builtins.input", return_value="n"):
            self.assertIs(self.tour.confirm("Q", True), False)


class QuestionsAutoSkipsTheTwoHumanOnlyPicks(unittest.TestCase):
    """A brokerage's logo and its music bed are never guessed, even when
    global_assets/ has exactly one of each -- an unambiguous default is still
    a choice only a human should make.
    """

    def setUp(self):
        self.tour = helpers.tour_module()
        self.tmp = tempfile.mkdtemp(prefix="questions_auto_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        os.makedirs(os.path.join(self.tmp, "assets", "logos"))
        os.makedirs(os.path.join(self.tmp, "assets", "music"))
        open(os.path.join(self.tmp, "assets", "logos", "brand.png"), "wb").close()
        open(os.path.join(self.tmp, "assets", "music", "track.mp3"), "wb").close()
        self.listing_dir = os.path.join(self.tmp, "listing")
        os.makedirs(os.path.join(self.listing_dir, "photos"))
        agents = os.path.join(self.tmp, "agents")
        os.makedirs(os.path.join(agents, "acme"))
        self.prev = (self.tour.ASSETS_ROOT, self.tour.LISTINGS_ROOT)
        self.tour.ASSETS_ROOT = os.path.join(self.tmp, "assets")
        self.tour.LISTINGS_ROOT = agents
        self.addCleanup(self._restore)

    def _restore(self):
        self.tour.ASSETS_ROOT, self.tour.LISTINGS_ROOT = self.prev

    def test_logo_and_music_stay_unset(self):
        with mock.patch(
                "builtins.input",
                side_effect=AssertionError("input() was called under auto=True")):
            cfg = self.tour.questions(self.listing_dir, "acme",
                                      dict(self.tour.DEFAULTS), auto=True)
        self.assertIsNone(cfg.get("logo"))
        self.assertIsNone(cfg.get("music"))


class OfferPrefixesAutoRenamesWithoutAsking(unittest.TestCase):

    def setUp(self):
        self.tour = helpers.tour_module()
        self.tmp = tempfile.mkdtemp(prefix="offer_prefixes_auto_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        os.makedirs(os.path.join(self.tmp, "photos"))
        for name in ("b.jpg", "a.jpg"):
            open(os.path.join(self.tmp, "photos", name), "wb").close()

    def test_renames_without_a_confirm(self):
        with mock.patch(
                "builtins.input",
                side_effect=AssertionError("input() was called under auto=True")):
            self.tour.offer_prefixes(self.tmp, auto=True)
        names = sorted(os.listdir(os.path.join(self.tmp, "photos")))
        self.assertEqual(len(names), 2)
        self.assertTrue(all(n[:1].isdigit() for n in names), names)


class AutoTargets(unittest.TestCase):
    """Derived from out/ on every call -- the resume mechanism is that there
    is nothing else to derive it from.
    """

    def setUp(self):
        self.tour = helpers.tour_module()
        self.tmp = tempfile.mkdtemp(prefix="auto_targets_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.agents = os.path.join(self.tmp, "agents")
        os.makedirs(self.agents)
        self.prev_root = self.tour.LISTINGS_ROOT
        self.tour.LISTINGS_ROOT = self.agents
        self.addCleanup(setattr, self.tour, "LISTINGS_ROOT", self.prev_root)

    def make(self, brand, listing, *out_names):
        d = os.path.join(self.agents, brand, listing)
        os.makedirs(os.path.join(d, "out"), exist_ok=True)
        for n in out_names:
            open(os.path.join(d, "out", n), "wb").close()
        return d

    def test_a_listing_with_no_cuts_is_a_target(self):
        d = self.make("acme", "1_main_st")
        self.assertEqual(self.tour.auto_targets(), [("acme", d)])

    def test_a_listing_with_sample_cuts_is_excluded(self):
        self.make("acme", "1_main_st", "sample_branded.mp4",
                  "sample_unbranded.mp4", "sample_vertical.mp4")
        self.assertEqual(self.tour.auto_targets(), [])

    def test_scoped_to_one_listing(self):
        self.make("acme", "1_main_st")
        self.make("acme", "2_oak_ave")
        self.assertEqual(
            self.tour.auto_targets(scope="acme/1_main_st"),
            [("acme", os.path.join(self.agents, "acme", "1_main_st"))])

    def test_scoped_to_a_nonexistent_listing_raises(self):
        with self.assertRaises(SystemExit):
            self.tour.auto_targets(scope="acme/does_not_exist")

    def test_a_target_with_nothing_built_yet_is_unaffected_by_a_prior_call(self):
        """The whole resume mechanism: nothing about a halt is ever recorded,
        so calling auto_targets() again -- as a rerun after a manual photo
        deletion would -- finds the exact same listing, unchanged.
        """
        self.make("acme", "1_main_st")
        first = self.tour.auto_targets()
        second = self.tour.auto_targets()
        self.assertEqual(first, second)


class MainRoutesAutoToAutoFlow(unittest.TestCase):

    def test_auto_dispatches_to_auto_flow_not_build_flow(self):
        tour = helpers.tour_module()
        prev_argv = list(sys.argv)
        prev_auto, prev_build = tour.auto_flow, tour.build_flow
        calls = []
        tour.auto_flow = lambda args: calls.append(("auto", args))
        tour.build_flow = lambda args: calls.append(("build", args))
        try:
            sys.argv = ["tour.py", "--auto", "acme/1_main_st"]
            tour.main()
        finally:
            sys.argv = prev_argv
            tour.auto_flow, tour.build_flow = prev_auto, prev_build
        self.assertEqual(calls, [("auto", ["acme/1_main_st"])])


class AutoFlowNeverPublishesOrDrafts(unittest.TestCase):
    """The sample_ cuts are the reviewed artifact. Publishing and drafting stay
    manual, by-hand steps -- see the module docstring's --auto paragraph.
    """

    def test_never_calls_publish_rung(self):
        for fn in ("auto_flow", "_auto_build_one"):
            self.assertEqual(calls_in(fn, "publish_rung"), [],
                             f"{fn} must never call publish_rung")

    def test_never_passes_the_draft_flag(self):
        for fn in ("auto_flow", "_auto_build_one"):
            self.assertNotIn("--draft", constants_in(fn),
                             f"{fn} must never build a draft")


class AutoBuildOneIntegration(unittest.TestCase):
    """One listing through _auto_build_one, with the encode itself stubbed."""

    def setUp(self):
        self.tour = helpers.tour_module()
        self.tmp = tempfile.mkdtemp(prefix="auto_build_one_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.agents = os.path.join(self.tmp, "agents")
        self.listing_dir = os.path.join(self.agents, "acme", "1_main_st")
        os.makedirs(os.path.join(self.listing_dir, "photos"))
        for name in ("010_a.jpg", "020_b.jpg"):
            open(os.path.join(self.listing_dir, "photos", name), "wb").close()

        self.prev = (self.tour.LISTINGS_ROOT, self.tour.preflight,
                     self.tour.run_build, self.tour.floorplan.detect)
        self.tour.LISTINGS_ROOT = self.agents
        self.tour.preflight = lambda listing_dir, cfg: {"1080p": [], "720p": []}
        self.build_calls = []
        self.tour.run_build = lambda listing_dir, flags: (
            self.build_calls.append(list(flags)), 0)[1]
        self.addCleanup(self._restore)

    def _restore(self):
        (self.tour.LISTINGS_ROOT, self.tour.preflight, self.tour.run_build,
         self.tour.floorplan.detect) = self.prev

    def test_a_flagged_photo_halts_before_any_delivery_build(self):
        self.tour.floorplan.detect = lambda paths: [
            ("020_b.jpg", "looks like a floor plan or site map")]
        result = self.tour._auto_build_one("acme", self.listing_dir,
                                           ignore_floorplan=False)
        self.assertEqual(result, "flagged")
        self.assertEqual(self.build_calls, [["--contact-sheet"]],
                         "a flagged listing must not reach the delivery build")

    def test_a_clean_contact_sheet_proceeds_to_the_sample_build(self):
        self.tour.floorplan.detect = lambda paths: []
        result = self.tour._auto_build_one("acme", self.listing_dir,
                                           ignore_floorplan=False)
        self.assertEqual(result, "built")
        self.assertEqual(len(self.build_calls), 2)
        self.assertEqual(self.build_calls[0], ["--contact-sheet"])
        self.assertIn("--samples-only", self.build_calls[1])

    def test_ignore_floorplan_check_skips_detection_entirely(self):
        def boom(paths):
            raise AssertionError("floorplan.detect ran despite the override")
        self.tour.floorplan.detect = boom
        result = self.tour._auto_build_one("acme", self.listing_dir,
                                           ignore_floorplan=True)
        self.assertEqual(result, "built")

    def test_ignore_floorplan_check_never_reaches_saved_config_or_state(self):
        self.tour.floorplan.detect = lambda paths: []
        saved = {}
        prev_save_config, prev_save_state = self.tour.save_config, self.tour.save_state
        self.tour.save_config = lambda listing_dir, cfg: saved.setdefault(
            "config", dict(cfg))
        self.tour.save_state = lambda listing_dir, rung, cfg, preset: saved.setdefault(
            "state", dict(cfg))
        try:
            self.tour._auto_build_one("acme", self.listing_dir, ignore_floorplan=True)
        finally:
            self.tour.save_config = prev_save_config
            self.tour.save_state = prev_save_state
        blob = repr(saved).lower()
        self.assertNotIn("ignore_floorplan", blob)
        self.assertNotIn("ignore-floorplan", blob)


class AutoFlowRequiresAScopeForTheOverride(unittest.TestCase):
    """--ignore-floorplan-check with no brand/listing would silently waive the
    floor-plan check for an entire batch -- refuse rather than allow that.
    """

    def test_bare_override_with_no_scope_refuses(self):
        tour = helpers.tour_module()
        with self.assertRaises(SystemExit):
            tour.auto_flow(["--ignore-floorplan-check"])


if __name__ == "__main__":
    unittest.main()
