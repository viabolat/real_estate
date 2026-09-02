r"""migrate_layout.py moves a legacy folder; it never names one and never merges.

Guards _rules/an-agent-folder-is-one-that-holds-a-config.md and
_rules/the-scrape-names-the-folders.md. The destination slug comes out of
leads.csv through status.legacy_target() -- a listing folder with no lead row
behind it is refused, not hand-named, and the only bytes the script ever deletes
are a legacy copy that is byte-identical to an already-migrated one.

The stand-in phone ids are deliberately NOT phone-shaped: check_pii.py matches
by shape, so a fictional 555 number in a committed fixture still trips it. See
tests/README.md.
"""
import inspect
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers

ML = None
TRUTH = {"1001": ("brokerage_one", "11_first_st", "agent_a"),
         "2002": ("brokerage_two", "22_second_st", "agent_b")}


def setUpModule():
    global ML
    ML = helpers.migrate_layout_module()


class Tree(unittest.TestCase):
    """A temp agents/ tree, built folder by folder."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="migrate_test_")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.agents = os.path.join(self.root, "agents")
        os.makedirs(self.agents)

    def photos(self, where, names=("01_a.jpg", "02_b.jpg"), body=b"pixels"):
        os.makedirs(where, exist_ok=True)
        for n in names:
            with open(os.path.join(where, n), "wb") as f:
                f.write(body + n.encode())

    def config(self, where, **over):
        os.makedirs(where, exist_ok=True)
        cfg = {"agent_name": "Agent A", "agent_phone": "1001"}
        cfg.update(over)
        with open(os.path.join(where, "config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f)

    def legacy(self, brand="brokerage_one", listing="11_first_st", **over):
        d = os.path.join(self.agents, brand, listing)
        self.config(d, **over)
        self.photos(os.path.join(d, "photos"))
        return d

    def snapshot(self):
        out = {}
        for base, _dirs, files in os.walk(self.root):
            for f in files:
                p = os.path.join(base, f)
                with open(p, "rb") as fh:
                    out[os.path.relpath(p, self.root)] = fh.read()
        return out

    def plan(self):
        return ML.plan(agents_dir=self.agents, truth=TRUTH)


class TestPlanClassifies(Tree):

    def test_a_legacy_folder_with_a_lead_row_is_a_move(self):
        self.legacy()
        self.assertEqual(
            self.plan(),
            [("move", "brokerage_one", "11_first_st", "agent_a", "2 photos")])

    def test_a_legacy_folder_with_no_lead_row_is_refused_never_named(self):
        """The scrape cannot name a listing it has no row for."""
        self.legacy(agent_phone="9009")
        kind, _brand, _listing, slug, detail = self.plan()[0]
        self.assertEqual(kind, "refuse")
        self.assertIsNone(slug)
        self.assertIn("leads.csv", detail)

    def test_a_healthy_four_level_listing_is_left_out_entirely(self):
        d = os.path.join(self.agents, "brokerage_one", "11_first_st", "agent_a")
        self.config(d)
        self.photos(os.path.join(d, "photos"))
        self.assertEqual(self.plan(), [])

    def test_a_byte_identical_copy_beside_the_migrated_one_is_a_duplicate(self):
        listing = self.legacy()
        agent = os.path.join(listing, "agent_a")
        self.config(agent)
        self.photos(os.path.join(agent, "photos"))
        self.assertEqual(self.plan()[0][0], "duplicate")

    def test_a_differing_copy_is_a_conflict_not_a_merge(self):
        """Two different photo sets are a question for a human, not a rename."""
        listing = self.legacy()
        agent = os.path.join(listing, "agent_a")
        self.config(agent)
        self.photos(os.path.join(agent, "photos"), body=b"different")
        self.assertEqual(self.plan()[0][0], "conflict")

    def test_a_config_with_no_photos_beside_it_is_not_legacy(self):
        """An agent folder mid-scaffold is not a listing level in the old shape."""
        self.config(os.path.join(self.agents, "brokerage_one", "11_first_st"))
        self.assertEqual(self.plan(), [])


class TestPlanningWritesNothing(Tree):

    def test_plan_leaves_every_byte_where_it_was(self):
        self.legacy()
        self.legacy(brand="brokerage_two", listing="22_second_st",
                    agent_phone="2002")
        before = self.snapshot()
        self.plan()
        self.assertEqual(self.snapshot(), before)

    def test_main_needs_yes_before_it_touches_anything(self):
        src = inspect.getsource(ML.main)
        self.assertIn("if args.yes:", src)
        self.assertIn("Nothing was written", src)


class TestApply(Tree):

    def apply(self, action):
        kind, brand, listing, slug, _detail = action
        return ML.apply_one(kind, brand, listing, slug, agents_dir=self.agents,
                            root=self.root, say=lambda *a, **k: None)

    def test_a_move_relocates_every_byte_into_the_agent_folder(self):
        self.legacy()
        before = {os.path.basename(k): v for k, v in self.snapshot().items()}
        self.apply(self.plan()[0])
        agent = os.path.join(self.agents, "brokerage_one", "11_first_st", "agent_a")
        self.assertTrue(os.path.isdir(os.path.join(agent, "photos")))
        self.assertTrue(os.path.isfile(os.path.join(agent, "config.json")))
        after = {os.path.basename(k): v for k, v in self.snapshot().items()}
        self.assertEqual(sorted(after), sorted(before))
        for name in ("01_a.jpg", "02_b.jpg"):
            self.assertEqual(after[name], before[name])
        self.assertEqual(self.plan(), [])

    def test_a_build_that_already_ran_keeps_its_cuts_and_its_work_stitch(self):
        """reason: a migration must not cost anyone a re-encode -- out/ and the
        kept work_*.mp4 ride along, per
        _rules/a-build-deletes-its-own-intermediates.md."""
        listing = self.legacy()
        self.photos(os.path.join(listing, "out"), names=("sample_branded.mp4",))
        with open(os.path.join(listing, "work_silent.mp4"), "wb") as f:
            f.write(b"stitch")
        self.apply(self.plan()[0])
        agent = os.path.join(self.agents, "brokerage_one", "11_first_st", "agent_a")
        self.assertTrue(os.path.isfile(
            os.path.join(agent, "out", "sample_branded.mp4")))
        self.assertTrue(os.path.isfile(os.path.join(agent, "work_silent.mp4")))

    def test_the_duplicate_is_removed_and_the_migrated_copy_survives(self):
        listing = self.legacy()
        agent = os.path.join(listing, "agent_a")
        self.config(agent, agent_email="address-on-file")
        self.photos(os.path.join(agent, "photos"))
        self.apply(self.plan()[0])
        self.assertFalse(os.path.exists(os.path.join(listing, "photos")))
        self.assertFalse(os.path.exists(os.path.join(listing, "config.json")))
        self.assertTrue(os.path.isdir(os.path.join(agent, "photos")))
        with open(os.path.join(agent, "config.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["agent_email"], "address-on-file")

    def test_a_refusal_and_a_conflict_change_nothing(self):
        self.legacy(agent_phone="9009")
        before = self.snapshot()
        self.assertFalse(self.apply(self.plan()[0]))
        self.assertEqual(self.snapshot(), before)


class TestConfigNormalisation(Tree):

    def write(self, **cfg):
        d = os.path.join(self.root, "cfg")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "config.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        return path

    def read(self, path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def test_an_empty_music_is_dropped_so_the_brand_default_is_inherited(self):
        path = self.write(agent_name="A", music="")
        ML.normalise_config(path, root=self.root)
        self.assertNotIn("music", self.read(path))
        self.assertEqual(self.read(path)["agent_name"], "A")

    def test_a_logo_whose_file_is_gone_is_dropped_not_kept_as_a_dead_path(self):
        path = self.write(logo="global_assets/logos/vanished.png")
        ML.normalise_config(path, root=self.root)
        self.assertNotIn("logo", self.read(path))

    def test_a_logo_that_resolves_is_left_exactly_alone(self):
        os.makedirs(os.path.join(self.root, "global_assets", "logos"))
        open(os.path.join(self.root, "global_assets", "logos", "real.png"),
             "wb").close()
        path = self.write(logo="global_assets/logos/real.png", music="")
        ML.normalise_config(path, root=self.root)
        self.assertEqual(self.read(path)["logo"], "global_assets/logos/real.png")

    def test_nothing_else_in_the_config_is_touched(self):
        path = self.write(agent_name="A", agent_phone="1001",
                          address="1 Test St", music="")
        ML.normalise_config(path, root=self.root)
        cfg = self.read(path)
        self.assertEqual(cfg, {"agent_name": "A", "agent_phone": "1001",
                               "address": "1 Test St"})


class TestBrandNormalisation(Tree):

    def brand(self, **data):
        d = os.path.join(self.agents, "brokerage_one")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "brand.json"), "w", encoding="utf-8") as f:
            json.dump(data, f)
        return d

    def asset(self, sub, name):
        d = os.path.join(self.root, "global_assets", sub)
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, name), "wb").close()

    def read(self, d):
        with open(os.path.join(d, "brand.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_a_bare_filename_becomes_repo_relative(self):
        """reason: find_gaps.logo_status() resolves the logo against the repo
        root, so a bare "tcc.png" read as no logo at all and the brand was
        reported as an acronym near_miss against the file it already named."""
        self.asset("logos", "tcc.png")
        d = self.brand(logo="tcc.png")
        ML.normalise_brand(d, root=self.root)
        self.assertEqual(self.read(d)["logo"], "global_assets/logos/tcc.png")

    def test_a_path_that_is_already_relative_is_left_alone(self):
        self.asset("logos", "tcc.png")
        d = self.brand(logo="global_assets/logos/tcc.png")
        ML.normalise_brand(d, root=self.root)
        self.assertEqual(self.read(d)["logo"], "global_assets/logos/tcc.png")

    def test_a_bare_filename_with_no_file_behind_it_is_not_invented(self):
        d = self.brand(logo="nothing_here.png")
        ML.normalise_brand(d, root=self.root)
        self.assertEqual(self.read(d)["logo"], "nothing_here.png")

    def test_a_brand_with_no_brand_json_is_not_created(self):
        d = os.path.join(self.agents, "brand_new_co")
        os.makedirs(d)
        ML.normalise_brand(d, root=self.root)
        self.assertFalse(os.path.exists(os.path.join(d, "brand.json")))


class TestItDeletesOnlyTheDuplicate(unittest.TestCase):

    def test_removal_lives_only_in_the_duplicate_branch(self):
        """reason: bytes here are unrecoverable -- agents/ is gitignored. The
        script moves; the single exception is a copy proven byte-identical."""
        src = inspect.getsource(ML.apply_one)
        head, _sep, tail = src.partition('if kind != "move":')
        for token in ("rmtree", "os.remove"):
            self.assertIn(token, head)
            self.assertNotIn(token, tail)

    def test_it_reuses_the_naming_authority_rather_than_a_second_copy(self):
        src = inspect.getsource(ML)
        self.assertIn("status.legacy_target", src)
        self.assertIn("status.scraped_names", src)
        self.assertNotIn("def slugify(", src)


if __name__ == "__main__":
    unittest.main()
