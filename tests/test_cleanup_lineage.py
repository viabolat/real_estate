"""cleanup() clears the draft lineage on a delivery build, and only its own on a draft.

reason: work_draft.mp4 and clips_draft/ are named apart from the delivery
intermediates so a draft-quality stitch can never feed a delivery build. Nothing
on the delivery side ever deleted them, and tour.py always passes --keep-work or
--finish-only -- so every listing it drafted kept ~35MB of dead intermediates
forever. The mirror-image bug was a bare --draft deleting work_branded.mp4, which
belongs to the delivery rung.
"""
import os
import unittest

import helpers


def touch(*names):
    for n in names:
        d = os.path.dirname(n)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(n, "wb") as f:
            f.write(b"x")


class DeliveryClearsTheDraftLineage(unittest.TestCase):

    def test_delivery_clears_draft_intermediates_even_with_keep_work(self):
        with helpers.listing(config={}, argv=["make_tour.py", "--keep-work"]) as (m, _):
            touch("work_silent.mp4", "work_branded.mp4", "work_draft.mp4",
                  "clips/001.mp4", "clips_draft/001.mp4", "draft.mp4")
            m.cleanup(keep_work=True)
            # its own stitches survive --keep-work
            self.assertTrue(os.path.exists("work_silent.mp4"))
            self.assertTrue(os.path.exists("work_branded.mp4"))
            self.assertTrue(os.path.exists("clips/001.mp4"))
            # the superseded draft lineage does not
            self.assertFalse(os.path.exists("work_draft.mp4"))
            self.assertFalse(os.path.exists("clips_draft/001.mp4"))
            self.assertFalse(os.path.isdir("clips_draft"))
            # the review cut the operator asked for is not an intermediate
            self.assertTrue(os.path.exists("draft.mp4"))

    def test_draft_never_touches_the_delivery_lineage(self):
        with helpers.listing(config={}, argv=["make_tour.py", "--draft"]) as (m, _):
            touch("work_silent.mp4", "work_branded.mp4", "work_draft.mp4",
                  "clips/001.mp4", "clips_draft/001.mp4")
            m.cleanup(keep_work=False)
            # a draft clears only what a draft wrote
            self.assertFalse(os.path.exists("work_draft.mp4"))
            self.assertFalse(os.path.exists("clips_draft/001.mp4"))
            # a kept delivery stitch survives it intact -- both halves or neither
            self.assertTrue(os.path.exists("work_silent.mp4"))
            self.assertTrue(os.path.exists("work_branded.mp4"))
            self.assertTrue(os.path.exists("clips/001.mp4"))

    def test_delivery_without_keep_work_still_clears_both(self):
        with helpers.listing(config={}, argv=["make_tour.py"]) as (m, _):
            touch("work_silent.mp4", "work_branded.mp4", "work_draft.mp4",
                  "clips/001.mp4", "clips_draft/001.mp4")
            m.cleanup(keep_work=False)
            for f in ("work_silent.mp4", "work_branded.mp4", "work_draft.mp4",
                      "clips/001.mp4", "clips_draft/001.mp4"):
                self.assertFalse(os.path.exists(f), f)

    def test_cleanup_is_a_noop_when_there_is_no_draft_lineage(self):
        """A folder that never drafted must not gain an error or a stray message."""
        with helpers.listing(config={}, argv=["make_tour.py", "--keep-work"]) as (m, _):
            touch("work_silent.mp4")
            m.cleanup(keep_work=True)
            self.assertTrue(os.path.exists("work_silent.mp4"))
            self.assertEqual([], m.draft_lineage())


if __name__ == "__main__":
    unittest.main()
