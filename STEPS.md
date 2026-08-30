# STEPS.md — Runbook

Two parts, because two different people read this file.

**Part 1 — Operator** is everything needed to ship a listing: one command, the
three rungs, the review link, and a fenced-off one-time setup section. If your job
is producing client deliverables, Part 1 is the whole runbook.

**Part 2 — Engine room** is `make_tour.py` itself: every flag, all thirty
scenarios, the tuning keys, the resolution gate and the failure modes. **You do
not need any of it to ship a listing.** It is here for the day something behaves
unexpectedly, or a listing needs something the wizard does not ask about.

`WALKTHROUGH.md` is the eleven-step version of Part 1, for someone doing this for
the first time; this file is the depth behind it. When they disagree, this file is
right and `WALKTHROUGH.md` needs updating.

For photo sourcing and resolution rules, see `IDEA.md`. For the rules that must not
be broken, `_rules/` — the table in `_rules/CONTEXT.md` routes by area. `CLAUDE.md`
routes to everything.

---

# Part 1 — Operator

## 0a. The one command

```bash
python3 tour.py
```

It opens on the roll-up — every listing, its photo count, its smallest photo and
the one thing standing between it and a deliverable — then offers four things:

| | | |
|---|---|---|
| **1** | Build a tour | the three rungs, §0b |
| **2** | Import *n* new dumps | runs the scraper on dumps with no listing folder yet |
| **3** | Publish a review link | the watermarked cuts, to the review bucket |
| **4** | Brand settings | what a brokerage sets once, and re-applying it |

Which dumps are pending is worked out by checking whether
`agents/<brand>/<listing>/<agent>` exists. There is no marker file and nothing to
tidy between runs — delete a listing folder and its dump is offered again.

`python3 tour.py --build` skips the screen when you already know the listing.

If the roll-up says it is unavailable, that is `status.py` failing to import the
scraper. Building is unaffected: pick 1 and carry on.

**Brand settings** (menu **4**) edits `agents/<brand>/brand.json` — the logo,
music, card and pacing every listing that brokerage owns shares. It does **not**
hold the agent's name or phone: `leads.csv` lists two agents under some
brokerages, so a brand-level name or phone would put one agent's details on the
other's video. Those live in the listing's `config.json`. Changing a brand default
does not reach back into listings already scaffolded; **Re-apply brand defaults**
is the explicit action that does, and it shows every key it would change, per
listing, before writing anything.

### Getting a listing onto disk

Menu item **2** does this for you. The command behind it:

```bash
python3 scraper/run.py            # every *.txt in scraper/dumps/
python3 scraper/run.py one.txt    # or just the one
```

Paste one listing per file into `scraper/dumps/`. **Never two in one file** — the
parsers take the first match in the whole text, so a concatenated file puts the first
listing's agent name and phone on the second listing's photos, with nothing raised.
A dump that is not a listing page (empty, half-copied, wrong tab) is refused and
writes nothing; the run names it at the end and exits non-zero. Re-running the folder
is safe — duplicate lead rows are skipped, photos already on disk are skipped, and
neither JSON is ever overwritten — so there is nothing to move or tidy between runs.

It appends the lead row to `scraper/leads.csv`, creates
`agents/<broker_name>/<address>/photos/` — both names slugified from the scrape, which
is the only naming authority; do not rename these by hand — downloads every photo in
gallery order, writes `brand.json` and `config.json` from the dump (address, agent,
phone, brokerage, watermark path), and prints the resolution verdict the gate in §3
would give. Neither JSON is ever overwritten if it already exists.

Two fields it deliberately leaves blank, because they are yours: `logo` and `music`.
Fill them in once per brokerage in `agents/<broker_name>/brand.json` — or, for the
logo, drop the file at `global_assets/logos/<broker_name>.png` and let `--auto` find
it (below). Until either happens the card falls back to the type-only design and the
build is silent.

To see where every listing stands:

```bash
python3 status.py            # one line each: photo count, smallest photo, next action
python3 status.py --long     # also show what each listing inherits
```

Two lists can follow the table. **Folder name(s) do not match the scrape** prints
an `mv` per folder — run it, the scrape is the naming authority. **Folder(s) have
no lead row to check against** is not a rename instruction: those listings predate
the scrape or their lead row is gone, so nothing can derive their names. Leave
them, or re-scrape the listing.

It writes nothing. It also re-checks every folder name against `leads.csv` and prints
the `mv` for any that drifted.

---

## 0b. Shipping a listing

### The whole job, one command
```bash
python3 tour.py        # then 1, or --build to skip the home screen
```
Pick brand → listing (or create either on the spot). If `photos/` is empty it asks
for a source folder and copies them in; if the filenames carry no numeric prefix it
offers to add `010_`, `020_` … in the current alphabetical order — the prefix is
the order, and there is no manifest anywhere.

Then, **before anything encodes**, it prints the preflight: the resolved photo
order, which preset the photos actually clear, which assets resolved and which are
missing, and whether `.build.lock` is held. Anything absent is named here rather
than found five minutes into a render.

The question set is short, and everything with the same answer on every listing is
inherited from `agents/<brand>/brand.json` rather than asked: the logo and music;
the card (outro / intro+outro / intro / none) and its length; whether the lower
third stays up or clears after the opening seconds; seconds per photo. What it
still asks per listing is the address, the agent's name and phone, and the
brokerage — and a changed brokerage is the only one of those it offers to keep as
a brand default.

**The agent's name and phone are never saved to a brand**, and there is no prompt
that offers to. A brand folder is keyed on the *brokerage*, and `leads.csv` lists
two agents under `Coldwell Banker Realty - Boston`, two under
`Gibson Sotheby's International Realty` and two under `Serhant`. A brand-level
name or phone would put one agent's details on the other's card, lower third and
output filenames across every listing that brokerage owns, and it would do it
silently, because `brand.json` is layered *under* the listing's `config.json`.

Then the three rungs, confirming between each — contact sheet, draft, build —
where the third asks which family to write and defaults to what `out/` says is
next: the three watermarked `sample_` cuts on a listing with nothing built, the
three `tour_` deliverables once the client has signed off. All six in one go stays
one keystroke away. See §3 —
with the delivery built at 720p even when the photos do not clear it, after it
names the count and the worst file — and again when the cuts are done. Nothing in
the filenames records that; the console does. It picks the build
mode for you: `--finish-only` when only branding, music or timing changed since the
last build of that rung, a full `--keep-work` build when the photos, the pacing, the
card or the output preset changed. Draft and delivery keep separate records in
`.last_build.json`, so a draft can never authorise a `--finish-only` delivery build.

`make_tour.py` never reads `brand.json` — `tour.py` resolves
`DEFAULTS → brand.json → listing config.json` and writes the result into the
listing, so `config.json` stays the single record of what produced a delivered
video. Changing a brand default does not retroactively alter existing listings —
**Brand settings → Re-apply brand defaults** on the home screen is the explicit
action that does, and it prints every key it would change, per listing, first.

The lock belongs to the script. `tour.py` only reads `.build.lock` to report it, and
never writes it — doing so would lock the build out of its own folder.

### Hands-off: paste a dump, walk away, check the mp4
```bash
python3 tour.py --auto                                # every pending dump/listing
python3 tour.py --auto <brand>/<listing>               # just one -- also the resume, below
python3 tour.py --auto <brand>/<listing> --ignore-floorplan-check   # force a false positive through
python3 tour.py --auto <brand>/<listing> --ignore-missing-phone-check   # phone is genuinely unavailable
python3 tour.py --auto <brand>/<listing> --ignore-missing-logo-check    # brokerage genuinely has no mark
```
Imports every pending dump, then answers the same question set above from
`config.json`/`brand.json` alone — never `input()` — for every listing with no
cuts yet. It skips the music pick outright rather than guess one: a brokerage
with no `music.mp3` builds silent, the same way a hand-run build with nothing
set does. The logo is different: before anything else, it checks
`global_assets/logos/<brand>.png` — the brand folder's own slug, not a
guess among several unrelated marks — and adopts it as the brand default
the moment it exists. It builds the contact sheet, skips the draft rung
entirely, and goes straight to the three `sample_` cuts.

Before it stitches anything, it checks three things no default can safely
answer. First, whether `agent_phone` is blank — Zillow does not always expose
one, especially for a team listing, and a card with no way to call back
defeats the point of sending the video. Second, whether the brokerage's logo
resolved anywhere — neither `config.json`/`brand.json`'s own `logo` nor the
brand-slug lookup above — and would otherwise ship the type-only card without
anyone deciding that on purpose. Third, whether a photo in `photos/` is a
floor plan or whole-house layout image, which must never appear in the video.
A hit on any halts just that listing — printed, never guessed at or deleted —
and the rest of the batch keeps going. Fix `config.json`, add the logo file,
or delete the photo by hand and rerun `--auto`, bare or scoped to that
`brand/listing`; nothing about any halt is written anywhere, so re-running
from the top is the entire resume mechanism. A false positive or a
genuinely-absent asset can be forced through once, per listing, with
`--ignore-missing-phone-check`, `--ignore-missing-logo-check`, or
`--ignore-floorplan-check` — all three need a scope, and none is ever allowed
to waive its check for a whole batch.

It never builds a draft and never publishes. Checking the mp4 in `out/`, then
running `publish.py` from the listing folder (above), stays the last manual
step.

### Have Claude read the contact sheet (optional)
```bash
python3 tour.py --check-photos
```
Builds the contact sheet, then asks Claude to name the room in each numbered cell,
say whether the filename agrees, and flag a running order that opens or closes on a
bathroom. It proposes renames and **renames nothing** — the prefix is the order, so
you rename the files yourself. It uses the Claude Code login already on this
machine: no key, nothing to install. If `claude` is not on PATH it says so and
tells you to read the sheet yourself, which is the check that actually matters.

### Send the client a review link
```bash
cd agents/<brand>/<listing>/<agent>
python3 ../../../../publish.py --dry-run   # what would go public, and the exact URLs
python3 ../../../../publish.py             # the same, then asks, then uploads
```
`tour.py` offers this as rung 4 straight after a **sample** build — that is the
run whose whole purpose is to be reviewed. After a delivery-only run it prints the
send-by-hand line instead, since the sample cuts sitting in `out/` were published
weeks earlier and re-offering them would be noise. It defaults to
**no** — it is the one rung that leaves the machine — and is skipped in silence
when no credentials are configured, so an operator without a key is not nagged on
every delivery. Choosing **3. Publish a review link** from the home screen says
what is missing instead: silence in answer to something you asked for reads as
success.

**Only the three `sample_` cuts upload.** The `tour_` cuts are listed as *held
back* and there is no flag that lifts it: the bucket behind `/preview/` is public,
and the whole point of the two families is that the unwatermarked deliverable does
not go out before sign-off. Send that one by hand, afterwards.

The upload prints every filename, its size, the exact remote path
(`<brand>/<listing>/<file>` — never the bare filename, or two listings collide)
and the resulting `https://real-estate.viabolat.com/preview/...` URL, then asks.
`--dry-run` stops there. If the listing's photos
miss the 720p gate it says so — measured from `photos/`, not read off a filename —
and asks a second time: a prospect judges the quality of your work by the file you
send them.

Confirmed links are appended to `outreach/links.csv` as
`uploaded_at,brand,listing,cut,url`. The URL is the **last** field on the line so
that nothing can be swallowed into it when you copy it. "Confirmed" means the
storage API lists the object at the right size — not that the public URL answered,
because the CDN edge may lag the upload by a few seconds. **A `/preview/` link
that 404s immediately after a publish is usually a cold edge, not a failed
upload.** Wait and retry before re-uploading.

**A cut over the bucket's ~50MB cap compresses instead of failing.** A two-minute
720p `sample_` cut can land past what the Supabase project accepts on a single
`PUT`. When that happens `publish.py` re-encodes a smaller review-only copy of the
same file, uploads that instead, and says so once the run finishes
(`N cut(s) were over the bucket's upload cap...`). `out/` is never touched — only
the copy that leaves the machine is smaller. See
[`an-oversized-upload-compresses-a-review-copy`](_rules/an-oversized-upload-compresses-a-review-copy.md).

**The email writes itself.** Every confirmed publish also leaves a ready-to-send
draft at `agents/<brand>/<listing>/<agent>/outreach_draft.txt` — right beside the
photos and `out/` cuts that produced it — with the wording from
`outreach/template.txt`, the agent's first name and the address from the listing's
`config.json`, and the `sample_branded` link. Open it, read it, paste it into your
mail client. `--dry-run` prints the draft instead of writing it, so you can see
exactly what it would say before anything uploads.

Two things it will not do. It never quotes a `tour_` link — cold outreach sends
the watermarked cut, and the difference is one word in a filename. And it never
sends: there is no SMTP credential in this repo and no flag that adds one. If a
field is blank in `config.json` the draft keeps the `{placeholder}` visible and
the console tells you which — fill it in before you send.

The local files in `out/` are never touched. `out/` stays the copy of record.

---

## 0c. One-time setup

Three things set up once and then never thought about again. They sit here, out
of the recurring loop, because a step you take once per project does not belong
beside one you take per listing.

### Arm the PII gate (once per clone)

```bash
git config core.hooksPath hooks
```

`hooks/pre-push` runs `check_pii.py` on every `git push` and refuses the push on
a finding. The hook file is committed, but **`core.hooksPath` is per-clone
config** — a fresh clone has the gate present and *off*, which on screen looks
exactly like the gate passing. So `tour.py`'s home screen checks the wiring on
every run and prints this command when it is missing, and runs the scan itself
regardless, because libgit2-based git clients — most IDE integrations — do not
run git hooks at all.

There is no bypass in the hook. `git push --no-verify` is git's own escape hatch
and is visible in the command you typed, which a bypass baked into the hook
would not be.

### Before pushing

```bash
python3 check_pii.py
```

**Exit 2 means the check could not run** — git missing, or the folder is not a git
repository — and is a refusal, not a pass. The scan enumerates files through git, so
outside a repository it would otherwise scan nothing and print that as clean. Treat
exit 2 as "do not push until this runs properly".

Exit 0 means no lead, agent phone or email address is in anything git would publish.
It scans against the real values in `leads.csv`, and prints findings **masked** — a
check that echoes the phone number it found has moved the leak into your scrollback.
Run it before every push; the repo being private is not the same as the data being
redacted.

### The publish credentials

`publish.py` needs two values, and refuses to run without them:

```
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_KEY=<the service_role key, not the anon key>
```

Put them in a `.env` beside `publish.py` — copy `.env.example` — or export them.
An exported variable always beats the file, so a shell you set deliberately is
never overridden by a stale `.env`. `.env` is gitignored, and `check_pii.py` now
also refuses a service key pasted anywhere git would publish.

**Exit 2 means the credentials are missing**, and is a refusal, not a pass. A
publish that quietly does nothing reads exactly like one that worked.

### Deploy the preview rewrite

A preview link only answers once the rewrite is deployed. Vercel hosts **no
video** — `vercel.json` is a single rewrite rule pointing `/preview/:path*` at the
public bucket, and the bytes come from Supabase. The published link is absolute,
`https://real-estate.viabolat.com/preview/<brand>/<listing>/<cut>`, so it works
where it is actually used: pasted into an email. The host lives in one place,
`PREVIEW_HOST` in `publish.py`, and must match the domain attached to this
deployment.

```bash
python3 check_pii.py       # exit 0, or do not push
git push
npx vercel --prod
```

`:path*`, not `:slug` — a remote object is `<brand>/<listing>/<file>`, three path
segments, and `:slug` matches one.

**`.vercelignore` is a second publishing boundary, and `check_pii.py` cannot see
it.** That check enumerates what *git* would publish; the Vercel CLI uploads the
working directory against `.vercelignore`, and when that file exists it takes
precedence over `.gitignore` — so a path being gitignored does **not** keep it out
of a deploy. `.env`, `scraper/`, `outreach/`, `agents.txt` and
`property_email.txt` are listed there explicitly for that reason. Anything new
holding a key or a lead has to be added there as well as to `.gitignore`.

Reading a 404 from `/preview/`:

| What you see | What it means |
|---|---|
| Vercel's branded `404: NOT_FOUND` page | The request never reached the rewrite — wrong path, or the deploy predates `vercel.json` |
| Supabase JSON `{"statusCode":"404"}` | The rewrite worked; the object is not in the bucket |
| A 404 for a few seconds, then it works | Cold CDN edge. `publish.py` already confirmed the object at the origin |

---

# Part 2 — Engine room

`make_tour.py` and everything under it. **You do not need this section to ship a
listing** — `tour.py` writes the `config.json` and runs the exact commands below.
Read it when something behaves unexpectedly, or when a listing needs something the
question set does not ask about.

## 0. What the script expects

| Path | Required | Notes |
|---|---|---|
| `photos/` | **yes** | Numbered in tour order: `01_exterior.jpg`, `02_entry.webp`, ... The prefix **is** the order. Every run prints the resolved order first — read it. |
| `music.mp3` | no | A **licensed** track. Skip with `--no-music`. |
| `lower_third.png` | no | Agent + listing info. Full-frame 1920x1080 plate, or a small strip. **Absent, one is drawn** from `address` / `agent_name` / `agent_phone` in `config.json`. |
| `logo.png` | no | Brokerage mark, top-left. Transparent padding trimmed automatically. |
| `viabolat.png` | no | Proofing watermark, centered. **`sample_` cuts only.** Wants >= 864px. |
| `config.json` | no | Per-listing overrides: timing, pacing, asset paths. See §4. |

Missing branding files are skipped silently in the build, but the run prints which
ones it found — check those two lines if branding doesn't appear.

Supported photo extensions: `.jpg .jpeg .png .webp .tif .tiff .bmp .heic`

**Run from the folder that holds `photos/`** — normally a listing folder,
`agents/<brand>/<listing>/<agent>/`. Every path in the script is relative to your working
directory. The one exception: an asset path that does not resolve there is retried
beside `make_tour.py`, which is what lets `viabolat.png` and the shared
`global_assets/` library work from any listing folder without being copied in.

`python3 tour.py` (from the project root) does all of this for you — see §0b. It
is a front end, not a separate pipeline: it writes `config.json` and runs the exact
commands shown in the scenarios below.

---

## 1. Flags

| Flag | Effect |
|---|---|
| `--contact-sheet` | Write `contact_sheet.png` — a numbered grid of `photos/` in build order — and exit. ~1s, no encoding, runs **before** the resolution gate. |
| `--draft` | 720p at a fast preset, **one** cut: `draft.mp4` in the listing root, branded and watermarked. ~1min. Never a deliverable — see §3. |
| *(none)* | 1920x1080. Requires photos >= 2150px wide. |
| `--720p` | 1280x720. Requires photos >= 1433px wide. |
| `--allow-lowres` | Build from photos that miss the gate. Output names are unchanged; the shortfall is printed before and after the build — see §5. |
| `--no-music` | Silent build. Outputs still carry a silent audio track. |
| `--keep-work` | Keep `clips/`, `work_silent.mp4` and `work_branded.mp4` so `--finish-only` can reuse them. Applies to the rung being run — a delivery build clears the draft lineage either way. |
| `--finish-only` | Reuse the stitches, redo music + branding only. Implies `--keep-work`. Restitches `work_branded.mp4` from the kept clips if it is gone; falls back to a full build if the clips are gone too. |
| `--samples-only` | Write only the three `sample_` cuts — run 1, the client's proofing copy. |
| `--delivery-only` | Write only the three `tour_` cuts — run 2, after sign-off. Needs no watermark. |

Flags combine freely: `python3 make_tour.py --720p --no-music --keep-work`

`--samples-only` and `--delivery-only` are opposites and passing both **exits 2** —
"build neither family" is not a request. Passing neither builds all six, which is
what a bare CLI run has always done; `tour.py` is what stages them across two runs.
See §3.

`--contact-sheet` ignores everything else and exits. `--draft` forces 720p, so
`--720p` is redundant with it and `--allow-lowres` is implied by intent — a draft
is a preview, and that is what the flag is for. Its intermediates are named apart
(`work_draft.mp4`, `clips_draft/`), so `--draft --finish-only` reuses the previous
*draft's* stitch and can never touch `work_silent.mp4`.

**One build per folder.** The script takes `.build.lock` with `O_EXCL` on startup
and releases it on any exit, clean or not. A second run — CLI or `tour.py` —
refuses immediately and names the pid holding it.

---

## 2. Scenarios

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
`tour.py` asks this every run ("Keep the lower third up for the whole tour?").

**When a card exists, the default answer is no.** The card and the drawn lower
third are rendered from the same `address` / `agent_name` / `agent_phone`, so
keeping the lower third up for the whole tour prints the operator's details twice
in one video. The default is instead: lower third introduces the property, clears
at `brand_out`, card closes. `tour.py` says so out loud and you can still override
it. A hand-made `lower_third.png` is exempt — it says something the card does not,
so it stays persistent by default.

By hand:
```bash
# in the listing folder, config.json:
#   {"brand_persistent": false, "brand_in": 2.0, "brand_out": 8.5}
python3 ../../../../make_tour.py --finish-only
```
`brand_out` must be greater than `brand_in` or the build refuses to start — an
inverted window is a valid filtergraph in which the overlay simply never appears.
A `brand_out` past the end of the video warns and leaves the lower third up to the
last frame. With an **intro** card the window is measured from the end of the card,
so `brand_in: 0.8` still means 0.8s into the photos, and the lower third never
appears over a card in either position.

### Change the intro / outro card
```bash
# in the listing folder, config.json:
#   {"card": "both", "card_seconds": 5.0}
python3 ../../../../make_tour.py --keep-work    # full rebuild required
```
`card` is `none`, `intro`, `outro` or `both`; `outro` is what `tour.py` writes on a
new listing. The card is drawn by ffmpeg from `address`, `agent_name`,
`agent_phone`, `brokerage` and the logo — nothing is exported from Canva. Its layout
picks itself: a logo that resolves gets the logo design, no logo gets the type-only
design with the brokerage name in its place, and a card with nothing to say is not
built at all (the run says so). `card_style` forces either layout, `card_theme`
forces the dark or light ground, `accent` and `font` restyle both the card and the
lower third.

The card rides in `work_branded.mp4`, **not** `work_silent.mp4` — that is what keeps
it off the MLS cut. Changing `card` or `card_seconds` therefore invalidates that
stitch, so it needs a full build, not `--finish-only`. The branded cuts come out
longer than the unbranded ones by the card(s) they carry; the run prints both
lengths.

### Swap the lower third text
```bash
# in the listing folder, config.json:
#   {"address": "46 Beacon St, Unit 5", "agent_name": "...", "agent_phone": "..."}
python3 ../../../../make_tour.py --finish-only
```
No Canva export, no PNG. The lower third is drawn from those three fields, and any
of them may be blank — blanks are dropped and the rest close up. A
`lower_third.png` that exists still wins, so a hand-authored plate stays available
for a listing that earns it.

### Build from scratch
```bash
python3 make_tour.py --keep-work
```
Builds all clips, stitches, adds music and branding, writes all **six** cuts.
Runtime scales with photo count — 17 photos takes a few minutes.

`--keep-work` is worth adding by default. Without it the intermediates are deleted
on success and any later branding tweak forces a full rebuild. It keeps *this* rung's
intermediates only — a successful delivery build clears `work_draft.mp4` and
`clips_draft/` regardless, since it can never reuse them.

### Swap a hand-made lower third plate
```bash
# replace lower_third.png, then:
python3 make_tour.py --finish-only
```
No code change. The file is re-read every build, and it takes precedence over the
drawn one. ~1 minute instead of a full rebuild.

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
python3 make_tour.py --delivery-only --finish-only
```
Moving `viabolat.png` out of the way does **not** do this: a watermark that will
not resolve is a hard refusal, not a skipped layer, because a `sample_` cut without
one is an unwatermarked deliverable wearing a proofing filename. It refuses at
preflight, in under a second, before the lock or any encoding — not five minutes in.
Ask for the delivery family instead and no watermark is needed.

### Build only the sample cuts
```bash
python3 make_tour.py --samples-only
```
Run 1. Three watermarked cuts, and the stitch is kept for run 2.

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
the situation, and `tour.py` says the same in its preflight — and offers to add the
prefixes for you in the current alphabetical order.

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
Or just use the `_tour_unbranded.mp4` cut, which already has no branding. Note this also
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

## 3. Outputs

Six files land in `out/`, overwritten on every run. Two families, same edit — or
one family at a time, which is how `tour.py` drives it.

**Two runs per listing.** The `tour_` trio is the paid deliverable and is only sent
after the client signs off, so building it up front spends half a six-minute encode,
and its share of ~200 MB, on a cold-outreach listing that may never reply. So:

| Run | Flag | Writes | Cost |
|---|---|---|---|
| 1 — proofing | `--samples-only` | the three `sample_` cuts | full build, ~6 min |
| 2 — after sign-off | `--delivery-only` | the three `tour_` cuts | `--finish-only`, ~1 min |

Run 2 is cheap because both families come off the **same stitch**, which run 1 left
behind. `.last_build.json`'s rung key names that intermediate lineage — `draft` /
`delivery` — not the cut family, so both runs record `delivery` and run 2 finds the
record unchanged. Change the photos or the pacing in between and it correctly does
a full rebuild instead.

**Which run a listing is on is derived from `out/`**, never recorded: nothing there
means run 1, `sample_` cuts alone mean run 2 is next, any `tour_` cut means
delivered. That is the same rule that keeps photo order in the filename prefix — a
marker file beside the artifacts drifts out of sync with them. `status.py` names
the state (`sample built -- publish the review link`, `sample published -- awaiting
sign-off`, `delivered, N cuts`).

A bare `python3 make_tour.py` still writes all six, and `tour.py` offers *All six
now* from the same menu for a client who has already paid. The staging is a
default, not a restriction.

Every filename is `<agent>_<family>_<shape>.mp4`. The `<agent>` part is
`output_prefix`, or `agent_name` slugified when that is blank — six listings all
writing `tour_branded.mp4` collide the moment the files leave `out/`. With both
blank the bare names come back, so an older folder driven from the CLI is
unchanged. The slug matches the one that named the folder: apostrophes drop
rather than separate, so `Sean O'Brien` gets `sean_obrien_tour_branded.mp4`.
Examples below use `jane_smith`.

### Delivery — `*_tour_*`, clean. Send **after** sign-off.

| File | Contents | Use |
|---|---|---|
| `jane_smith_tour_branded.mp4` | Card(s) + lower third + logo + music | Social, your site, your channels |
| `jane_smith_tour_unbranded.mp4` | Music only — no branding, **no card** | **MLS / IDX** — required to be clean |
| `jane_smith_tour_vertical.mp4` | 9:16 portrait, branded centre, clean blurred bands | Reels, TikTok, Shorts |

### Sample — `*_sample_*`, watermarked. Send **for review**.

| File | Contents |
|---|---|
| `jane_smith_sample_branded.mp4` | the branded tour + centered watermark |
| `jane_smith_sample_unbranded.mp4` | the unbranded tour + centered watermark |
| `jane_smith_sample_vertical.mp4` | the vertical tour + centered watermark |

### When the photos missed the gate

A build made with `--allow-lowres` produces the same six names as any other build.
The edit is identical; the pixels are an upscale. It is watchable for a review and
**not** MLS-ready, and **the filename will not tell you that** — `tour.py` prints
the count, the worst file and its upscale factor before it builds one and again
with the finished list, `status.py` marks the listing `soft (NNNpx photos)`, and
`publish.py` asks twice. See §5.

The client watches a `sample_` cut to decide. On approval, deliver the matching
`tour_` file. The watermark sits centered at 45% of frame and 35% opacity —
obscuring the room is the point, so an unapproved cut is not usable as-is.

> **Never send a `sample_` file as a deliverable. Never send a `tour_` file before
> sign-off.** The filename is the safeguard.

The watermark is **not** gated on branding — `sample_unbranded.mp4` carries it too,
otherwise the MLS-safe cut would be an unwatermarked free copy.

Runtime = `photos x 4s - (photos - 1) x 0.5s`. 17 photos = 60.0s. A card adds
`card_seconds - 0.5s` to the **branded** cuts only, so with a 5s outro that same
listing delivers 60.0s unbranded and 64.5s branded. Both lengths are printed.

### The card, and the two stitches

The intro/outro card is branding, so it rides in a second stitch:

| Stitch | Contents | Feeds |
|---|---|---|
| `work_silent.mp4` | photos only | `tour_unbranded`, `sample_unbranded` |
| `work_branded.mp4` | `[intro] + photos + [outro]` | `tour_branded`, `sample_branded`, `draft.mp4` |

That separation is what makes the MLS cut structurally card-free, rather than
card-free by a flag someone can flip. With `card: none` the second stitch is skipped
and every cut reads `work_silent.mp4`, so a no-card build is byte-identical to one
made before cards existed.

While a card is on screen the lower third and the top-left logo are held off — the
card already carries the address, the agent and the mark at full size, and running
both prints everything twice. The **watermark is exempt**: an unwatermarked outro
card is exactly the frame an unapproved sample would be screenshot from.

Note: each vertical cut is built from *two* sources — the blurred band from the
unbranded sibling, the centered frame from the branded one. So the band is clean and
the centre still carries the lower third and logo. The branded source is the longer
of the two when a card is configured, so the band is clone-padded and the output
pinned to the branded length — the last blurred room frame holds behind the card
rather than the band running out early.

### Draft — `draft.mp4`, listing root. Never leaves this machine.

`--draft` writes one file, and deliberately **not** into `out/`: `out/` holds real
cuts only, which is what makes the `tour_`/`sample_` prefix a boundary you can trust
at a glance. A draft is 720p at a fast x264 preset and carries the watermark. It is
a review rung for you, not for the client — the client reviews a `sample_` cut.

Its intermediates are `work_draft.mp4` and `clips_draft/`, named apart from the
delivery ones so a draft-quality stitch can never be picked up by a delivery build.

A successful **delivery** build clears them, whether or not you passed `--keep-work`:
a delivery supersedes any draft of the same listing and never reuses a draft stitch,
so keeping them just accumulates ~35 MB per listing. The next `--draft` after a
delivery therefore rebuilds in full instead of taking `--finish-only`. `draft.mp4`
itself is left in place — it is the review cut you asked for, not an intermediate.
The reverse never happens: a `--draft` run only ever clears what a draft wrote, so a
kept delivery stitch survives drafting intact.

That is `make_tour.py`'s own contract; it never touches `draft.mp4`. `tour.py` goes
one step further at rung 3: once a build actually writes the `sample_` cuts to
`out/`, it deletes `contact_sheet.png` and `draft.mp4` from the listing root — the
order and edit questions they answered are settled the moment the sample cuts exist.
A delivery-only rebuild (the client already signed off) does not re-run this; those
files were already cleared the first time this listing's samples were built.

---

## 4. Tuning

Constants marked **cfg** are also `config.json` keys — set them per listing without
touching the script. The rest are code edits that apply to every listing.

| Line | Constant | cfg key | Default | Effect |
|---|---|---|---|---|
| 177 | `CLIP_SECONDS` | `clip_seconds` | `4.0` | Seconds per photo |
| 178 | `XFADE_SECONDS` | `xfade_seconds` | `0.5` | Crossfade length |
| 180 | `ZOOM_MAX` | — | `1.12` | Ken Burns push. Above ~1.20 looks cheap. |
| 181 | `MUSIC_VOLUME` | — | `0.55` | Soundtrack level |
| 184 | `BRAND_PERSISTENT` | `brand_persistent` | `True` | `False` = lower third only during a window |
| 185-186 | `BRAND_IN` / `BRAND_OUT` | `brand_in` / `brand_out` | `0.8` / `6.5` | That window, when `BRAND_PERSISTENT` is `False`. Measured from the end of an intro card. |
| 187 | `LOGO_PERSISTENT` | — | `True` | Same, for the logo — but see the note below |
| 188 | `LOGO_BOX_W, LOGO_BOX_H` | — | `360, 200` | Logo size box, 1080p-relative (~19% frame width) |
| 191-193 | `LOWER_THIRD` / `LOGO` / `MUSIC` | `lower_third` / `logo` / `music` | the plain filenames | Which files the build uses |
| 196 | `SAMPLE_WATERMARK` | `watermark` | `"viabolat.png"` | Which file the sample cuts watermark with |
| 204-207 | `AGENT_NAME` / `AGENT_PHONE` / `ADDRESS` / `BROKERAGE` | `agent_name` / `agent_phone` / `address` / `brokerage` | `""` | The text on the drawn lower third and card. Any may be blank. |
| 212 | `CARD` | `card` | `"none"` | `none` / `intro` / `outro` / `both`. `tour.py` writes `outro` on a new listing. |
| 213 | `CARD_SECONDS` | `card_seconds` | `5.0` | Seconds per card |
| 214 | `CARD_STYLE` | `card_style` | `"auto"` | `auto` / `logo` / `type`. `auto` = logo layout if a logo resolves. |
| 215 | `CARD_THEME` | `card_theme` | `"auto"` | `auto` / `dark` / `light`. `auto` reads the logo's contrast. |
| 219 | `ACCENT` | `accent` | `"#C8A24A"` | Accent rule on both plates. On a light card an unset accent darkens. |
| 230 | `FONT` | `font` | `"Liberation Sans"` | A fontconfig **family name**, never a path |
| 231 | `SCRIM` | `scrim` | `"black@0.55"` | The panel behind the drawn lower third |
| 235 | `SAMPLE_WM_FRAC` | — | `0.45` | Watermark size, fraction of the frame |
| 236 | `SAMPLE_WM_OPACITY` | — | `0.35` | Watermark opacity, 0-1 |
| 250-251 | `CRF` / `X264_PRESET` | — | `18` / `medium` | Delivery encode quality. `--draft` swaps these to `20` / `veryfast`. |
| 252 | `VERTICAL_CRF` | — | `20` | Portrait cut, which re-encodes an already-encoded source |
| 282 | `MARGIN` | — | `70 * SCALE` | Overlay inset from the frame edge |
| 297-299 | `PLATE_W, PLATE_H` / `PLATE_MARGIN` / `CARD_LOGO_W, CARD_LOGO_H` | — | `1920, 1080` / `70` / `760, 300` | Plates are always authored at 1080p and scaled down, so 720p is not a second layout |
| 1025 | `CELL_W, CELL_H` | — | `480, 270` | Contact sheet cell. 4 across = a 1920px sheet. |

Branding, watermark, music and lower-third **text** changes need only
`--finish-only`. Changing `CLIP_SECONDS`, `XFADE_SECONDS`, `ZOOM_MAX`, `card` or
`card_seconds` requires a full rebuild — the first three reshape the clips and the
last two reshape `work_branded.mp4`, and `--finish-only` reuses both stitches.

The text fields feed both plates: the drawn lower third takes the address, agent
name and phone; the card takes those plus the brokerage, which stands in for a
missing logo on the type-only layout. A `lower_third.png` that resolves always wins
over the drawn one.

Setting `LOGO_PERSISTENT = False` makes the logo reuse `BRAND_IN`/`BRAND_OUT` —
the enable window in `finish()` is shared by every non-persistent layer. Give the
logo its own window before relying on that.

Raising `ZOOM_MAX` also raises the resolution requirement — the gate is
`OUT_W x ZOOM_MAX`.

`WORK_W` (line 277) is **not** a tuning knob. The comment above it records measured
frame-to-frame judder against supersample factor; `7680` is the knee for both
presets. Lowering it to "speed up 720p" reintroduces the judder it exists to remove.

---

## 5. The resolution gate

Every run measures the photos before it encodes anything, printing a per-file table
and the worst offender:

```
17 of 17 photos are below 2150px on the long edge, which is what 1920x1080 needs:
  01_exterior_front.webp              768x576  upscaled 2.8x
  02_exterior_street.png              384x288  upscaled 5.6x
  03_exterior_entrance.webp         1440x1080  upscaled 1.5x
  ...
  worst: 02_exterior_street.png at 384x288, upscaled 5.6x
```

From the bare CLI it then exits, naming the pixel target, the smaller preset if
that would clear it, and `--allow-lowres`. With the flag it builds and prints:

```
  --allow-lowres set: building anyway at 1920x1080. The cuts are named
  like any other build; the shortfall is restated when the build finishes.
```

and, once the cuts exist:

```
  BELOW PAR. 17 of 17 photos are under 2150px, so every cut
  above is a 1920x1080 upscale -- worst 02_exterior_street.png at 384x288,
  upscaled 5.6x.
  Watchable, not sharp. Rebuild from the photographer's originals before this
  goes to the MLS. Nothing in the filenames records this -- see IDEA.md 4.
```

`tour.py` never dead-ends. When neither preset clears it says so, quotes the count
and the worst file, drops to 720p + `--allow-lowres`, and builds. It used
to refuse at the *end* of a run — after the question set and a draft — despite
having known at preflight, which threw the work away and named no numbers. The gate
still measures exactly the same thing; it now **reports** rather than refusing or
renaming, everywhere the question comes up: preflight, the build confirmation, the
finished file list, `status.py`, and `publish.py`.

| Preset | Output | Minimum source width |
|---|---|---|
| default | 1920x1080 | **2150px** |
| `--720p` | 1280x720 | **1433px** |

The minimum is output width x `ZOOM_MAX` — the zoom crops *into* the photo, so the
pipeline needs more pixels than the final frame.

**`--allow-lowres` does not improve anything.** Upscaling a 384px photo to 1920px
smears what's there; there is no detail to recover. The console output is the
warning, not permission.

> **Never send a soft cut to a client or the MLS. If a build needs the flag, the
> photos are not ready.** The filename is silent on this by design — the check is
> re-run from `photos/` by `status.py` and `publish.py`, so it survives long after
> the build log has scrolled away.

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
| `A build is already running here (pid N)` | Another build holds `.build.lock` | Wait for it. If that pid is gone, delete `.build.lock` |
| Delivered video looks soft | Shipped `draft.mp4`, or a `--draft` cut renamed | Drafts are 720p at a fast preset. Rebuild without `--draft`; deliverables come out of `out/` |
| `draft.mp4` didn't pick up a photo change | Used `--draft --finish-only` | Same rule as delivery — anything that changes `photos/` needs a full run |
| Contact sheet disagrees with the video | Sheet regenerated after a rename, video built before it | The sheet is always current; rebuild fully with `--keep-work` |
| `no text for the card -- skipping it` | `address`, `agent_name`, `agent_phone` and `brokerage` are all blank | Fill at least one in `config.json`, or leave `card: none` and ignore it |
| Card appeared on the MLS cut | Cannot happen — the card lives in `work_branded.mp4` | If you see it, something wrote a card into `work_silent.mp4`. Delete both and rebuild |
| Branded cut is longer than the unbranded one | Expected — it carries the card(s) | The run prints both lengths. the `_tour_unbranded` cut is the clean, card-free one |
| Card or lower third text is clipped at the edge | Address longer than the plate | Shorten it, or drop the font size in `CARD_SIZES` / the lower-third rows |
| Card text renders as boxes or the wrong face | `font` names a family fontconfig cannot resolve | `fc-list \| grep -i <family>`. Unset `font` to fall back to the default family |
| Card ground is dark when you wanted light | The ground is picked from the logo's contrast | Set `card_theme` to `light` or `dark` to force it |
| Card carries a logo you wanted left off | A logo resolved, so the logo layout won | Set `card_style` to `type` |
| `REFUSING TO PUBLISH: SUPABASE_... not set` | No credentials in the environment or `.env` | See §0a. Exit 2 is a refusal, not a pass |
| A `tour_` cut shows as *held back* | Working as designed | The deliverable never auto-publishes. Send it by hand after sign-off |
| A `/preview/` link 404s right after publishing | CDN edge has not replicated yet | Wait, then retry. The run already confirmed the object at the origin |
| `UNVERIFIED: <file> is absent at the origin` | Upload reported success but the object is not there | Nothing was written to `links.csv`. Re-run the publish |
| `Uploads finished but the listing check could not run` | Network dropped between upload and verification | Treat as unverified — re-run rather than sending the link |
| `HTTP 401`/`403` on upload | Anon key instead of the `service_role` key | See §0a. The anon key cannot write to the bucket |
| `HTTP 400 EntityTooLarge` on upload | Cut is past the bucket's ~50MB cap | Nothing to do — `publish.py` retries with a compressed copy automatically |

**A failed build keeps its intermediates on purpose** so you can inspect them. Only a
successful run cleans up — which also means a failed delivery build leaves the draft
lineage in place along with everything else.

**Locking.** The script takes `.build.lock` with `O_EXCL` at startup and releases it
on any exit, clean or not, so two builds in one folder can no longer delete each
other's intermediates — whichever starts second refuses and names the pid holding
the lock. `tour.py` builds by running the script, so it is covered by the same lock —
it only ever *reads* the file to report who holds it, never writes it, or the build it
launched would be locked out of its own folder. If a run was killed hard enough to
leave the file behind, delete `.build.lock`.
