# CLAUDE.md — Real Estate Photo Tour Generator

Project-level context. Loaded automatically each session, alongside the global
`~/.claude/CLAUDE.md` baseline (which it does not override).

## What this project is

`make_tour.py` turns a folder of still listing photos into a branded walkthrough
video with music. Single script, no dependencies beyond `ffmpeg` / `ffprobe`.

`dashboard.py` is a local Streamlit front end over it — shared asset library, UI
timing controls, per-listing settings, live build log. It is the only part of the
project with a third-party dependency (`requirements.txt`); the script itself has
none, and everything the dashboard does can still be done from the CLI.

Reads from the **working directory**, which is normally a listing folder:

| Path | Required | Purpose |
|---|---|---|
| `photos/` | yes | Numbered in tour order; the prefix *is* the order |
| `music.mp3` | no | Licensed track. `--no-music` to skip. |
| `lower_third.png` | no | Agent + listing info |
| `logo.png` | no | Brokerage mark, top-left |
| `viabolat.png` | no | Proofing watermark, centered, `sample_` cuts only |
| `config.json` | no | Per-listing overrides — timing, pacing, asset paths |

Any asset path that does not resolve against the working directory is retried
beside `make_tour.py`, so the shared library and `viabolat.png` keep working from
any listing folder. All are read fresh every build — swapping any of them needs
only `--finish-only`.

## Layout

```
agents/<brand>/<listing>/     photos/, config.json, out/  — cwd for a build
global_assets/logos/          shared branding, referenced by config.json
global_assets/music/
global_assets/lower_thirds/
```

`config.json` — every key optional, defaults are the constants in the source:

| Key | Default | Note |
|---|---|---|
| `clip_seconds` | `4.0` | forces a full rebuild when changed |
| `xfade_seconds` | `0.5` | forces a full rebuild when changed |
| `brand_persistent` | `true` | `false` = lower third only inside the window below |
| `brand_in` / `brand_out` | `0.8` / `6.5` | only read when not persistent; out > in |
| `lower_third` / `logo` / `music` / `watermark` | the plain filenames | repo-relative paths into `global_assets/` |

Outputs **six** cuts to `out/`, in two families:

**Delivery** — clean, what the client gets on sign-off:
- `tour_branded.mp4`   — lower third + top-left logo, for social / your own channels
- `tour_unbranded.mp4` — no branding, MLS/IDX-safe
- `tour_vertical.mp4`  — 9:16 portrait cut with blurred side bands

**Sample** — identical edit plus a centered proofing watermark (`viabolat.png`),
what the client reviews before paying:
- `sample_branded.mp4`
- `sample_unbranded.mp4`
- `sample_vertical.mp4`

The watermark is deliberately **not** gated on the `branded` flag — it is the entire
reason a sample cut exists, so it appears on `sample_unbranded.mp4` too.

## READ FIRST: `IDEA.md`

**`IDEA.md` is the photo sourcing standard and is required reading before any work
on image quality.** §1-7 cover the resolution gates and where they come from, the
sourcing ladder, what not to do, and the current state of `photos/`.

`IDEA.md` §8 is a separate **branding/output backlog** — proposed, not approved, not
built. It is parked there by agreement and is not part of the sourcing standard.

Do not re-derive or re-litigate that guidance — it was established through
measurement, not assumption.

## Non-negotiables

- **`--allow-lowres` is for previews only.** Never for anything a client or the MLS
  sees. If a build needs the flag, the photos are not ready. See `IDEA.md` §4.
- **No AI upscaling of listing photos.** It fabricates detail that is not in the
  room, which on a property listing is misrepresentation. See `IDEA.md` §3.
- **Photo order lives in the filename prefix and nowhere else.** No sidecar file, no
  manifest, no lookup table — those drift out of sync with the folder. Rename to
  reorder. `config.json` and `.last_build.json` carry timing, pacing, asset paths
  and build state **only**; neither may ever gain a photo order or selection key.
  Because sorting the filenames *is* the ordering mechanism, a folder with no
  numeric prefixes still builds — it just builds in alphabetical order. Every build
  prints the resolved order first and warns when nothing authored it; the dashboard
  shows the same list. Keep both. That silent failure shipped once already.
- **A successful build deletes its own intermediates.** A failed build keeps them
  for inspection. Do not add cleanup that fires before `finish()` and `vertical()`.

- **Never send a `sample_` file as a deliverable, and never send a `tour_` file
  before sign-off.** The two families exist to keep that boundary enforceable by
  filename. Do not add a flag that strips the watermark from a sample cut.

- **Docs do not go stale.** Any change to `make_tour.py` — new feature, flag, output,
  renamed constant, changed default — must be propagated to `CLAUDE.md`, `IDEA.md`,
  `STEPS.md`, and the module docstring in the *same* pass. `STEPS.md` is the runbook
  someone else follows to produce client deliverables; drift there produces bad work.

## Running it

```bash
streamlit run dashboard.py            # the UI: assets, timing, build, review
```

Or straight from a listing folder — everything the dashboard does, it does by
running this:

```bash
cd agents/corcoran/46_beacon_5
python3 ../../../make_tour.py         # 1920x1080, needs photos >= 2150px
python3 ../../../make_tour.py --720p           # 1280x720, needs photos >= 1433px
python3 ../../../make_tour.py --allow-lowres   # bypass the gate — PREVIEW ONLY
python3 ../../../make_tour.py --no-music       # silent build
python3 ../../../make_tour.py --keep-work      # keep clips/ + work_silent.mp4
python3 ../../../make_tour.py --finish-only    # reuse work_silent, redo branding
```

`--finish-only` implies `--keep-work` — it falls back to a full build if
`work_silent.mp4` is absent. It rebuilds all six cuts; it does **not** pick up photo
changes, since it reuses the already-stitched `work_silent.mp4`.

See `STEPS.md` for the full runbook — every scenario, flag, and failure mode.

## Known constraints

- Zillow's CDN tops out at ~1440px (`uncropped_scaled_within_1536_1152`). That
  clears 720p and fails 1080p. 1080p requires the photographer's originals or the
  MLS back end.
- The script has no locking. Two concurrent builds in one folder will collide — one
  run's cleanup deletes files the other is still using. The dashboard guards this
  with a `.build.lock` per listing; a build started straight from the CLI does not,
  and does not see the dashboard's lock either.
- `finish()` applies `BRAND_IN`/`BRAND_OUT` to *any* non-persistent layer, not just
  the lower third. Nothing is broken today — the logo is always persistent — but
  giving the logo its own window means adding `LOGO_IN`/`LOGO_OUT` and making the
  window per-layer, not reusing the brand one.
- `--finish-only` reuses `work_silent.mp4`, which was stitched from the photo list as
  it stood at the time. Renaming photos to reorder them therefore does **not** reach
  a `--finish-only` build — it would reship the old order. The CLI warns; the
  dashboard withholds the flag outright once `photo_state()` changes.
- `vertical()` sources from the *branded* cut of each family (`tour_branded.mp4` and
  `sample_branded.mp4`), so branding ghosts into the blurred side bands of both
  vertical outputs. Sourcing from the unbranded cuts would fix it. Not yet approved.
- The centered sample watermark wants a source at least 864px on the long edge at
  1080p. `viabolat.png` is currently 50x50 and upscales ~9.7x; the build warns.
