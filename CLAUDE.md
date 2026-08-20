# CLAUDE.md — Real Estate Photo Tour Generator

Project-level context. Loaded automatically each session, alongside the global
`~/.claude/CLAUDE.md` baseline (which it does not override).

## What this project is

`make_tour.py` turns a folder of still listing photos into a branded walkthrough
video with music. Single script, no dependencies beyond `ffmpeg` / `ffprobe`.

Reads from the project root:

| Path | Required | Purpose |
|---|---|---|
| `photos/` | yes | Numbered in tour order; the prefix *is* the order |
| `music.mp3` | no | Licensed track. `--no-music` to skip. |
| `lower_third.png` | no | Agent + listing info |
| `logo.png` | no | Brokerage mark, top-left |
| `viabolat.png` | no | Proofing watermark, centered, `sample_` cuts only |

All are read fresh every build — swapping any of them needs only `--finish-only`.

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
  reorder.
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
python3 make_tour.py                  # 1920x1080, needs photos >= 2150px
python3 make_tour.py --720p           # 1280x720,  needs photos >= 1433px
python3 make_tour.py --allow-lowres   # bypass the gate — PREVIEW ONLY
python3 make_tour.py --no-music       # silent build
python3 make_tour.py --keep-work      # keep clips/ + work_silent.mp4
python3 make_tour.py --finish-only    # reuse work_silent.mp4, redo music/branding
```

`--finish-only` implies `--keep-work` — it falls back to a full build if
`work_silent.mp4` is absent. It rebuilds all six cuts; it does **not** pick up photo
changes, since it reuses the already-stitched `work_silent.mp4`.

See `STEPS.md` for the full runbook — every scenario, flag, and failure mode.

## Known constraints

- Zillow's CDN tops out at ~1440px (`uncropped_scaled_within_1536_1152`). That
  clears 720p and fails 1080p. 1080p requires the photographer's originals or the
  MLS back end.
- The script has no locking. Two concurrent builds in this directory will collide —
  one run's cleanup will delete files the other is still using.
- `vertical()` sources from the *branded* cut of each family (`tour_branded.mp4` and
  `sample_branded.mp4`), so branding ghosts into the blurred side bands of both
  vertical outputs. Sourcing from the unbranded cuts would fix it. Not yet approved.
- The centered sample watermark wants a source at least 864px on the long edge at
  1080p. `viabolat.png` is currently 50x50 and upscales ~9.7x; the build warns.
