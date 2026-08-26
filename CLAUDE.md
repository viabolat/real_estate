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
publish.py                    sample_ cuts -> the public review bucket. NEVER tour_
status.py                     read-only: every listing and its one next action.
                              Names the run each is on -- see the two-run rule
hooks/pre-push                runs check_pii.py. Arm per clone -- see Running it
tests/                        stdlib unittest guards for the non-negotiables below
```

`<brand>` and `<listing>` are **not named by hand.** Both are slugified straight from
the scrape — `broker_name` and `address` in `scraper/leads.csv` — by
`scraper/photos.py`, so the folder and the lead row can never disagree. The
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
existing listings, which is what the explicit "Re-apply brand defaults" action
under **Brand settings** on `tour.py`'s home screen is for. It shows every key it
would change, per listing, and asks before writing — it is the one action in the
tool that edits files the operator is not looking at.

`config.json` — every key optional, defaults are the constants in the source:

| Key | Default | Note |
|---|---|---|
| `clip_seconds` | `4.0` | forces a full rebuild when changed |
| `xfade_seconds` | `0.5` | forces a full rebuild when changed |
| `brand_persistent` | `true` | `false` = lower third only inside the window below. `tour.py` defaults it to `false` when a card is carrying the same three lines — see below |
| `brand_in` / `brand_out` | `0.8` / `6.5` | only read when not persistent; out > in |
| `lower_third` / `logo` / `music` / `watermark` | the plain filenames | repo-relative paths into `global_assets/`. `tour.py`'s `DEFAULTS` pins `watermark` to `global_assets/logos/viabolat.png` — the bare filename does not resolve from a listing folder, and a watermark that will not resolve now refuses the sample build |
| `address` / `agent_name` / `agent_phone` | `""` | the lower third's three lines, and the card's body. Any may be blank |
| `brokerage` | `""` | card only, and only when there is no logo |
| `output_prefix` | `""` | what leads the output filenames. Blank derives it from `agent_name`; blank both leaves the bare `tour_`/`sample_` names. `tour.py` writes the brand folder here when `agent_name` is blank — `make_tour.py` must never learn the `agents/<brand>/<listing>` layout itself |
| `card` | `"none"` | `intro` \| `outro` \| `both`. `tour.py` writes `outro` on a new listing; a bare CLI run in an older folder is unchanged |
| `card_seconds` | `5.0` | forces a full rebuild when changed |
| `card_style` | `"auto"` | `logo` when one resolves, `type` when none does |
| `card_theme` | `"auto"` | measures the logo against both grounds, takes the higher contrast |
| `accent` / `font` / `scrim` | `#C8A24A` / `Liberation Sans` / `black@0.55` | rule and phone line / any installed family / the lower third's panel |

Outputs **six** cuts to `out/`, in two families — but not in one run. `tour.py`
builds the `sample_` trio first and the `tour_` trio only after the client signs
off; see the two-run rule below. Every name is prefixed with the
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

### Two runs, and how the tool knows which one it is on

`--samples-only` and `--delivery-only` build one family instead of both. A bare
`make_tour.py` still builds all six, unchanged; the staging is `tour.py`'s. The two
flags are opposites and passing both **exits 2** — "build neither family" is not a
request.

| Run | What it writes | Cost |
|---|---|---|
| 1 — proofing | the three `sample_` cuts | full build, ~6 min |
| 2 — after sign-off | the three `tour_` cuts | `--finish-only`, ~1 min |

The `tour_` trio is the paid deliverable and only ever leaves after sign-off, so
building it during cold outreach spends half a six-minute encode, and ~200 MB, on a
listing that may never reply.

**The stage is derived from `out/`, and is never recorded.** Nothing built → run 1;
`sample_` cuts alone → run 2 is next; any `tour_` cut → delivered. Same rule as the
photo order: a marker file beside the artifacts drifts out of sync with them and is
then wrong in a way nothing detects. There is no stage key in `config.json` and
there must never be one.

**`.last_build.json` gains no new rung, and that is the point.** Its top-level key
names the *intermediate lineage* — `draft` ↔ `work_draft.mp4`, `delivery` ↔
`work_silent.mp4` — not the cut family. Both runs write `delivery`, so run 2 finds
run 1's record with preset, pacing, card and `photo_state()` unchanged and takes
`--finish-only`. Change the photos or the pacing in between and `rebuild_reason()`
correctly forces a full rebuild. Two orthogonal questions, two mechanisms that
already existed: `out/` answers *which run is this*, `.last_build.json` answers
*can the stitch be reused*. Splitting the rung per family would leave run 2 with no
record and re-stitch photos that never moved.

Staging is a default, never a restriction: `build_choice()` keeps *all six now* and
a rebuild of either family reachable from every stage, because a client who has
already paid should not have to build a proof first.

A build from photos that miss the resolution gate names all six exactly the same
way. The shortfall is reported to the console — at preflight, and again once the
cuts exist — and never written into a filename. See the resolution non-negotiable
below.

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

- **Below-par photos build, and the shortfall is reported, never encoded in a
  filename.** The gate does not refuse and does not rename: it measures and says
  so, out loud, more than once. A build that needs `--allow-lowres` produces the
  same six names as any other build, and `tour.py` passes the flag only after
  stating the count, the worst offender and its upscale factor. The verdict is
  printed at preflight, restated before the delivery build is confirmed, and
  restated again with the finished file list. It used to refuse outright at the
  *end* of a run, after the question set and a draft had already been paid for,
  having known the verdict at preflight — second one. That threw the work away and
  gave the operator nothing to act on. Do not restore the refusal, and do not
  reintroduce a filename suffix: `out_path()` takes the cut name and nothing else,
  and `tests/test_naming.py` fails if any cut grows a resolution tag.
- **A soft cut is not MLS-ready, and its name will not tell you.** The console is
  the warning. `status.py` and `publish.py` both re-measure `photos/` rather than
  reading a verdict off a filename, so the reminder still arrives weeks after the
  build — `status.py` prints `soft (NNNpx photos)` and `publish.py` asks a second
  time before a soft cut goes to a client. If a delivery is soft, the photos are
  not ready — get the photographer's originals. See `IDEA.md` §4.
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
  `--keep-work` / `--finish-only` govern *the rung being run*: a successful
  **delivery** build clears the draft lineage — `work_draft.mp4`, `clips_draft/` —
  regardless of either flag, because a delivery supersedes any draft of the same
  listing and never reuses a draft stitch. Nothing did that before, and `tour.py`
  always passes one of those flags, so every listing it drafted kept ~35 MB of dead
  intermediates forever. `draft.mp4` is **not** touched — it is the review cut the
  operator asked for, not an intermediate. The asymmetry is deliberate and must
  stay: a `--draft` run clears only what a draft wrote, or it would delete
  `work_branded.mp4` out from under a kept delivery stitch and leave half a lineage
  behind. `tests/test_cleanup_lineage.py` guards both directions.

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

- **A subset build must be structurally incapable of crossing families.** The
  `--samples-only` / `--delivery-only` guards in `main()` are the `sample_`/`tour_`
  boundary expressed as build wiring, upstream of the one `publishable()` holds at
  the bucket. Each of the six call sites stays exactly where it was and is only
  *nested*: `tests/test_card_isolation.py` walks `main()` with `ast.walk` and
  asserts **four** `finish()` calls with a `cuts[...]` target and **two**
  `vertical()` calls — that is the guard keeping the card off the MLS, and deleting
  or restructuring a call site breaks it. `tests/test_build_stage.py` reads the
  guards themselves and fails if a `tour_` cut is reachable under `--samples-only`.
  Do not reach for `argparse` here either: unrecognised argv is silently ignored
  today, and argparse would start rejecting it.

- **Never send a `sample_` file as a deliverable, and never send a `tour_` file
  before sign-off.** The two families exist to keep that boundary enforceable by
  filename. Do not add a flag that strips the watermark from a sample cut.

- **Only `sample_` cuts publish, and `make_tour.py` never uploads.** The bucket
  behind `/preview/` is public, so `publish.py` refuses anything that is not
  `sample_*` — there is no `--force`, and `tests/test_publish_gate.py` fails if
  `publishable()` grows an override. The obvious implementation, a
  `for f in out/*.mp4` loop at the end of a build, would put the unwatermarked
  `tour_branded.mp4` on a guessable public URL *before sign-off*: the exact
  boundary the two families exist to hold. Publishing also stays out of
  `make_tour.py` for three separate reasons — it is stdlib + ffmpeg only, it holds
  `.build.lock` through a six-minute encode where a network timeout would fail a
  good build, and it is contractually blind to the `agents/<brand>/<listing>`
  layout that a collision-free remote path needs. The remote path is
  `<brand>/<listing>/<file>`, never the bare filename: with `x-upsert` a flat
  bucket lets one listing silently overwrite another's, which is the collision
  `output_prefix` already solved locally.

- **A publish verifies against the storage API, never the public URL.** Objects are
  served through a CDN, so a `HEAD` on the `/preview/` link seconds after an upload
  can hit an edge that has not replicated and report a correct upload as failed.
  `publish.py` confirms with one authenticated `object/list` call against the
  origin and compares sizes. Do not replace it with a fetch of the public link.

- **A publish never deletes the local cut.** `out/` stays the copy of record after
  an upload; a public bucket must not become the only place a deliverable exists,
  and `config.json` is meant to still explain what shipped months later. Storage
  pressure is a reason to prune old listings deliberately, never a reason for a
  fresh delivery to remove itself. `tests/test_publish_gate.py` fails on an
  `os.remove` anywhere in `publish.py`.

- **The recorded link is the last field on its line, and nothing is ever appended
  after it.** `outreach/links.csv` used to read
  `brand,listing,cut,url,uploaded_at`, so anything that grabbed the link took
  `,2026-08-26T16:58:12` with it and the URL 404'd — and `csv`'s default `\r\n`
  glued a carriage return onto the last field by a second route. `LINK_COLUMNS`
  now ends in `url`, `record_links()` writes `lineterminator="\n"`, and it
  migrates an older file in place rather than appending a second shape into it —
  the file is gitignored, so a fix applied once here would never reach another
  clone. `tests/test_outreach_draft.py` fails if a column is added after `url`.

- **The draft is written automatically; the send is not, and never becomes a
  flag.** `PROGRESS.md` §5.1 settled that mail leaving the machine is a
  deliberate act. There is no SMTP credential anywhere in this repo and
  `tests/test_outreach_draft.py` fails on `smtplib`, `sendmail`, `SMTP(` or
  `starttls` appearing in `publish.py`. The draft also quotes the
  `sample_branded` cut and only that — `PRIMARY_CUT` — because a cold email
  linking a `tour_` file is the paid deliverable given away in a one-word
  filename difference, the same boundary `publishable()` holds at the bucket.
  A blank `agent_name` or `address` leaves the `{placeholder}` visibly in the
  file and says so on the console: a gap you can see beats one silently filled
  with an empty string.

- **A deploy is a second publishing boundary, and `.vercelignore` is its only
  gate.** `check_pii.py` enumerates what *git* would publish; it has no view of
  what the Vercel CLI uploads. And when a `.vercelignore` exists it takes
  precedence over `.gitignore`, so adding one turned off the implicit protection
  that had been keeping `.env`, `scraper/leads.csv` and the raw dumps out of a
  deploy — gitignored is not deploy-ignored. `.env`, `.env.*`, `scraper/`,
  `outreach/`, `agents.txt` and `property_email.txt` are listed there explicitly.
  Anything new holding a key or a lead is added to **both** files, or it ships to
  a third party on the next `npx vercel --prod`. Vercel hosts no video: the
  deployment is a rewrite rule and nothing else, which is why `out/`, `agents/`,
  `clips/` and `*.mp4` are excluded too.

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

- **A folder with no lead row still gets a start line.** Provenance is a fact about
  a folder, not a blocker on it. `next_action()` used to test `if not cfg:` *before*
  it looked at readiness, so a listing with photos and no `config.json` reported
  `not in leads.csv` forever and could never read as ready — while `tour.py`'s
  picker already offered it and its question set already wrote the config. The
  roll-up was refusing to say what the tool would happily do. The fact now travels
  as a suffix on the real next action instead of replacing it. A **scraped** folder
  with no config is still sent back to `photos.py`, because there the scrape can
  fill in the address, agent, phone and watermark path properly. Nothing about the
  naming authority moves: the folder is not renamed, `audit()` is untouched, and it
  keeps reporting as *unverifiable*.

- **`brand.json` never carries `agent_name` or `agent_phone`.** A brokerage has many
  agents; the folder is keyed on the brokerage. See the `brand.json` note above.
  `tour.py` enforced this at neither end for a while: `BRAND_KEYS` listed both
  keys and `questions()` offered *"Save the name, phone and brokerage as
  {brand} defaults?"* with the confirm defaulting to **yes**. Nothing had gone
  wrong yet — all nine `brand.json` files were clean — but `leads.csv` lists two
  agents under `Coldwell Banker Realty - Boston`, two under `Gibson Sotheby's`
  and two under `Serhant`, and `load_config()` layers `brand.json` *under* the
  listing's `config.json` without printing anything. One yes would have put one
  agent's phone number on the other agent's card, lower third and output
  filenames across every listing that brokerage owns, silently. `save_brand()`
  now filters the two keys out and `load_brand()` strips them on the way back in,
  so a hand-edited or legacy file cannot reintroduce them either;
  `tests/test_brand_scope.py` fails if either returns by any route. `brokerage`
  stays — it is the same string for every listing a brand owns, which is what a
  brand default *is*.

- **The PII gate runs itself, and an unwired gate is reported, never assumed.**
  `check_pii.py` never has an interesting answer, which is exactly why an
  operator stops running it. `hooks/pre-push` makes it automatic. But `hooks/` is
  committed while `core.hooksPath` is **per-clone config**, so a fresh clone
  ships the file with the gate *off* — present and silent, which on screen is
  indistinguishable from the gate passing. That is this repo's own stated failure
  shape. So `tour.py`'s home screen checks `core.hooksPath` and the hook's
  executable bit and prints the one-line fix when either is wrong, **and** runs
  `check_pii.py`'s scan itself regardless: the hook only fires for pushes through
  the git CLI, and libgit2-based clients — most IDE git integrations — do not run
  git hooks at all. Do not add a bypass to the hook; `git push --no-verify` is
  git's own escape hatch and is visible in the command someone typed, where a
  bypass baked into the hook would not be. `tests/test_hook_wired.py` guards
  both.

- **The two slug functions agree on apostrophes, and are still two functions.**
  `scraper/photos.slugify` names the folders; `make_tour._slug` names the
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

One command. Everything else is a gate, a one-time setup step, or an escape hatch.

```bash
python3 tour.py                       # the home screen: roll-up, then four choices
```

`status.py`'s out/ states name the **family**, not just a count — a first run
writes three cuts on purpose, so a bare `built, 3 cuts` was indistinguishable from
a six-cut build that died halfway:

| State | Means |
|---|---|
| `ready to build` | nothing in `out/` yet |
| `sample built -- publish the review link` | run 1 done |
| `sample published -- awaiting sign-off` | a cut is on the review bucket |
| `delivered, N cuts` | a `tour_` cut exists |

*Published* is derived from `outreach/links.csv`, which `publish.py` already writes
on every confirmed upload, read **by header name** — no marker file is invented to
hold it, and a missing file means "nothing published" exactly as a missing
`leads.csv` means "nothing scraped". `publish.family()` is the single owner of
which prefix means what; `status.py` and `tour.py` both ask it rather than testing
the prefix themselves, because a second implementation of that boundary would drift
and the drift would be an unwatermarked deliverable counted as a proof. The
soft-photo verdict rides along on every state and is still measured from `photos/`.
`next_action()` also merges `brand.json` **under** the listing's `config.json`
before the asset checks, mirroring `tour.load_config()` — without it a listing that
inherits its logo, which is the normal case, reported `logo blank/missing` forever.

It opens on `status.py`'s roll-up — every listing and its one next action, plus
the scrape-naming drift report — then offers: **1** build a tour, **2** import the
dumps that have no listing folder yet, **3** publish a review link, **4** brand
settings. Which dumps are pending is *derived* from whether
`agents/<brand>/<listing>` exists; there is no marker file and no manifest, for
the same reason photo order lives in the filename prefix. `--build` skips the
screen when you already know the listing.

**Once per clone**, or the PII gate is present and off:

```bash
git config core.hooksPath hooks       # arms hooks/pre-push -> check_pii.py
```

**Once per project**, to make the preview links resolve:

```bash
npx vercel --prod                     # deploys vercel.json's rewrite. No video.
```

The links `publish.py` prints and records are absolute —
`https://real-estate.viabolat.com/preview/<brand>/<listing>/<cut>` — because that
string is pasted into a cold email, where a site-relative `/preview/...` path is
not a link at all. The host is `PREVIEW_HOST` in `publish.py`; it must stay the
domain pointed at the deployment that carries `vercel.json`'s rewrite.

Everything below still runs standalone, unchanged, and is what the home screen
runs for you:

```bash
python3 scraper/run.py                # every dump in scraper/dumps/ -> leads + listings
python3 status.py                     # what every listing is waiting on
python3 check_pii.py                  # what the pre-push hook runs; exit 0 = safe
python3 tour.py --check-photos        # optional: Claude reads the contact sheet
python3 publish.py --dry-run          # from a listing: what would go public, and where
python3 publish.py                    # upload this listing's sample_ cuts
python3 -m unittest discover -s tests -t .   # the non-negotiables, ~0.6s, no ffmpeg
```

`run.py` names the folders, downloads `photos/`, writes `brand.json` and
`config.json` from the dump, pins the watermark path, and prints the resolution
verdict `make_tour.py`'s gate would give — before any of it is worth building. It
never overwrites an existing `brand.json` or `config.json`. Point it at one dump
file, or let it default to every `*.txt` in `scraper/dumps/`. See
`scraper/README.md`.

`publish.py` needs `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`, from the environment
or from a `.env` beside it (see `.env.example`; an exported variable always wins).
Missing either is **exit 2**, not a quiet no-op. `tour.py` offers it as an optional
rung 4 after a delivery build, defaulting to *no*, and stays silent when no key is
configured — silent there only, because an operator with no key should not be
nagged on every delivery. Reached deliberately from the home screen's **Publish a
review link** it says what is missing instead, since silence in answer to a
request reads as success. Both paths print the file list, the remote paths and the
resulting `https://real-estate.viabolat.com/preview/...` URLs before anything moves,
and write those same absolute links to `outreach/links.csv` as
`uploaded_at,brand,listing,cut,url` — **`url` last, `uploaded_at` first**, with
`\n` endings. Every confirmed publish also renders one email draft to
`outreach/drafts/<brand>__<listing>.txt` from `outreach/template.txt`, filled in
with the agent's first name and the address out of the listing's `config.json` and
the `sample_branded` link. `--dry-run` prints it instead of writing it. Nothing is
sent. `outreach/template.txt` is the only committed thing under `outreach/` —
`.gitignore` uses the directory-contents form `outreach/*` plus
`!outreach/template.txt`, because git does not descend into an excluded directory
and a negation under a bare `outreach/` would match nothing.

Or straight from a listing folder — everything `tour.py` does, it does by
running this. Three rungs, each costing what the question is worth:

```bash
cd agents/corcoran/46_beacon_5
python3 ../../../make_tour.py --contact-sheet  # ~1s   is the order right?
python3 ../../../make_tour.py --draft          # ~1min does the edit feel right?
python3 ../../../make_tour.py --samples-only   # ~6min the client's proofing copy
python3 ../../../make_tour.py --delivery-only  # ~1min after sign-off
```

Only the last two produce cuts, and only `--delivery-only` produces deliverables;
a bare `make_tour.py` still writes all six in one go. `--contact-sheet` writes
`contact_sheet.png` — a numbered grid of `photos/` in build order — and exits
before encoding *and before the resolution gate*, since "are these in the right
order" is worth answering on photos that are not yet good enough to build with.
`--draft` forces 720p at a fast preset and writes one branded, watermarked cut to
`draft.mp4` in the listing root.

The rest:

```bash
python3 ../../../make_tour.py                  # 1920x1080, needs photos >= 2150px
python3 ../../../make_tour.py --720p           # 1280x720, needs photos >= 1433px
python3 ../../../make_tour.py --allow-lowres   # build anyway; names are unchanged
python3 ../../../make_tour.py --no-music       # silent build
python3 ../../../make_tour.py --keep-work      # keep clips/ + work_silent.mp4
python3 ../../../make_tour.py --finish-only    # reuse work_silent, redo branding
python3 ../../../make_tour.py --samples-only   # run 1: the 3 sample_ cuts only
python3 ../../../make_tour.py --delivery-only  # run 2: the 3 tour_ cuts only
```

`--finish-only` implies `--keep-work` — it falls back to a full build if
`work_silent.mp4` is absent. It rebuilds all six cuts; it does **not** pick up photo
changes, since it reuses the already-stitched `work_silent.mp4`.

See `STEPS.md` for the full runbook — every scenario, flag, and failure mode.

- **A gate that cannot run must fail closed.** `check_pii.py` enumerates files by
  shelling out to git, and `git()` swallows a failed subprocess and returns `[]`.
  Outside a repository — git not installed, or the tree copied without its `.git` —
  it therefore scanned *nothing* and printed `Safe to push`, exit 0, over a folder
  that may hold the whole lead list. "Nothing to scan" and "nothing found" are
  indistinguishable in the output and opposite in meaning. `require_git()` and the
  empty-file-list check both exit 2 rather than let that read as clean. Do not add a
  flag that downgrades either to a warning.
- **A broken *or missing* watermark stops the build; broken branding does not.** An
  unreadable logo or lower third costs a cosmetic layer, so it warns and drops out
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
  uploaded on the strength of its name. `tour.py`'s `DEFAULTS` carries
  `watermark: global_assets/logos/viabolat.png` so every listing it writes pins it,
  matching `scraper/photos.py`. A `--delivery-only` run needs no watermark and is
  unaffected. The refusal fires at **preflight** — before the lock, the clips and
  the stitch — via `require_watermark()`, and again inside `finish()` as the last
  gate before the pixels. Refusing at minute five over something known at second
  one is this repo's own stated failure shape; it is what the resolution gate was
  fixed for, and the same mistake was not worth repeating here.

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
