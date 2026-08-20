# STEPS.md — Runbook for `make_tour.py`

Every scenario the script covers and the exact command for it.
For photo sourcing and resolution rules, see `IDEA.md`. For project rules, `CLAUDE.md`.

---

## 0. What the script expects

| Path | Required | Notes |
|---|---|---|
| `photos/` | **yes** | Numbered in tour order: `01_exterior.jpg`, `02_entry.webp`, ... |
| `music.mp3` | no | A **licensed** track. Skip with `--no-music`. |
| `lower_third.png` | no | Agent + listing info. Full-frame 1920x1080 plate, or a small strip. |
| `logo.png` | no | Brokerage mark, top-left. Transparent padding trimmed automatically. |
| `viabolat.png` | no | Proofing watermark, centered. **`sample_` cuts only.** Wants >= 864px. |

Missing branding files are skipped silently in the build, but the run prints which
ones it found — check those two lines if branding doesn't appear.

Supported photo extensions: `.jpg .jpeg .png .webp .tif .tiff .bmp .heic`

**Always run from inside this directory.** Every path in the script is relative to
your working directory, not to the script's location.

---

## 1. Flags

| Flag | Effect |
|---|---|
| *(none)* | 1920x1080. Requires photos >= 2150px wide. |
| `--720p` | 1280x720. Requires photos >= 1433px wide. |
| `--allow-lowres` | Bypass the resolution gate. **Preview only** — see §5. |
| `--no-music` | Silent build. Outputs still carry a silent audio track. |
| `--keep-work` | Keep `clips/` and `work_silent.mp4` so `--finish-only` can reuse them. |
| `--finish-only` | Reuse `work_silent.mp4`, redo music + branding only. Implies `--keep-work`. |

Flags combine freely: `python3 make_tour.py --720p --no-music --keep-work`

---

## 2. Scenarios

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

To change the file it uses, edit `SAMPLE_WATERMARK` at `make_tour.py:69`.

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

---

## 4. Tuning (edit `make_tour.py`, no flag)

| Line | Constant | Default | Effect |
|---|---|---|---|
| 57 | `CLIP_SECONDS` | `4.0` | Seconds per photo |
| 58 | `XFADE_SECONDS` | `0.5` | Crossfade length |
| 60 | `ZOOM_MAX` | `1.12` | Ken Burns push. Above ~1.20 looks cheap. |
| 61 | `MUSIC_VOLUME` | `0.55` | Soundtrack level |
| 63 | `BRAND_PERSISTENT` | `True` | `False` = lower third only during a window |
| 64 | `BRAND_IN, BRAND_OUT` | `0.8, 6.5` | That window, when `BRAND_PERSISTENT` is `False` |
| 65 | `LOGO_PERSISTENT` | `True` | Same, for the logo |
| 66 | `LOGO_BOX_W, LOGO_BOX_H` | `360, 200` | Logo size box, 1080p-relative (~19% frame width) |
| 69 | `SAMPLE_WATERMARK` | `"viabolat.png"` | Which file the sample cuts watermark with |
| 70 | `SAMPLE_WM_FRAC` | `0.45` | Watermark size, fraction of the frame |
| 71 | `SAMPLE_WM_OPACITY` | `0.35` | Watermark opacity, 0-1 |
| 91 | `MARGIN` | `70 * SCALE` | Overlay inset from the frame edge |

After changing any of lines 63-91, `--finish-only` is enough. Changing 57-60 requires
a full rebuild.

Raising `ZOOM_MAX` also raises the resolution requirement — the gate is
`OUT_W x ZOOM_MAX`.

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
| Branding missing from output | Filename typo | Check the `lower third:` / `logo:` lines in the run output |
| Logo is an opaque box | PNG has no alpha channel | Re-export as RGBA |
| `WARNING: watermark upscales N.Nx` | `viabolat.png` too small | Supply >= 864px on the long edge |
| `sample_` files identical to `tour_` | Watermark file missing | Check the `sample watermark:` line in the run output |
| `--finish-only` did a full rebuild | No `work_silent.mp4` to reuse | Expected fallback. It says so and continues. |
| Photo change didn't appear | Used `--finish-only` | Full rebuild — see §2 |
| Files vanished after a run | Successful builds clean up | Use `--keep-work` |

**A failed build keeps its intermediates on purpose** so you can inspect them. Only a
successful run cleans up.

**No locking.** Two builds in this directory at the same time will collide — one
run's cleanup deletes files the other is still using. Run one at a time.
