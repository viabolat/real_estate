# IDEA.md — Photo Sourcing Standard for `make_tour.py`

Reference for getting consistent, high-quality source photos into the tour pipeline.
The video generator is solved; **source resolution is the only remaining ceiling on output quality.**

---

## 1. THE STANDARD

**3000px+ on the long edge. JPEG or WebP. Straight from the original file.**

That survives a 1080p build with room left over to crop and Ken-Burns into.
Anything below it is a preview, not a deliverable.

### Why those numbers

`make_tour.py` derives its gate from the output preset and the zoom range:

```
MIN_PHOTO_W = OUT_W * ZOOM_MAX
```

| Preset | Output | Minimum source width | Comfortable source width |
|---|---|---|---|
| `--720p` | 1280x720 | **1433px** | 2000px+ |
| default | 1920x1080 | **2150px** | 3000px+ |

The minimum is the *hard floor* where the deepest zoom stops inventing pixels.
The comfortable column is where the image still looks sharp after motion and encode.

---

## 2. SOURCING LADDER — best first

### 1. The photographer  ⭐ ends the problem permanently
It is your listing; you or the brokerage paid for the shoot. Ask for the delivery
gallery or the original export set. Real estate shooters deliver 3000-4000px as
standard and usually still have the files. **This is the correct answer.**

### 2. Your MLS back end
Flexmls, Matrix, Paragon — whatever your board runs. The agent-side photo manager
holds the full-resolution uploads, not the syndicated downsamples. Bulk-download
from the listing's photo tab.

### 3. Your own originals
If the shoot was in-house: the camera or phone files. **Not** anything that has been
through a messaging app — iMessage, WhatsApp, and SMS all recompress and downscale.

### 4. Zillow CDN variant swap — 720p ONLY, fallback not plan
The `-cc_ft_384` suffix in a Zillow filename **is the pixel width**. The hash prefix
stays constant across variants, so it is a mechanical rewrite:

```
https://photos.zillowstatic.com/fp/<hash>-cc_ft_384.webp                        ->  384px
https://photos.zillowstatic.com/fp/<hash>-cc_ft_1536.webp                       -> ~1440px
https://photos.zillowstatic.com/fp/<hash>-uncropped_scaled_within_1536_1152.webp -> ~1440px  (largest public variant)
```

**Zillow's CDN cannot reach 1080p.** Its largest public variant is ~1440px, which clears
the 720p gate (1433px) by 7px and fails the 1080p gate (2150px). No amount of URL
fiddling fixes this — you must go upstream of Zillow.

---

## 3. WHAT NOT TO DO

### ❌ Screenshots, or right-click "Save image as" off the listing page
**This is the single biggest cause of low-resolution source photos.** The browser saves
the *rendered* size, not the intrinsic file. A photo displayed at 375x281 in a listing
carousel saves as 375x281 no matter how large the underlying image is.

To see the real size: DevTools > Elements > hover the `<img>`. It reports
`375 x 281 (natural: 1536 x 1152)` — the second pair is what you actually want.

### ❌ AI upscaling / "enhance"
It invents detail that is not in the room. On a property listing that is
misrepresentation, not a quality fix — and it becomes a problem precisely when a deal
goes sideways. Upscalers routinely fabricate fixtures, window views, and trim detail.

### ❌ Building deliverables with `--allow-lowres`
That flag exists for previews. See §4.

### ❌ Re-encoding through chat apps, Google Photos "storage saver", or email compression
Every hop downsamples. Move files with a zip, a drive link, or a USB stick.

---

## 4. ENFORCEMENT — already baked into the script

`check_resolution()` hard-exits before any encoding work, printing a per-photo table
with the exact upscale factor each file would need:

```
17 of 17 photos are below 1433px wide:
  01_exterior_front.webp              768x576  upscaled 1.9x
  02_exterior_street.png              384x288  upscaled 3.7x
  ...
```

**The working rule:**

> `--allow-lowres` is for previews only. Never for anything a client or the MLS sees.
> **If a build needs the flag, the photos are not ready.**

The gate *is* the consistency mechanism. If it builds clean, quality is guaranteed by
construction — you cannot accidentally ship a soft tour.

---

## 5. THE ACTUAL WORKFLOW

1. Get originals from the photographer or the MLS back end (§2.1 / §2.2).
2. Drop them in `photos/` using the existing ordering convention:
   `01_exterior_front.jpg`, `02_exterior_street.jpg`, ... `17_exterior_courtyard.jpg`
   The numeric prefix sets tour order; the rest of the name is for your own reference.
   Supported extensions: `.jpg .jpeg .png .webp .tif .tiff .bmp .heic`
3. Run without `--allow-lowres`:
   ```bash
   python3 make_tour.py
   ```
4. If it exits with the resolution table, go back to step 1. Do not reach for the flag.

---

## 6. CURRENT STATE (as of 2026-08-19)

The 17 photos in `photos/` are Zillow-sourced downsamples:

- 11 files at **384x288** — need 3.7x upscale for 720p, 5.6x for 1080p
- 5 files at **768x576** — need 1.9x upscale for 720p, 2.8x for 1080p
- 1 file at **1440x1080** — the only file that clears the 720p gate

Every build to date has required `--allow-lowres`, which is why the output is soft and
why clips built from the 768px files visibly outclass the rest.

**Action required:** request the original export set from the listing photographer, or
pull full-resolution files from the MLS back end. Nothing else moves the quality needle.

---

## 7. ORDERING NOTE

Photo order is baked into the filename prefix and nothing else — no sidecar file, no
manifest, no lookup table. Rename to reorder. This is deliberate: an external ordering
file is a temporary fix that drifts out of sync with the folder.

---

## 8. PROPOSED, NOT BUILT — review later

> **Scope note:** §1-7 above are the photo sourcing standard. This section is a
> branding/output backlog and is *not* part of that standard. It lives here only as
> the agreed parking spot for proposals. Nothing below is implemented; nothing below
> is approved.

Both items were proposed on 2026-08-19 while adding the logo overlay and the
`sample_` cuts. Both were deferred, not rejected.

### 8.1 Programmatic drop shadow on the logo

**Problem.** `logo.png` is thin line art with a dark wordmark. On light backgrounds —
which is most of this listing's top-left corners: cream cabinets, pale walls — it
washes out and becomes hard to read. Enlarging it made this more visible, not less.
Baking a shadow into the PNG fixes one logo; the next brokerage logo has the problem
again.

**Why programmatic.** Same principle as `alpha_bbox()` auto-trim: the operator should
not have to inspect and hand-tune every asset. Contrast is a property of the
*composite*, not of the logo file, so the pipeline is the right place to solve it.

**Sketch.** In `finish()`, split the scaled logo, zero its RGB to black via
`colorchannelmixer`, blur the result, offset it a few px, and overlay it beneath the
logo. Needs a `pad` first or the blur clips at the layer edge.

**Open questions.**
- Shadow vs. outline vs. a soft scrim behind the mark — shadow is the most neutral,
  outline survives busier backgrounds.
- Does it also apply to the `sample_` watermark, or only the corner logo?
- New constants (`LOGO_SHADOW`, sigma, opacity, offset) or one on/off toggle?

**Risk.** The filtergraph is more brittle than the current one — `gblur` behaviour on
the alpha plane needs verifying per ffmpeg build. Test before trusting.

### 8.2 Brand card on the outro

**Problem.** A corner watermark provides *presence*; it cannot provide *identity*.
Trying to get identity out of it is what pushes toward a bigger, more centered mark —
which competes with the room. A dedicated card sidesteps that tradeoff entirely.

**Recommendation: tail only. Do not add a head card.** On Reels/TikTok/Shorts the
first 1-2 seconds decide whether anyone keeps watching. Opening on a brokerage logo
instead of the property loses that audience. A 2.5-3s card at the tail, where the
video is already fading, costs nothing and is where contact info actually gets read.

**Sketch.** Generate a card segment (logo + agent + contact, on a solid or blurred
ground) and concat it after the tour inside `finish()`, before the fades are applied
— or as a separate segment with its own short fade.

**Open questions.**
- Reuse `lower_third.png` artwork, or a separate `outro.png`?
- Does the card appear on `tour_unbranded.mp4`? Almost certainly **no** — it is
  branding, and that cut must stay MLS/IDX-clean.
- Does the `sample_` family get it? Probably yes, so the client reviews the real edit.
- Music: does the tail fade need re-timing to land on the card instead of the last
  photo? Likely yes — `finish()` currently pins the audio fade to `dur`.
- Vertical cut: the card must be legible at 9:16, which a 16:9 card letterboxed into
  portrait may not be.

**Blocked on.** Neither is worth building against 384px photos. Revisit once real
source photos land (§2).
