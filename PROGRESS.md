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
- **`scraper/leads.csv` is excluded by a global `*.csv` rule** in
  `~/.gitignore_global`, not by this repo's `.gitignore`. It is the **naming
  authority** — `agents/<slug(broker_name)>/<slug(address)>` is derived from it, and
  `status.py` validates every folder against it. Without it, `status.py` silently
  skips the folder-name check and there is nothing to re-derive names from.

**Decided 2026-08-21: `leads.csv` stays untracked.** It is the lead list — agent
names, phones, emails — and the repo is now hardened so no lead can reach the remote
at all (see §2). Copy it across by hand, or re-derive it by re-running the scrape.
It is now ignored by a **repo-level** rule rather than only by the global one, so the
protection travels with the clone.

Branch: **`scraper`**, cut from `3c5e1a8`. **Nothing on it is committed yet.**

---

## 2. BUILT

### 2026-08-21 — Batch scraping, and hardening the repo for a private remote

**Batch scraping.** `zillow_run.py` now takes a single dump *or* a folder, defaulting
to `scraper/dumps/`:

```bash
python3 scraper/zillow_run.py            # every *.txt in scraper/dumps/
python3 scraper/zillow_run.py one.txt    # unchanged single-dump path
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
  prose, one in the `zillow_lead.py` module docstring's example. Both replaced.

*Why bother at all on a private repo:* a private repo is an access-control boundary,
not a redaction one. It gets shared with a collaborator, cloned onto a second machine,
or made public years later, and nothing re-reviews the history at that moment.

### 2026-08-21 — Scrape-driven listing creation, and the scrape as naming authority

The pipeline used to start at a listing folder someone made by hand. It now starts at
a copied Zillow page dump.

```bash
python3 scraper/zillow_run.py scraper/paste.txt   # lead row + a scaffolded, buildable listing
python3 status.py                                 # every listing and its one next action
```

**Photos land in the build tree.** `scraper/zillow_photos.py` writes to
`agents/<slug(broker_name)>/<slug(address)>/photos/`, a sibling of `scraper/`, not a
subfolder. That is exactly the working directory `make_tour.py` expects, so a scrape
drops in ready to build with no moving or renaming.

**The scrape is the naming authority.** Both folder names are slugified from the same
dump fields `zillow_lead.py` writes to the `broker_name` and `address` columns, so a
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
> past the gate while adding nothing, defeating the `_lowres` tag and violating
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
- `zillow_photos.py` had a byte-identical second copy of `zillow_lead.field()`. Two
  copies of a regex that has already been tightened twice is a drift hazard; it now
  imports the one copy.

**Docs updated in the same pass** (`CLAUDE.md` non-negotiable): `CLAUDE.md` layout +
two new non-negotiables + Running it, `STEPS.md` §0a, `scraper/README.md`, and the
module docstrings in `zillow_photos.py` and `status.py`.

### Earlier — see `IDEA.md` §8.2

The intro/outro card and the two-stitch build shipped 2026-08-20. That entry is the
record of what was decided and why; it is not repeated here.

---

## 3. CURRENT STATE

`python3 status.py` is the live answer; this is the snapshot as of 2026-08-21.

| Listing | Photos | Smallest | Next action |
|---|---|---|---|
| `boston_advanced_realty/335_w_2nd_st_unit_8` | 12 | 270px | photos only 346px — get originals, **do not build** |
| `brewester/9_w_cedar` | 17 | 384px | no `config.json` (predates the scraper) |
| `coldwell_banker_realty_boston/2_commonwealth_ave` | 28 | 1024px | built, 6 cuts |
| `corcoran/46_beacon_5` | 8 | 1080px | no `config.json` (predates the scraper) |
| `gibson_sothebys_international_realty/260_262_commonwealth_ave_1b` | 31 | 1024px | built, 6 cuts — `_lowres`, sample only |

Four lead rows have **no folder yet**: `coldwell_banker_realty_waltham/284_sumner_st_3`,
`coldwell_banker_realty_boston/8_dartmouth_st_5`, `compass/12_adella_pl`,
`gibson_sothebys_international_realty/169_k_st_1`.

`IDEA.md` §6 "CURRENT STATE" is a **historical snapshot** of one folder from
2026-08-19, kept for the sourcing argument it supports. This table supersedes it.

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

**Approved by the operator.**

---

## 5. PROPOSED — designed, deliberately deferred

### 5.1 Cold-outreach email generation

The operator is wary of automated sending and **explicitly does not want mail going out
automatically**. Design agreed on that basis; not built.

**Two phases, no send path in the code at all:**

1. `emails.py --draft` reads `leads.csv`, finds each listing's finished cuts, and writes
   one file per lead into `outreach/drafts/`. A lead with no video link yet is written
   as `NEEDS_LINK_<agent>.eml` — the blocker rides in the filename, exactly like
   `_lowres`.
2. The link lands in `outreach/links.csv`; `--render` fills the drafts in.
3. Output is `.eml` files to drag into a mail client. **No SMTP credentials in the
   repo.** Sending, if ever, is a separate deliberate decision — never a flag someone
   trips.

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
- **Commit the `scraper` branch.** Nothing on it is committed. Note `CLAUDE.md` §9:
  **no `Co-Authored-By` trailer** on any commit message.
- **`agents.txt` and `property_email.txt`** are untracked scratch at the repo root and
  have no owner. Both are now gitignored — they hold client first names, a live Stripe
  payment link, and delivery URLs for work already sold. `property_email.txt` still
  contains literal `[Your Name]` / `[Phone]` placeholders.
- **`scraper/photos/`** is the pre-`agents/` scrape output. Gitignored, but still on
  disk. Delete it or keep it for reference — not decided.

---

## 7. STANDING OPERATOR PREFERENCES

- **Do not run a video build without asking.**
- **Explain why**, not just what, when automating something.
- Logos and music are the operator's to supply; automate the rest.
- **Walk through the CLI.** Give the commands to run rather than executing the whole
  job — `tour.py` / `make_tour.py` are the interface and demonstrating them is the
  point.
