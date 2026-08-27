---
name: a-missing-watermark-stops-the-build
area: build
type: non-negotiable
guarded_by:
  - tests/test_guards.py
  - tests/test_home_screen.py
source: CLAUDE.md@717ce32 L611-631
---

# A broken *or missing* watermark stops the build; broken branding does not

An unreadable logo or lower third costs a cosmetic layer, so it warns and drops out
rather than killing a build that is already minutes deep. The proofing watermark is
the only thing separating a `sample_` cut from a deliverable, so a watermark that
will not render is a hard refusal — degrading it silently writes exactly the
unmarked proof the `tour_`/`sample_` split exists to prevent. That refusal now
covers an **absent** file too: `use_wm = bool(watermark and os.path.exists(...))`
meant a present-but-corrupt watermark refused while a missing one was skipped in
silence. Every `config.json` the scraper writes pins the path, so the hole only
opened on folders that were never scraped — exactly the hand-placed ones `tour.py`
now admits — and the bare `viabolat.png` fallback does not resolve from a listing
folder. The result was an unwatermarked `sample_` cut that `publish.py` then
uploaded on the strength of its name. `tour.py`'s `DEFAULTS` carries `watermark:
global_assets/logos/viabolat.png` so every listing it writes pins it, matching
`scraper/photos.py`. A `--delivery-only` run needs no watermark and is unaffected.
The refusal fires at **preflight** — before the lock, the clips and the stitch — via
`require_watermark()`, and again inside `finish()` as the last gate before the
pixels. Refusing at minute five over something known at second one is this repo's
own stated failure shape; it is what the resolution gate was fixed for, and the same
mistake was not worth repeating here.
