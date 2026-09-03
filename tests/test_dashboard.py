"""dashboard.py -- a read-only browser view of state that is already derived.

reason: the dashboard adds an HTTP surface to a project that had none, and
three things it makes newly possible have to stay impossible: a viewer that
grows a writer, a PII artifact on disk, and a tour_ cut leaving the machine
through a URL. Those are the rungs of this file. The rest pins the seven-rung
ladder as a partition, because a listing appearing under both "contacted" and
"follow-up due" is a lead that gets emailed twice.

Fixtures are synthetic throughout -- example_brokerage / 1_example_st /
a_lister, phone 1001, a_lister@example.com. check_pii.py scans this file on
every run and it is right to; see tests/README.md.
"""
import ast
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers

DASH = helpers.dashboard_module()
FAMILY = helpers.publish_module().family
SOURCE = open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "dashboard.py"), encoding="utf-8").read()

BRAND, LISTING, AGENT = "example_brokerage", "1_example_st", "a_lister"


def row(brand=BRAND, listing=LISTING, agent=AGENT, action="next action",
        agent_name="A Lister", agent_phone="1001",
        agent_email="a_lister@example.com"):
    """One status.survey() 9-tuple."""
    cfg = {"agent_name": agent_name, "agent_phone": agent_phone,
           "agent_email": agent_email, "address": "1 Example St"}
    return (brand, listing, agent, 12, 1600, 2400, action, {}, cfg)


class FakeSources:
    """Every attribute Sources binds, canned.

    reason: status.AGENTS, tour.LISTINGS_ROOT and publish.LINKS are all fixed
    to the real repo root at import time and cannot be pointed at a sandbox.
    dashboard.Sources exists so a test can hand the collector its facts, the
    same way active_view.rebuild() takes agents_dir=/dest_dir=.
    """

    def __init__(self, agents_dir, rows=(), samples=(), delivered=(),
                 published=(), contacted=(), due=(), pending=(), leads=(),
                 drift=(), unverifiable=(), orphans=(), logo_gaps=(),
                 email_gaps=(), css=""):
        # The real nesting: publish.followup_due() reads contacted_at(), so a
        # due listing is always a contacted one. A fake where the two sets are
        # already disjoint would be testing a fiction, not the ladder.
        assert set(due) <= set(contacted), "due must be a subset of contacted"
        self.agents_dir = agents_dir
        self._rows = list(rows)
        self._samples = set(samples)
        self._delivered = set(delivered)
        self._published = set(published)
        self._contacted = set(contacted)
        self._due = set(due)
        self._pending = list(pending)
        self._leads = list(leads)
        self._audit = (list(drift), list(unverifiable), list(orphans))
        self._logo_gaps = list(logo_gaps)
        self._email_gaps = list(email_gaps)
        self.css = css
        self.lead_fields = ["brand", "agent_name", "agent_phone"]
        self.family = FAMILY

    def _key(self, listing_dir):
        return tuple(os.path.normpath(listing_dir).split(os.sep)[-3:])

    def survey(self):
        return self._rows, {}, set()

    def audit(self, rows, truth, known):
        return self._audit

    def published(self, brand, listing):
        return (brand, listing) in self._published

    def contacted(self, brand, listing, agent):
        return (brand, listing, agent) in self._contacted

    def followup_due(self, brand, listing, agent):
        return (brand, listing, agent) in self._due

    def stage(self, listing_dir):
        return "delivered" if self._key(listing_dir) in self._delivered \
            else "sample"

    def sample_cuts(self, listing_dir):
        return list(self._samples) if self._key(listing_dir) in {
            (BRAND, LISTING, AGENT)} and self._samples else []

    def unimported_dumps(self):
        return self._pending

    def recorded_link(self, brand, listing, agent):
        return "https://example.com/review"

    def contacted_at(self, brand, listing, agent):
        return "2026-09-01" if (brand, listing, agent) in self._contacted \
            else None

    def follow_up_date(self, marked_at):
        return "2026-09-06"

    def brand_gaps(self, rows, agents_dir=None):
        return self._logo_gaps

    def email_gaps(self, rows, agents_dir=None):
        return self._email_gaps

    def load_leads(self):
        return self._leads


class Tree:
    """A temp agents/ tree with one real agent folder."""

    def __enter__(self):
        self.root = tempfile.mkdtemp()
        self.agents = os.path.join(self.root, "agents")
        self.out = os.path.join(self.agents, BRAND, LISTING, AGENT, "out")
        os.makedirs(self.out)
        # an agent folder is one that holds a config.json -- a fixture without
        # it is invisible to every walker in the project.
        with open(os.path.join(self.agents, BRAND, LISTING, AGENT,
                               "config.json"), "w", encoding="utf-8") as f:
            json.dump({}, f)
        return self

    def cut(self, name, data=b""):
        path = os.path.join(self.out, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def url(self, name):
        return "/media/%s/%s/%s/%s" % (BRAND, LISTING, AGENT, name)

    def __exit__(self, *exc):
        shutil.rmtree(self.root, ignore_errors=True)


class TheModuleHasNoImportTimeSideEffects(unittest.TestCase):
    """Importing must bind no socket, open no tab and parse no argv.

    reason: tour.py imports it from inside dashboard_action(), status.py is
    loaded lazily by Sources, and check_pii.py imports nothing -- but a module
    that reached the network or argv at import would make every one of those
    a live action instead of a lookup.
    """

    def test_the_module_body_calls_nothing(self):
        body = ast.parse(SOURCE).body
        calls = [n for n in body
                 if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)]
        self.assertEqual(calls, [])

    def test_argparse_and_webbrowser_live_inside_functions(self):
        tree = ast.parse(SOURCE)
        top = {a.name for n in tree.body if isinstance(n, ast.Import)
               for a in n.names}
        self.assertNotIn("argparse", top)
        self.assertNotIn("webbrowser", top)

    def test_the_main_guard_calls_only_main(self):
        for node in ast.parse(SOURCE).body:
            if isinstance(node, ast.If) and ast.dump(node.test).count(
                    "__name__"):
                names = {n.func.id for n in ast.walk(node)
                         if isinstance(n, ast.Call)
                         and isinstance(n.func, ast.Name)}
                self.assertEqual(names, {"main"})
                return
        self.fail("no __main__ guard")


class TheRungLadderIsAPartition(unittest.TestCase):
    """Exactly one rung per listing, ordered highest first.

    reason: publish.followup_due() already IMPLIES contacted -- it reads
    contacted_at() and compares against FOLLOW_UP_DAYS. Rendered as two
    independent filters, every due listing would appear twice: once under a
    heading that means "leave it alone" and once under one that means "act".
    That is the duplicate-send shape a-follow-up-is-its-own-draft-and-its-own-
    row.md already records. The ordering is what makes it a partition.
    """

    def test_every_combination_yields_exactly_one_rung(self):
        seen = set()
        for delivered in (0, 1):
            for contacted in (0, 1):
                for due in (0, 1):
                    if due and not contacted:
                        continue        # the real sets are nested
                    for published in (0, 1):
                        for sample in (0, 1):
                            n = DASH.rung(delivered, due, contacted,
                                          published, sample)
                            self.assertIn(n, range(2, 8))
                            seen.add(n)
        self.assertEqual(seen, {2, 3, 4, 5, 6, 7})

    def test_a_followup_due_listing_is_rung_6_and_never_rung_5(self):
        self.assertEqual(DASH.rung(False, True, True, True, True), 6)

    def test_delivered_outranks_everything(self):
        self.assertEqual(DASH.rung(True, True, True, True, True), 7)

    def test_contacted_without_a_published_link_still_reads_5(self):
        self.assertEqual(DASH.rung(False, False, True, False, False), 5)

    def test_nothing_built_is_rung_2(self):
        self.assertEqual(DASH.rung(False, False, False, False, False), 2)

    def test_collect_places_a_due_listing_in_6_and_not_5(self):
        with Tree() as t:
            src = FakeSources(t.agents, rows=[row()],
                              contacted=[(BRAND, LISTING, AGENT)],
                              due=[(BRAND, LISTING, AGENT)])
            data = DASH.collect(src)
            self.assertEqual(len(data["rungs"][6]), 1)
            self.assertEqual(data["rungs"][5], [])

    def test_an_unimported_dump_is_rung_1_and_nowhere_else(self):
        with Tree() as t:
            src = FakeSources(t.agents, rows=[row()],
                              pending=[("dump.txt", BRAND, LISTING, AGENT)])
            data = DASH.collect(src)
            self.assertEqual(len(data["rungs"][1]), 1)
            self.assertEqual(sum(len(v) for v in data["rungs"].values()), 2)


class TheRungLadderDegradesRatherThanCrashes(unittest.TestCase):
    """status._publish is loaded guarded and may be None; leads.csv may be
    absent. One broken source must cost a field, never the page."""

    def test_a_raising_source_falls_through_to_ready_to_build(self):
        def boom(*a):
            raise RuntimeError("no publish")

        with Tree() as t:
            src = FakeSources(t.agents, rows=[row()])
            src.published = src.contacted = src.followup_due = boom
            src.load_leads = boom
            data = DASH.collect(src)
            self.assertEqual(len(data["rungs"][2]), 1)
            self.assertEqual(data["leads"], [])

    def test_a_survey_that_fails_renders_an_empty_page(self):
        with Tree() as t:
            src = FakeSources(t.agents)
            src.survey = lambda: 1 / 0
            data = DASH.collect(src)
            self.assertEqual(sum(len(v) for v in data["rungs"].values()), 0)
            self.assertIn("Listings (0)", DASH.render(data))


class TheRangeParser(unittest.TestCase):
    """RFC 7233, one range. A malformed header is ignored and the whole file
    served; only a well-formed set that cannot be satisfied earns a 416."""

    def test_absent_or_foreign_units_serve_the_whole_file(self):
        for header in (None, "", "items=0-1", "bytes 0-1", "garbage"):
            self.assertIsNone(DASH.parse_range(header, 500), header)

    def test_a_closed_range(self):
        self.assertEqual(DASH.parse_range("bytes=0-99", 500), (0, 99))

    def test_an_open_ended_range(self):
        self.assertEqual(DASH.parse_range("bytes=100-", 500), (100, 499))

    def test_a_suffix_range(self):
        self.assertEqual(DASH.parse_range("bytes=-100", 500), (400, 499))

    def test_a_suffix_longer_than_the_file_clamps_to_the_start(self):
        self.assertEqual(DASH.parse_range("bytes=-900", 500), (0, 499))

    def test_the_last_byte_is_clamped(self):
        self.assertEqual(DASH.parse_range("bytes=0-999999", 500), (0, 499))

    def test_a_start_past_the_end_is_unsatisfiable(self):
        self.assertIs(DASH.parse_range("bytes=500-", 500), DASH.UNSATISFIABLE)

    def test_a_zero_length_suffix_is_unsatisfiable(self):
        self.assertIs(DASH.parse_range("bytes=-0", 500), DASH.UNSATISFIABLE)

    def test_an_empty_file_satisfies_nothing(self):
        for header in ("bytes=0-", "bytes=0-9", "bytes=-1"):
            self.assertIs(DASH.parse_range(header, 0), DASH.UNSATISFIABLE,
                          header)

    def test_multi_range_is_ignored_rather_than_refused(self):
        self.assertIsNone(DASH.parse_range("bytes=0-1,5-6", 500))

    def test_a_non_integer_is_ignored(self):
        for header in ("bytes=a-b", "bytes=-", "bytes="):
            self.assertIsNone(DASH.parse_range(header, 500), header)


class TheMediaGateRefusesATourCut(unittest.TestCase):
    """publish.family() is asked before the filesystem is touched.

    reason: only-sample-cuts-publish.md makes family() the single owner of the
    boundary, and a local URL becomes a publishing boundary the moment it is
    pasted or the screen is shared. Asking first also means a tour_ request is
    403 whether or not the file is there, so the 403-vs-404 difference never
    leaks which deliverables exist.
    """

    def test_a_sample_cut_resolves(self):
        with Tree() as t:
            t.cut("sample_branded.mp4", b"x")
            code, full = DASH.resolve_media(t.url("sample_branded.mp4"),
                                            t.agents, FAMILY)
            self.assertEqual(code, 200)
            self.assertTrue(os.path.isfile(full))

    def test_a_tour_cut_that_exists_is_refused(self):
        with Tree() as t:
            t.cut("tour_branded.mp4", b"x")
            self.assertEqual(DASH.resolve_media(t.url("tour_branded.mp4"),
                                                t.agents, FAMILY)[0], 403)

    def test_a_tour_cut_that_does_not_exist_is_403_not_404(self):
        with Tree() as t:
            self.assertEqual(DASH.resolve_media(t.url("tour_branded.mp4"),
                                                t.agents, FAMILY)[0], 403)

    def test_the_agent_prefixed_infix_form_is_refused_too(self):
        with Tree() as t:
            t.cut("a_lister_tour_branded.mp4", b"x")
            self.assertEqual(DASH.resolve_media(
                t.url("a_lister_tour_branded.mp4"), t.agents, FAMILY)[0], 403)

    def test_anything_that_is_not_a_cut_is_refused(self):
        with Tree() as t:
            for name in ("config.json", "01_front.jpg", "outreach_draft.txt"):
                self.assertEqual(DASH.resolve_media(t.url(name), t.agents,
                                                    FAMILY)[0], 403, name)

    def test_the_module_never_tests_the_prefix_itself(self):
        code = "\n".join(SOURCE.split('"""')[2:])   # past the module docstring
        self.assertNotIn('"tour_"', code)
        self.assertNotIn('"sample_"', code)


class TheMediaGateRefusesTraversal(unittest.TestCase):
    """realpath against the agents/ base, and the separator matters."""

    def test_dot_dot_is_refused(self):
        with Tree() as t:
            self.assertEqual(DASH.resolve_media(
                "/media/../../../etc/passwd", t.agents, FAMILY)[0], 403)

    def test_percent_encoded_dot_dot_is_refused(self):
        with Tree() as t:
            self.assertEqual(DASH.resolve_media(
                "/media/a/b/c/%2e%2e%2f%2e%2e%2fsample_x.mp4",
                t.agents, FAMILY)[0], 403)

    def test_an_encoded_separator_cannot_smuggle_a_segment(self):
        with Tree() as t:
            self.assertEqual(DASH.resolve_media(
                "/media/a/b/c%2f..%2f..%2fd/sample_x.mp4",
                t.agents, FAMILY)[0], 403)

    def test_a_symlink_out_of_the_tree_is_refused(self):
        with Tree() as t:
            outside = os.path.join(t.root, "secret.mp4")
            with open(outside, "wb") as f:
                f.write(b"x")
            link = os.path.join(t.out, "sample_branded.mp4")
            try:
                os.symlink(outside, link)
            except (OSError, NotImplementedError):
                self.skipTest("no symlinks here")
            # reason: normpath would pass this. realpath resolves the link and
            # lands outside agents/, which is the whole reason it is used.
            self.assertEqual(DASH.resolve_media(t.url("sample_branded.mp4"),
                                                t.agents, FAMILY)[0], 403)

    def test_a_sibling_directory_does_not_pass_as_the_base(self):
        with Tree() as t:
            evil = t.agents + "_evil"
            os.makedirs(os.path.join(evil, "out"))
            with open(os.path.join(evil, "out", "sample_x.mp4"), "wb") as f:
                f.write(b"x")
            # bare startswith(base) would admit agents_evil/; base + os.sep
            # is what refuses it.
            self.assertEqual(DASH.resolve_media(
                "/media/../agents_evil/out/sample_x.mp4",
                t.agents, FAMILY)[0], 403)

    def test_the_wrong_depth_is_not_found(self):
        with Tree() as t:
            self.assertEqual(DASH.resolve_media(
                "/media/a/b/sample_x.mp4", t.agents, FAMILY)[0], 404)

    def test_a_missing_sample_cut_is_404(self):
        with Tree() as t:
            self.assertEqual(DASH.resolve_media(t.url("sample_gone.mp4"),
                                                t.agents, FAMILY)[0], 404)


class TheServerBindsToLoopbackOnly(unittest.TestCase):
    """This page renders every lead's name, phone and email in full."""

    def test_the_host_constant(self):
        self.assertEqual(DASH.HOST, "127.0.0.1")

    def test_the_source_names_no_other_interface(self):
        # assertFalse, not assertNotIn: a failure here would dump the
        # whole module into the report.
        self.assertFalse("0.0.0.0" in SOURCE,
                         "dashboard.py names a wildcard interface")
        self.assertFalse('(("", ' in SOURCE,
                         "dashboard.py binds the empty host")

    def test_a_bound_server_is_on_loopback(self):
        with Tree() as t:
            httpd = DASH.make_server(0, FakeSources(t.agents))
            try:
                self.assertEqual(httpd.server_address[0], "127.0.0.1")
            finally:
                httpd.server_close()


class TheRendererEscapes(unittest.TestCase):
    """Every interpolated value goes through html.escape(), no exceptions --
    the discipline lead.write_html_table() already holds."""

    def test_a_scripted_agent_name_is_escaped(self):
        with Tree() as t:
            src = FakeSources(t.agents,
                              rows=[row(agent_name="<script>alert(1)</script>",
                                        agent_email='A & B "q"')])
            page = DASH.render(DASH.collect(src))
            self.assertIn("&lt;script&gt;", page)
            self.assertNotIn("<script>alert(1)", page)
            self.assertIn("&amp;", page)
            self.assertIn("&quot;", page)

    def test_a_crafted_link_cannot_break_out_of_the_href(self):
        with Tree() as t:
            src = FakeSources(t.agents, rows=[row()])
            src.recorded_link = lambda *a: '" onmouseover=x'
            page = DASH.render(DASH.collect(src))
            self.assertNotIn('" onmouseover=x', page)
            self.assertIn("&quot; onmouseover=x", page)

    def test_the_house_style_is_imported_not_forked(self):
        lead = helpers.scraper_module("lead")
        with Tree() as t:
            data = DASH.collect(FakeSources(t.agents))
            data["css"] = lead.CSS
            page = DASH.render(data)
            self.assertIn(lead.CSS, page)
            self.assertIn("prefers-color-scheme", page)
            self.assertNotIn(":root {", DASH.EXTRA_CSS)


class TheDashboardWritesNothing(unittest.TestCase):
    """Every mutation stays behind tour.py's prompts. A button here would give
    outreach/contacted.csv a second writer."""

    def test_the_source_holds_no_mutating_call(self):
        for bad in ("os.remove", "os.rename", "os.replace", "os.unlink",
                    "os.mkdir", "os.makedirs", "os.rmdir", "shutil.",
                    "save_config", "save_state", "publish_rung"):
            self.assertNotIn(bad, SOURCE, bad)

    def test_every_open_is_read_binary(self):
        opens = [n for n in ast.walk(ast.parse(SOURCE))
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id == "open"]
        self.assertTrue(opens)
        for call in opens:
            modes = [a.value for a in call.args[1:]
                     if isinstance(a, ast.Constant)]
            self.assertEqual(modes, ["rb"])

    def test_a_full_render_leaves_the_tree_byte_identical(self):
        with Tree() as t:
            t.cut("sample_branded.mp4", b"0123456789")
            before = sorted(
                (p, sorted(d), sorted(f)) for p, d, f in os.walk(t.root))
            src = FakeSources(t.agents, rows=[row()],
                              samples=["sample_branded.mp4"])
            DASH.render(DASH.collect(src))
            after = sorted(
                (p, sorted(d), sorted(f)) for p, d, f in os.walk(t.root))
            self.assertEqual(before, after)


class TheServerAnswersOnLoopback(unittest.TestCase):
    """One real ThreadingHTTPServer on port 0. Threading is not a nicety --
    a single-threaded server streaming a cut cannot answer a page reload."""

    DATA = bytes(range(256)) * 40      # 10240 bytes, known at every offset

    @classmethod
    def setUpClass(cls):
        cls.tree = Tree().__enter__()
        cls.tree.cut("sample_branded.mp4", cls.DATA)
        cls.tree.cut("tour_branded.mp4", cls.DATA)
        src = FakeSources(cls.tree.agents, rows=[row()],
                          samples=["sample_branded.mp4"])
        cls.httpd = DASH.make_server(0, src)
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever,
                                      daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)
        cls.tree.__exit__(None, None, None)

    def get(self, path, headers=None):
        req = urllib.request.Request(self.base + path,
                                     headers=headers or {})
        return urllib.request.urlopen(req, timeout=5)

    def test_the_page_renders(self):
        resp = self.get("/")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.headers["Content-Type"],
                         "text/html; charset=utf-8")
        self.assertIn("Listings (1)", resp.read().decode("utf-8"))

    def test_the_page_is_never_cached(self):
        self.assertEqual(self.get("/").headers["Cache-Control"], "no-store")

    def test_an_unknown_path_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.get("/nope")
        self.assertEqual(caught.exception.code, 404)

    def test_a_tour_cut_is_refused_over_the_socket(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.get(self.tree.url("tour_branded.mp4"))
        self.assertEqual(caught.exception.code, 403)

    def test_the_whole_cut_without_a_range(self):
        resp = self.get(self.tree.url("sample_branded.mp4"))
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.headers["Accept-Ranges"], "bytes")
        self.assertEqual(resp.read(), self.DATA)

    def test_a_closed_range_is_206(self):
        resp = self.get(self.tree.url("sample_branded.mp4"),
                        {"Range": "bytes=0-3"})
        self.assertEqual(resp.status, 206)
        self.assertEqual(resp.headers["Content-Range"], "bytes 0-3/10240")
        self.assertEqual(resp.headers["Content-Length"], "4")
        self.assertEqual(resp.read(), self.DATA[:4])

    def test_a_suffix_range_reads_the_tail(self):
        resp = self.get(self.tree.url("sample_branded.mp4"),
                        {"Range": "bytes=-16"})
        self.assertEqual(resp.status, 206)
        self.assertEqual(resp.read(), self.DATA[-16:])

    def test_an_open_ended_range_reads_to_the_end(self):
        resp = self.get(self.tree.url("sample_branded.mp4"),
                        {"Range": "bytes=10000-"})
        self.assertEqual(resp.status, 206)
        self.assertEqual(resp.read(), self.DATA[10000:])

    def test_a_malformed_range_serves_the_whole_file(self):
        resp = self.get(self.tree.url("sample_branded.mp4"),
                        {"Range": "kilobytes=0-1"})
        self.assertEqual(resp.status, 200)
        self.assertEqual(len(resp.read()), len(self.DATA))

    def test_an_unsatisfiable_range_is_416(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.get(self.tree.url("sample_branded.mp4"),
                     {"Range": "bytes=10240-"})
        self.assertEqual(caught.exception.code, 416)
        self.assertEqual(caught.exception.headers["Content-Range"],
                         "bytes */10240")

    def test_a_write_method_is_refused(self):
        req = urllib.request.Request(self.base + "/", data=b"x", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(caught.exception.code, 405)


class TheTourMenuReachesIt(unittest.TestCase):
    """The sixth entry, and the counts that have to move with it."""

    def setUp(self):
        self.tour = helpers.tour_module()
        self.src = helpers.repo_source("tour.py")

    def test_the_menu_has_a_sixth_entry(self):
        self.assertIn('("6", "Open the dashboard", dashboard_action)',
                      self.src)
        self.assertTrue(callable(self.tour.dashboard_action))

    def test_the_prompt_names_six(self):
        self.assertIn("Pick 1-6", self.src)
        self.assertNotIn("Pick 1-5", self.src)

    def test_the_action_only_serves(self):
        body = self.src.split("def dashboard_action():")[1].split(
            "\ndef ")[0]
        self.assertIn("dashboard.serve()", body)
        for bad in ("save_config", "publish_rung", "survey()"):
            self.assertNotIn(bad, body)


class TheAuditTablesMatchWhatAuditActuallyReturns(unittest.TestCase):
    """The three audit lists are 4-tuples, and the renderer must read them as such.

    reason: this shipped broken. render() unpacked drift as a pair and joined
    unverifiable as if every element were a string, and neither table was ever
    reached -- the live tree had no drift, no orphans and no unverifiable folder,
    and FakeSources defaults all three to (). The first folder with no lead row
    put a bool through "/".join and took the whole page down with a 500. A fake
    that cannot reproduce the real shape is not a fake, so this pins the arity
    against status.audit() itself rather than against a hand-written literal.
    """

    def test_status_audit_returns_the_shapes_the_renderer_reads(self):
        status = helpers.status_module()
        rows = [("b", "l", "a", 1, 1, 1, "act", {}, {"agent_phone": "1001"})]
        drift, unverifiable, orphans = status.audit(
            rows, {"1001": ("b2", "l2", "a2")}, set())
        self.assertEqual(drift, [("b", "l", "a", ("b2", "l2", "a2"))])
        self.assertEqual(len(drift[0]), 4)
        self.assertIsInstance(drift[0][3], tuple)

        drift2, unverifiable, orphans = status.audit(rows, {}, set())
        self.assertEqual(unverifiable, [("b", "l", "a", True)])
        self.assertEqual(len(unverifiable[0]), 4)
        self.assertIsInstance(unverifiable[0][3], bool)

    def test_a_non_empty_audit_renders_instead_of_raising(self):
        src = FakeSources(
            "/nowhere",
            drift=[(BRAND, LISTING, AGENT, ("other", "l2", "a2"))],
            unverifiable=[(BRAND, LISTING, AGENT, True),
                          ("hand_named", "9_x_st", "someone", False)],
            orphans=[(BRAND, LISTING, AGENT)])
        page = DASH.render(DASH.collect(src))
        self.assertIn("example_brokerage/1_example_st/a_lister", page)
        self.assertIn("other/l2/a2", page)
        self.assertIn("<td>yes</td>", page)
        self.assertIn("<td>no</td>", page)
        self.assertNotIn("True", page)

    def test_the_renderer_never_joins_a_raw_audit_tuple(self):
        body = SOURCE.split("def render(")[1]
        self.assertNotIn('"/".join(u) if isinstance', body)


if __name__ == "__main__":
    unittest.main()
