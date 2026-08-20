# STEPS.md — Runbook for `make_tour.py`

Every scenario the script covers and the exact command for it.
For photo sourcing and resolution rules, see `IDEA.md`. For project rules, `CLAUDE.md`.

---

## 0. What the script expects

| Path | Required | Notes |
|---|---|---|
| `photos/` | **yes** | Numbered in tour order: `01_exterior.jpg`, `02_entry.webp`, ... The prefix **is** the order. Every run prints the resolved order first — read it. |
| `music.mp3` | no | A **licensed** track. Skip with `--no-music`. |
| `lower_third.png` | no | Agent + listing info. Full-frame 1920x1080 plate, or a small strip. |
| `logo.png` | no | Brokerage mark, top-left. Transparent padding trimmed automatically. |
| `viabolat.png` | no | Proofing watermark, centered. **`sample_` cuts only.** Wants >= 864px. |
| `config.json` | no | Per-listing overrides: timing, pacing, asset paths. See §4. |

Missing branding files are skipped silently in the build, but the run prints which
ones it found — check those two lines if branding doesn't appear.

Supported photo extensions: `.jpg .jpeg .png .webp .tif .tiff .bmp .heic`

**Run from the folder that holds `photos/`** — normally a listing folder,
`agents/<brand>/<listing>/`. Every path in the script is relative to your working
directory. The one exception: an asset path that does not resolve there is retried
beside `make_tour.py`, which is what lets `viabolat.png` and the shared
`global_assets/` library work from any listing folder without being copied in.

`streamlit run dashboard.py` (from the project root) does all of this through a UI
— see §2. It is a front end, not a separate pipeline: it writes `config.json` and
runs the exact command shown in each scenario below.

---

## 1. Flags

| Flag | Effect |
|---|---|
| `--contact-sheet` | Write `contact_sheet.png` — a numbered grid of `photos/` in build order — and exit. ~1s, no encoding, runs **before** the resolution gate. |
| `--draft` | 720p at a fast preset, **one** cut: `draft.mp4` in the listing root, branded and watermarked. ~1min. Never a deliverable — see §3. |
| *(none)* | 1920x1080. Requires photos >= 2150px wide. |
| `--720p` | 1280x720. Requires photos >= 1433px wide. |
| `--allow-lowres` | Bypass the resolution gate. **Preview only** — see §5. |
| `--no-music` | Silent build. Outputs still carry a silent audio track. |
| `--keep-work` | Keep `clips/` and `work_silent.mp4` so `--finish-only` can reuse them. |
| `--finish-only` | Reuse `work_silent.mp4`, redo music + branding only. Implies `--keep-work`. |

Flags combine freely: `python3 make_tour.py --720p --no-music --keep-work`

`--contact-sheet` ignores everything else and exits. `--draft` forces 720p, so
`--720p` is redundant with it and `--allow-lowres` is implied by intent — a draft
is a preview, and that is what the flag is for. Its intermediates are named apart
(`work_draft.mp4`, `clips_draft/`), so `--draft --finish-only` reuses the previous
*draft's* stitch and can never touch `work_silent.mp4`.

**One build per folder.** The script takes `.build.lock` with `O_EXCL` on startup
and releases it on any exit, clean or not. A second run — CLI or dashboard —
refuses immediately and names the pid holding it.

---

## 2. Scenarios

### Build from the dashboard
```bash
pip install -r requirements.txt     # once
streamlit run dashboard.py
```
Pick brand → listing. The Build tab is three buttons — **Check order**, **Draft**,
**Build delivery** — matching the three rungs below. Logo and music are inherited
from `agents/<brand>/brand.json` and shown as text, not dropdowns; the output preset
is derived from what the photos can actually feed and the delivery button is
disabled when neither preset clears the gate. The lower third is the one per-listing
control left on the main view. Pacing, timing, per-listing asset overrides, a manual
preset, `--no-music` and `--allow-lowres` are under **Advanced**.

It writes `<listing>/config.json`, runs the script with cwd set to that listing, and
streams the log. It picks the build mode for you: `--finish-only` when only
branding, music or timing changed since the last build of that rung, a full
`--keep-work` build when the photos, the pacing, or the output preset changed.
Draft and delivery keep separate records in `.last_build.json`, so a draft can never
authorise a `--finish-only` delivery build.

The **Brand** tab edits `brand.json`. `make_tour.py` never reads that file — the
dashboard resolves `DEFAULTS → brand.json → listing config.json` and writes the
result into the listing, so `config.json` stays the single record of what produced a
delivered video. New listings inherit at creation; existing ones only change when
you use **Re-apply brand defaults**.

The lock belongs to the script, not the dashboard. The dashboard only reads
`.build.lock` to report it, and offers **Clear stale lock** for a killed run.

### Check the order before building anything
```bash
python3 make_tour.py --contact-sheet
```
Writes `contact_sheet.png` — every photo, scaled into a grid, numbered in the exact
order the tour will play. ~1s. This is the cheap answer to the question that cost a
shuffled delivery once already: **look at the sheet before you spend six minutes.**
It runs before the resolution gate, so it works on photos that are not yet good
enough to build with.

### Iterate on an edit
```bash
python3 make_tour.py --draft                 # ~1min, first time
python3 make_tour.py --draft --finish-only   # ~20s, after a branding tweak
```
One 720p cut at a fast preset, written to `draft.mp4` in the listing root. It
carries the lower third, the logo **and** the centered watermark, so every branding
decision is visible at once. Use it to settle pacing, timing and asset choices, then
build the six real cuts once at the end.

`draft.mp4` never enters `out/` and is never a deliverable — see §3.

### Change when the lower third appears
Dashboard: untick **Persistent**, set the two sliders, build. By hand:
```bash
# in the listing folder, config.json:
#   {"brand_persistent": false, "brand_in": 2.0, "brand_out": 8.5}
python3 ../../../make_tour.py --finish-only
```
`brand_out` must be greater than `brand_in` or the build refuses to start — an
inverted window is a valid filtergraph in which the overlay simply never appears.
A `brand_out` past the end of the video warns and leaves the lower third up to the
last frame.

### Build from scratch
```bash
python3 make_tour.py --keep-work
```
Builds all clips, stitches, adds music and branding, writes all **six** cuts.
Runtime scales with photo count — 17 photos takes a few minutes.

`--keep-work` is worth adding by default. Without it the intermediates are deleted
on success and any later branding tweak forces a full rebuild.

### Swap the lower third (agent name, price, phone)
```bash
# replace lower_third.png, then:
python3 make_tour.py --finish-only
```
No code change. The file is re-read every build. ~1 minute instead of a full rebuild.

### Swap the logo
```bash
# replace logo.png, then:
python3 make_tour.py --finish-only
```
Any size or aspect works. Transparent padding is measured and trimmed
automatically, so the mark fills its slot regardless of how it was exported.
The run prints what it did:
```
  logo: logo.png
    logo art 514x273 -> renders 360x191 top-left
```

### Swap the sample watermark
```bash
# replace viabolat.png, then:
python3 make_tour.py --finish-only
```
Affects the three `sample_` cuts only; `tour_` files are untouched. Padding is
trimmed automatically, same as the logo. The build warns if the source is too small
to scale — at 1080p it wants **864px** or more on the long edge.

The run prints what it did, and warns when the source is undersized:
```
  sample watermark: viabolat.png
    watermark art 50x50 -> renders 486x486 centered at 35% opacity
    WARNING: watermark upscales 9.7x and will look soft. Supply at least 864px on the long edge.
```

To change the file it uses, edit `SAMPLE_WATERMARK` at `make_tour.py:165`, or set the `watermark` key in `config.json`.

### Build without the sample cuts
```bash
mv viabolat.png viabolat.png.off
python3 make_tour.py --finish-only
```
The `sample_` files are still written, just without a watermark — which makes them
duplicates of the `tour_` files. Delete them, or keep the watermark in place.

### Swap the music
```bash
# replace music.mp3, then:
python3 make_tour.py --finish-only
```
Short tracks are looped automatically with a 2s crossfade; long ones are trimmed.
Leading and trailing silence is detected and cut.

### Reorder the photos
Rename the numeric prefix. That prefix is the only thing that sets order — there is
no manifest or sidecar file.
```bash
mv photos/07_interior_living2.webp photos/05_interior_living2.webp
python3 make_tour.py --keep-work     # full rebuild required
```
`--finish-only` reuses `work_silent.mp4` and would reship the old order. It warns,
but it does not stop. Drop the flag after any rename.

### Photos arrived with CDN or camera filenames
Files pulled off a listing CDN look like `adr5o9req9xnxs3mopdy.png`; phone dumps look
like `IMG_4417.HEIC`. Neither carries a prefix, so the tour plays in whatever order
those names sort into — **the build succeeds and ships a shuffled walkthrough.**
Rename them before doing anything else:
```bash
cd photos
mv adr5o9req9xnxs3mopdy.png 05_dining_formal.png     # and so on, one per file
```
A workable default running order, adapt per property:

    01 exterior / entry → 02-04 main living spaces → 05-06 dining → 07 kitchen
    → bedrooms → baths → outdoor space last

The run prints `WARNING: N of M filenames do not start with a number` when this is
the situation, and the dashboard raises the same warning above the photo list.

### Add, remove, or replace a photo
```bash
python3 make_tour.py --keep-work     # full rebuild required
```
**`--finish-only` will not pick this up.** It reuses the already-stitched
`work_silent.mp4`, which still contains the old photo set.

Rule of thumb: anything that changes `photos/` needs a full rebuild. Anything that
changes branding or music can use `--finish-only`.

### Build without branding
```bash
mv logo.png logo.png.off
mv lower_third.png lower_third.png.off
python3 make_tour.py
```
Or just use `out/tour_unbranded.mp4`, which already has no branding. Note this also
strips branding from the `sample_` cuts — the watermark survives, since it is not
gated on branding.

### Build silent
```bash
python3 make_tour.py --no-music
```
For when you'll drop your own audio in an editor. Outputs still carry a silent
stereo track so every player and platform handles them normally.

### Quick preview from low-res photos
```bash
python3 make_tour.py --720p --allow-lowres --keep-work
```
Checking pacing, ordering, or branding placement before the real photos arrive.
See §5 before sending the result to anyone.

---

## 3. Outputs

Six files land in `out/`, overwritten on every run. Two families, same edit.

### Delivery — `tour_*`, clean. Send **after** sign-off.

| File | Contents | Use |
|---|---|---|
| `tour_branded.mp4` | Lower third + logo + music | Social, your site, your channels |
| `tour_unbranded.mp4` | Music only, no branding | **MLS / IDX** — required to be clean |
| `tour_vertical.mp4` | 9:16 portrait, blurred side bands | Reels, TikTok, Shorts |

### Sample — `sample_*`, watermarked. Send **for review**.

| File | Contents |
|---|---|
| `sample_branded.mp4` | `tour_branded` + centered watermark |
| `sample_unbranded.mp4` | `tour_unbranded` + centered watermark |
| `sample_vertical.mp4` | `tour_vertical` + centered watermark |

The client watches a `sample_` cut to decide. On approval, deliver the matching
`tour_` file. The watermark sits centered at 45% of frame and 35% opacity —
obscuring the room is the point, so an unapproved cut is not usable as-is.

> **Never send a `sample_` file as a deliverable. Never send a `tour_` file before
> sign-off.** The filename is the safeguard.

The watermark is **not** gated on branding — `sample_unbranded.mp4` carries it too,
otherwise the MLS-safe cut would be an unwatermarked free copy.

Runtime = `photos x 4s - (photos - 1) x 0.5s`. 17 photos = 60.0s.

Note: both vertical cuts are built *from* their branded sibling, so branding ghosts
into the blurred bands.

### Draft — `draft.mp4`, listing root. Never leaves this machine.

`--draft` writes one file, and deliberately **not** into `out/`: `out/` holds real
cuts only, which is what makes the `tour_`/`sample_` prefix a boundary you can trust
at a glance. A draft is 720p at a fast x264 preset and carries the watermark. It is
a review rung for you, not for the client — the client reviews a `sample_` cut.

Its intermediates are `work_draft.mp4` and `clips_draft/`, named apart from the
delivery ones so a draft-quality stitch can never be picked up by a delivery build.

---

## 4. Tuning

Constants marked **cfg** are also `config.json` keys — set them per listing without
touching the script. The rest are code edits that apply to every listing.

| Line | Constant | cfg key | Default | Effect |
|---|---|---|---|---|
| 146 | `CLIP_SECONDS` | `clip_seconds` | `4.0` | Seconds per photo |
| 147 | `XFADE_SECONDS` | `xfade_seconds` | `0.5` | Crossfade length |
| 149 | `ZOOM_MAX` | — | `1.12` | Ken Burns push. Above ~1.20 looks cheap. |
| 150 | `MUSIC_VOLUME` | — | `0.55` | Soundtrack level |
| 153 | `BRAND_PERSISTENT` | `brand_persistent` | `True` | `False` = lower third only during a window |
| 154-155 | `BRAND_IN` / `BRAND_OUT` | `brand_in` / `brand_out` | `0.8` / `6.5` | That window, when `BRAND_PERSISTENT` is `False` |
| 156 | `LOGO_PERSISTENT` | — | `True` | Same, for the logo — but see the note below |
| 157 | `LOGO_BOX_W, LOGO_BOX_H` | — | `360, 200` | Logo size box, 1080p-relative (~19% frame width) |
| 160-162 | `LOWER_THIRD` / `LOGO` / `MUSIC` | `lower_third` / `logo` / `music` | the plain filenames | Which files the build uses |
| 165 | `SAMPLE_WATERMARK` | `watermark` | `"viabolat.png"` | Which file the sample cuts watermark with |
| 169 | `SAMPLE_WM_FRAC` | — | `0.45` | Watermark size, fraction of the frame |
| 170 | `SAMPLE_WM_OPACITY` | — | `0.35` | Watermark opacity, 0-1 |
| 184-185 | `CRF` / `X264_PRESET` | — | `18` / `medium` | Delivery encode quality. `--draft` swaps these to `20` / `veryfast`. |
| 186 | `VERTICAL_CRF` | — | `20` | Portrait cut, which re-encodes an already-encoded source |
| 210 | `MARGIN` | — | `70 * SCALE` | Overlay inset from the frame edge |
| 571 | `CELL_W, CELL_H` | — | `480, 270` | Contact sheet cell. 4 across = a 1920px sheet. |

Branding, watermark and music changes need only `--finish-only`. Changing
`CLIP_SECONDS`, `XFADE_SECONDS` or `ZOOM_MAX` requires a full rebuild — they
reshape the clips themselves, and `--finish-only` reuses the stitched cut.

Setting `LOGO_PERSISTENT = False` makes the logo reuse `BRAND_IN`/`BRAND_OUT` —
the enable window in `finish()` is shared by every non-persistent layer. Give the
logo its own window before relying on that.

Raising `ZOOM_MAX` also raises the resolution requirement — the gate is
`OUT_W x ZOOM_MAX`.

`WORK_W` (line 205) is **not** a tuning knob. The comment above it records measured
frame-to-frame judder against supersample factor; `7680` is the knee for both
presets. Lowering it to "speed up 720p" reintroduces the judder it exists to remove.

---

## 5. The resolution gate

The script refuses to build if photos are too small, printing a per-file table:

```
17 of 17 photos are below 2150px wide:
  01_exterior_front.webp              768x576  upscaled 2.8x
  02_exterior_street.png              384x288  upscaled 5.6x
  03_exterior_entrance.webp         1440x1080  upscaled 1.5x
  ...
  --allow-lowres set: building anyway, expect soft output.
```

| Preset | Output | Minimum source width |
|---|---|---|
| default | 1920x1080 | **2150px** |
| `--720p` | 1280x720 | **1433px** |

The minimum is output width x `ZOOM_MAX` — the zoom crops *into* the photo, so the
pipeline needs more pixels than the final frame.

**`--allow-lowres` only silences the gate. It does not improve anything.** Upscaling
a 384px photo to 1920px smears what's there; there is no detail to recover.

> **`--allow-lowres` is for previews only. Never for anything a client or the MLS
> sees. If a build needs the flag, the photos are not ready.**

The fix is always better sources — the listing photographer's originals or the MLS
back end. See `IDEA.md` §2.

---

## 6. Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `No photos found` | Empty `photos/`, or unsupported extensions | Check §0 extension list |
| Resolution table, then exit | Photos below the gate | Get real photos (`IDEA.md` §2). Not the flag. |
| `music.mp3 is missing, empty, or has no audio stream` | Bad or absent track | Replace it, or `--no-music` |
| Branding missing from output | Filename typo, or a `config.json` path that resolves nowhere | Check the `lower third:` / `logo:` lines in the run output — they print the resolved path |
| `brand_out (N) must be greater than brand_in (N)` | Inverted timing window | Fix `config.json`. The overlay would never appear. |
| `WARNING: brand_out Ns is past the ...s runtime` | Window ends after the video does | Harmless — the lower third stays up to the last frame. Shorten it if that is not what you wanted. |
| Lower third appears despite a window | Overlay set to persistent | `brand_in`/`brand_out` are read only when `brand_persistent` is `false` |
| Logo is an opaque box | PNG has no alpha channel | Re-export as RGBA |
| `WARNING: watermark upscales N.Nx` | `viabolat.png` too small | Supply >= 864px on the long edge |
| `sample_` files identical to `tour_` | Watermark file missing | Check the `sample watermark:` line in the run output |
| `--finish-only` did a full rebuild | No `work_silent.mp4` to reuse | Expected fallback. It says so and continues. |
| `WARNING: N of M filenames do not start with a number` | Photos still carry CDN or camera names | Rename to `01_`, `02_`, ... **before** delivering. The order is alphabetical, not yours. See §2 |
| Rooms play in the wrong order | Prefixes wrong, or a rename was rebuilt with `--finish-only` | Fix the prefixes, then a full rebuild with `--keep-work` |
| `WARNING: --finish-only reuses that earlier stitch` | Photos may have changed since `work_silent.mp4` was made | If they did, drop the flag. If they did not, ignore it. |
| Photo change didn't appear | Used `--finish-only` | Full rebuild — see §2 |
| Files vanished after a run | Successful builds clean up | Use `--keep-work` |
| `A build is already running here (pid N)` | Another build holds `.build.lock` | Wait for it. If that pid is gone, delete `.build.lock` — or use the dashboard's **Clear stale lock** |
| Delivered video looks soft | Shipped `draft.mp4`, or a `--draft` cut renamed | Drafts are 720p at a fast preset. Rebuild without `--draft`; deliverables come out of `out/` |
| `draft.mp4` didn't pick up a photo change | Used `--draft --finish-only` | Same rule as delivery — anything that changes `photos/` needs a full run |
| Contact sheet disagrees with the video | Sheet regenerated after a rename, video built before it | The sheet is always current; rebuild fully with `--keep-work` |

**A failed build keeps its intermediates on purpose** so you can inspect them. Only a
successful run cleans up.

**Locking.** The script takes `.build.lock` with `O_EXCL` at startup and releases it
on any exit, clean or not, so two builds in one folder can no longer delete each
other's intermediates — whichever starts second refuses and names the pid holding
the lock. This covers the CLI and the dashboard equally, since the dashboard builds
by running the script. If a run was killed hard enough to leave the file behind,
delete `.build.lock` or use the dashboard's **Clear stale lock** button.
