---
name: excess-photos-are-trimmed-by-quality-never-halted
area: photos
type: non-negotiable
guarded_by:
  - tests/test_photo_quality.py
source: PROGRESS.md@this-change — "a dump with 30-39 photos built past 90s with no ceiling", 2026-08-30
---

# A photo set too large for `max_total_seconds` is trimmed by quality, not halted

`make_tour.py`'s `select_photos()` runs between `check_resolution()` and
`build_clips()`. When `len(photos)` already fits `MAX_TOTAL_SECONDS` (default
`90.0`, `[cfg] max_total_seconds`) nothing changes — this is a ceiling, never a
target, and a short photo set is never padded up to it. When it doesn't fit,
`photo_quality.select()` scores every photo for sharpness (edge energy over a
downsampled luma grid, the same ffmpeg-subprocess-and-score-in-Python shape
`floorplan.py` uses for its white/chroma test) and keeps the sharpest
`max_photos_for(MAX_TOTAL_SECONDS)` of them, dropping the rest. `max_photos_for()`
duplicates `tour.py`'s `runtime(n, cfg)` arithmetic on purpose — `make_tour.py`
cannot import `tour.py`, which is the module that imports it, not the reverse —
and `tests/test_photo_quality.py` holds the two formulas in agreement.

This is a **deliberate, narrow exception** to
[`floor-plan-detection-is-flag-only`](floor-plan-detection-is-flag-only.md)'s
philosophy. A floor-plan candidate halts for a human because dropping a real
room photo by mistake there is a silent-failure risk worth a person's
attention. Trimming excess photos was explicitly requested to run unattended
under `--auto` instead — the failure mode (a slightly weaker photo set) is
minor and the report is loud (dropped filenames and scores printed before the
build), so a halt would only add operator attention this request exists to
remove.

`photo_quality.select()` restores the kept photos to their original relative
order before returning — it filters, it never reorders survivors and never
touches a file on disk, so it cannot conflict with
[`photo-order-lives-in-the-filename-prefix`](photo-order-lives-in-the-filename-prefix.md).
`tests/test_photo_quality.py` scans `photo_quality.py`'s source text for
`os.remove`, `os.rename`, `os.unlink`, `shutil.move`, `shutil.rmtree`, and
`open(` the same way `test_floorplan.py` guards `floorplan.py`, and asserts
selection never yields a runtime over `max_total_seconds`.

`max_total_seconds` is a duration cap, not a selection key — nothing in
`config.json` names *which* photos survive; that is scored fresh on every
build. See [`photo-order-lives-in-the-filename-prefix`](photo-order-lives-in-the-filename-prefix.md)'s
"no selection key" rule in `_reference/config-schema.md`.
