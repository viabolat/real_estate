---
name: constraints
type: reference
---

# Known constraints

Things that are true and not going to change soon: platform limits, deliberate
asymmetries, and bugs that were found, understood and fixed — kept because the
reasoning stops them being reintroduced.

- Zillow's CDN tops out at ~1440px (`uncropped_scaled_within_1536_1152`). That
  clears 720p and fails 1080p. 1080p requires the photographer's originals or the
  MLS back end.
- `make_tour.py` takes `.build.lock` with `O_EXCL` at startup and releases it via
  `atexit` on any exit, clean or not, so two runs can no longer corrupt each other's
  intermediates. `tour.py` only *reads* the lock to report it — it must never write
  it, or the build it launches would be locked out of its own folder.
- `finish()` applies `BRAND_IN`/`BRAND_OUT` to *any* non-persistent layer, not just
  the lower third. Nothing is broken today — the logo is always persistent — but
  giving the logo its own window means adding `LOGO_IN`/`LOGO_OUT` and making the
  window per-layer, not reusing the brand one. With an intro card the window shifts
  by the card's length, so `brand_in: 0.8` still means 0.8s into the *photos*.
- With a card, the branded cut outruns the unbranded one, so `vertical()` pads the
  blurred band with `tpad=stop_mode=clone` and pins the output to the branded
  length. The band holds the last blurred room frame behind the card rather than
  ending early. Without a card the pad is not emitted and the output is unchanged.
- `--finish-only` reuses `work_silent.mp4`, which was stitched from the photo list as
  it stood at the time. Renaming photos to reorder them therefore does **not** reach
  a `--finish-only` build — it would reship the old order. The CLI warns; `tour.py`
  withholds the flag outright once `photo_state()` changes. It withholds
  it for a changed `card` or `card_seconds` too — the card rides in the branded
  stitch, so changing it invalidates that intermediate exactly like the pacing keys.
- The centered sample watermark wants a source at least 864px on the long edge at
  1080p. `viabolat.png` is currently 50x50 and upscales ~9.7x; the build warns.
- `prepare_music()` loops a short track by crossfading it onto itself, so its length
  step is `length*2 - d`. That has a fixed point at `d`: with the seam pinned to
  `MUSIC_XFADE` a 2.0s body never grew and anything shorter ran negative, and the
  loop never exited — a **hang**, with no error and no output. The seam is now
  `min(MUSIC_XFADE, body/2)`, which is `MUSIC_XFADE` exactly for any body ≥ 4s, so
  real tracks are unaffected. `MUSIC_LOOP_MAX` is the backstop.
- Every fit box is `min(BOX_W / aw, BOX_H / ah)`, so an asset that exists but cannot
  be decoded — a 0-byte or truncated PNG — divided by zero *inside `finish()`*, after
  every clip had already been rendered. `image_ok()` is the `music_ok()` of images and
  is checked before any fit box.
- `status.py` is read-only and must survive whatever is in `photos/`. A **directory**
  named `01_front.jpg` matched the extension filter and raised `IsADirectoryError` out
  of `jpeg_size()`, killing the whole report over one bad entry. Both it and
  `make_tour.py` now require `os.path.isfile`.
- `tour.py`'s "+ New brand / + New listing" takes typed text, which is hand-naming —
  the thing the scrape-naming rule exists to prevent. It cannot be removed without
  losing the no-dump path, so it applies `make_tour._slug` to whatever is typed and
  says out loud that the folder will read as *unverifiable* until it is scraped.
- `status.next_action()` merges `brand.json` **under** the listing's `config.json`
  before the asset checks, mirroring `tour.load_config()`. Without it a listing that
  inherits its logo — which is the normal case — reported `logo blank/missing`
  forever. Any new asset check in `status.py` must read the merged config, not the
  listing's file alone.
