---
name: a-publish-prompt-has-one-owner
area: publishing
type: non-negotiable
guarded_by:
  - tests/test_publish_pending.py
source: PROGRESS.md@this-change — "--publish-pending loops publish_action()'s
  rung 4 across every listing instead of one", 2026-09-01
---

# A publish prompt has one owner, no matter how many listings ask it

`publish_rung(listing_dir, quiet=False)` is the single implementation of "ask
before uploading": it lists the files, prints `"Publish the sample cuts?"`,
defaults to **No**, and only on an explicit yes shells out to `publish.py` --
which prints the exact remote paths/URLs and asks again itself. Nothing else in
`tour.py` is allowed to grow a second implementation of that ask, and nothing is
allowed to answer it on a caller's behalf.

[`--auto` never reaches `publish_rung()` at all](the-draft-is-automatic-the-send-is-not.md)
-- sample-cut review and publishing stay a manual, by-hand step, guarded by
`tests/test_auto_flow.py`'s `test_never_calls_publish_rung`. `--publish-pending`
(`publish_pending()`) is the opposite case: a batch entry that walks every listing
with an unpublished `sample_` cut in `out/` (via `sample_cuts()`, not `stage()` --
`stage()` alone would re-offer an already-published-and-swept listing) and calls
`publish_rung()` once per candidate, exactly as `publish_action()`'s menu item 3
already does for one. It saves the trip back to the home screen; it does not move
the gate. There is no `--yes`, no `--force`, and `publish_pending()` never calls
`confirm(` itself -- `tests/test_publish_pending.py`'s
`test_no_hardcoded_confirm_bypass` greps its source for exactly that, the same
shape `tests/test_publish_gate.py` already uses to guard `publish.py` against
growing a `--force`/`--allow-tour`/`--unwatermarked` override.

Any future loop over multiple listings' publish step must call `publish_rung()`
per listing, the same way, for the same reason: a batch convenience is only safe
because the human is still asked once per listing, every time, with no override.
