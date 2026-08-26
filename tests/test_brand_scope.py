"""A brand is a brokerage, and a brokerage has many agents.

Guards CLAUDE.md: "brand.json never carries agent_name or agent_phone. A
brokerage has many agents; the folder is keyed on the brokerage."

reason: tour.py's BRAND_KEYS carried agent_name and agent_phone, and questions()
offered to save them as brand defaults with the confirm defaulting to YES. Nine
brand.json files on disk were clean, so nothing had gone wrong yet -- but
leads.csv lists two agents under Coldwell Banker Realty - Boston, two under
Gibson Sotheby's International Realty and two under Serhant, and load_config()
layers brand.json UNDER the listing's config.json without printing anything. One
yes would have put one agent's phone number on another agent's card, lower third
and output filenames across every listing that brokerage owns, silently. This
file fails if either key returns to the brand scope by any route.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers

AGENT = ("agent_name", "agent_phone")
# reason: deliberately not phone-shaped. check_pii.py scans every file
# git would publish for \d{3}-\d{3}-\d{4}, and a test fixture that
# trips the repo's own PII gate teaches people to ignore it.
PHONE_SHAPED_ENOUGH = "NOT-A-REAL-NUMBER"


class TestBrandScope(unittest.TestCase):

    def setUp(self):
        self.tour = helpers.tour_module()

    def test_brand_keys_excludes_agent_identity(self):
        for key in AGENT:
            self.assertNotIn(
                key, self.tour.BRAND_KEYS,
                f"{key} is back in BRAND_KEYS. A brand folder is keyed on the "
                "brokerage and a brokerage has many agents.")

    def test_agent_keys_names_both(self):
        self.assertEqual(tuple(self.tour.AGENT_KEYS), AGENT)

    def test_save_brand_cannot_write_agent_identity(self):
        """Even handed the keys explicitly, they must not reach the file."""
        tmp = tempfile.mkdtemp(prefix="brand_scope_")
        prev = self.tour.LISTINGS_ROOT
        try:
            self.tour.LISTINGS_ROOT = tmp
            os.makedirs(os.path.join(tmp, "some_brokerage"))
            self.tour.save_brand("some_brokerage", {
                "logo": "global_assets/logos/x.png",
                "brokerage": "Some Brokerage",
                "agent_name": "First Agent",
                "agent_phone": PHONE_SHAPED_ENOUGH,
            })
            with open(os.path.join(tmp, "some_brokerage", "brand.json")) as f:
                written = json.load(f)
        finally:
            self.tour.LISTINGS_ROOT = prev
            shutil.rmtree(tmp, ignore_errors=True)
        for key in AGENT:
            self.assertNotIn(key, written,
                             f"save_brand() wrote {key} into brand.json.")
        self.assertEqual(written.get("brokerage"), "Some Brokerage",
                         "brokerage is a real brand default and must survive.")

    def test_load_brand_strips_a_hand_edited_agent(self):
        """A brand.json that already carries an agent must not be inherited."""
        tmp = tempfile.mkdtemp(prefix="brand_scope_")
        prev = self.tour.LISTINGS_ROOT
        try:
            self.tour.LISTINGS_ROOT = tmp
            os.makedirs(os.path.join(tmp, "some_brokerage"))
            with open(os.path.join(tmp, "some_brokerage", "brand.json"), "w") as f:
                json.dump({"logo": "l.png", "agent_name": "First Agent",
                           "agent_phone": PHONE_SHAPED_ENOUGH}, f)
            got = self.tour.load_brand("some_brokerage")
        finally:
            self.tour.LISTINGS_ROOT = prev
            shutil.rmtree(tmp, ignore_errors=True)
        for key in AGENT:
            self.assertNotIn(key, got,
                             f"load_brand() passed {key} through to a listing.")
        self.assertEqual(got.get("logo"), "l.png")

    def test_no_brand_json_on_disk_carries_an_agent(self):
        """The nine real files, checked directly rather than by proxy."""
        root = os.path.join(helpers.REPO, "agents")
        offenders = []
        for brand in sorted(os.listdir(root)) if os.path.isdir(root) else []:
            path = os.path.join(root, brand, "brand.json")
            if not os.path.isfile(path):
                continue
            with open(path) as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    continue
            for key in AGENT:
                if data.get(key):
                    offenders.append(f"{brand}/brand.json:{key}")
        self.assertEqual(offenders, [],
                         f"agent identity in a brand default: {offenders}")


if __name__ == "__main__":
    unittest.main()
