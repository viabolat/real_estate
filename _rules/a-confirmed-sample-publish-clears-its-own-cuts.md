---
name: a-confirmed-sample-publish-clears-its-own-cuts
area: publishing
type: non-negotiable
guarded_by:
  - tests/test_publish_gate.py
  - tests/test_build_stage.py
source: PROGRESS.md@this-change — "publish.py uploads sample_ cuts to the CDN but never removes the local copies in out/ -- by design, today", 2026-08-30
---

# A confirmed sample publish clears its own cuts

[`a-publish-never-deletes-the-local-cut`](a-publish-never-deletes-the-local-cut.md)
stays fully true of `publish.py` itself — it still contains zero `os.remove`,
still guarded by `tests/test_publish_gate.py`, still safe to run standalone. This
rule is a **deliberate, scoped narrowing**, added one layer up in `tour.py`, not a
reversal: once a `sample_` cut's upload is verified against the storage API (not
assumed from a 200) and recorded as a row in `outreach/links.csv`, the CDN copy
*is* the record from then on, and the local copy in `out/` is deleted.

Two things keep this narrow instead of becoming a second, looser deletion path:

- The delete only ever runs from `tour.py`'s `clear_published_cuts()`, called
  after `publish_rung()` sees a successful (`returncode == 0`) run of
  `publish.py`, or from `tour.py --sweep-published-samples --yes` doing the same
  check retroactively across every listing. Nothing is removed unless a
  `links.csv` row names that exact filename as confirmed for that
  `(brand, listing)` — the same "verify against the record, not an assumption"
  shape `publish.py` already uses for the upload itself.
- A `tour_` file can never appear in that row (`publish.publishable()` already
  refuses to upload one), but `clear_published_cuts()` also checks
  `publish.family(name) == "sample"` before deleting, so the guarantee holds even
  if `links.csv` is ever hand-edited or replayed by the sweep.

`clear_review_artifacts()` (the `contact_sheet.png`/`draft.mp4` cleanup) also now
runs unconditionally after a successful publish, closing the gap where a
`--draft` rerun after the sample build regenerates those files with nothing left
to clear them a second time.

**The gap this created, and its fix.** `tour.py`'s `stage()` and `status.py`'s
`next_action()` are both derived from `out/`'s contents alone — "nothing built"
and "sample cuts already built-and-cleaned-up" would otherwise look identical,
which would make `auto_targets()` re-select an already-published,
awaiting-sign-off listing as fresh. Both functions fall back to a
`links.csv`-backed `published(brand, listing)` lookup when `out/` has neither
cut family, before concluding "ready to build." No new marker file or config
key — one more call to a lookup that already existed for exactly this question.
