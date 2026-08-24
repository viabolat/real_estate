# CLAUDE.md — Real Estate Photo Tour Generator

Project-level context. Loaded automatically each session, alongside the global
`~/.claude/CLAUDE.md` baseline (which it does not override).

## What this project is

`make_tour.py` turns a folder of still listing photos into a branded walkthrough
video with music. Single script, no dependencies beyond `ffmpeg` / `ffprobe`.

`tour.py` is the interface: one command, a short question set, an mp4. It picks the
listing, imports and numbers the photos, names what is missing *before* anything
encodes, asks only what actually varies, and walks the three rungs (*is the order
right, does the edit feel right, ship it*), running `make_tour.py` for each. It is
stdlib only — the project has no third-party dependencies — and everything it does
can still be done from the CLI.

It replaced a Streamlit dashboard, which put thirteen controls on screen and still
left the operator to remember which of them mattered. The rule that came out of
that: anything with the same answer on every listing is inherited from `brand.json`
or derived from the photos, and never becomes a control.

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
agents/<brand>/brand.json     per-brand defaults — tour.py ONLY, see below
agents/<brand>/<listing>/     photos/, config.json, out/  — cwd for a build
global_assets/logos/          shared branding, referenced by config.json
global_assets/music/
global_assets/lower_thirds/
scraper/                      Zillow dump -> leads.csv + a scaffolded listing
status.py                     read-only: every listing and its one next action
tests/                        stdlib unittest guards for the non-negotiables below
```

`<brand>` and `<listing>` are **not named by hand.** Both are slugified straight from
the scrape — `broker_name` and `address` in `scraper/leads.csv` — by
`scraper/zillow_photos.py`, so the folder and the lead row can never disagree. The
slug drops apostrophes rather than turning them into separators, so
`Gibson Sotheby's International Realty` is `gibson_sothebys_international_realty`,
not `gibson_sotheby_s_...`. `status.py` re-checks every folder against `leads.csv` on
each run — matched on agent phone, since address text formatting varies and a phone
number does not — and prints the `mv` for anything that has drifted.

One consequence, accepted deliberately: `Coldwell Banker Realty - Boston` and
`Coldwell Banker Realty - Waltham` are two brand folders with two `brand.json` files,
because that is what the scrape says. Set the logo twice rather than maintaining an
alias table, which is a second naming authority and would drift.

`brand.json` holds what is identical across every listing a brokerage owns — logo,
music, pacing, lower-third timing, the card mode. It holds **no agent identity.**
`leads.csv` already lists two agents under `Coldwell Banker Realty - Boston` and two
under `Gibson Sotheby's International Realty`, so a brand-level `agent_name` /
`agent_phone` puts one agent's phone number on another agent's video. Those two keys
live in the listing's `config.json`, written from the scrape, and nowhere else.
**`make_tour.py` never reads it.** `tour.py`
resolves `DEFAULTS → brand.json → listing config.json` and writes the effective
values into the listing's `config.json`, which stays the single source of truth for
a build. That keeps the script's contract intact — read the working directory, know
nothing about the `agents/<brand>/<listing>` layout — and keeps `config.json` an
accurate record of what produced a delivered video months later. A new listing
inherits at creation; changing a brand default does **not** retroactively alter
existing listings, which is what the explicit "Re-apply brand defaults" action in
the Brand tab is for.

`config.json` — every key optional, defaults are the constants in the source:

| Key | Default | Note |
|---|---|---|
| `clip_seconds` | `4.0` | forces a full rebuild when changed |
| `xfade_seconds` | `0.5` | forces a full rebuild when changed |
| `brand_persistent` | `true` | `false` = lower third only inside the window below. `tour.py` defaults it to `false` when a card is carrying the same three lines — see below |
| `brand_in` / `brand_out` | `0.8` / `6.5` | only read when not persistent; out > in |
| `lower_third` / `logo` / `music` / `watermark` | the plain filenames | repo-relative paths into `global_assets/` |
| `address` / `agent_name` / `agent_phone` | `""` | the lower third's three lines, and the card's body. Any may be blank |
| `brokerage` | `""` | card only, and only when there is no logo |
| `output_prefix` | `""` | what leads the output filenames. Blank derives it from `agent_name`; blank both leaves the bare `tour_`/`sample_` names. `tour.py` writes the brand folder here when `agent_name` is blank — `make_tour.py` must never learn the `agents/<brand>/<listing>` layout itself |
| `card` | `"none"` | `intro` \| `outro` \| `both`. `tour.py` writes `outro` on a new listing; a bare CLI run in an older folder is unchanged |
| `card_seconds` | `5.0` | forces a full rebuild when changed |
| `card_style` | `"auto"` | `logo` when one resolves, `type` when none does |
| `card_theme` | `"auto"` | measures the logo against both grounds, takes the higher contrast |
| `accent` / `font` / `scrim` | `#C8A24A` / `Liberation Sans` / `black@0.55` | rule and phone line / any installed family / the lower third's panel |

Outputs **six** cuts to `out/`, in two families. Every name is prefixed with the
agent's own name — `output_prefix`, or `agent_name` slugified when that is blank —
because six listings all producing a `tour_branded.mp4` collide the moment the
files leave `out/` for a downloads folder or an email thread. Both blank leaves the
bare names, so a pre-existing folder built from the CLI is unchanged. The slug is
the folder rule applied to a filename — apostrophes drop rather than separate, so
`Sean O'Brien` signs `sean_obrien_tour_branded.mp4` inside `sean_obrien/` and not
`sean_o_brien_...`:

**Delivery** — clean, what the client gets on sign-off:
- `<agent>_tour_branded.mp4`   — card + lower third + top-left logo, for social /
  your own channels. Longer than the unbranded cut by the card(s) it carries
- `<agent>_tour_unbranded.mp4` — no branding, MLS/IDX-safe
- `<agent>_tour_vertical.mp4`  — 9:16 portrait, branded centre, clean blurred bands

**Sample** — identical edit plus a centered proofing watermark (`viabolat.png`),
what the client reviews before paying:
- `<agent>_sample_branded.mp4`
- `<agent>_sample_unbranded.mp4`
- `<agent>_sample_vertical.mp4`

A build from photos that miss the resolution gate names all six `..._lowres.mp4`.
See the `_lowres` non-negotiable below.

Plus one more, only from `--draft`, and deliberately outside `out/`:

- `draft.mp4` — 720p at a fast x264 preset, branded **and** watermarked, one cut,
  written to the listing root. A review rung, never a deliverable. Its
  intermediates (`work_draft.mp4`, `clips_draft/`) are named apart from the
  delivery ones so a draft-quality stitch can never feed a delivery build.

The watermark is deliberately **not** gated on the `branded` flag — it is the entire
reason a sample cut exists, so it appears on `sample_unbranded.mp4` too.

## The card, and why a build stitches twice

The intro/outro card is drawn by ffmpeg from `config.json` — logo (or brokerage type
when there is no logo) over address, agent and phone. Nothing is exported from Canva
any more; the lower third is drawn the same way from the same three fields, and a
`lower_third.png` that exists still wins, so a hand-authored plate stays available
for a listing that earns it.

The card is branding, so it must never reach the MLS cut. That is why a build with a
card stitches twice:

| Stitch | Contents | Feeds |
|---|---|---|
| `work_silent.mp4` | photos only | `tour_unbranded`, `sample_unbranded` |
| `work_branded.mp4` | `[intro]` + photos + `[outro]` | `tour_branded`, `sample_branded`, `draft.mp4` |

With no card configured the second stitch is skipped and both read the same file — a
no-card build is byte-identical to one from before cards existed, verified against
`0722f52`. The cost when there *is* a card is one extra stitch, ~26s on a 6-minute
build.

## READ FIRST: `IDEA.md`

**`IDEA.md` is the photo sourcing standard and is required reading before any work
on image quality.** §1-7 cover the resolution gates and where they come from, the
sourcing ladder, what not to do, and the current state of `photos/`.

`IDEA.md` §8 is a separate **branding/output backlog** — proposed, not approved, not
built. It is parked there by agreement and is not part of the sourcing standard.

Do not re-derive or re-litigate that guidance — it was established through
measurement, not assumption.

## Non-negotiables

- **Below-par photos build, and the shortfall rides in the filename.** The gate no
  longer refuses — it decides what the files are *called*. A build that needs
  `--allow-lowres` names every cut `..._lowres.mp4`, and `tour.py` passes the flag
  only after stating the count, the worst offender and its upscale factor. It used
  to refuse outright at the *end* of a run, after the question set and a draft had
  already been paid for, having known the verdict at preflight — second one. That
  threw the work away and gave the operator nothing to act on. A console refusal is
  a boundary that survives nothing; a filename is a boundary that survives being
  emailed. Do not restore the refusal, and do not add a flag that drops the tag.
- **A `_lowres` cut is not MLS-ready.** The tag is the warning, not permission. If
  a delivery needs it, the photos are not ready — get the photographer's originals.
  See `IDEA.md` §4.
- **No AI upscaling of listing photos.** It fabricates detail that is not in the
  room, which on a property listing is misrepresentation. See `IDEA.md` §3.
- **Photo order lives in the filename prefix and nowhere else.** No sidecar file, no
  manifest, no lookup table — those drift out of sync with the folder. Rename to
  reorder. `config.json` and `.last_build.json` carry timing, pacing, asset paths
  and build state **only**; neither may ever gain a photo order or selection key.
  Because sorting the filenames *is* the ordering mechanism, a folder with no
  numeric prefixes still builds — it just builds in alphabetical order. Every build
  prints the resolved order first and warns when nothing authored it; `tour.py`
  shows the same list and offers to add prefixes. Keep all three. That silent
  failure shipped once already.
- **A successful build deletes its own intermediates.** A failed build keeps them
  for inspection. Do not add cleanup that fires before `finish()` and `vertical()`.

- **The card never rides in `work_silent.mp4`.** That stitch feeds the unbranded
  cuts, which are the MLS/IDX files. A card baked into it puts an agent's name and
  phone number on the MLS. Two stitches, always, whenever a card exists.

- **Branding is held off wherever the card is on screen, and the watermark is not.**
  The card already carries the address, the agent and the phone at full size in the
  middle of the frame; the lower third and the logo over the top of it print the
  same lines twice. `finish()` takes a `cards=(intro, outro)` span and gates the
  branding layers to the photo body. The proofing watermark is deliberately exempt —
  an unwatermarked outro card is exactly the frame an unapproved sample would be
  screenshot from.

- **The lower third does not say what the card already says.** Both are drawn from
  the same `address` / `agent_name` / `agent_phone`, so a persistent lower third
  plus a card prints the operator's details twice in one video. `finish()` keeps
  the two from overlapping *in time*; that rule says nothing about the redundancy
  across the whole cut. So `tour.py` defaults `brand_persistent` to `false`
  whenever a card exists and no hand-made `lower_third.png` does: the lower third
  introduces the property, clears, and the card closes. A `lower_third.png`
  someone authored says something the card does not, so it is exempt. The default
  is stated out loud and still overridable.

- **Never send a `sample_` file as a deliverable, and never send a `tour_` file
  before sign-off.** The two families exist to keep that boundary enforceable by
  filename. Do not add a flag that strips the watermark from a sample cut.

- **`vertical()` takes two sources per family, and that is not redundancy.** The
  blurred band comes from the *unbranded* cut, the centered frame from the
  *branded* one. Both layers used to come from the branded cut, and because the
  band is the source scaled ~1.8x and centre-cropped, the lower third reappeared
  in it large enough to read the street address off. Do not collapse it back to a
  single input. Sourcing both layers from the unbranded cut also removes the
  ghost — by stripping the branding off the social cut, which is not the same fix.

- **`draft.mp4` is not a deliverable and does not go in `out/`.** `out/` holds real
  cuts only, which is what makes the `tour_`/`sample_` prefix a reliable boundary. A
  draft is 720p at a fast preset and carries the watermark; do not add a flag that
  removes it, and do not let `--draft` read or write `work_silent.mp4`. A stale
  draft-quality intermediate silently feeding a delivery build is the same failure
  shape as the shuffled photo order — it produces a bad video with no error.

- **One dump per file, and a dump that is not a listing is refused.** The parsers
  are first-match regexes over the whole text, so two dumps concatenated into one
  file read the first listing's agent name and phone onto the second listing's
  photos. Both scripts now exit non-zero on a dump with no `zpid` and no address
  rather than writing a row of blanks and an `agents/unknown_brokerage/listing/`
  folder — that exited 0, so a batch run reported it as processed cleanly while
  poisoning `leads.csv`, which is also the naming authority.

- **No lead, phone number or email address is ever committed.** `leads.csv`,
  `leads.html`, the raw dumps, `agents.txt` and `property_email.txt` are ignored by
  repo-level rules, not by a global `~/.gitignore_global` that does not travel.
  `python3 check_pii.py` scans everything git would publish — against the real
  values in `leads.csv`, not a guess — and exits non-zero. Run it before every
  push. A private repo is an access-control boundary, not a redaction one: it gets
  shared, cloned, or opened up years later, and nothing re-reviews the history at
  that moment. Write `.gitignore` patterns on their own lines — git only honours
  `#` at the start of a line, so a trailing comment turns the pattern into a
  literal that matches nothing.

- **The scrape names the folders; nothing else does.** `agents/<brand>/<listing>` is
  `slugify(broker_name)/slugify(address)` from `scraper/leads.csv`. Do not hand-name
  a listing folder, and do not add an alias table mapping a scraped brokerage onto a
  shorter hand-picked name — that is a second naming authority, and the two drift the
  moment a brokerage is renamed. `coldwell_banker/2_comm_ave` sat beside a lead row
  reading `Coldwell Banker Realty - Boston` / `2 Commonwealth Ave` for exactly that
  reason. `status.py` prints the `mv` when a folder no longer matches its lead row.
  A folder with **no** lead row behind it is reported separately as *unverifiable*,
  not passed: the check keys on `agent_phone` out of `config.json`, so a folder
  that never had a `config.json` — the strongest signal it was never scaffolded by
  the scraper, and so the likeliest hand-named folder there is — used to fall
  silently through the check built to catch it. `brewester/9_w_cedar` and
  `corcoran/46_beacon_5` sat through the scrape-naming commit that way. They are
  left alone deliberately: the scrape cannot name a listing it has no row for, and
  hand-naming one is the second authority this rule exists to prevent.

- **`brand.json` never carries `agent_name` or `agent_phone`.** A brokerage has many
  agents; the folder is keyed on the brokerage. See the `brand.json` note above.

- **The two slug functions agree on apostrophes, and are still two functions.**
  `scraper/zillow_photos.slugify` names the folders; `make_tour._slug` names the
  files inside them. Both drop apostrophes rather than turning them into
  separators, or one agent's name gets two spellings —
  `sean_obrien/sean_o_brien_tour_branded.mp4`. They stay separate on purpose:
  `make_tour.py` runs with cwd set to a listing folder and nothing but ffmpeg on
  the path, so importing the scraper would make a build depend on the scrape,
  which it otherwise never does. They also differ on the empty case on purpose —
  the scraper falls back to `listing` because a folder cannot be named `""`,
  while `_slug` returns `""` so a blank `agent_name` leaves the bare
  `tour_`/`sample_` names. Change one apostrophe rule, change both;
  `tests/test_naming.py` fails if they drift.

- **Docs do not go stale.** Any change to `make_tour.py` or `tour.py` — new feature, flag, output,
  renamed constant, changed default — must be propagated to `CLAUDE.md`, `IDEA.md`,
  `STEPS.md`, and the module docstring in the *same* pass. `STEPS.md` is the runbook
  someone else follows to produce client deliverables; drift there produces bad work.

## Running it

```bash
python3 scraper/zillow_run.py         # every dump in scraper/dumps/ -> leads + listings
python3 check_pii.py                  # before any push: no lead, phone or email escapes
python3 status.py                     # what every listing is waiting on
python3 tour.py                       # the wizard: listing, questions, three rungs
python3 tour.py --check-photos        # optional: Claude reads the contact sheet
python3 -m unittest discover -s tests -t .   # the non-negotiables, ~0.5s, no ffmpeg
```

`zillow_run.py` names the folders, downloads `photos/`, writes `brand.json` and
`config.json` from the dump, pins the watermark path, and prints the resolution
verdict `make_tour.py`'s gate would give — before any of it is worth building. It
never overwrites an existing `brand.json` or `config.json`. Point it at one dump
file, or let it default to every `*.txt` in `scraper/dumps/`. See
`scraper/README.md`.

Or straight from a listing folder — everything `tour.py` does, it does by
running this. Three rungs, each costing what the question is worth:

```bash
cd agents/corcoran/46_beacon_5
python3 ../../../make_tour.py --contact-sheet  # ~1s   is the order right?
python3 ../../../make_tour.py --draft          # ~1min does the edit feel right?
python3 ../../../make_tour.py                  # ~6min ship it
```

Only the third produces deliverables. `--contact-sheet` writes
`contact_sheet.png` — a numbered grid of `photos/` in build order — and exits
before encoding *and before the resolution gate*, since "are these in the right
order" is worth answering on photos that are not yet good enough to build with.
`--draft` forces 720p at a fast preset and writes one branded, watermarked cut to
`draft.mp4` in the listing root.

The rest:

```bash
python3 ../../../make_tour.py                  # 1920x1080, needs photos >= 2150px
python3 ../../../make_tour.py --720p           # 1280x720, needs photos >= 1433px
python3 ../../../make_tour.py --allow-lowres   # build anyway; names every cut _lowres
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
