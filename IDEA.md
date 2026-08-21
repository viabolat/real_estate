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

### ❌ Sending a `_lowres` cut to the MLS
`--allow-lowres` builds; it does not fix. Every cut it produces is named
`..._lowres.mp4` precisely so that this stays visible after the console has
scrolled away. See §4.

### ❌ Re-encoding through chat apps, Google Photos "storage saver", or email compression
Every hop downsamples. Move files with a zip, a drive link, or a USB stick.

---

## 4. ENFORCEMENT — already baked into the script

`check_resolution()` runs before any encoding work and prints a per-photo table with
the exact upscale factor each file would need, plus the worst offender:

```
17 of 17 photos are below 1433px on the long edge, which is what 1280x720 needs:
  01_exterior_front.webp              768x576  upscaled 1.9x
  02_exterior_street.png              384x288  upscaled 3.7x
  ...
  worst: 02_exterior_street.png at 384x288, upscaled 3.7x
```

From the bare CLI it then exits, naming the pixel target and the way out.
With `--allow-lowres` it builds — and **names every cut `..._lowres.mp4`.**

**The working rule:**

> A `_lowres` cut is a review copy. Never send one to a client or the MLS.
> **If a build needs the flag, the photos are not ready.**

### Why the gate marks instead of refusing

It used to refuse, full stop — including in `tour.py`, at the *end* of a run, after
the question set and a draft had already been paid for, despite having computed the
identical verdict at preflight in the first second. That failed twice over: it threw
away ten minutes of the operator's work, and the refusal text named no count, no
size and no target, so there was nothing to act on.

The gate is unchanged as a *measurement*. What changed is the consequence: it now
decides what the files are **called**. That is a stronger boundary, not a weaker one
— a console refusal protects nothing once the operator reaches for the flag, whereas
`jane_smith_tour_unbranded_lowres.mp4` still says what it is three weeks later in
somebody's downloads folder. `tour.py` states the count, the worst offender and its
upscale factor *before* it builds, and says plainly that the result is not MLS-ready.

Stripping the tag is a deliberate two-hand act — rename the file yourself — which is
the point.

---

## 5. THE ACTUAL WORKFLOW

`python3 tour.py` from the project root walks every step below in order: it picks or
creates the listing, copies the photos in, offers the prefixes, prints the preflight
(order, which presets the photos clear, which assets and text fields are missing)
**before** anything encodes, asks the handful of questions that actually vary, and
then walks the three rungs. Photos that fail the gate still build — at 720p, named
`_lowres`, after it has told you the count, the worst file and its upscale factor.
It writes the answers into `config.json` and runs the exact commands spelled out
below — the steps are what it does, not an alternative to it.

1. Get originals from the photographer or the MLS back end (§2.1 / §2.2).
2. Drop them in the listing's `photos/` — `agents/<brand>/<listing>/photos/` — using
   the existing ordering convention:
   `01_exterior_front.jpg`, `02_exterior_street.jpg`, ... `17_exterior_courtyard.jpg`
   The numeric prefix sets tour order; the rest of the name is for your own reference.
   **Rename CDN or camera filenames before anything else.** Files straight off a
   listing CDN (`adr5o9req9xnxs3mopdy.png`) carry no prefix, so the tour plays in
   whatever order the hashes sort into — the build still succeeds, it just ships a
   shuffled walkthrough. The CLI warns and `tour.py` says the same in its preflight
   — and offers to add the prefixes in the current alphabetical order — but a
   warning is only useful if you read it.
   Supported extensions: `.jpg .jpeg .png .webp .tif .tiff .bmp .heic`
3. **Check the order before spending anything on an encode.**
   ```bash
   cd agents/<brand>/<listing> && python3 ../../../make_tour.py --contact-sheet
   ```
   ~1s, no encoding. Writes `contact_sheet.png` — every photo in a numbered grid, in
   the exact order the tour will play. It runs *before* the resolution gate on
   purpose: "are these in the right order" is worth answering on photos that are not
   yet good enough to build with. `tour.py` runs this rung first and stops for you
   to look. `python3 tour.py --check-photos` will additionally hand the sheet to
   Claude to name the rooms and flag filenames that disagree with the image — it
   proposes renames and renames nothing, and it is off unless you ask for it.
4. Settle the edit on a draft, not on deliverables:
   ```bash
   python3 ../../../make_tour.py --draft
   ```
   ~1min, one 720p cut at `draft.mp4` — branded and watermarked, so pacing, timing
   and every branding choice show at once. Iterate here. `draft.mp4` is never a
   deliverable and never enters `out/`.
5. Run without `--allow-lowres`, from the listing folder:
   ```bash
   python3 ../../../make_tour.py
   ```
   Or let `tour.py` do it — it derives the preset from what the photos can actually
   feed, and drops to 720p + `--allow-lowres` only when neither preset clears, after
   naming the shortfall.
6. If it exits with the resolution table, go back to step 1. A `_lowres` build is a
   review copy to keep the job moving, not the answer to the table.

The gate is a property of the photos, not of the interface. `tour.py` runs the same
script and measures the same wall; what it will not do is hand you a `_lowres` file
without saying so, or let one lose the tag on its way out.

---

## 6. CURRENT STATE (as of 2026-08-19)

> **Historical snapshot.** This describes one folder before the `agents/` layout and
> the scraper existed. It is kept because it is the evidence the sourcing argument
> below rests on. For the live picture across every listing, run `python3 status.py`
> or see `PROGRESS.md` §3.


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

The tradeoff is that a folder with **no** prefixes still builds — `make_tour.py` sorts
the filenames it finds, and unprefixed names sort into an order nobody chose. That is
not hypothetical: `46_beacon_5` was delivered from Zillow hashes and opened on a dining
room, with the entry hall third and the roof terrace second-to-last. Nothing errored.

Three guards exist now, and all three should stay:

- Every build prints the resolved order as a numbered list before encoding, and warns
  when filenames carry no numeric prefix.
- `tour.py` prints the same list in its preflight, says so when any photo is
  unprefixed, and offers to add the prefixes in the current alphabetical order — a
  rename on disk, which is where the order lives, never a sidecar.
- `--contact-sheet` renders the order as an image in about a second, so checking it
  costs nothing. A numbered list catches a missing prefix; only the sheet catches
  "the entry hall is third." Look at it before the first real build.

A sensible default running order, adapt per property:

    01 exterior / entry → 02-04 main living spaces → 05-06 dining → 07 kitchen
    → bedrooms → baths → outdoor space last

Renaming to reorder invalidates both stitches, `work_silent.mp4` and
`work_branded.mp4`. Rebuild fully — a `--finish-only` run reuses them and reships the
old order.

---

## 8. BRANDING / OUTPUT BACKLOG

> **Scope note:** §1-7 above are the photo sourcing standard. This section is a
> branding/output backlog and is *not* part of that standard. It lives here only as
> the agreed parking spot for proposals.

Both items were proposed on 2026-08-19 while adding the logo overlay and the
`sample_` cuts. Both were deferred, not rejected. **8.1 is still parked. 8.2 was
built on 2026-08-20** — its entry below is kept as the record of what was decided
and why, because the reasoning is what makes the default defensible later.

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

**Blocked on.** Not worth building against 384px photos. Revisit once real source
photos land (§2).

### 8.2 Brand card on the outro — **BUILT 2026-08-20**

**Problem.** A corner watermark provides *presence*; it cannot provide *identity*.
Trying to get identity out of it is what pushes toward a bigger, more centered mark —
which competes with the room. A dedicated card sidesteps that tradeoff entirely.

**Recommendation as written: tail only. Do not add a head card.** On
Reels/TikTok/Shorts the first 1-2 seconds decide whether anyone keeps watching.
Opening on a brokerage logo instead of the property loses that audience. A 2.5-3s
card at the tail, where the video is already fading, costs nothing and is where
contact info actually gets read.

**What shipped, and where it differs.** The operator asked for an intro option as
well, so the recommendation became the **default** rather than a prohibition: `card`
is `none` for a bare CLI run, `tour.py` writes `outro` on a new listing, and `intro`
or `both` is an explicit opt-in you have to choose. The retention argument above is
the reason the default is what it is — read it before switching a listing to `both`.

**How it was answered.**

| Question | Answer as built |
|---|---|
| Reuse `lower_third.png`, or a separate `outro.png`? | Neither. Both plates are **drawn by ffmpeg `drawtext`** from `address` / `agent_name` / `agent_phone` / `brokerage` in `config.json`. No Canva round trip, one text source, and a listing cannot be shipped carrying another listing's plate. A hand-made `lower_third.png` still wins if one exists. |
| Does the card appear on the `_tour_unbranded` cut? | **No**, and not by a flag — by construction. The card rides in a second stitch, `work_branded.mp4`; the unbranded cuts read `work_silent.mp4`, which is photos only. |
| Does the `sample_` family get it? | Yes — same edit, so the client reviews the real thing. The centered watermark is deliberately **not** held off over the card: an unwatermarked outro card is exactly the frame an unapproved sample would be screenshot from. |
| Music re-timed to land on the card? | Yes. The audio fade is pinned to the branded duration, which now includes the card. |
| Legible at 9:16? | Verified. The vertical band is clone-padded and the output pinned to the branded length, so the last blurred room frame holds behind the card instead of the band ending early. |

Two things the sketch did not anticipate, both found by building it:

- `stitch()` computed each crossfade offset as `i * (CLIP_SECONDS - XFADE_SECONDS)`.
  A card of a different length desyncs every transition after it, and the build still
  succeeds — the same silent-failure shape as the shuffled photo order. Offsets now
  accumulate real durations.
- The lower third and the top-left logo ran *over* the card, printing the address and
  the mark twice. Branding is now held off for the card's span.

**Layout.** It picks itself: a logo that resolves gets the logo layout, no logo gets
type-only with the brokerage in its place, and a card with no text at all is not
built — the run says so rather than shipping an empty frame. `card_style`,
`card_theme`, `accent` and `font` override. See `STEPS.md` §3-4.
