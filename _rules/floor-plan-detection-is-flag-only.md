---
name: floor-plan-detection-is-flag-only
area: photos
type: non-negotiable
guarded_by:
  - tests/test_floorplan.py
  - tests/test_auto_flow.py
source: PROGRESS.md@144c075 L254-265
---

# Floor-plan detection flags a candidate; it never reorders, renames, or deletes

`PROGRESS.md` §4.2: "print them as candidates, and never reorder or delete. The
operator confirms." `floorplan.py` holds to that by construction, not convention —
the only filesystem access anywhere in the module is an ffmpeg subprocess whose
decoded pixels are captured to an in-memory bytes object; no function in it is ever
handed a path to write, rename, or remove. `tests/test_floorplan.py` scans the
module's source text for `os.remove`, `os.rename`, `os.unlink`, `shutil.move`,
`shutil.rmtree`, and `open(` and fails if any appear.

`tour.py --auto` calls `floorplan.detect()` once per listing, right after the
contact sheet and before anything encodes. A flagged photo halts only that
listing — printed, never acted on — and the rest of the batch keeps going.
Nothing about the halt is recorded: no marker file, no `config.json` key, no
rename. Deleting the file by hand and re-running `--auto` is the entire resume
mechanism, the same "derive, never record" discipline `stage()` already uses.
`tests/test_auto_flow.py` guards that `auto_flow()`/`_auto_build_one()` stop
before any delivery build on a flagged photo, and that `--ignore-floorplan-check`
— the one-shot override, and it always needs a `brand/listing` scope — never
reaches what `save_config()`/`save_state()` write to disk.

The scoring thresholds (`GRID`, `NEAR_WHITE`, `LOW_CHROMA`, `WHITE_FRACTION`,
`CHROMA_FRACTION`) are module constants, never a `config.json` key — a tuning
value with one correct answer for every listing is a control this interface does
not need (`nothing-invariant-becomes-a-control.md`).
