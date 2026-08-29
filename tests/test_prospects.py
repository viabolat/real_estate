"""prospects.rebuild() -- a view of agents/ keyed by agent, not brokerage.

reason: brand.json carries no agent identity (see brand-json-carries-no-agent-
identity.md), and one brokerage can have several agents -- prospects/ answers
"everything tied to one agent" that agents/<brand>/<listing> cannot. It must be
keyed on name AND phone, since two different agents at two different
brokerages can share a name, and it must be a regenerated view (symlinks),
never a second copy of the folders, the same way leads.html is regenerated
from leads.csv rather than hand-maintained.
"""
import os
import shutil
import tempfile
import unittest

import helpers


def row(brand, listing, agent_name="", agent_phone=""):
    cfg = {}
    if agent_name:
        cfg["agent_name"] = agent_name
    if agent_phone:
        cfg["agent_phone"] = agent_phone
    return (brand, listing, 0, None, None, "next action", {}, cfg)


class ProspectsIsARegeneratedView(unittest.TestCase):

    def setUp(self):
        self.prospects = helpers.prospects_module()
        self.slugify = helpers.scraper_module("photos").slugify
        self.tmp = tempfile.mkdtemp(prefix="prospects_test_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.agents_dir = os.path.join(self.tmp, "agents")
        self.dest_dir = os.path.join(self.tmp, "prospects")
        os.makedirs(self.agents_dir)

    def make_listing(self, brand, listing):
        d = os.path.join(self.agents_dir, brand, listing)
        os.makedirs(d, exist_ok=True)
        return d

    def rebuild(self, rows):
        self.prospects.rebuild(rows, self.slugify,
                                agents_dir=self.agents_dir, dest_dir=self.dest_dir)

    def test_symlinks_a_listing_under_its_agent(self):
        self.make_listing("compass", "41_worcester_sq")
        self.rebuild([row("compass", "41_worcester_sq", "Mary Smith", "1001001001")])
        link = os.path.join(self.dest_dir, "mary_smith__1001001001",
                             "compass__41_worcester_sq")
        self.assertTrue(os.path.islink(link))
        self.assertTrue(os.path.samefile(
            link, os.path.join(self.agents_dir, "compass", "41_worcester_sq")))

    def test_same_agent_name_different_phone_does_not_collide(self):
        self.make_listing("compass", "1_main_st")
        self.make_listing("remax", "2_main_st")
        self.rebuild([
            row("compass", "1_main_st", "Mary Smith", "1001001001"),
            row("remax", "2_main_st", "Mary Smith", "2002002002"),
        ])
        self.assertTrue(os.path.isdir(
            os.path.join(self.dest_dir, "mary_smith__1001001001")))
        self.assertTrue(os.path.isdir(
            os.path.join(self.dest_dir, "mary_smith__2002002002")))

    def test_same_agent_two_listings_land_under_one_key(self):
        self.make_listing("remax", "9_w_cedar")
        self.make_listing("remax", "123_elm_st")
        self.rebuild([
            row("remax", "9_w_cedar", "Mary Smith", "1001001001"),
            row("remax", "123_elm_st", "Mary Smith", "1001001001"),
        ])
        key_dir = os.path.join(self.dest_dir, "mary_smith__1001001001")
        self.assertTrue(os.path.islink(os.path.join(key_dir, "remax__9_w_cedar")))
        self.assertTrue(os.path.islink(os.path.join(key_dir, "remax__123_elm_st")))

    def test_blank_agent_name_is_skipped(self):
        self.make_listing("compass", "no_agent_yet")
        self.rebuild([row("compass", "no_agent_yet")])
        self.assertEqual(os.listdir(self.dest_dir) if os.path.isdir(self.dest_dir)
                          else [], [])

    def test_placeholder_row_is_skipped(self):
        self.rebuild([("some_brand", "-", 0, None, None, "no listings yet", {}, {})])
        self.assertFalse(os.path.isdir(self.dest_dir))

    def test_a_removed_listing_disappears_on_the_next_rebuild(self):
        self.make_listing("compass", "1_main_st")
        self.rebuild([row("compass", "1_main_st", "Mary Smith", "1001001001")])
        key_dir = os.path.join(self.dest_dir, "mary_smith__1001001001")
        self.assertTrue(os.listdir(key_dir))
        self.rebuild([])                       # listing gone from the next survey
        self.assertFalse(os.path.exists(key_dir))

    def test_rebuild_is_idempotent(self):
        self.make_listing("compass", "1_main_st")
        rows = [row("compass", "1_main_st", "Mary Smith", "1001001001")]
        self.rebuild(rows)
        self.rebuild(rows)
        link = os.path.join(self.dest_dir, "mary_smith__1001001001",
                             "compass__1_main_st")
        self.assertTrue(os.path.islink(link))


if __name__ == "__main__":
    unittest.main()
