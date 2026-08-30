# PROGRESS.md — Build log and handoff

What has been built, what is proposed, and what a session picking this up from
another machine needs to know. Newest work at the top of §2.

**How this relates to the other docs.** `CLAUDE.md` is the standing project contract
and the non-negotiables. `STEPS.md` is the runbook — the exact command for every
scenario. `IDEA.md` is the photo sourcing standard (§1-7) plus a *branding/output*
backlog (§8). None of those track cross-project state, which is what this file is
for. When something here ships, its rule moves into `CLAUDE.md` and its command into
`STEPS.md`; the entry stays here as the record of *why*.

---

## 1. READ THIS FIRST IF YOU ARE ON A DIFFERENT MACHINE

Two things do not travel with the repo:

- **`agents/` is gitignored in full** — every listing folder, `photos/`, `config.json`,
  `brand.json`, and all six output cuts. A fresh clone has code and docs, no listings.
- **`scraper/leads.csv` is gitignored** — by a repo-level rule, so the protection
  travels with the clone (it was once covered only by a global `*.csv` rule, which
  does not). It is the **naming authority** —
  `agents/<slug(broker_name)>/<slug(address)>/<slug(agent_name)>`
  is derived from it, and `status.py` validates every folder against it. Without it,
  `status.py` cannot run the folder-name check and there is nothing to re-derive
  names from.

**Decided 2026-08-21: `leads.csv` stays untracked.** It is the lead list — agent
names, phones, emails — and the repo is now hardened so no lead can reach the remote
at all (see §2). Copy it across by hand, or re-derive it by re-running the scrape.
It is now ignored by a **repo-level** rule rather than only by the global one, so the
protection travels with the clone.

Branch: **`scraper`**, cut from `3c5e1a8`. The naming-integrity and test-suite work
below is committed and pushed to `origin/scraper`; the branch is not merged to `main`.

**Two files are deliberately untracked and do not travel:** `spec.md` (working notes
for whatever is in flight, which expire on ship) and `.claude/settings.local.json`
(machine-local). `LOGIC_GUIDE.md` **does** travel — it is the decision record, and the
*alternatives rejected* in it are the part that stops settled work being redone.

---

## 2. BUILT

### 2026-08-31 — A "contacted" tracker for leads

There was no record of which leads had actually been emailed — `leads.csv` gave
no signal of who'd been contacted once a draft went out. `publish.py` gains
`outreach/contacted.csv` (`marked_at,brand,listing,agent`), byte-for-byte the
same append-by-header-name shape `record_links()` already uses, plus
`record_contacted()`/`contacted()` — a write and a lookup, mirroring
`published_listings()`. Nothing writes it automatically:
`tour.py`'s `publish_rung()` asks once, right after a publish succeeds,
defaulting to No like every other prompt on this side of
`the-draft-is-automatic-the-send-is-not.md` — it only records a send that
already happened by hand. A new home-screen item **5**
(`mark_contacted_action()`) walks every published, not-yet-contacted listing
and asks the same question one at a time, for whatever was published in an
earlier session or skipped at that first prompt.

`status.py` gets a `contacted(brand, listing, agent)` wrapper and a `CONTACTED`
column in `print_rows()`, added without touching `survey()`'s row-tuple shape
(several call sites unpack it positionally). `scraper/lead.py`'s `leads.html`
gets the same column, joined by slugifying each row the same way
`scraper/photos.py`'s `target_for()` already names its folder.

The plan's literal instruction was to import `photos.slugify()` into `lead.py`
"the same way `status.py` already imports it" — at module scope. Tracing the
actual import order first found that would crash on the very first run:
`photos.py` imports *from* `lead.py`, and `lead.py` is not registered under
the name `"lead"` while running as `__main__`, so a module-level load in
`lead.py` re-executes `lead.py`'s own file fresh under that name, recursing
before `field()`/`extract_zip_city_state()` exist on it. Fixed by making the
load lazy and function-scoped (`lead._load_photos()`, called only from inside
`write_html_table()`), verified against a direct run with no hang or crash,
and pinned down by `TestLeadHtmlContactedColumn` in
`tests/test_scraper_duplicates.py` so the regression would show up as an
import error, not a wrong column. `lead.py` reads `outreach/contacted.csv`
directly rather than importing `publish.py` for the lookup, since
`publish.py`'s own `_jpeg_size()` also transitively loads `photos.py`.

`tests/test_outreach_draft.py` (`TestContactedRecord`),
`tests/test_scraper_duplicates.py` (`TestLeadHtmlContactedColumn`): 280 tests
total, ~2.5s, no ffmpeg. `python3 check_pii.py`: clean.

### 2026-08-30 — A confirmed sample publish clears its own cuts from `out/`

`publish.py` uploads `sample_` cuts to the review bucket but, by design, never
deleted the local copies — `a-publish-never-deletes-the-local-cut.md` still
holds for `publish.py` itself, unchanged. This adds the deletion one layer up:
`tour.py`'s `publish_rung()` now captures the `subprocess.run()` return code,
and on success calls a new `clear_published_cuts()`, which cross-checks
`outreach/links.csv` (via a new `publish.published_cuts(brand, listing)`) and
removes only the exact `sample_` filenames that row confirms are on the CDN —
never a `tour_` file, which can't appear in that column but is also checked by
`family()` directly in case a row is ever hand-edited or replayed. A successful
publish now also unconditionally re-runs `clear_review_artifacts()`, closing a
gap where a `--draft` rerun after the sample build regenerated
`draft.mp4`/`contact_sheet.png` with nothing left to clear them a second time.
A new `tour.py --sweep-published-samples [--yes]` applies the same cleanup
retroactively across every listing, dry-run by default, reusing
`clear_published_cuts()` so there is one implementation of "is this cut safe
to remove."

This makes "nothing built" and "published, then swept" look identical to
`out/`'s state, which would let `auto_targets()` re-select an
already-published, awaiting-sign-off listing as fresh. `tour.stage()` and
`status.py`'s `next_action()` both gained a `published(brand, listing)`
fallback (checked only when `out/` has neither cut family) to close it.
Writing the test for this (`tests/test_publish_cleanup.py`) surfaced a
pre-existing off-by-one bug in `stage()`'s brand/listing derivation — it read
`os.path.basename(listing_dir)` (the agent folder) as `listing` and its parent
as `brand`, one level shallower than `agents/<brand>/<listing>/<agent>`
actually nests (confirmed against `publish.remote_path()`, and against
`status.py`'s own already-correct version) — fixed as part of this change; no
existing test exercised that fallback path deeply enough to have caught it.
See
[`a-confirmed-sample-publish-clears-its-own-cuts`](_rules/a-confirmed-sample-publish-clears-its-own-cuts.md).
`tests/test_publish_cleanup.py`, `tests/test_publish_gate.py`: 272 tests total,
~2s, no ffmpeg. `python3 check_pii.py`: clean.

### 2026-08-30 — A 90-second ceiling, filled by the sharpest photos, never exceeded

Some dumps carry 30-39 photos; at a fixed per-photo pace that built a
2-3-minute video with nothing capping it. `make_tour.py` gained
`max_total_seconds` (`[cfg]`, default `90.0`) and a new `photo_quality.py`
module (same shape as `floorplan.py`: an ffmpeg subprocess decodes each photo
to a small in-memory RGB grid, scored in pure Python — edge/gradient energy
over luma — never given a path to write). A photo set that already fits is
untouched; one that doesn't gets trimmed to the sharpest photos that fit,
restored to their original filename order before the build, with a loud
report of what was dropped and why. This is a deliberate, narrow exception to
[`floor-plan-detection-is-flag-only`](_rules/floor-plan-detection-is-flag-only.md):
that halts for a human because dropping a real room photo by mistake is a
silent-failure risk, but excess-photo trimming was explicitly requested to run
unattended instead. See
[`excess-photos-are-trimmed-by-quality-never-halted`](_rules/excess-photos-are-trimmed-by-quality-never-halted.md).
`make_tour.py`'s own cap arithmetic (`max_photos_for()`) is deliberately
duplicated from `tour.py`'s `runtime()` rather than imported — `tour.py`
imports `make_tour`, not the other way around — held in agreement by a test.
`tests/test_photo_quality.py`. Docs: `_reference/config-schema.md`, the
`make_tour.py` module docstring, `STEPS.md`.

### 2026-08-30 — Loud, resource-saving duplicate detection in the scraper

A dump pasted twice for the same company/address/agent used to re-walk every
photo URL (skipping each on the per-file `os.path.exists()` check) and print
as though something happened, wasting a download pass and inviting a
redundant 6-minute encode. `scraper/photos.py` gained
`already_scraped(out_dir, urls)` — a pure function checking whether the
target folder already holds at least as many photos as the dump has URLs —
called before the download loop starts; a hit prints a loud banner and exits
`3` before touching a URL. A folder with *fewer* photos than the dump has URLs
is treated as an interrupted run, not a duplicate, and falls through to the
ordinary loop. `scraper/lead.py`'s existing `find_duplicate()` skip got the
same banner treatment via a new `duplicate_banner()`. `scraper/run.py` now
classifies each dump as new/duplicate/failed (via the exit-code pairs) instead
of binary pass/fail, and reports three separate counts in its batch summary.
Both `main()` entry points write into real, gitignored, PII-bearing paths
(`agents/`, `scraper/leads.csv`), so `tests/test_scraper_duplicates.py`
exercises only the pure, extracted functions directly, never `main()`.

### 2026-08-30 — A bare `make_tour.py` build now says what building "both" means, and no code defect was found for it

Investigated a report of "6 mp4s built instead of 3." Three research passes
over `tour.py`'s dispatch and `make_tour.py`'s flag parsing found no defect:
`--auto` hardcodes `cuts="sample"` unconditionally, and every default in
`build_choice()` resolves to 3 cuts — building all six is only reachable by an
explicit, non-default menu pick, or a bare `python3 make_tour.py` run outside
`tour.py` entirely. `STEPS.md` documents that bare form in a few diagnostic
recipes, which is the likely real-world path to the confusion. Fix was
guardrails, not a bug fix: `build_choice()`'s `"both"` branch, chosen at the
*sample* stage, now prints one explicit line naming the consequence
("Building the tour_ deliverables now too, before sign-off..."), and the bare
`make_tour.py` recipes in `STEPS.md` now carry a reminder to add
`--samples-only`/`--delivery-only` for one family.

### 2026-08-30 — `agents/`, `prospects/` and the outreach draft unify under company/address/agent

One property's outputs were scattered three ways: photos and `out/` cuts under
`agents/<brand>/<listing>/`, a review-view symlink under
`prospects/<agent>__<phone>/`, and the cold-email draft under
`outreach/drafts/<brand>__<listing>.txt`. `compass/41_worcester_sq_penthouse` had
three unrelated places to look for one deliverable.

`agents/<brand>/<listing>` grows a third, scrape-named segment:
`agents/<brand>/<listing>/<agent>`, sourced the same way as the first two —
`scraper/photos.py`'s `target_for()` now returns a 3-tuple, with a new
`UNASSIGNED_AGENT = "unassigned_agent"` placeholder for a blank `agentName`
(mirrors the existing `"unknown_brokerage"` fallback) rather than a silent empty
path segment. Every consumer threaded from `(brand, listing)` to
`(brand, listing, agent)`: `status.py`'s `survey()`/`next_action()`/`audit()`,
`prospects.py`'s `rebuild()`, `publish.py`'s `remote_path()`/`write_draft()`, and
every listing-walking function in `tour.py`, including a new `agent_dirs()`
helper and a third "Agent" pick step in `choose_listing()`.

The flat `outreach/drafts/` tree is retired. The draft now writes to
`agents/<brand>/<listing>/<agent>/outreach_draft.txt`, beside the `photos/` and
`out/` that produced it. `publish.py`'s remote bucket layout and
`outreach/links.csv`'s schema deliberately stay agent-blind
(`<brand>/<listing>/<file>`) — real `links.csv` rows already reference brands no
longer present under `agents/` at all, so it is a decoupled historical log, not
something this restructuring should retrofit. `remote_path()` now validates the
third segment exists (and fails closed on a stale 2-level leftover path) but
never includes it in the string it returns; `output_prefix` already keeps two
agents' identically-named cuts from colliding at the CDN layer.

`prospects/` keeps its shape and its own index key (slugified `agent_name` +
phone digits) — a different identity than the folder's `<agent>` slug, since the
two can legitimately run out of step (a folder can still sit on
`unassigned_agent` while `config.json` already carries the real name). Its
symlinks now point three levels deep and are named
`<brand>__<listing>__<agent>`. Correcting a placeholder once the real name is
known is `status.py`'s existing drift audit, extended to 3-tuples — no new
rename automation was built for it.

Two pre-existing bugs surfaced by re-reading the affected functions directly,
not by the original ask, and fixed as part of this change: `tour.py`'s
`_auto_build_one()` rerun-hint strings were truncating to just the agent segment
(`os.path.basename(listing_dir)` instead of a full relative path), and
`brand_settings()`/`reapply_brand()` were reading `config.json` one level too
shallow, which would have silently reported "nothing to apply" for every
listing.

Five real listings already on disk were migrated by hand into the new layout.
See [`the-scrape-names-the-folders`](_rules/the-scrape-names-the-folders.md) and
[`a-blank-agent-name-gets-a-placeholder-slug`](_rules/a-blank-agent-name-gets-a-placeholder-slug.md).
`tests/test_naming.py`, `tests/test_auto_flow.py`, `tests/test_home_screen.py`:
239 tests, ~0.6s, no ffmpeg. `python3 check_pii.py`: clean.

### 2026-08-30 — An oversized upload compresses a review copy instead of 413ing

`keller_williams_realty/16_holmfield_ave`'s first real publish put two of three
`sample_` cuts — `sample_branded` (77.8MB) and `sample_unbranded` (74.5MB) —
against Supabase Storage and got `HTTP 400 EntityTooLarge` on both. Only
`sample_vertical` (38.0MB) went through. `PRIMARY_CUT` is `sample_branded`, so
no cut confirmed and no email draft was written even though the build had
already succeeded and the operator had confirmed the upload interactively.

The bucket (`listing-media`) has no per-bucket `file_size_limit` — checked
directly against the Storage API's own bucket record — so the cap is the
Supabase project's platform default, roughly 50MB, and not something a bucket
setting can raise. A two-minute 720p `sample_` cut at `make_tour.py`'s `CRF 18`
routinely lands past it.

`publish.py` now carves the one retryable failure (`_too_large()`: a genuine
413 `EntityTooLarge`, not an auth or path error) out of `upload()`'s existing
fail-fast behavior. On that failure `main()` walks `UPLOAD_CRF_LADDER`
(`23, 28, 32`), re-encoding `out/`'s file smaller into a throwaway temp copy
via `_compressed_copy()` and retrying the same `PUT` at each rung until one
clears the cap or the ladder runs out. `out/` is never touched — the ladder
re-encodes the same local master into a new temp file each attempt and
discards it once that `PUT` resolves either way, so `out/` and every paid
`tour_` deliverable stay exactly as built. Verification (`present.get(name) !=
size`) was updated to compare against the size actually written to the wire
rather than `out/`'s original size — a compressed upload is legitimately
smaller than the local master by design, and comparing against the wrong
number would report every successful compressed upload as `UNVERIFIED`. A
publish run that compressed anything says so at the end, so the trade-off
(the public CDN copy is not byte-identical to `out/`) is disclosed, not
silent.

See [`an-oversized-upload-compresses-a-review-copy`](_rules/an-oversized-upload-compresses-a-review-copy.md).
`tests/test_publish_gate.py`: 21 tests, no network. `python3 check_pii.py`: clean.

### 2026-08-30 — 16 Holmfield Ave built with no logo, and no `brand.json` ever pointed at one

`keller_williams_realty/16_holmfield_ave` ran through `--auto` clean and built
the type-only card, even though `global_assets/logos/keller_williams_realty.png`
had sat in the repo the whole time — `brand.json` had simply never been told
about it, because `questions()`'s logo picker (asking a human to choose among
several unrelated marks) is deliberately skipped under `auto=True`, and
nothing else in `--auto` ever looked at `global_assets/logos/` on its own.

That skip is still correct when a brand has several candidate marks to choose
from. But a brokerage's *own* logo is not one of several — it lives at exactly
one predictable path, `global_assets/logos/<brand>.png`, the same slug as the
`agents/<brand>` folder. `_auto_build_one()` now tries that path before
`preflight()` runs, adopts it the moment it exists, and saves it to
`brand.json` with `save_brand()` — the same mechanism `questions()` already
uses to persist a confirmed brokerage name — so every other listing under
that brand inherits it from then on. When neither `cfg["logo"]` nor that
fixed path resolves, the listing halts, the same shape and the same place as
the phone check: printed, nothing built, the rest of the batch keeps going,
nothing recorded. `--ignore-missing-logo-check` is the same one-shot,
scope-required override as the other two.

See [`auto-picks-up-the-brand-logo-by-slug`](_rules/auto-picks-up-the-brand-logo-by-slug.md).
`tests/test_auto_flow.py`: 223 tests, ~2s, no ffmpeg. `python3 check_pii.py`: clean.

One side effect worth knowing about: `the_collaborative_companies/brand.json`
already points `logo` at a bare `tcc.png`, which resolves nowhere (not the
listing folder, not the repo root) — that brand's builds were already
shipping the type-only card silently. Its logo file is `global_assets/logos/
tcc.png`, and the folder slug is `the_collaborative_companies`, so the two
names disagree and the brand-slug lookup will not find it either. Its next
`--auto` run will halt until `brand.json`'s `logo` is pointed at
`global_assets/logos/tcc.png` directly, or the file is renamed/copied to
`global_assets/logos/the_collaborative_companies.png`.

### 2026-08-30 — A pasted dump runs itself to the 3 samples, and stops for one photo

**The ask, in the operator's words.** *"i want this to run so that after a .txt is
pasted (or more than one) it goes through the process up until the point of
contact sheet where I will check to see if there are any map images. ... If there
is a way to detect that and build that in to the code base I wam ok with that in
that case the automation should go all the way through to the 3 sample stage. ...
if there is a layout image needing to removed I will do that and then a trigger or
rerun needs to happen to make it go through all the way to the 3 samples stage.
That way when I paste the .txt and when the process is done the only thing I am
doing is checking the mp4 and if good copying the email template."*

`tour.py --auto` answers the same question set `build_flow()` already asks, from
`config.json`/`brand.json` alone (`auto=True` on `ask`/`confirm`/`pick`/`number` —
never `input()`), for every listing `stage()` reads as not yet at the sample
rung. It skips the logo and music picks outright rather than guess one — an
unresolved brokerage logo or a missing `music.mp3` builds with neither, same as a
hand-run build today. It builds the contact sheet, skips the draft rung, and
walks straight to the 3 `sample_` cuts.

**The floor-plan half of 4.2, built here.** New module `floorplan.py` scores every
photo right after the contact sheet, using the same ffmpeg-subprocess-plus-
raw-bytes technique `alpha_bbox()`/`art_contrast()` already use: downsample to a
32×32 grid and flag only a photo that clears both a high near-white fraction
**and** a high low-chroma fraction — requiring both, not either, is what keeps a
genuinely bright, white-walled room from tripping it. A hit halts just that
listing, prints the filename and the reason, and the batch keeps going; the
photo is never deleted, renamed or moved — `floorplan.py` is structurally
incapable of any of the three, checked by a source-text scan in its own test
file, not just asserted in a docstring.

**No new state for "resume."** A halted listing has written nothing to `out/`,
so `stage()` still reads it as a target on the next call — same "derive, never
record" discipline already governing `stage()` and `unimported_dumps()`.
Deleting the flagged file by hand and re-running `--auto`, bare or scoped to
`brand/listing`, is the entire resume mechanism. `--ignore-floorplan-check`
forces a false positive through once; it needs a scope, refusing to waive the
check across an entire batch, and is read once from argv — it never reaches
`config.json` or `.last_build.json`.

It never builds a draft and never publishes: the sample cuts already are the
reviewed artifact, and `publish.py`'s email draft can only be written from an
already-uploaded public URL, so auto-publishing would skip the human look this
whole feature exists to force. This is the one deliberate, narrow exception to
§7's "do not run a video build without asking" — the interactive flow is
unaffected whenever `--auto` is not the argument typed. Nothing here changes
`_auto_build_one()`'s destinations: it calls the same `run_build()`
`build_flow()` does, into the same `out/`, and `auto_targets()`'s
`stage() == "sample"` guard excludes an already-built listing from every later
sweep, so no listing's cuts can end up built twice.

`tests/test_floorplan.py` and `tests/test_auto_flow.py` guard both halves. 212
tests, ~2s, no ffmpeg. `python3 check_pii.py`: clean.

### 2026-08-30 — The first `--auto` listing shipped with no way to call back

The first real listing run through `--auto` end to end — imported, built,
published — belonged to a team agent whose `leads.csv` row had no
`agent_phone` (Zillow does not always expose one for a team listing), so
`questions(auto=True)` silently kept the blank default, same as it silently
keeps any other already-known value. The card and lower third built and
published with an address, a name and a brokerage, and no number. The
operator caught it after the sample cuts were already on the public bucket
and asked for a way to catch this before it ships again.

`_auto_build_one()` now checks `cfg.get("agent_phone")` right after
`questions(auto=True)`, before the contact sheet or any encode — the cheapest
possible point to stop. A blank phone halts that one listing exactly the way a
flagged floor-plan photo does: printed, not guessed at, the rest of the batch
keeps going, and nothing about the halt is recorded — filling in
`agent_phone` in `config.json` and re-running `--auto` (bare or scoped) is the
entire resume mechanism. `--ignore-missing-phone-check` is the same shape as
`--ignore-floorplan-check`: a one-shot override that always needs a
`brand/listing` scope and never reaches `save_config()`/`save_state()`.

This was a same-mechanism extension, not a new pattern — the phone check and
the floor-plan check now share one halt/resume story in `_auto_build_one()`.
See [`auto-halts-on-a-blank-agent-phone`](_rules/auto-halts-on-a-blank-agent-phone.md).
`tests/test_auto_flow.py`: 216 tests, ~2s, no ffmpeg. `python3 check_pii.py`: clean.

### 2026-08-30 — The review rungs clear themselves, and a view of agents/ by agent

**The ask, in the operator's words.** *"we have to have the codebase after the 3
samples get created delete all irrelevant files in the dir/folder of the property
and only keep like .json files or whatever is needed when the client agrees to pay
and then go back to tour.py run it and get the 3 mp4 the client paid for. also keep
track of it in like a prospects dir with the agent name and property."*

This resolves the open question from 2026-08-24 (*"should a successful delivery
build also remove `draft.mp4`?"*) but not the way it was framed there: the answer
is not "make `make_tour.py`'s delivery build do it." `contact_sheet.png` and
`draft.mp4` are `tour.py`'s own review rungs — rung 1 and rung 2, answering "is the
order right" and "does the edit feel right" — so `tour.py` clears them itself, in
`build_flow()`, the moment a run actually writes the `sample_` cuts (`what in
("sample", "both")`). `clear_review_artifacts()` deliberately does **not** touch
`work_draft.mp4`/`clips_draft/`: a delivery build already clears that lineage
regardless of `--keep-work` (2026-08-24, above), and duplicating that removal here
would be a second place doing one job. A delivery-only rebuild of an
already-sampled listing does not re-run this — those files were cleared the first
time. `photos/`, `config.json`, `brand.json`, `.last_build.json`, and the kept
delivery stitch are never touched, so a later "client said yes" run stays a fast
`--finish-only` rebuild instead of starting over.

**`prospects/<agent>__<phone>/<brand>__<listing>`** is the second half: a view of
`agents/` grouped by agent instead of brokerage, since `brand.json` deliberately
carries no agent identity (`brand-json-carries-no-agent-identity.md`) and one
brokerage can have several agents. Keyed on slugified `agent_name` **and** the
digits of `agent_phone` — name alone collides the moment two brokerages share an
agent name, which `leads.csv` already has. It is symlinks, not copies, wiped and
rewritten from scratch on every call — new module `prospects.py`, called from
`tour.py`'s `roll_up()` and from `status.py`'s own `__main__` — the same derived-
index pattern `leads.html` already uses, and for the same reason: a hand-maintained
second tree is the naming-drift failure `the-scrape-names-the-folders.md` already
happened once. `status.py`'s own docstring says it writes nothing, so the rebuild
does not live inside `survey()`; both call sites pass in `status.py`'s existing
`slugify` rather than `prospects.py` loading a third copy of it.

`prospects/` holds an agent's name and phone number in its directory names and
symlinks straight into `agents/`, so it is exactly the PII `agents/` is already
gitignored to keep off the repo — added to both `.gitignore` and `.vercelignore`,
the second publishing boundary `a-deploy-is-a-second-publishing-boundary.md`
requires. `check_pii.py` only scans what git would publish, so an ignored
`prospects/` is invisible to it by design, same as `agents/`.

`tests/test_review_cleanup.py` and `tests/test_prospects.py` guard both. 179
tests, ~0.6s, no ffmpeg. `python3 check_pii.py`: clean.

### 2026-08-26 — One front door, and a brand default that would have crossed two agents

**The complaint, in the operator's words.** *"i feel there are too many .py files
and that confuse the user. npx vercel --prod then publish.py check_pii.py etc etc
these are all confusing and hard to remember which does what."*

Correct, and it is the same failure `tour.py` was built to fix, one level up.
`tour.py` replaced a dashboard with thirteen controls by inheriting or deriving
anything with the same answer every time. That rule was applied to the build and
then never applied to the pipeline around it, which grew back to eight commands.
Sorted by what they actually are, only one is a decision:

| Command | What it really is | What happened to it |
|---|---|---|
| `check_pii.py` | a gate; never has an interesting answer | `hooks/pre-push` |
| `npx vercel --prod` | one-time setup, not per listing | out of the recurring runbook |
| `publish.py` | already rung 4 | also home-screen item 3 |
| `status.py` | "where am I" | **is** the home screen |
| `run.py` | a real action, but a *detectable* one | offered, not remembered |
| `unittest` | developer-only | out of the operator runbook |
| `make_tour.py` | the engine | documented escape hatch |
| `tour.py` | the front door | stays |

**What was built.** `python3 tour.py` now opens on `status.py`'s roll-up — the
same rows, the same drift and *unverifiable* reports — then four choices: build,
import pending dumps, publish a review link, brand settings. `--build` skips it.

Nothing behind that screen changed. `build_flow()` is the whole of what `main()`
used to be, moved down one level; every rung, prompt, default, refusal and flag is
what it was, verified by driving it through preflight, the question set and all
three rungs.

`status.py`'s body was split into `survey()` / `audit()` / `print_audit()` so the
home screen calls the *same* functions rather than growing a second copy. Two
implementations of the scrape-naming check is the exact drift that check exists to
catch. `status.py` still runs standalone and prints byte-identical output.

**Pending dumps are derived, never recorded.** Which `scraper/dumps/*.txt` have no
listing yet is answered by parsing the dump and checking whether
`agents/slugify(broker)/slugify(address)` exists. No marker file, no manifest —
the photo-order rule one level up: a record kept beside the artifacts drifts out
of sync with them and is then wrong in a way nothing detects. Deleting a listing
folder correctly re-offers its dump, which a marker could not do.
`tests/test_home_screen.py` asserts the detection writes nothing, and parses the
three relevant files with `ast` — comments stripped — to fail if any of them ever
gains a processed-dumps record.

**The PII gate now runs itself.** `hooks/pre-push` runs `check_pii.py`, armed with
`git config core.hooksPath hooks`. Verified: a phone number in a tracked file exits
1 and blocks; removing it exits 0. Two holes are stated rather than papered over —
a fresh clone has `core.hooksPath` unset, so the hook is present and *off*; and
libgit2-based clients (most IDE git integrations) do not run git hooks at all, and
this repo *has* been pushed by something that was not the shell. So the home screen
checks the wiring and shouts with the one-line fix, and runs the scan itself
regardless. `check_pii.py` is unmodified.

**"Re-apply brand defaults" now exists.** `CLAUDE.md` had promised it since the
Streamlit dashboard was deleted; it existed nowhere. Brand settings → pick brand →
it lists every key it would change, per listing, and asks before writing. It is the
one action in the tool that edits files the operator is not looking at.

**A latent bug found on the way in, and the reason it mattered.** `tour.py`'s
`BRAND_KEYS` carried `agent_name` and `agent_phone`, and `questions()` offered
*"Save the name, phone and brokerage as {brand} defaults?"* with the confirm
defaulting to **yes**. `CLAUDE.md` names the opposite as a non-negotiable.

Nothing had gone wrong yet — all nine `brand.json` files on disk were clean, so
this was armed, not fired. But `leads.csv` lists **two agents under Coldwell Banker
Realty - Boston, two under Gibson Sotheby's International Realty and two under
Serhant**, and `load_config()` layers `brand.json` *under* the listing's
`config.json` without printing anything. One yes would have put one agent's phone
number on the other agent's card, lower third and output filenames across every
listing that brokerage owns, silently.

It also sat directly in the path of this work: "Re-apply brand defaults" is
precisely the operation that would have pushed it into every listing at once.
Fixed at both ends — `save_brand()` filters the two keys, `load_brand()` strips
them on read so a hand-edited or legacy file cannot reintroduce them either — and
the prompt now offers only `brokerage`, which is genuinely the same string for
every listing a brand owns. `tests/test_brand_scope.py` fails if either key returns
by any route, including a check of the nine real files on disk.

**STEPS.md split by audience.** 660 lines and 30+ flat scenario headings was the
thing that was actually hard to navigate. Part 1 — Operator: one command, the three
rungs, the review link, and a fenced one-time setup section holding the hook wiring,
the publish credentials and `npx vercel --prod`. Part 2 — Engine room: the flags,
the scenarios, the tuning, the gate, the failure modes, framed as *you do not need
this to ship a listing*. Content preserved; ordering and framing changed.

**Cleanup pass, same day.** Four things the first cut left duplicated:
`status.py`'s row table is now `print_rows()` beside `print_audit()`, and the home
screen calls it instead of its own copy -- that copy had already drifted, silently
dropping the *"N brokerage(s) need a logo or music set once"* line, so the home
screen was telling the operator to add a logo per listing and never saying it is
set once per brand, which is the whole point of the Brand settings action beneath
it. `scraper/photos.py` grew `target_for(text)`, the one function that turns
a dump into the folder it scaffolds *or refuses it*; `main()` and `tour.py`'s
pending-dump scan both call it, so the folder-naming decision has one owner rather
than two copies that could disagree about an already-imported listing. The two
near-identical module importers in `tests/helpers.py` became one. And the home
screen no longer re-walks every photo, re-parses every dump and re-runs
`check_pii.py` to reprint four lines after a mistyped menu key -- it recomputes
after any action that writes, which is all of them.

**One real bug surfaced by testing that refactor.** `scraper/photos.py` has
called `sys.exit(2)` on a non-listing dump since the refusal was added, and never
imported `sys` -- so that path raised `NameError` and exited **1** with a traceback
where the contract says 2. It wrote nothing and exited non-zero either way, which
is exactly why it survived: the failure looked like the refusal working. Added the
import; the refusal now prints its message and exits 2.

**Verified.** 116 tests (95 + 21), ~0.6s, no ffmpeg. `check_pii.py` exit 0.
`status.py` output unchanged. The hook blocks and clears. Unsetting
`core.hooksPath` makes the home screen shout and re-setting it clears the warning.
`mv scraper /tmp` leaves the roll-up unavailable *with the reason printed* and the
build route intact. One test fixture and one hook `echo` had to be reworded: both
tripped the repo's own guards by containing a phone-shaped string and the literal
`--no-verify` in prose, which is the guards working.

### 2026-08-24 — The draft lineage was never swept up

**The symptom, as the operator hit it.** Three near-identical files sitting in a
listing folder after a `tour.py` run — `work_silent.mp4`, `work_branded.mp4`,
`work_draft.mp4`, all silent, all unbranded, one of them apparently a duplicate.

Three of the four observations were the system working as designed, and the
explanation is worth keeping because the question will be asked again:

- **All three are silent and unbranded** because the stitch stage is deliberately a
  naked photo reel. Music, lower third, logo and watermark are applied in
  `finish()`, which writes to `out/`. Nothing named `work_*` should ever have
  branding on it.
- **`work_silent` ≠ `work_branded`** — 70.5s vs 75.0s on `8_dartmouth_st_5`, which is
  exactly the 5.0s outro card less the 0.5s crossfade. That split is the MLS rule:
  `work_silent.mp4` feeds the unbranded cuts, so a card baked into it would put an
  agent's name and phone on the MLS file.
- **They survive at all** because `tour.py` always passes `--keep-work` or
  `--finish-only` on both rungs, so the next rung can reuse the stitch. A bare
  `python3 make_tour.py` deletes them.
- **`work_branded` and `work_draft` really were near-duplicates here** — but only
  because the delivery build also ran at 720p (the photos miss the 2150px gate). At
  1080p they differ in resolution as well as preset.

**The real defect underneath.** `cleanup()` only ever removed `SILENT_WORK` and
`BRANDED_WORK`, so on a delivery run — where `SILENT_WORK` is `work_silent.mp4` —
nothing ever deleted `work_draft.mp4` or `clips_draft/`. Combined with `tour.py`
always passing `--keep-work`/`--finish-only`, **every listing ever drafted kept its
draft lineage forever**: 68 MB across two listings on this machine, and it would
have grown with every listing. Not a correctness bug, which is why it survived the
2026-08-24 audit — nothing it produced was wrong, it just never stopped
accumulating.

**The fix, and the asymmetry that is deliberate.** A successful **delivery** build
now clears `work_draft.mp4` and `clips_draft/` *regardless of `--keep-work`*.
`--keep-work` and `--finish-only` are about reusing **this rung's** stitch next run,
and a delivery run can never reuse a draft stitch — so the flags have nothing to say
about the other rung's intermediates. The cost is that the next `--draft` after a
delivery rebuilds in full (~45s) instead of taking `--finish-only`, which is the
right trade: after a delivery you have shipped, and a stale draft-quality
intermediate is exactly the hazard the separate names exist to prevent.

The reverse is **not** symmetric and must not be made so. A `--draft` run clears only
what a draft wrote. Fixing this surfaced a latent bug in the old code: `cleanup()`
deleted `BRANDED_WORK` unconditionally, so a bare `python3 make_tour.py --draft` in a
folder holding a kept delivery stitch deleted `work_branded.mp4` and left
`work_silent.mp4` — half a lineage. It degraded to a restitch rather than a bad
video (the `--finish-only` path rebuilds a missing `work_branded.mp4` from the kept
clips), so it never showed up as a failure. Each rung now clears its own.

`draft.mp4` is **not** touched. It is the review cut the operator asked for, sitting
in the listing root by design — not an intermediate. Deleting a named output on the
operator's behalf is a different decision, and it was not taken here.
See §6 for the one question this left open.

`tests/test_cleanup_lineage.py` guards both directions plus the `draft.mp4`
exemption. 79 tests, ~0.8s, no ffmpeg. The 68 MB of existing leftovers were removed.

**Also settled this session, no code change:**

- **`make_tour.py` does not need `photos/` in the repo root.** It reads the *working
  directory* — `cd agents/<brand>/<listing>; python3 ../../../make_tour.py`. Only
  shared assets (`viabolat.png`, `global_assets/`) fall back to `SCRIPT_DIR`.
- **`make_tour.py` stays alongside `tour.py`.** They are engine and interface, not
  two ways to do the same thing: `tour.py` has zero encoding logic and shells out
  (`tour.py:590`). Merging them is blocked on `make_tour.py` resolving every tuning
  constant from `config.json` at *import* time against the process cwd — importing
  it from the repo root binds the wrong values, which is precisely why `tour.py`
  subprocesses instead of calling functions. It also imports `gate_failures`,
  `_slug`, `PHOTO_EXTS` and `gate_min` from it so the wizard and the build cannot
  drift on the resolution gate or the filename slug.
- **A positional directory argument was designed and deferred** — see §5.

---

### 2026-08-24 — Five crashes, a hang, and a gate that failed open

An external audit proposed seven findings. **All seven were reproduced by running
them** before anything was changed; three of its severity calls and one of its
remediations were wrong, and are corrected below. Six are fixed, one is deferred
with the reason recorded in §6.

**The gate failed open, which the audit rated LOW.** `check_pii.py` enumerates
files by shelling out to git, and `git()` returns `[]` on a failed subprocess. In a
folder that is not a git repository it scanned nothing and printed *"Scanned 0
publishable file(s) / No leads or PII found. Safe to push."* — exit 0, over a
directory that may hold the entire lead list. That is this file's own philosophy
inverted: *"A pattern that fails is invisible; a check that exits non-zero is not."*
It now exits 2 both when git will not run and when the file list comes back empty.
Rated highest here because it is the only finding that silently weakens a boundary
rather than crashing.

**The music loop could hang.** `prepare_music` loops a short track by crossfading
it onto itself, stepping `length = length*2 - d`. That has a fixed point at `d`:
with `d` pinned to `MUSIC_XFADE = 2.0`, a 2.0s body stayed 2.0s forever and
anything shorter ran negative, so `while length < need` never exited. No error, no
output, no timeout — the build just stopped. `music_span()` floors the body at
1.0s, so any track under ~2s of real music reached it. The seam is now
`min(MUSIC_XFADE, body/2)`, which is **exactly `MUSIC_XFADE` for any body ≥ 4s**, so
no real track's audio changes; `MUSIC_LOOP_MAX` is the backstop.

**A 0-byte PNG divided by zero mid-build.** Every fit box is
`min(BOX_W / aw, BOX_H / ah)`, and `dimensions()` returns `(0, 0)` for anything it
cannot decode. `os.path.exists()` passed the file, so the crash landed inside
`finish()` — after every clip had already been rendered. This is the same hole
`music_ok()` was written to close, one asset type over; `image_ok()` closes it.

*The audit's remediation here was wrong and was not followed.* It said to skip the
overlay with a warning. Doing that for the **watermark** writes an unmarked
`sample_` cut — the one file `CLAUDE.md` forbids sending. Branding is cosmetic and
degrades with a warning; the watermark is a boundary and refuses.

**`status.py` died on one bad entry.** A *directory* named `01_front.jpg` matched
the extension filter, and `jpeg_size()` opens its path with no error handling, so
the read-only overview raised `IsADirectoryError` and reported nothing at all. Both
it and `make_tour.py`'s photo glob now require `os.path.isfile`; `_size()` also
swallows `PermissionError`, which is the likelier real-world trigger.

**`tour.py` was a second naming authority.** Its "+ New brand / + New listing"
took typed text literally, so `Coldwell Banker Realty - Boston` created a folder
with spaces that no scrape could produce and that `status.py` flags forever after.
The audit rated this LOW; against the *"the scrape names the folders; nothing else
does"* non-negotiable it is the most direct contract violation in the set. It now
runs `make_tour._slug` — already imported, so no third slug function — and says out
loud that a hand-named folder reads as unverifiable until it is scraped.

**The resolution gates had nothing holding them together.** `GATE_1080P` / `GATE_720P`
are hardcoded in `status.py` and `scraper/photos.py`, mirroring
`int(OUT_W * ZOOM_MAX)` in `make_tour.py`. Importing across would make the scraper
depend on the builder, which is rejected for the same reason the two sluggers stay
separate — so the redundancy stays and a test holds it together instead.

`tests/test_guards.py` — 15 tests, bringing the suite to **75**. Each was verified
to fail on the regression it names: reverting the crossfade clamp errors both music
tests, reverting `image_ok` raises `ZeroDivisionError`, reverting the `isfile`
filter raises `IsADirectoryError`, and drifting `GATE_1080P` fails with
*"status.py's 1080p gate has drifted from make_tour"*. The PII test needed **both**
new guards reverted to fail, since either one alone catches the case — defence in
depth, confirmed rather than assumed.

The new fixtures tripped `check_pii.py` again, exactly as the last batch did: the
gate matches phone *shape*, so a made-up number in the 555 range is a finding all
the same -- being fictional is not a property the regex can see. The fixture was
rewritten to carry no number at all; the gate was not touched. Same rule applies
to prose: this paragraph cannot quote the literal it is about.

### 2026-08-24 — A test suite for the non-negotiables, and one slug rule for both namers

`tests/` — 60 stdlib `unittest` tests, ~0.3s, no ffmpeg invoked (75 across six
modules after the audit entry above). They guard the
rules in `CLAUDE.md` that fail *silently*: a card leaking into `work_silent.mp4`
puts an agent's phone number on the MLS and still produces a valid video, and a
shuffled photo order was delivered once already with no symptom but the finished
film. Run with `python3 -m unittest discover -s tests -t .`

Three techniques, one per kind of rule. A fresh import under a temp cwd, because
every `[cfg]` constant resolves from `config.json` at import time. A real
`finish()` with `run()` stubbed, because the filtergraph *is* the deliverable and
which overlay carries an `enable=` window is the whole of the card/branding rule.
AST inspection of `main()`, because which stitch each `finish()` call is handed is
wiring, not behaviour — there is nothing to assert on at runtime short of decoding
frames.

Each guard was verified to fail on the regression it names, not merely to pass on
green: injecting a `photo_order` config key broke three tests, and pointing
`tour_unbranded` at `branded_silent` produced *"tour_unbranded reads
'branded_silent' -- the card-bearing stitch would put the agent's details on the
MLS"*.

**The two slug functions now agree on apostrophes.** Writing the tests surfaced a
divergence: `scraper/photos.slugify` strips apostrophes before separating
(it names the folders), while `make_tour._slug` mapped every non-alphanumeric to a
separator (it names the files inside them). An agent called Sean O'Brien would
have had `sean_obrien/` holding `sean_o_brien_tour_branded.mp4` — one name, two
spellings, which is exactly the drift a single naming authority exists to prevent.
`_slug` now drops both the straight and typographic apostrophe.

*Impact on existing work: none.* No `agent_name` or `output_prefix` in any
listing's `config.json` contains an apostrophe — the two that do carry one hold it
in `brokerage`, which is card display text and never passes through a slugger. No
delivered filename changes. The fix is preventive, and it was verified that way
before it was made rather than assumed.

**`status.py` no longer passes config-less folders silently.** The drift check
keys on `agent_phone` out of `config.json`, so a folder that never had one
produced no match and fell through — and "has no config.json" is the strongest
available signal that a folder was never scaffolded by the scraper, i.e. the
likeliest hand-named folder there is. The check skipped precisely the case it was
built to catch, which is how `brewester/9_w_cedar` sat through the scrape-naming
commit. It now reports those as *unverifiable*, and `next_action` stops telling
them to rerun `photos.py` — there is no dump behind them to rerun, so the
advice was a dead end. The phone match itself is unchanged and still runs on every
folder, including ones whose name matches the scrape: a folder named for one lead
row while its config carries another agent's phone is worse drift, not less.

*Both legacy folders were left in place, deliberately.* `brewester/9_w_cedar` (17
photos, 384–1440px, six cuts in the listing root rather than `out/`, no agent
prefix, stale `work_silent.mp4` + `clips/`) and `corcoran/46_beacon_5` predate the
`out/` convention and the prefix rule. The scrape cannot name a listing it has no
row for, and hand-naming one is the second authority the rule exists to prevent.

*Why they are still two functions:* `make_tour.py` runs with cwd set to a listing
folder and nothing but ffmpeg on the path, so importing from `scraper/` would make
a build depend on the scrape, which it otherwise never does. They also differ on
the empty case deliberately — the scraper falls back to `listing` because a folder
cannot be named `""`, while `_slug` returns `""` so a blank `agent_name` leaves the
bare `tour_`/`sample_` names an older CLI folder already has. Both differences are
pinned by tests so neither gets "tidied up".

### 2026-08-21 — Batch scraping, and hardening the repo for a private remote

**Batch scraping.** `run.py` now takes a single dump *or* a folder, defaulting
to `scraper/dumps/`:

```bash
python3 scraper/run.py            # every *.txt in scraper/dumps/
python3 scraper/run.py one.txt    # unchanged single-dump path
```

*Why this shape:* one listing per file, never concatenated. The parsers are
first-match regexes over the whole text, so two dumps in one file read the first
listing's agent name and phone onto the second listing's photos — a wrong phone
number on a finished video, with nothing raised.

*Why there is no `processed/` folder.* Re-running is idempotent — duplicate lead rows
are skipped on `zpid` + agent phone, photos already on disk are skipped, neither JSON
is ever overwritten. Moving dumps after processing would be a second piece of state to
drift out of sync with the folder, the same objection that keeps photo order in the
filename. Leave them and run it again.

One bad dump does not stop the batch; failures are named in a summary and the run
exits non-zero, so a half-worked batch cannot look like a clean one.

**A dump that is not a listing is now refused** — found by building the batch and
testing it against an empty file and a garbage file. Both *succeeded*: each appended a
row of blanks to `leads.csv` and created `agents/unknown_brokerage/listing/` with a
`brand.json`, and the batch reported "4 of 4 processed cleanly". Worse, duplicate
detection needs a `zpid` to compare, so those blank rows could never be recognised as
duplicates — every rerun would append another. Both scripts now exit non-zero on a
dump with no `zpid` and no address, before writing anything. At one dump a human
notices; at twenty it silently poisons the lead list, which is also the naming
authority.

**PII hardening for a private remote.**

Git history was checked first and is clean — only code, docs and `.gitkeep` were ever
committed. No `leads.csv`, no dumps, no `agents/`. **No history rewrite is needed.**

- `.gitignore` gained repo-level rules for `leads.csv`, `leads.html`, `paste.txt`,
  `beautified.txt`, `dumps/*`, `scraper/photos/`, `agents.txt`, `property_email.txt`
  and `outreach/`. Previously `leads.csv` was covered **only** by a global
  `~/.gitignore_global` `*.csv` rule, which does not travel with the repo, and
  `leads.html` and `paste.txt` were not ignored at all.
- *Caught while writing it:* the first version put a trailing `# comment` after each
  pattern. **git only treats `#` as a comment at the start of a line**, so those were
  literal patterns containing spaces and matched nothing — `leads.html` and
  `paste.txt`, the two worst files, stayed unignored. Verified with `git check-ignore
  -v` on all ten paths afterwards. Every pattern is on its own line now, with that
  reason recorded in the file.
- **`check_pii.py`** (new, repo root) scans everything git would publish — tracked,
  staged, and untracked-but-not-ignored — for anything phone- or email-shaped, and for
  every real name, phone and email currently in `leads.csv`. Exits non-zero on a hit.
  *Why a dictionary scan rather than patterns alone:* the lead list is the ground truth
  for what must not escape, so it is what the scan runs against instead of a guess at
  what a name looks like. **Findings are printed masked** — a check that echoes the
  phone number it found has moved the leak into the terminal, the scrollback and any
  CI log. Verified by planting a phone number and an email in `STEPS.md`: it fired,
  then passed once removed.
- Two real agent names had leaked into text that would be pushed — one in `PROGRESS.md`
  prose, one in the `lead.py` module docstring's example. Both replaced.

*Why bother at all on a private repo:* a private repo is an access-control boundary,
not a redaction one. It gets shared with a collaborator, cloned onto a second machine,
or made public years later, and nothing re-reviews the history at that moment.

### 2026-08-21 — Scrape-driven listing creation, and the scrape as naming authority

The pipeline used to start at a listing folder someone made by hand. It now starts at
a copied Zillow page dump.

```bash
python3 scraper/run.py scraper/paste.txt   # lead row + a scaffolded, buildable listing
python3 status.py                                 # every listing and its one next action
```

**Photos land in the build tree.** `scraper/photos.py` writes to
`agents/<slug(broker_name)>/<slug(address)>/photos/`, a sibling of `scraper/`, not a
subfolder. That is exactly the working directory `make_tour.py` expects, so a scrape
drops in ready to build with no moving or renaming.

**The scrape is the naming authority.** Both folder names are slugified from the same
dump fields `lead.py` writes to the `broker_name` and `address` columns, so a
folder and its lead row cannot disagree. The slug drops apostrophes rather than
turning them into separators (`gibson_sothebys_international_realty`, not
`gibson_sotheby_s_...`).

*Why it was worth doing:* `coldwell_banker/2_comm_ave` sat on disk beside a lead row
reading `Coldwell Banker Realty - Boston` / `2 Commonwealth Ave`. Nothing was wrong
enough to notice, and nothing would have been until two brokerages collided. The
alternative considered and **rejected** was an alias table mapping scraped brokerage
names onto shorter hand-picked ones — that is a second naming authority, and the two
drift the moment a brokerage is renamed.

*Accepted cost:* `Coldwell Banker Realty - Boston` and `Coldwell Banker Realty -
Waltham` are two brand folders with two `brand.json` files. Set that logo twice.

**Existing folders were migrated onto it**, matched to lead rows by **agent phone** —
address text formatting varies between config and CSV, a phone number does not:

```
coldwell_banker/2_comm_ave                  -> coldwell_banker_realty_boston/2_commonwealth_ave
gibson_sothebys/260_262_commonwealth_ave_1b -> gibson_sothebys_international_realty/260_262_commonwealth_ave_1b
```

`boston_advanced_realty/335_w_2nd_st_unit_8` was already correct. `brewester/9_w_cedar`
and `corcoran/46_beacon_5` have no lead row and were left untouched — they predate the
scraper and there is nothing to derive their names from.

**`status.py` re-checks folder names on every run** and prints the `mv` for anything
that has drifted. A one-off rename fixes today; the check is what keeps it fixed.
A folder with no lead row at all is listed separately as unverifiable — see
2026-08-24, which closed the hole where those passed silently.

**Scaffolding, written from the dump, never overwritten:**

- `agents/<broker>/brand.json` — pacing, card defaults, brokerage name. `logo` and
  `music` are left **blank** on purpose; those are the operator's to supply.
- `agents/<broker>/<address>/config.json` — brokerage, display address, agent name,
  agent phone, the brand's values inherited at creation, and a pinned `watermark` path.

*Why scaffold at all:* every one of those fields is already in the dump. Retyping an
agent's phone number is a transcription error that ships on a finished client video
and is invisible in review, because a wrong number still looks like a phone number.

**`brand.json` no longer carries `agent_name` / `agent_phone`**, and the two existing
files that did were stripped. `leads.csv` lists two agents under *Coldwell Banker
Realty - Boston* and two different agents under *Gibson Sotheby's International
Realty*. The Gibson `brand.json` held one of those agents' phone numbers, and the
other Gibson listing would have inherited it onto their video. Now a `CLAUDE.md`
non-negotiable.

(No agent name, phone or email appears anywhere in this repo — see §1 and
`check_pii.py`.)

**The `watermark` path is pinned at creation.** The built-in default `viabolat.png`
resolves against the listing folder then beside `make_tour.py` — neither is where this
repo keeps it. When it fails, the build prints one line and drops the mark, shipping
an **unwatermarked `sample_` cut**, which is a free deliverable. `status.py` surfaced
this on `2_commonwealth_ave`; that config was backfilled.

**The display address is composed from the dump** — `2 Commonwealth Ave, Boston, MA
02116` from `streetAddress` + city/state/zip. The bare `streetAddress` names the
folder (it has to match the CSV column); on a card it reads like an unfinished draft.
The two already-delivered listings were **not** rewritten — `config.json` is the record
of what produced a shipped video.

**Resolution verdict at scrape time.** `report_resolution()` gives `make_tour.py`'s
gate verdict while the files are already on disk. The variant in a photo URL is a
ceiling, not a promise: `uncropped_scaled_within_1536_1152` returns the original
untouched when the original is smaller, and `335_w_2nd_st_unit_8` came back at **346px**
from a URL advertising 1536. Finding that out 20 minutes into a build is the expensive
way.

> Investigated and rejected: the `d_d` CDN variant serves 800x532 for that same photo.
> PSNR against the honest 346px bicubic-upscaled to 800 is **42.11 dB** — identical.
> It is a server-side upscale with no added detail. Taking it would inflate dimensions
> past the gate while adding nothing, defeating the resolution verdict and violating
> `IDEA.md` §3. The scraper keeps the honest variant and reports the true number.

**`status.py` is new** — read-only, writes/encodes/downloads nothing. One line per
listing: photo count, smallest photo, and the single next action. *Why:* the pipeline
now spans a scrape, a brand file, a listing config, a photo set with its own verdict,
and six cuts. Any one can be the blocker, and finding out meant opening three files per
listing. Fine at one brokerage; the lead list covers five.

**Bug fixes this session:**

- `make_tour.py` `contact_sheet()` crashed with *"Error while filtering: Invalid
  argument"* on any mixed-aspect folder. `force_original_aspect_ratio=increase`
  rewrites SAR to preserve display aspect, so a 1024x683 beside a 1024x768 reached
  `concat` with `1:1` on some cells and `2048:2049` on others. The clip path at
  line 368 already pinned `setsar=1`; the contact sheet did not. Fixed at the site
  with a `# reason:` comment.
- `status.py` reported `brewester/9_w_cedar` as "no photos — scrape it" when it holds
  17. It only counted `.jpg`; Zillow serves `.webp`. Now mirrors `make_tour.py`'s
  `PHOTO_EXTS` with an ffprobe fallback for non-JPEG.
- `photos.py` had a byte-identical second copy of `lead.field()`. Two
  copies of a regex that has already been tightened twice is a drift hazard; it now
  imports the one copy.

**Docs updated in the same pass** (`CLAUDE.md` non-negotiable): `CLAUDE.md` layout +
two new non-negotiables + Running it, `STEPS.md` §0a, `scraper/README.md`, and the
module docstrings in `photos.py` and `status.py`.

### Earlier — see `IDEA.md` §8.2

The intro/outro card and the two-stitch build shipped 2026-08-20. That entry is the
record of what was decided and why; it is not repeated here.

---

## 3. CURRENT STATE

**`python3 status.py` is the answer. This section no longer restates it.**

It re-reads `leads.csv`, measures every photo, names the run each listing is on and
prints the `mv` for any folder that has drifted from its lead row. `tour.py` prints
it as the first thing on the home screen.

A hand-copied table of the same facts used to sit here. It was wrong within two days
of being written -- one listing folder had been deleted and the table still listed
it -- and it was wrong in the way this project has a rule about: a fact stored beside
the artifact, drifting out of sync with it, with nothing to detect the drift. The
same reasoning that keeps photo order in the filename prefix and the build stage in
`out/` applies to a state table in a build log. It is gone; `status.py` derives it.

What stays here is what `status.py` cannot derive -- the decisions:

- **`brewester/9_w_cedar` and `corcoran/46_beacon_5`** are hand-named, predate the
  scraper, and have no lead row. They are **left alone deliberately**: the scrape is
  the only thing that names a listing folder, and it cannot name one it has no row
  for. `status.py` reports them as *unverifiable*, which is the correct third
  answer, not a failure. See
  [`the-scrape-names-the-folders`](_rules/the-scrape-names-the-folders.md) and
  [`a-folder-with-no-lead-row-still-starts`](_rules/a-folder-with-no-lead-row-still-starts.md).
- **`boston_advanced_realty/335_w_2nd_st_unit_8` was deleted from disk** some time
  before 2026-08-26 -- the "photos too small, do not build" listing. Its lead row is
  still in `leads.csv` and its brand folder still exists, so `status.py` reports
  `boston_advanced_realty/- ... no listings yet`. Re-running `run.py` on its dump
  would scaffold it again, and the photos would still be too small. The deletion was
  never recorded at the time; it is recorded here now.
- **`scraper/dumps/` holds four `*.txt` files and all four are 0 bytes.** Both
  scraper scripts refuse a dump with no `zpid` and no address, so the home screen
  correctly reports **0** pending imports rather than offering an import that can
  only fail. Nothing on this machine exercises the dump parsers -- which is why the
  `lead.field()` comma bug in section 6 stays unfixed, and why it must stay unfixed
  until a real dump exists to regression-test the naming authority against.
- **Stale intermediates in the two pre-scraper listings** are an open item, not a
  state reading. See section 6.
- **`IDEA.md` section 6 "CURRENT STATE"** is a historical snapshot of one folder from
  2026-08-19, kept for the sourcing argument it supports. It is not a live reading
  either; `status.py` supersedes it.

---

## 4. PROPOSED — approved, not built

### 4.1 Batch scraping — **BUILT 2026-08-21**, see §2

### 4.2 Flag-only photo order review

Detect likely floor plans and near-duplicate frames, print them as candidates, and
**never reorder or delete**. The operator confirms.

*Why flag-only:* the recut on the Gibson listing needed judgment about a floor plan and
duplicate molding shots. Auto-dropping a real room photo is the same silent-failure
class as the shuffled photo order — a bad video with no error. Photo order lives in the
filename prefix and nowhere else (`CLAUDE.md` non-negotiable), so any action this takes
is a rename on disk, never a sidecar.

**Floor-plan half: BUILT 2026-08-30**, see §2 — `floorplan.py`, wired into
`tour.py --auto`. Near-duplicate-frame detection stays open.

**Approved by the operator.**

---

## 5. PROPOSED — designed, deliberately deferred

> **One deferred proposal is not in this section.** `IDEA.md` §8.1 — programmatic
> drop shadow on the logo — is parked in `IDEA.md` **by agreement**, as the branding/
> output backlog's spot. It was left there rather than moved here so that agreement
> is not overridden silently; this pointer is what keeps the backlog readable from
> one place. Anything else deferred belongs below.

### 5.0 A positional directory argument for `make_tour.py` — **deferred 2026-08-24**

Every argument `make_tour.py` takes today is a flag, checked by membership
(`"--draft" in sys.argv`). There is no way to hand it a path, so running it directly
means `cd`-ing into the listing and counting `../`s back to the script. The proposal
is to read the first non-flag word as the folder to build:

```bash
python3 make_tour.py agents/coldwell_banker_realty_boston/8_dartmouth_st_5 --draft
```

It `os.chdir()`s and then behaves identically — `photos/`, `config.json`, `out/`,
`.build.lock` all resolve against it, shared assets still fall back beside the
script. It does **not** teach the script the `agents/<brand>/<listing>` layout: it
accepts any directory, so the cwd contract in `CLAUDE.md` stays intact.

**The one constraint that decides the implementation.** `config.json` is read at
*import* time — `_cfg`, and every `[cfg]` constant bound from it directly below. The
`chdir` must therefore sit immediately after the imports, above that load. Any lower
and it binds the root's config and then encodes a different folder: a silent
wrong-config build, the exact failure shape this project keeps writing rules
against. Existing `in sys.argv` flag checks cannot collide with a path that does not
start with `-`, so no flag parsing changes.

Roughly six lines plus doc propagation and a test that a bare in-folder run still
resolves the cwd config. **Operator deferred it as not urgent** — `tour.py` covers
the daily path and the awkwardness only shows on direct CLI use.

### 5.1 Cold-outreach email generation

The operator is wary of automated sending and **explicitly does not want mail going out
automatically**. Design agreed on that basis. **The per-upload half is built as of
2026-08-26**; the multi-lead sweep is not.

**Built — `publish.py`, one draft per confirmed upload:**

- `outreach/template.txt` holds the wording with `{agent_first}`, `{address}` and
  `{url}`. It is the **only committed file under `outreach/`** — it carries no lead
  data, only the sender's own name — via `outreach/*` plus `!outreach/template.txt`
  in `.gitignore`, because git does not descend into an excluded directory and a
  negation under a bare `outreach/` matches nothing.
- Every confirmed publish renders it to `outreach/drafts/<brand>__<listing>.txt`
  from the listing's `config.json` and the `sample_branded` link. `--dry-run`
  prints it rather than writing it. A blank field leaves its `{placeholder}`
  visible and the console names it.
- `outreach/links.csv` is `uploaded_at,brand,listing,cut,url` — **url last**, `\n`
  endings. It used to be `brand,listing,cut,url,uploaded_at`, and anything that
  grabbed the link took the timestamp with it and 404'd. `record_links()` migrates
  an older file in place.
- Guarded by `tests/test_outreach_draft.py`: url stays the last column, the draft
  never quotes a `tour_` cut, and `smtplib` / `sendmail` / `SMTP(` / `starttls`
  may not appear in `publish.py`.

**Still unbuilt — `emails.py`, the multi-lead sweep:** read `leads.csv`, find each
listing's finished cuts, and draft for every lead at once, including the ones with
no link yet (`NEEDS_LINK_<agent>` — the blocker rides in a drafting artefact's
filename, never a deliverable's). Everything above is per-listing and only fires
where a publish already happened.

**No SMTP credentials in the repo**, in either half. Sending, if ever, is a separate
deliberate decision — never a flag someone trips.

**One rule it must hard-code:** cold outreach sends the **`sample_`** cut. That is what
the watermarked family is for. Grabbing the `tour_` file gives away the paid
deliverable, and it is a one-word difference in a filename.

**On the YouTube upload wait.** The YouTube Data API returns the video ID the moment the
upload completes — `youtube.com/watch?v=<id>` is deterministic, so the draft can be
composed immediately. Processing only has to finish before a *viewer* can watch.

**Verify before writing any code:**
- The `videos.insert` quota cost against the default daily quota — it is expensive, and
  the practical ceiling may be only a handful of uploads per day.
- Whether an **unaudited** API project can publish as *unlisted* at all. Uploads from
  unaudited clients are believed to be forced to private until the project passes
  review, which would sink the plan outright.

### 5.2 Link vs. attached video — settled, recorded here so it is not re-litigated

Measured on the actual delivered cuts: **19.2 MB** (smallest, vertical) to **71.7 MB**
(branded). Gmail's ceiling is 25 MB for the whole message, and base64 encoding inflates
attachments by roughly a third, so the real ceiling is about **18 MB of file**.
Outlook.com is 20 MB; brokerage Exchange gateways are commonly 10 MB.

**Nothing this pipeline produces fits.** Attaching is not a choice available, and for
cold contact it would be the wrong one anyway: a multi-megabyte attachment from an
unknown sender is a strong spam signal and is often stripped before a human sees it; it
yields no open/click signal, which is the entire basis for a follow-up call; and it
cannot be corrected after sending.

*On conversion numbers:* there is no trustworthy head-to-head figure. The "video in
email" lift numbers in circulation are published by companies selling video-email
hosting and measure a **thumbnail linking to a hosted video**, not an attached file.

**The play:** a still frame or short animated GIF in the email body — ~1 MB, renders in
the inbox, proves at a glance the video is genuinely *their* listing — linking out.
ffmpeg can cut it from the existing files; a natural addition to `make_tour.py`.

YouTube unlisted is the right place to start. Its weakness for cold outreach is that
the link reads `youtube.com` and the page carries YouTube's chrome, suggested videos and
a subscribe button — the last impression is rented. A page on an owned domain is better
once volume justifies it, and is not a reason to delay.

---

## 6. OPEN DECISIONS

- **`brewester/9_w_cedar` and `corcoran/46_beacon_5`** have no `config.json` and no lead
  row. Either back-fill lead rows so they join the naming scheme, or accept them as
  pre-scraper listings and leave them out of it.
- **Merge `scraper` to `main`.** The branch is committed and pushed to
  `origin/scraper` as of 2026-08-24; it is not merged. Note `CLAUDE.md` §9: **no
  `Co-Authored-By` trailer** on any commit message.
- **`agents.txt` and `property_email.txt`** are untracked scratch at the repo root and
  have no owner. Both are now gitignored — they hold client first names, a live Stripe
  payment link, and delivery URLs for work already sold. `property_email.txt` still
  contains literal `[Your Name]` / `[Phone]` placeholders.
- **`scraper/photos/`** is the pre-`agents/` scrape output. Gitignored, but still on
  disk. Delete it or keep it for reference — not decided.
- **Stale build intermediates in the two pre-scraper listings.** `brewester/9_w_cedar`
  and `corcoran/46_beacon_5` each still hold a `work_silent.mp4` and a `clips/` from a
  build that never reached `finish()` — a successful build deletes its own
  intermediates, so their presence means those two failed or were interrupted.
  Re-measured 2026-08-24: **55M and 27M of intermediates**, 82M total. (The 236M/123M
  figures previously recorded here were the whole listing folders, `photos/` included,
  not the intermediates — corrected.) Gitignored and harmless to the repo, but a
  `work_silent.mp4` is exactly what `--finish-only` would silently reuse. Delete both,
  or keep them as the record of a pre-`out/` build — not decided. Note the new
  delivery-clears-draft sweep does **not** reach these: it only ever runs at the end
  of a successful build, and neither of these listings has had one.
- **`lead.field()` truncates any value containing a comma.** Confirmed by
  running it: the regex value class is `[^\\",]*`, so
  `\"streetAddress\":\"123 Main St, Apt A\"` parses as `123 Main St`, and
  `\"brokerName\":\"Compass, Inc.\"` as `Compass`. Both feed `leads.csv`, which is
  the **naming authority** — a truncated address silently names the folder wrong
  and the lead row wrong, in agreement with each other, which is the one shape
  `status.py` cannot detect. Apostrophes are *not* affected; that was a false alarm
  in the first pass of the audit and was corrected by re-testing.
  **Deliberately not fixed yet.** The one-character change is `[^\\",]*` ->
  `[^\\"]*` (stop at the closing escaped quote instead of the first comma), but
  `scraper/dumps/` is empty on this machine — every dump is 0 bytes — so there is no
  real input to regression-test the naming authority's parser against, and the
  current 11 lead rows contain no commas, so nothing on disk exercises it either.
  Changing a parser this load-bearing on synthetic vectors alone is how a
  plausible-looking wrong address gets shipped. Apply and verify the moment a real
  dump is available.
- **Should a preview link be short?** As of 2026-08-26 a published cut is reachable
  at `https://real-estate.viabolat.com/preview/<brand>/<listing>/<agent>_sample_branded`
  — the bucket path, straight through the `vercel.json` rewrite. It is honest and collision-free, and it is long
  and ugly in a cold email. The case for a short alias: the link is the thing a
  prospect clicks, and a 90-character URL reads as machine-generated. The case
  against, and why nothing was built: an alias is a second name for an object that
  already has one, and this project has a standing rule that two naming authorities
  drift. Any short form has to be *derived* from the bucket path and stored
  somewhere, and that store is the drift. Revisit only if a real recipient reacts to
  the link.

- **Something outside the shell is pushing this repo, and it may not run hooks.**
  The reflog carries a push none of the recorded sessions ran (`4371860 ... update
  by push`), and there were no git hooks at the time, so it was not one. If it is a
  libgit2-based client -- which is most IDE git integrations -- it does **not** run
  git hooks at all, and `hooks/pre-push` will never fire for it. Not fixable from
  inside git, so it was mitigated instead: `tour.py`'s home screen runs the PII scan
  itself on every render and reports the hook's wiring separately. Open: identify
  what is pushing and either wire it or stop using it for this repo. Until then,
  `python3 check_pii.py` by hand before any push from a client that is not the
  shell.

- **One real end-to-end smoke build in `tests/`, behind a flag.** The suite proves the
  wiring and the filtergraph without invoking ffmpeg, which is what keeps it at 0.3s
  and dependency-free. Nothing currently proves the resulting command actually
  *encodes*. A smoke build would need fixture photos, which this repo must never carry,
  and would cost minutes rather than milliseconds. Open: add it behind an opt-in flag
  with generated (not listing) imagery, or accept that the gap is covered by the
  operator running `--draft` before every delivery.

---

## 7. STANDING OPERATOR PREFERENCES

- **Do not run a video build without asking.** Narrowed once, deliberately:
  `tour.py --auto` (§2, 2026-08-30) builds unattended through the 3 `sample_`
  cuts, since checking the mp4 afterward is the ask. It still never builds a
  draft and never publishes, and the interactive flow is unaffected whenever
  `--auto` is not the argument typed.
- **Explain why**, not just what, when automating something.
- Logos and music are the operator's to supply; automate the rest.
- **Walk through the CLI.** Give the commands to run rather than executing the whole
  job — `tour.py` / `make_tour.py` are the interface and demonstrating them is the
  point.
