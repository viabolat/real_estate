"""active_view.rebuild() -- a time-aware, active-only view of agents/.

reason: agents/ never shrinks -- every listing that has ever been photographed
stays there forever, delivered or not. needs_attention/ answers "what still
needs me right now": not archived (no tour_ cut yet) and not snoozed (contacted
and its follow-up date has not arrived). See active_view.py's own module
docstring for the three-tier rule and why built_families is injected rather
than imported.
"""
import datetime
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers


def row(brand, listing, agent="", agent_name="", agent_phone=""):
    cfg = {}
    if agent_name:
        cfg["agent_name"] = agent_name
    if agent_phone:
        cfg["agent_phone"] = agent_phone
    return (brand, listing, agent or "-", 0, None, None, "next action", {}, cfg)


def _days_ago(n):
    when = datetime.datetime.now() - datetime.timedelta(days=n)
    return when.isoformat(timespec="seconds")


class ActiveViewIsARegeneratedView(unittest.TestCase):

    def setUp(self):
        self.active_view = helpers.active_view_module()
        self.status = helpers.status_module()
        # active_view.py's own `import publish` -- not helpers.publish_module()'s
        # private copy -- is the exact module object tier() calls into, since
        # `import publish` is a plain top-level import that binds through
        # sys.modules. Patching that reference, not a separate one, is the only
        # way to make active_view.rebuild() see a temp contacted.csv.
        self.publish = self.active_view.publish
        self.tmp = tempfile.mkdtemp(prefix="active_view_test_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.agents_dir = os.path.join(self.tmp, "agents")
        self.dest_dir = os.path.join(self.tmp, "needs_attention")
        os.makedirs(self.agents_dir)

        # contacted.csv lives at a path publish.py resolves from its own ROOT
        # at import time -- point this test's copy at a temp file so marking
        # a listing "contacted" here never touches the real outreach/ tree.
        # Restored on cleanup since `publish` is a process-wide singleton other
        # test modules may share.
        original_contacted = self.publish.CONTACTED
        original_refresh = self.publish._refresh_leads_html
        self.addCleanup(setattr, self.publish, "CONTACTED", original_contacted)
        self.addCleanup(setattr, self.publish, "_refresh_leads_html", original_refresh)
        self.contacted_csv = os.path.join(self.tmp, "contacted.csv")
        self.publish.CONTACTED = self.contacted_csv
        self.publish._refresh_leads_html = lambda: None

    def make_listing(self, brand, listing, agent, tour_cut=False):
        d = os.path.join(self.agents_dir, brand, listing, agent)
        os.makedirs(d, exist_ok=True)
        if tour_cut:
            out = os.path.join(d, "out")
            os.makedirs(out, exist_ok=True)
            with open(os.path.join(out, "tour_branded.mp4"), "wb") as f:
                f.write(b"x")
        return d

    def mark_contacted(self, brand, listing, agent, marked_at):
        self.publish.record_contacted(brand, listing, agent,
                                       when=datetime.datetime.fromisoformat(marked_at))

    def rebuild(self, rows):
        self.active_view.rebuild(rows, self.status.built_families,
                                  agents_dir=self.agents_dir, dest_dir=self.dest_dir)

    def link_for(self, brand, listing, agent):
        return os.path.join(self.dest_dir, brand, listing, agent)

    def test_untouched_listing_is_active(self):
        self.make_listing("compass", "41_worcester_sq", "mary_smith")
        self.rebuild([row("compass", "41_worcester_sq", "mary_smith")])
        link = self.link_for("compass", "41_worcester_sq", "mary_smith")
        self.assertTrue(os.path.islink(link))
        self.assertTrue(os.path.samefile(
            link, os.path.join(self.agents_dir, "compass", "41_worcester_sq",
                                "mary_smith")))

    def test_contacted_one_day_ago_is_snoozed(self):
        self.make_listing("compass", "41_worcester_sq", "mary_smith")
        self.mark_contacted("compass", "41_worcester_sq", "mary_smith",
                             _days_ago(1))
        self.rebuild([row("compass", "41_worcester_sq", "mary_smith")])
        self.assertFalse(os.path.exists(
            self.link_for("compass", "41_worcester_sq", "mary_smith")))

    def test_contacted_six_days_ago_is_active_again(self):
        self.make_listing("compass", "41_worcester_sq", "mary_smith")
        self.mark_contacted("compass", "41_worcester_sq", "mary_smith",
                             _days_ago(6))
        self.rebuild([row("compass", "41_worcester_sq", "mary_smith")])
        self.assertTrue(os.path.islink(
            self.link_for("compass", "41_worcester_sq", "mary_smith")))

    def test_a_tour_cut_is_archived_even_if_recently_contacted(self):
        self.make_listing("compass", "41_worcester_sq", "mary_smith",
                           tour_cut=True)
        self.mark_contacted("compass", "41_worcester_sq", "mary_smith",
                             _days_ago(1))
        self.rebuild([row("compass", "41_worcester_sq", "mary_smith")])
        self.assertFalse(os.path.exists(
            self.link_for("compass", "41_worcester_sq", "mary_smith")))

    def test_a_listing_that_becomes_archived_drops_its_stale_link(self):
        d = self.make_listing("compass", "41_worcester_sq", "mary_smith")
        self.rebuild([row("compass", "41_worcester_sq", "mary_smith")])
        self.assertTrue(os.path.islink(
            self.link_for("compass", "41_worcester_sq", "mary_smith")))
        out = os.path.join(d, "out")
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "tour_branded.mp4"), "wb") as f:
            f.write(b"x")
        self.rebuild([row("compass", "41_worcester_sq", "mary_smith")])
        self.assertFalse(os.path.exists(
            self.link_for("compass", "41_worcester_sq", "mary_smith")))

    def test_placeholder_agent_row_is_skipped(self):
        self.rebuild([("compass", "41_worcester_sq", "-", 0, None, None,
                       "no agent folder -- rerun photos.py", {}, {})])
        self.assertFalse(os.path.isdir(self.dest_dir))

    def test_placeholder_listing_row_is_skipped(self):
        self.rebuild([("some_brand", "-", "-", 0, None, None, "no listings yet",
                        {}, {})])
        self.assertFalse(os.path.isdir(self.dest_dir))

    def test_rebuild_is_idempotent(self):
        self.make_listing("compass", "41_worcester_sq", "mary_smith")
        rows = [row("compass", "41_worcester_sq", "mary_smith")]
        self.rebuild(rows)
        self.rebuild(rows)
        self.assertTrue(os.path.islink(
            self.link_for("compass", "41_worcester_sq", "mary_smith")))


class ContactedAtAndFollowUpDate(unittest.TestCase):
    """publish.contacted_at() / publish.follow_up_date() -- the facts
    active_view.tier() derives snoozed from, kept honest against
    scraper/lead.py's own copy so leads.html and needs_attention/ can never
    compute two different follow-up windows."""

    def setUp(self):
        self.publish = helpers.publish_module()
        self.lead = helpers.scraper_module("lead")
        self.tmp = tempfile.mkdtemp(prefix="contacted_test_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.publish.CONTACTED = os.path.join(self.tmp, "contacted.csv")
        self.publish._refresh_leads_html = lambda: None

    def test_contacted_at_is_none_for_an_unknown_key(self):
        self.assertIsNone(
            self.publish.contacted_at("compass", "41_worcester_sq", "mary_smith"))

    def test_contacted_at_returns_the_recorded_timestamp(self):
        when = datetime.datetime.fromisoformat(_days_ago(2))
        self.publish.record_contacted("compass", "41_worcester_sq", "mary_smith",
                                       when=when)
        self.assertEqual(
            self.publish.contacted_at("compass", "41_worcester_sq", "mary_smith"),
            when.isoformat(timespec="seconds"))

    def test_follow_up_date_matches_leads_own_copy(self):
        marked_at = _days_ago(2)
        self.assertEqual(self.publish.follow_up_date(marked_at),
                          self.lead._follow_up_date(marked_at))


class FakeStatus:
    """A canned status.survey() -- avoids status.py's own AGENTS constant,
    which is fixed to the real repo root and cannot be pointed at a sandbox."""

    def __init__(self, rows, built_families):
        self._rows = rows
        self.built_families = built_families

    def survey(self):
        return self._rows, {}, set()


class ChooseListingPickerScope(unittest.TestCase):
    """tour.choose_listing(show_all=...) -- the picker filters through the
    same active_view.rebuild() as roll_up(), so an archived listing must stay
    reachable only behind --show-all."""

    def setUp(self):
        self.tour = helpers.tour_module()
        self.status = helpers.status_module()
        self.tmp = tempfile.mkdtemp(prefix="choose_listing_test_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.agents_dir = os.path.join(self.tmp, "agents")
        self.needs_attention_dir = os.path.join(self.tmp, "needs_attention")
        os.makedirs(self.agents_dir)

        self.active = os.path.join(self.agents_dir, "compass", "active_listing",
                                    "mary_smith")
        os.makedirs(os.path.join(self.active, "photos"), exist_ok=True)
        self.archived = os.path.join(self.agents_dir, "compass",
                                      "archived_listing", "mary_smith")
        out = os.path.join(self.archived, "out")
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "tour_branded.mp4"), "wb") as f:
            f.write(b"x")

        rows = [row("compass", "active_listing", "mary_smith"),
                row("compass", "archived_listing", "mary_smith")]
        fake_status = FakeStatus(rows, self.status.built_families)

        self.prev = (self.tour.LISTINGS_ROOT, self.tour._STATUS, self.tour.pick,
                     self.tour.ask, self.tour.active_view.AGENTS,
                     self.tour.active_view.NEEDS_ATTENTION,
                     self.tour.active_view.rebuild)
        self.tour.LISTINGS_ROOT = self.agents_dir
        self.tour._STATUS = (fake_status, None)
        self.tour.active_view.AGENTS = self.agents_dir
        self.tour.active_view.NEEDS_ATTENTION = self.needs_attention_dir
        # rebuild()'s agents_dir=/dest_dir= defaults were bound to the real
        # repo paths at def-time, when active_view.py first loaded -- patching
        # the AGENTS/NEEDS_ATTENTION module attributes above does not change
        # an already-compiled function's defaults. choose_listing() calls
        # rebuild() with no explicit dirs (correctly, for production), so the
        # only way to keep this test off the real needs_attention/ is to make
        # the sandbox dirs explicit here instead.
        real_rebuild = self.prev[6]
        self.tour.active_view.rebuild = (
            lambda rows, built_families, agents_dir=None, dest_dir=None:
            real_rebuild(rows, built_families, agents_dir=self.agents_dir,
                         dest_dir=self.needs_attention_dir))
        self.tour.ask = lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("must not prompt for free text in this test"))
        self.addCleanup(self._restore)

    def _restore(self):
        (self.tour.LISTINGS_ROOT, self.tour._STATUS, self.tour.pick,
         self.tour.ask, self.tour.active_view.AGENTS,
         self.tour.active_view.NEEDS_ATTENTION,
         self.tour.active_view.rebuild) = self.prev

    def _pick_by_value(self, target):
        def fake_pick(question, options, default=0, extra=None, auto=False):
            items = list(options) + ([extra] if extra else [])
            if target is not None:
                for value, _label in items:
                    if value == target:
                        return value
            return items[default][0]
        self.tour.pick = fake_pick

    def test_show_all_false_only_reaches_the_active_listing(self):
        self._pick_by_value(None)
        _brand, listing_dir = self.tour.choose_listing(show_all=False)
        self.assertEqual(listing_dir, self.active)

    def test_show_all_true_still_reaches_the_archived_listing(self):
        self._pick_by_value("archived_listing")
        _brand, listing_dir = self.tour.choose_listing(show_all=True)
        self.assertEqual(listing_dir, self.archived)


class HomeThreadsShowAllIntoBuildFlow(unittest.TestCase):
    """main()'s bare invocation (no --build) goes through home(), whose own
    "1. Build a tour" dispatch used to hardcode build_flow([]) -- silently
    dropping --show-all for the one usage STEPS.md/WALKTHROUGH.md document
    (`python3 tour.py --show-all`, no --build). Caught by the manual
    verification run in the plan, not by ChooseListingPickerScope above,
    which calls choose_listing() directly and never goes through home()."""

    def setUp(self):
        self.tour = helpers.tour_module()
        self.sandbox = tempfile.mkdtemp(prefix="home_show_all_")
        self.addCleanup(shutil.rmtree, self.sandbox, ignore_errors=True)
        self.prev = (self.tour.ROOT, self.tour._STATUS, self.tour.ask,
                     self.tour.gate_banner, self.tour.build_flow)
        self.tour.ROOT = self.sandbox
        self.tour._STATUS = ()
        self.tour.ask = lambda *a, **k: "1"
        self.tour.gate_banner = lambda: None
        self.calls = []
        self.tour.build_flow = lambda args, show_all=False: self.calls.append(
            (args, show_all))
        self.addCleanup(self._restore)

    def _restore(self):
        (self.tour.ROOT, self.tour._STATUS, self.tour.ask,
         self.tour.gate_banner, self.tour.build_flow) = self.prev

    def test_show_all_true_reaches_build_flow(self):
        self.tour.home(show_all=True)
        self.assertEqual(self.calls, [([], True)])

    def test_show_all_defaults_to_false(self):
        self.tour.home()
        self.assertEqual(self.calls, [([], False)])


if __name__ == "__main__":
    unittest.main()
