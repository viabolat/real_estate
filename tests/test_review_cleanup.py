"""tour.py clears its own review rungs once the sample cuts exist to replace them.

reason: contact_sheet.png answered "is the order right" and draft.mp4 answered
"does the edit feel right" -- once out/ holds the sample_ cuts those questions
are settled. This is deliberately narrower than make_tour.py's own cleanup:
work_draft.mp4/clips_draft/ are already cleared by a delivery build regardless
of --keep-work (see a-build-deletes-its-own-intermediates.md /
test_cleanup_lineage.py) -- clear_review_artifacts must not re-touch them, or
two places would be doing one job.
"""
import os
import shutil
import tempfile
import unittest

import helpers


def touch(*paths):
    for p in paths:
        d = os.path.dirname(p)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(p, "wb") as f:
            f.write(b"x")


class ClearReviewArtifacts(unittest.TestCase):

    def setUp(self):
        self.tour = helpers.tour_module()
        self.tmp = tempfile.mkdtemp(prefix="review_cleanup_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def path(self, *parts):
        return os.path.join(self.tmp, *parts)

    def test_removes_contact_sheet_and_draft(self):
        touch(self.path("contact_sheet.png"), self.path("draft.mp4"))
        removed = self.tour.clear_review_artifacts(self.tmp)
        self.assertEqual(set(removed), {"contact_sheet.png", "draft.mp4"})
        self.assertFalse(os.path.exists(self.path("contact_sheet.png")))
        self.assertFalse(os.path.exists(self.path("draft.mp4")))

    def test_never_touches_the_delivery_or_draft_lineage(self):
        touch(self.path("contact_sheet.png"), self.path("draft.mp4"),
              self.path("work_draft.mp4"), self.path("clips_draft", "001.mp4"),
              self.path("work_silent.mp4"), self.path("work_branded.mp4"),
              self.path("clips", "001.mp4"), self.path("config.json"))
        self.tour.clear_review_artifacts(self.tmp)
        for kept in ("work_draft.mp4", "clips_draft/001.mp4", "work_silent.mp4",
                     "work_branded.mp4", "clips/001.mp4", "config.json"):
            self.assertTrue(os.path.exists(self.path(*kept.split("/"))), kept)

    def test_is_a_no_op_when_nothing_is_there(self):
        self.assertEqual(self.tour.clear_review_artifacts(self.tmp), [])

    def test_is_idempotent(self):
        touch(self.path("draft.mp4"))
        self.tour.clear_review_artifacts(self.tmp)
        self.assertEqual(self.tour.clear_review_artifacts(self.tmp), [])


if __name__ == "__main__":
    unittest.main()
