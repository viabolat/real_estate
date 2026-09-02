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
  * a blank agent_phone halts the same way a flagged photo does -- checked
    before any encode -- and --ignore-missing-phone-check is the same kind of
    one-shot, scope-required override.
  * a brokerage's own mark at global_assets/logos/<brand>.png is adopted
    automatically and saved as the brand default -- unlike the ambiguous
    picker in questions(), which stays skipped under auto. Its absence halts
    the same way, with the same kind of override,
    --ignore-missing-logo-check.
"""
import ast
import json
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

    def make(self, brand, listing, agent, *out_names):
        d = os.path.join(self.agents, brand, listing, agent)
        os.makedirs(os.path.join(d, "out"), exist_ok=True)
        # reason: a real agent folder always holds a config.json --
        # scaffold() writes one and nothing ever deletes it. That is what
        # is_agent_dir() keys on, so a fixture without one is not a
        # listing the walkers would ever see. See
        # _rules/an-agent-folder-is-one-that-holds-a-config.md.
        open(os.path.join(d, "config.json"), "w").write("{}")
        for n in out_names:
            open(os.path.join(d, "out", n), "wb").close()
        return d

    def test_a_listing_with_no_cuts_is_a_target(self):
        d = self.make("acme", "1_main_st", "agent_a")
        self.assertEqual(self.tour.auto_targets(), [("acme", d)])

    def test_a_listing_with_sample_cuts_is_excluded(self):
        self.make("acme", "1_main_st", "agent_a", "sample_branded.mp4",
                  "sample_unbranded.mp4", "sample_vertical.mp4")
        self.assertEqual(self.tour.auto_targets(), [])

    def test_scoped_to_one_listing(self):
        self.make("acme", "1_main_st", "agent_a")
        self.make("acme", "2_oak_ave", "agent_b")
        self.assertEqual(
            self.tour.auto_targets(scope="acme/1_main_st"),
            [("acme", os.path.join(self.agents, "acme", "1_main_st", "agent_a"))])

    def test_scoped_to_one_agent(self):
        self.make("acme", "1_main_st", "agent_a")
        self.make("acme", "1_main_st", "agent_b")
        self.assertEqual(
            self.tour.auto_targets(scope="acme/1_main_st/agent_a"),
            [("acme", os.path.join(self.agents, "acme", "1_main_st", "agent_a"))])

    def test_scoped_to_a_nonexistent_listing_raises(self):
        with self.assertRaises(SystemExit):
            self.tour.auto_targets(scope="acme/does_not_exist")

    def test_a_legacy_listing_yields_no_agent_named_photos(self):
        """reason: _dirs() cannot tell an agent folder from the photos/, clips/
        and out/ a build writes inside one, so a listing still in the
        pre-agent-level shape reported "photos" as its agent -- and --auto
        built agents/<brand>/<listing>/photos/, found no photos/photos/, and
        reported an error. See
        _rules/an-agent-folder-is-one-that-holds-a-config.md.
        """
        d = os.path.join(self.agents, "acme", "1_main_st")
        for sub in ("photos", "clips", "out", "clips_draft", "work_text"):
            os.makedirs(os.path.join(d, sub))
        open(os.path.join(d, "config.json"), "w").write("{}")
        self.assertEqual(self.tour.agent_dirs("acme", "1_main_st"), [])
        self.assertEqual(self.tour.auto_targets(), [])

    def test_a_half_scaffolded_agent_folder_still_counts(self):
        """photos.py's scaffold() writes both; either alone is enough to name
        an agent, because a folder mid-scaffold is a listing, not a leftover."""
        base = os.path.join(self.agents, "acme", "1_main_st")
        os.makedirs(os.path.join(base, "only_photos", "photos"))
        os.makedirs(os.path.join(base, "only_config"))
        open(os.path.join(base, "only_config", "config.json"), "w").write("{}")
        self.assertEqual(self.tour.agent_dirs("acme", "1_main_st"),
                         ["only_config", "only_photos"])

    def test_a_target_with_nothing_built_yet_is_unaffected_by_a_prior_call(self):
        """The whole resume mechanism: nothing about a halt is ever recorded,
        so calling auto_targets() again -- as a rerun after a manual photo
        deletion would -- finds the exact same listing, unchanged.
        """
        self.make("acme", "1_main_st", "agent_a")
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
        # A phone and a logo are already on file here -- these tests exercise
        # the floor-plan halt, not the phone or logo ones. See
        # MissingPhoneHaltsAuto and LogoAutoAdoption below.
        open(os.path.join(self.listing_dir, "logo.png"), "wb").close()
        with open(os.path.join(self.listing_dir, "config.json"), "w") as f:
            json.dump({"agent_phone": "6175551234", "logo": "logo.png"}, f)

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


class MissingPhoneHaltsAuto(unittest.TestCase):
    """A blank agent_phone halts the same way a flagged photo does -- before
    any encode, printed rather than guessed at -- because Zillow does not
    always expose one (especially for a team listing), and a card with no way
    to reach anyone defeats the point of sending the video. See
    _auto_build_one and PROGRESS.md.
    """

    def setUp(self):
        self.tour = helpers.tour_module()
        self.tmp = tempfile.mkdtemp(prefix="missing_phone_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.agents = os.path.join(self.tmp, "agents")
        self.listing_dir = os.path.join(self.agents, "compass", "1_main_st")
        os.makedirs(os.path.join(self.listing_dir, "photos"))
        open(os.path.join(self.listing_dir, "photos", "010_a.jpg"), "wb").close()
        # No config.json at all -- agent_phone is blank, same as a fresh scrape
        # that never found one.

        self.prev = (self.tour.LISTINGS_ROOT, self.tour.preflight,
                     self.tour.run_build, self.tour.floorplan.detect)
        self.tour.LISTINGS_ROOT = self.agents
        self.tour.preflight = lambda listing_dir, cfg: {"1080p": [], "720p": []}
        self.tour.floorplan.detect = lambda paths: []
        self.build_calls = []
        self.tour.run_build = lambda listing_dir, flags: (
            self.build_calls.append(list(flags)), 0)[1]
        self.addCleanup(self._restore)

    def _restore(self):
        (self.tour.LISTINGS_ROOT, self.tour.preflight, self.tour.run_build,
         self.tour.floorplan.detect) = self.prev

    def test_blank_agent_phone_halts_before_any_build(self):
        # ignore_missing_logo=True: this fixture has no global_assets/logos/
        # sandbox of its own, and this test's concern is the phone gate, not
        # the logo one -- see LogoAutoAdoption below for that gate.
        result = self.tour._auto_build_one("compass", self.listing_dir,
                                           ignore_floorplan=False,
                                           ignore_missing_logo=True)
        self.assertEqual(result, "flagged")
        self.assertEqual(self.build_calls, [],
                         "a blank agent_phone must not reach the contact sheet")

    def test_ignore_missing_phone_check_proceeds_to_the_sample_build(self):
        result = self.tour._auto_build_one("compass", self.listing_dir,
                                           ignore_floorplan=False,
                                           ignore_missing_phone=True,
                                           ignore_missing_logo=True)
        self.assertEqual(result, "built")
        self.assertEqual(self.build_calls[0], ["--contact-sheet"])
        self.assertIn("--samples-only", self.build_calls[1])

    def test_ignore_missing_phone_check_never_reaches_saved_config_or_state(self):
        saved = {}
        prev_save_config, prev_save_state = self.tour.save_config, self.tour.save_state
        self.tour.save_config = lambda listing_dir, cfg: saved.setdefault(
            "config", dict(cfg))
        self.tour.save_state = lambda listing_dir, rung, cfg, preset: saved.setdefault(
            "state", dict(cfg))
        try:
            self.tour._auto_build_one("compass", self.listing_dir,
                                      ignore_floorplan=False,
                                      ignore_missing_phone=True,
                                      ignore_missing_logo=True)
        finally:
            self.tour.save_config = prev_save_config
            self.tour.save_state = prev_save_state
        blob = repr(saved).lower()
        self.assertNotIn("ignore_missing_phone", blob)
        self.assertNotIn("ignore-missing-phone", blob)


class LogoAutoAdoption(unittest.TestCase):
    """A brokerage's own mark at global_assets/logos/<brand>.png is not a
    guess -- unlike questions()'s picker, which asks a human to choose among
    several unrelated marks -- so --auto adopts it the moment the file
    exists and saves it as the brand default. When that fixed path does not
    exist either, and cfg["logo"] resolves to nothing else, the listing
    halts the same way a blank agent_phone does: before any encode, printed
    rather than guessed at. See _auto_build_one and
    _rules/auto-picks-up-the-brand-logo-by-slug.md.
    """

    def setUp(self):
        self.tour = helpers.tour_module()
        self.tmp = tempfile.mkdtemp(prefix="logo_auto_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.agents = os.path.join(self.tmp, "agents")
        self.listing_dir = os.path.join(self.agents, "acme", "1_main_st")
        os.makedirs(os.path.join(self.listing_dir, "photos"))
        open(os.path.join(self.listing_dir, "photos", "010_a.jpg"), "wb").close()
        with open(os.path.join(self.listing_dir, "config.json"), "w") as f:
            json.dump({"agent_phone": "6175551234"}, f)

        # mkdtemp() happens above, outside anything tour.ROOT touches, and
        # cleanup below deletes that LOCAL path -- never tour.ROOT itself --
        # the same discipline test_home_screen.py's TestRollUpDegrades uses,
        # so a failed patch can never point shutil.rmtree at the real repo.
        self.prev = (self.tour.ROOT, self.tour.LISTINGS_ROOT, self.tour.preflight,
                     self.tour.run_build, self.tour.floorplan.detect)
        self.tour.ROOT = self.tmp
        self.tour.LISTINGS_ROOT = self.agents
        self.tour.preflight = lambda listing_dir, cfg: {"1080p": [], "720p": []}
        self.tour.floorplan.detect = lambda paths: []
        self.build_calls = []
        self.tour.run_build = lambda listing_dir, flags: (
            self.build_calls.append(list(flags)), 0)[1]
        self.addCleanup(self._restore)

    def _restore(self):
        (self.tour.ROOT, self.tour.LISTINGS_ROOT, self.tour.preflight,
         self.tour.run_build, self.tour.floorplan.detect) = self.prev

    def _drop_brand_logo(self):
        d = os.path.join(self.tmp, "global_assets", "logos")
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "acme.png"), "wb").close()

    def test_a_matching_brand_logo_is_adopted_and_the_build_proceeds(self):
        self._drop_brand_logo()
        result = self.tour._auto_build_one("acme", self.listing_dir,
                                           ignore_floorplan=False)
        self.assertEqual(result, "built")
        self.assertEqual(self.build_calls[0], ["--contact-sheet"])

    def test_a_matching_brand_logo_is_saved_as_the_brand_default(self):
        self._drop_brand_logo()
        self.tour._auto_build_one("acme", self.listing_dir, ignore_floorplan=False)
        with open(os.path.join(self.agents, "acme", "brand.json")) as f:
            saved = json.load(f)
        self.assertEqual(saved.get("logo"), "global_assets/logos/acme.png")

    def test_no_matching_logo_halts_before_any_build(self):
        result = self.tour._auto_build_one("acme", self.listing_dir,
                                           ignore_floorplan=False)
        self.assertEqual(result, "flagged")
        self.assertEqual(self.build_calls, [],
                         "a missing brand logo must not reach the contact sheet")

    def test_ignore_missing_logo_check_proceeds_with_the_type_only_card(self):
        result = self.tour._auto_build_one("acme", self.listing_dir,
                                           ignore_floorplan=False,
                                           ignore_missing_logo=True)
        self.assertEqual(result, "built")
        self.assertEqual(self.build_calls[0], ["--contact-sheet"])

    def test_ignore_missing_logo_check_never_reaches_saved_config_or_state(self):
        saved = {}
        prev_save_config, prev_save_state = self.tour.save_config, self.tour.save_state
        self.tour.save_config = lambda listing_dir, cfg: saved.setdefault(
            "config", dict(cfg))
        self.tour.save_state = lambda listing_dir, rung, cfg, preset: saved.setdefault(
            "state", dict(cfg))
        try:
            self.tour._auto_build_one("acme", self.listing_dir,
                                      ignore_floorplan=False,
                                      ignore_missing_logo=True)
        finally:
            self.tour.save_config = prev_save_config
            self.tour.save_state = prev_save_state
        blob = repr(saved).lower()
        self.assertNotIn("ignore_missing_logo", blob)
        self.assertNotIn("ignore-missing-logo", blob)

    def test_an_already_resolving_logo_is_left_untouched(self):
        """A listing-local logo.png already resolves -- the brand-slug lookup
        must not override an explicit, already-working choice, and must not
        write a brand.json that was never asked for."""
        open(os.path.join(self.listing_dir, "logo.png"), "wb").close()
        with open(os.path.join(self.listing_dir, "config.json"), "w") as f:
            json.dump({"agent_phone": "6175551234", "logo": "logo.png"}, f)
        result = self.tour._auto_build_one("acme", self.listing_dir,
                                           ignore_floorplan=False)
        self.assertEqual(result, "built")
        self.assertFalse(
            os.path.exists(os.path.join(self.agents, "acme", "brand.json")),
            "an already-resolving logo must not trigger a brand save")


class AutoFlowRequiresAScopeForTheOverride(unittest.TestCase):
    """--ignore-floorplan-check with no brand/listing would silently waive the
    floor-plan check for an entire batch -- refuse rather than allow that.
    Same reasoning, same rule, for --ignore-missing-phone-check and
    --ignore-missing-logo-check.
    """

    def test_bare_override_with_no_scope_refuses(self):
        tour = helpers.tour_module()
        with self.assertRaises(SystemExit):
            tour.auto_flow(["--ignore-floorplan-check"])

    def test_bare_missing_phone_override_with_no_scope_refuses(self):
        tour = helpers.tour_module()
        with self.assertRaises(SystemExit):
            tour.auto_flow(["--ignore-missing-phone-check"])

    def test_bare_missing_logo_override_with_no_scope_refuses(self):
        tour = helpers.tour_module()
        with self.assertRaises(SystemExit):
            tour.auto_flow(["--ignore-missing-logo-check"])


class TestTheCardsTextInvalidatesTheStitch(unittest.TestCase):
    """A correction to the card's text must not take the --finish-only path.

    The outro card carries address / agent_name / agent_phone / brokerage, and it
    is baked into work_branded.mp4. --finish-only reuses that stitch whole, while
    render_lower_third() redraws the lower third on every pass -- so fixing a
    wrong phone number in config.json used to produce one cut showing the new
    number in the lower third and the old one on the card. Phone digits are the
    deliverable here; a stale one on screen is the failure this guards.

    Ids are short and non-phone-shaped on purpose -- check_pii.py matches by
    shape, not just against leads.csv (tests/README.md).
    """

    def setUp(self):
        self.tour = helpers.tour_module()
        self.d = tempfile.mkdtemp(prefix="rebuild_reason_")
        self.addCleanup(shutil.rmtree, self.d, True)
        open(os.path.join(self.d, "work_silent.mp4"), "wb").close()
        self.cfg = dict(self.tour.DEFAULTS)
        self.cfg.update({"address": "1 Test St", "agent_name": "A Team",
                         "agent_phone": "1001", "brokerage": "A Brokerage"})
        self.tour.save_state(self.d, "delivery", dict(self.cfg), "1080p")

    def reason(self, **changes):
        cfg = dict(self.cfg, **changes)
        return self.tour.rebuild_reason(self.d, cfg, "1080p", "delivery",
                                        "work_silent.mp4")

    def test_an_unchanged_config_still_takes_the_fast_path(self):
        self.assertIsNone(self.reason())

    def test_a_corrected_phone_forces_a_rebuild(self):
        self.assertEqual(self.reason(agent_phone="2002"),
                         "the card's text changed")

    def test_every_card_text_key_forces_a_rebuild(self):
        for key, value in (("address", "2 Test St"), ("agent_name", "B Team"),
                           ("agent_phone", "2002"),
                           ("brokerage", "B Brokerage")):
            with self.subTest(key=key):
                self.assertIsNotNone(self.reason(**{key: value}))

    def test_the_card_keys_are_exactly_what_render_card_draws(self):
        # reason: the two lists drifting is the whole failure mode -- a fifth
        # line added to the card with no matching key here silently returns the
        # stale-text bug. make_tour.py names them as module globals.
        with open(os.path.join(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))), "make_tour.py")) as f:
            src = f.read()
        card = src[src.index("def render_card("):src.index("def card_clip(")]
        drawn = {g for g in ("ADDRESS", "AGENT_NAME", "AGENT_PHONE", "BROKERAGE")
                 if g in card}
        self.assertEqual({k.upper() for k in self.tour.CARD_TEXT_KEYS}, drawn)

    def test_no_card_means_the_text_is_not_a_reason(self):
        self.cfg["card"] = "none"
        self.tour.save_state(self.d, "delivery", dict(self.cfg), "1080p")
        self.assertIsNone(self.reason(agent_phone="2002"))


if __name__ == "__main__":
    unittest.main()
