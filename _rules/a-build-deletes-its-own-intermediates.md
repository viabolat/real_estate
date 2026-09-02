---
name: a-build-deletes-its-own-intermediates
area: build
type: non-negotiable
guarded_by:
  - tests/test_cleanup_lineage.py
source: CLAUDE.md@717ce32 L243-255
---

# A successful build deletes its own intermediates

A failed build keeps them for inspection. Do not add cleanup that fires before
`finish()` and `vertical()`. `--keep-work` / `--finish-only` govern *the rung being
run*: a successful **delivery** build clears the draft lineage — `work_draft.mp4`,
`clips_draft/` — regardless of either flag, because a delivery supersedes any draft
of the same listing and never reuses a draft stitch. Nothing did that before, and
`tour.py` always passes one of those flags, so every listing it drafted kept ~35 MB
of dead intermediates forever. `draft.mp4` is **not** touched — it is the review cut
the operator asked for, not an intermediate. The asymmetry is deliberate and must
stay: a `--draft` run clears only what a draft wrote, or it would delete
`work_branded.mp4` out from under a kept delivery stitch and leave half a lineage
behind. `tests/test_cleanup_lineage.py` guards both directions.
