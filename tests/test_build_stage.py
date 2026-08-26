"""Which run a listing is on, and which family a run is allowed to write.

Guards the two-stage build: run 1 writes the three watermarked `sample_` cuts a
client reviews, run 2 -- only after sign-off -- writes the three `tour_`
deliverables. Two rules hold that apart, and both are wiring rather than output:

  * the stage is DERIVED from out/, never recorded. No marker file, no stage key
    in config.json -- the same rule that keeps photo order in the filename prefix
    and nowhere else. A sidecar would drift the moment someone moved a cut.
  * `--samples-only` must be structurally incapable of writing a `tour_` name.
    That is the sample_/tour_ boundary expressed as build wiring, upstream of the
    boundary publish.py holds at the bucket. A regression writes an unwatermarked
    deliverable into a folder whose stage then reads "delivered" -- a valid video
    and a wrong one, with no error.
"""
import ast
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers

REPO = helpers.REPO
TOUR = helpers.tour_module()
PUBLISH = TOUR.publish

CUTS = ("tour_branded", "tour_unbranded", "tour_vertical",
        "sample_branded", "sample_unbranded", "sample_vertical")


def guarded_cuts():
    """{cuts[...] key: {(flag, expected_value)}} for every write in main().

    Walks main() carrying the enclosing `if` conditions, because the guard is
    exactly what ast.walk() -- which test_card_isolation.py uses, and must keep
    using -- cannot see. Nesting is invisible to a flat walk; here it is the
    whole point.
    """
    tree = ast.parse(helpers.source())
    main = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "main")
    found = {}

    def flag(test):
        """(name, value-that-enters-this-branch) for `if FLAG` / `if not FLAG`."""
        if isinstance(test, ast.Name):
            return test.id, True
        if (isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not)
                and isinstance(test.operand, ast.Name)):
            return test.operand.id, False
        return None

    def visit(node, guards):
        if isinstance(node, ast.If):
            f = flag(node.test)
            for stmt in node.body:
                visit(stmt, guards | ({f} if f else set()))
            for stmt in node.orelse:
                visit(stmt, guards | ({(f[0], not f[1])} if f else set()))
            return
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            # finish() names its target 4th; vertical() names it 3rd. Both are
            # cuts[...]; anything else in main() is not a cut write.
            for arg in node.args:
                if (isinstance(arg, ast.Subscript)
                        and isinstance(arg.value, ast.Name)
                        and arg.value.id == "cuts"
                        and isinstance(arg.slice, ast.Constant)
                        and node.func.id in ("finish", "vertical")):
                    found.setdefault(arg.slice.value, set()).update(guards)
        for child in ast.iter_child_nodes(node):
            visit(child, guards)

    for stmt in main.body:
        visit(stmt, frozenset())
    return found


class TestTheStageIsDerivedFromOut(unittest.TestCase):
    """out/ is the record. Nothing else may become one."""

    def stage_with(self, *names):
        with tempfile.TemporaryDirectory() as d:
            os.mkdir(os.path.join(d, "out"))
            for n in names:
                open(os.path.join(d, "out", n), "wb").close()
            return TOUR.stage(d)

    def test_an_empty_folder_is_on_the_sample_run(self):
        self.assertEqual(self.stage_with(), "sample")

    def test_no_out_directory_at_all_is_the_sample_run(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(TOUR.stage(d), "sample")

    def test_sample_cuts_alone_mean_the_delivery_run_is_next(self):
        self.assertEqual(self.stage_with(
            "sample_branded.mp4", "sample_unbranded.mp4",
            "sample_vertical.mp4"), "delivery")

    def test_any_tour_cut_means_delivered(self):
        self.assertEqual(self.stage_with(
            "sample_branded.mp4", "tour_branded.mp4"), "delivered")

    def test_the_agent_prefix_does_not_hide_the_family(self):
        """Every cut is prefixed with the agent's name. The family is still read."""
        self.assertEqual(self.stage_with("sean_obrien_sample_branded.mp4"),
                         "delivery")
        self.assertEqual(self.stage_with("sean_obrien_tour_branded.mp4"),
                         "delivered")

    def test_a_draft_is_not_a_cut(self):
        """draft.mp4 lives outside out/ precisely so it cannot count as one."""
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "draft.mp4"), "wb").close()
            self.assertEqual(TOUR.stage(d), "sample")

    def test_intermediates_in_out_do_not_count_as_cuts(self):
        self.assertEqual(self.stage_with("work_silent.mp4", "contact_sheet.png"),
                         "sample")


class TestOneOwnerOfTheFamilyBoundary(unittest.TestCase):
    """publish.family() and publishable() must never disagree."""

    def test_family_agrees_with_publishable_on_every_cut(self):
        for name in CUTS:
            f = f"{name}.mp4"
            ok, _ = PUBLISH.publishable(f)
            self.assertEqual(ok, PUBLISH.family(f) == "sample", f)

    def test_only_the_sample_family_publishes(self):
        for name in CUTS:
            self.assertEqual(PUBLISH.family(f"{name}.mp4"), name.split("_")[0])

    def test_a_non_cut_belongs_to_no_family_and_does_not_publish(self):
        for name in ("draft.mp4", "work_silent.mp4", "contact_sheet.png",
                     "sample_branded.txt"):
            self.assertIsNone(PUBLISH.family(name), name)
            self.assertFalse(PUBLISH.publishable(name)[0], name)


class TestASubsetRunCannotCrossFamilies(unittest.TestCase):
    """The boundary, read off the wiring in main()."""

    def setUp(self):
        self.guards = guarded_cuts()

    def test_every_cut_is_written_somewhere(self):
        self.assertEqual(set(self.guards), set(CUTS))

    def test_no_tour_cut_is_reachable_under_samples_only(self):
        for cut in ("tour_branded", "tour_unbranded", "tour_vertical"):
            self.assertIn(("SAMPLES_ONLY", False), self.guards[cut],
                          f"{cut} is not gated on SAMPLES_ONLY -- a proofing run "
                          "would write an unwatermarked deliverable")

    def test_no_sample_cut_is_reachable_under_delivery_only(self):
        for cut in ("sample_branded", "sample_unbranded", "sample_vertical"):
            self.assertIn(("DELIVERY_ONLY", False), self.guards[cut],
                          f"{cut} is not gated on DELIVERY_ONLY")

    def test_a_family_is_never_gated_on_the_other_familys_flag(self):
        """A tour_ cut behind DELIVERY_ONLY would vanish from a full build."""
        for cut, flag in (("tour_branded", "DELIVERY_ONLY"),
                          ("sample_branded", "SAMPLES_ONLY")):
            self.assertFalse([g for g in self.guards[cut] if g[0] == flag],
                             f"{cut} is gated on {flag}")

    def test_a_bare_run_still_builds_all_six(self):
        with helpers.listing(config={}) as (m, _):
            self.assertFalse(m.SAMPLES_ONLY)
            self.assertFalse(m.DELIVERY_ONLY)

    def test_each_flag_is_read_from_argv(self):
        for argv, sample, delivery in (
                (["make_tour.py", "--samples-only"], True, False),
                (["make_tour.py", "--delivery-only"], False, True)):
            with helpers.listing(config={}, argv=argv) as (m, _):
                self.assertEqual(m.SAMPLES_ONLY, sample)
                self.assertEqual(m.DELIVERY_ONLY, delivery)


class TestTheFlagsAreOpposites(unittest.TestCase):

    def run_with(self, *flags):
        with tempfile.TemporaryDirectory() as d:
            return subprocess.run(
                [sys.executable, os.path.join(REPO, "make_tour.py"), *flags],
                cwd=d, capture_output=True, text=True, timeout=60)

    def test_both_flags_together_exit_two(self):
        """"Build neither family" is not a request. It must not read as success."""
        r = self.run_with("--samples-only", "--delivery-only")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("--samples-only", r.stderr)

    def test_the_refusal_happens_before_any_work(self):
        """Nothing is written, and no lock is taken, before the argv is sane."""
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(
                [sys.executable, os.path.join(REPO, "make_tour.py"),
                 "--samples-only", "--delivery-only"],
                cwd=d, capture_output=True, text=True, timeout=60)
            self.assertEqual(os.listdir(d), [])


class TestTourStagesTheBuild(unittest.TestCase):
    """delivery_flags() turns a stage into the flags make_tour reads."""

    def flags(self, cuts):
        with tempfile.TemporaryDirectory() as d:
            f, _ = TOUR.delivery_flags(d, {}, "1080p", cuts=cuts)
            return f

    def test_a_sample_run_asks_for_samples_only(self):
        self.assertIn("--samples-only", self.flags("sample"))

    def test_a_delivery_run_asks_for_delivery_only(self):
        self.assertIn("--delivery-only", self.flags("delivery"))

    def test_both_passes_neither_flag(self):
        f = self.flags("both")
        self.assertNotIn("--samples-only", f)
        self.assertNotIn("--delivery-only", f)

    def test_no_run_ever_passes_both(self):
        for cuts in ("sample", "delivery", "both"):
            f = self.flags(cuts)
            self.assertFalse("--samples-only" in f and "--delivery-only" in f)

    def test_both_families_record_the_same_rung(self):
        """The rung names the stitch lineage, not the cut family.

        This is what makes run 2 cost a minute instead of six: it finds run 1's
        record unchanged and takes --finish-only off the same work_silent.mp4.
        A separate rung per family would leave run 2 with no record, forcing a
        full re-stitch of photos that have not moved.
        """
        tree = ast.parse(helpers.repo_source("tour.py"))
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "delivery_flags")
        rungs = {a.value for c in ast.walk(fn)
                 if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                 and c.func.id == "rebuild_reason"
                 for a in c.args if isinstance(a, ast.Constant)}
        self.assertIn("delivery", rungs)
        self.assertNotIn("sample", rungs)


class TestBuildChoiceKeepsEveryRouteReachable(unittest.TestCase):
    """Staging is a default, never a restriction."""

    def test_every_family_is_offered_from_every_stage(self):
        tree = ast.parse(helpers.repo_source("tour.py"))
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "build_choice")
        offered = {n.value for n in ast.walk(fn) if isinstance(n, ast.Constant)}
        for route in ("sample", "delivery", "both"):
            self.assertIn(route, offered,
                          f"{route!r} is unreachable from the build menu")


if __name__ == "__main__":
    unittest.main()
