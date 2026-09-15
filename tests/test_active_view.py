"""active_view.rebuild() -- a time-aware, active-only view of agents/.

reason: agents/ never shrinks -- every listing that has ever been photographed
stays there forever, delivered or not. needs_attention/ answers "what still
needs me right now": not archived (no tour_ cut yet) and not snoozed (contacted
and its follow-up date has not arrived). See active_view.py's own module
docstring for the three-tier rule and why built_families is injected rather
than imported.

The tiering tests below inject a blocker that always fires, so that "is this
listing active?" -- their actual subject -- is the only thing deciding whether
a flag.txt appears. Whether a REAL blocker fires is FlagFileNamesWhatIsMissing's
subject, further down.
"""
import datetime
import json
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
        # reason: a real agent folder always holds a config.json --
        # scaffold() writes one and nothing ever deletes it. That is what
        # is_agent_dir() keys on, so a fixture without one is not a
        # listing the walkers would ever see. See
        # _rules/an-agent-folder-is-one-that-holds-a-config.md.
        open(os.path.join(d, "config.json"), "w").write("{}")
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
        return self.active_view.rebuild(
            rows, self.status.built_families, agents_dir=self.agents_dir,
            dest_dir=self.dest_dir,
            blocker=lambda *a, **kw: ("no_photos", {}))

    def link_for(self, brand, listing, agent):
        return os.path.join(self.dest_dir, brand, listing, agent,
                            self.active_view.FLAG_FILE)

    def test_untouched_listing_is_active(self):
        self.make_listing("compass", "41_worcester_sq", "mary_smith")
        active = self.rebuild([row("compass", "41_worcester_sq", "mary_smith")])
        self.assertTrue(os.path.isfile(
            self.link_for("compass", "41_worcester_sq", "mary_smith")))
        self.assertEqual(active,
                         [("compass", "41_worcester_sq", "mary_smith")])

    def test_the_tree_holds_the_file_and_nothing_else(self):
        """No symlink, no folder to work in -- the fix happens in agents/.

        reason: it used to symlink the agent folder, which meant the view was
        also somewhere you could edit FROM. Two places to do the work is one
        too many. See _rules/needs-attention-is-a-view-not-a-move.md.
        """
        self.make_listing("compass", "41_worcester_sq", "mary_smith")
        self.rebuild([row("compass", "41_worcester_sq", "mary_smith")])
        found = []
        for here, dirs, files in os.walk(self.dest_dir):
            found += [os.path.join(here, f) for f in files]
            self.assertEqual([d for d in dirs
                              if os.path.islink(os.path.join(here, d))], [])
        self.assertEqual(
            found, [self.link_for("compass", "41_worcester_sq", "mary_smith")])

    def test_an_active_listing_is_returned_even_when_nothing_blocks_it(self):
        """The picker's set and the tree are deliberately different sets.

        reason: the tree lists what is BLOCKED. A build picker fed from that
        would offer exactly the listings that cannot be built.
        """
        self.make_listing("compass", "41_worcester_sq", "mary_smith")
        rows = [row("compass", "41_worcester_sq", "mary_smith")]
        active = self.active_view.rebuild(
            rows, self.status.built_families, agents_dir=self.agents_dir,
            dest_dir=self.dest_dir, blocker=lambda *a, **kw: None)
        self.assertEqual(active,
                         [("compass", "41_worcester_sq", "mary_smith")])
        self.assertFalse(os.path.isdir(self.dest_dir))

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
        self.assertTrue(os.path.isfile(
            self.link_for("compass", "41_worcester_sq", "mary_smith")))

    def test_a_tour_cut_is_archived_even_if_recently_contacted(self):
        self.make_listing("compass", "41_worcester_sq", "mary_smith",
                           tour_cut=True)
        self.mark_contacted("compass", "41_worcester_sq", "mary_smith",
                             _days_ago(1))
        self.rebuild([row("compass", "41_worcester_sq", "mary_smith")])
        self.assertFalse(os.path.exists(
            self.link_for("compass", "41_worcester_sq", "mary_smith")))

    def test_a_listing_that_becomes_archived_drops_its_stale_flag(self):
        d = self.make_listing("compass", "41_worcester_sq", "mary_smith")
        self.rebuild([row("compass", "41_worcester_sq", "mary_smith")])
        self.assertTrue(os.path.isfile(
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
        self.assertTrue(os.path.isfile(
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


class AFollowUpIsItsOwnDraftAndItsOwnRow(unittest.TestCase):
    """contacted.csv carries one row per send, and the latest one wins.

    The shipped failure: contacted_at() returned the FIRST matching row, so a
    recorded follow-up could never move the window forward. needs_attention/
    kept resurfacing the listing, the only draft in the folder was the
    first-contact one, and three agents received a byte-identical duplicate of an
    email from two weeks earlier.
    """

    def setUp(self):
        self.publish = helpers.publish_module()
        self.tmp = tempfile.mkdtemp(prefix="followup_test_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.publish.CONTACTED = os.path.join(self.tmp, "contacted.csv")
        self.publish.LINKS = os.path.join(self.tmp, "links.csv")
        self.publish._refresh_leads_html = lambda: None
        self.key = ("compass", "41_worcester_sq", "mary_smith")

    def mark(self, days):
        self.publish.record_contacted(
            *self.key, when=datetime.datetime.fromisoformat(_days_ago(days)))

    def test_the_latest_row_wins_not_the_first(self):
        self.mark(20)
        self.mark(1)
        self.assertEqual(self.publish.contacted_at(*self.key),
                         datetime.datetime.fromisoformat(
                             _days_ago(1)).isoformat(timespec="seconds"))

    def test_a_stale_lead_is_due_a_follow_up(self):
        self.mark(20)
        self.assertTrue(self.publish.followup_due(*self.key))

    def test_a_fresh_lead_is_not(self):
        self.mark(1)
        self.assertFalse(self.publish.followup_due(*self.key))

    def test_an_uncontacted_lead_is_never_due(self):
        self.assertFalse(self.publish.followup_due(*self.key))

    def test_recording_the_follow_up_re_arms_the_window(self):
        self.mark(20)
        self.assertTrue(self.publish.followup_due(*self.key))
        self.publish.record_contacted(*self.key)
        self.assertFalse(self.publish.followup_due(*self.key))

    def test_recorded_link_returns_the_branded_url(self):
        self.publish.record_links([
            {"uploaded_at": "2026-08-26T00:00:00", "brand": "compass",
             "listing": "41_worcester_sq", "cut": "mary_smith_sample_branded.mp4",
             "url": "https://example.test/b.mp4"},
            {"uploaded_at": "2026-08-26T00:00:00", "brand": "compass",
             "listing": "41_worcester_sq", "cut": "mary_smith_sample_vertical.mp4",
             "url": "https://example.test/v.mp4"}])
        self.assertEqual(self.publish.recorded_link(*self.key),
                         "https://example.test/b.mp4")

    def test_recorded_link_survives_a_folder_renamed_to_match_the_scrape(self):
        # reason: the cut filename carries the agent_name config.json held at
        # BUILD time. Renaming a drifted folder to the scrape's name must not
        # orphan the link the agent already has.
        self.publish.record_links([
            {"uploaded_at": "2026-08-26T00:00:00", "brand": "compass",
             "listing": "41_worcester_sq",
             "cut": "mary_smith_and_team_sample_branded.mp4",
             "url": "https://example.test/b.mp4"}])
        self.assertEqual(self.publish.recorded_link(*self.key),
                         "https://example.test/b.mp4")

    def test_recorded_link_prefers_the_matching_agent_when_two_share_a_listing(self):
        self.publish.record_links([
            {"uploaded_at": "2026-08-26T00:00:00", "brand": "compass",
             "listing": "41_worcester_sq", "cut": "bob_jones_sample_branded.mp4",
             "url": "https://example.test/bob.mp4"},
            {"uploaded_at": "2026-08-26T00:00:00", "brand": "compass",
             "listing": "41_worcester_sq", "cut": "mary_smith_sample_branded.mp4",
             "url": "https://example.test/mary.mp4"}])
        self.assertEqual(self.publish.recorded_link(*self.key),
                         "https://example.test/mary.mp4")

    def test_recorded_link_is_blank_when_nothing_was_published(self):
        self.assertEqual(self.publish.recorded_link(*self.key), "")

    def test_the_follow_up_draft_is_not_the_first_contact_draft(self):
        # reason: this is the whole bug. Two files, two wordings, two names --
        # if they ever render identically, sending the follow-up is sending the
        # first email again.
        d = os.path.join(self.tmp, "listing")
        os.makedirs(d)
        with open(os.path.join(d, "config.json"), "w") as f:
            json.dump({"agent_name": "Mary Smith",
                       "address": "41 Worcester Sq"}, f)
        url = "https://example.test/b.mp4"
        first, _ = self.publish.write_draft(d, url)
        second, _ = self.publish.write_followup(d, url)
        self.assertNotEqual(first, second)
        with open(first) as f:
            a = f.read()
        with open(second) as f:
            b = f.read()
        self.assertNotEqual(a, b)
        for text in (a, b):
            self.assertIn("Mary", text)
            self.assertIn("41 Worcester Sq", text)
            self.assertIn(url, text)
            self.assertNotIn("{", text)


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
        # reason: a real agent folder always holds a config.json --
        # scaffold() writes one and nothing ever deletes it. That is what
        # is_agent_dir() keys on, so a fixture without one is not a
        # listing the walkers would ever see. See
        # _rules/an-agent-folder-is-one-that-holds-a-config.md.
        open(os.path.join(self.archived, "config.json"), "w").write("{}")
        with open(os.path.join(out, "tour_branded.mp4"), "wb") as f:
            f.write(b"x")

        # reason: the publish rung narrows the same picker to listings that
        # HAVE a sample_ cut. Sorted after both names above, so every default
        # pick in this class still lands on active_listing.
        self.sample_built = os.path.join(self.agents_dir, "compass",
                                         "sample_built_listing", "mary_smith")
        sample_out = os.path.join(self.sample_built, "out")
        os.makedirs(sample_out, exist_ok=True)
        open(os.path.join(self.sample_built, "config.json"), "w").write("{}")
        with open(os.path.join(sample_out, "mary_smith_sample_branded.mp4"),
                  "wb") as f:
            f.write(b"x")

        rows = [row("compass", "active_listing", "mary_smith"),
                row("compass", "archived_listing", "mary_smith"),
                row("compass", "sample_built_listing", "mary_smith")]
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
            lambda rows, built_families, agents_dir=None, dest_dir=None, **kw:
            real_rebuild(rows, built_families, agents_dir=self.agents_dir,
                         dest_dir=self.needs_attention_dir, **kw))
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

    def test_the_picker_does_not_read_needs_attention(self):
        """The menu survives an empty -- or deleted -- warning tree.

        reason: choose_listing() used to set root = NEEDS_ATTENTION and walk
        it. That directory lists only BLOCKED listings now, so walking it
        would offer exactly the ones that cannot be built -- and deleting it,
        which the flag.txt invites, would empty the menu. It takes
        rebuild()'s returned active set instead.
        """
        self._pick_by_value(None)
        _brand, listing_dir = self.tour.choose_listing(show_all=False)
        self.assertEqual(listing_dir, self.active)
        self.assertFalse(os.path.isdir(self.needs_attention_dir))

    def test_show_all_true_still_reaches_the_archived_listing(self):
        self._pick_by_value("archived_listing")
        _brand, listing_dir = self.tour.choose_listing(show_all=True)
        self.assertEqual(listing_dir, self.archived)

    def test_keep_narrows_the_picker_to_what_the_action_can_touch(self):
        """The publish rung's narrowing: active is the wrong set for it.

        reason: a published, contacted listing stays active while its
        follow-up is due, and its out/ was cleared by the publish that
        confirmed. Offering it from "Publish a preview link" dead-ended on
        "No sample_ cuts -- build it first". keep= filters the same set by
        what is on disk now, so only the built one is reachable.
        """
        self._pick_by_value(None)
        listing_dir = self.tour.choose_listing(
            keep=lambda k: bool(self.tour.sample_cuts(
                os.path.join(self.agents_dir, *k))))[1]
        self.assertEqual(listing_dir, self.sample_built)

    def test_keep_matching_nothing_returns_none_instead_of_an_empty_picker(self):
        """reason: the caller says what is missing in its own words -- an
        empty Brand list would offer only "+ New brand", which for the publish
        rung means scaffolding a folder that by definition has no cut."""
        self.tour.pick = lambda *a, **k: self.fail(
            "must not open a picker when nothing survives keep=")
        self.assertIsNone(self.tour.choose_listing(keep=lambda k: False))


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


class FlagFileNamesWhatIsMissing(unittest.TestCase):
    """needs_attention/<brand>/<listing>/<agent>/flag.txt -- and nothing else.

    reason: the view answered "which listings need you" and nothing else, so a
    flagged listing sat in the folder with no way to tell what it was waiting
    for short of running a build and reading the halt message. It then answered
    two questions at once -- what is blocked, and what can be picked to build --
    which are opposite sets. It answers only the first now: a warning light,
    lit while something is wrong, out when it is fixed, back on if it is not.
    See active_view.py's docstring and
    _rules/needs-attention-is-a-view-not-a-move.md.
    """

    def setUp(self):
        self.active_view = helpers.active_view_module()
        self.status = helpers.status_module()
        self.publish = self.active_view.publish
        self.tmp = tempfile.mkdtemp(prefix="active_view_flag_test_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.agents_dir = os.path.join(self.tmp, "agents")
        self.dest_dir = os.path.join(self.tmp, "needs_attention")
        os.makedirs(self.agents_dir)
        original = self.publish.CONTACTED
        self.addCleanup(setattr, self.publish, "CONTACTED", original)
        self.publish.CONTACTED = os.path.join(self.tmp, "contacted.csv")

    def rebuild(self, rows, extra=None, blocker=True):
        return self.active_view.rebuild(
            rows, self.status.built_families, agents_dir=self.agents_dir,
            dest_dir=self.dest_dir,
            blocker=self.status.blocker if blocker else None,
            scraped_keys=(), extra=extra)

    def flag_path(self, brand, listing, agent):
        return os.path.join(self.dest_dir, brand, listing, agent,
                            self.active_view.FLAG_FILE)

    def make_listing(self, brand, listing, agent, photos=0, cfg=None):
        d = os.path.join(self.agents_dir, brand, listing, agent)
        os.makedirs(os.path.join(d, "photos"), exist_ok=True)
        with open(os.path.join(d, "config.json"), "w") as f:
            json.dump(cfg or {}, f)
        return d

    def buildable_row(self, brand, listing, agent):
        """A row status.blocker() finds nothing wrong with."""
        cfg = {"logo": "logo.png", "watermark": "logo.png",
               "agent_phone": "6175551234"}
        d = self.make_listing(brand, listing, agent, cfg=cfg)
        open(os.path.join(d, "logo.png"), "wb").write(b"x")
        return (brand, listing, agent, 12, 1536, 1536, "ready to build", {}, cfg)

    def blocked_row(self, brand, listing, agent):
        """A row with no photos -- the first rung of the blocker ladder."""
        self.make_listing(brand, listing, agent)
        return (brand, listing, agent, 0, None, None, "no photos -- scrape it",
                {}, {})

    def test_a_blocked_listing_gets_the_reason_and_the_fix(self):
        self.rebuild([self.blocked_row("acme", "12_main_st", "jo_ray")])
        text = open(self.flag_path("acme", "12_main_st", "jo_ray")).read()
        self.assertIn("missing:", text)
        self.assertIn("photos/ is empty", text)
        self.assertIn("fix:", text)
        self.assertIn("scraper/run.py", text)

    def test_the_fix_is_pointed_at_agents_not_at_the_view(self):
        """The file says where the work happens, because it is not here."""
        self.rebuild([self.blocked_row("acme", "12_main_st", "jo_ray")])
        text = open(self.flag_path("acme", "12_main_st", "jo_ray")).read()
        self.assertIn("agents/", text)
        self.assertNotIn("edit this", text.lower())

    def test_a_listing_with_nothing_blocking_it_is_absent_entirely(self):
        """Not "present without a file" -- absent. That is the whole signal.

        reason: it used to be symlinked in whether or not anything was wrong,
        so the folder listed everything active and the operator still had to
        open each one to find out which needed them.
        """
        active = self.rebuild([self.buildable_row("acme", "12_main_st", "jo_ray")])
        self.assertFalse(os.path.exists(
            os.path.join(self.dest_dir, "acme")))
        self.assertEqual(active, [("acme", "12_main_st", "jo_ray")])

    def test_the_file_is_not_written_back_once_the_listing_is_fixed(self):
        self.rebuild([self.blocked_row("acme", "12_main_st", "jo_ray")])
        self.assertTrue(os.path.exists(
            self.flag_path("acme", "12_main_st", "jo_ray")))
        self.rebuild([self.buildable_row("acme", "12_main_st", "jo_ray")])
        self.assertFalse(os.path.exists(
            self.flag_path("acme", "12_main_st", "jo_ray")))

    def test_an_unfixed_listing_is_flagged_again_on_the_next_run(self):
        rows = [self.blocked_row("acme", "12_main_st", "jo_ray")]
        self.rebuild(rows)
        self.rebuild(rows)
        self.assertTrue(os.path.exists(
            self.flag_path("acme", "12_main_st", "jo_ray")))

    def test_deleting_the_whole_view_by_hand_costs_nothing(self):
        rows = [self.blocked_row("acme", "12_main_st", "jo_ray")]
        self.rebuild(rows)
        shutil.rmtree(self.dest_dir)
        self.rebuild(rows)
        self.assertTrue(os.path.exists(
            self.flag_path("acme", "12_main_st", "jo_ray")))

    def test_a_finding_the_view_cannot_derive_is_carried_in(self):
        r = self.buildable_row("acme", "12_main_st", "jo_ray")
        self.rebuild([r], extra={("acme", "12_main_st", "jo_ray"):
                                 [("2 photo(s) look like a floor plan: 04.jpg",
                                   "delete them, then rerun --auto")]})
        text = open(self.flag_path("acme", "12_main_st", "jo_ray")).read()
        self.assertIn("look like a floor plan", text)
        self.assertIn("delete them", text)

    def test_two_agents_under_one_listing_get_a_file_each(self):
        """reason: they shared one appended-to file when they shared one
        folder. They have a folder each now, so neither can erase the other
        and neither has to be read to find the other's problem."""
        self.rebuild([self.blocked_row("acme", "12_main_st", "jo_ray"),
                      self.blocked_row("acme", "12_main_st", "sam_poe")])
        for agent in ("jo_ray", "sam_poe"):
            text = open(self.flag_path("acme", "12_main_st", agent)).read()
            self.assertEqual(text.count("Written by tour.py"), 1)
            self.assertIn("photos/ is empty", text)

    def test_one_agent_blocked_does_not_flag_the_other(self):
        self.rebuild([self.blocked_row("acme", "12_main_st", "jo_ray"),
                      self.buildable_row("acme", "12_main_st", "sam_poe")])
        self.assertTrue(os.path.exists(
            self.flag_path("acme", "12_main_st", "jo_ray")))
        self.assertFalse(os.path.exists(
            os.path.join(self.dest_dir, "acme", "12_main_st", "sam_poe")))

    def test_without_a_blocker_nothing_is_written_and_the_set_still_stands(self):
        """Omitting the injection empties the tree, it does not corrupt it.

        reason: tour.py reads status.blocker through getattr() -- a guarded
        load that can come back without it. An empty warning tree understates
        the problem; a picker with no listings in it would stop the operator
        working entirely.
        """
        active = self.rebuild([self.blocked_row("acme", "12_main_st", "jo_ray")],
                              blocker=False)
        self.assertFalse(os.path.isdir(self.dest_dir))
        self.assertEqual(active, [("acme", "12_main_st", "jo_ray")])
