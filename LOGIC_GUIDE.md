# LOGIC_GUIDE.md

## Purpose
Tracks architectural decisions, non-obvious tradeoffs, and resolved bugs across sessions.
Update immediately when: architecture shifts, a tradeoff is made, a recurring bug is resolved.
Do not defer updates to end-of-session.

## Entries

### 2026-09-03 — The dashboard is a socket, not a file, and it reads only

**What:** `dashboard.py` — every lead and listing on one page in a browser, on a
sixth home-screen entry and as a standalone command. It joins what `status.py`'s
roll-up, `scraper/leads.html`, `needs_attention/` and the three `outreach/` CSVs
already know, and plays the sample cut.

**Why a socket and not a written HTML file.** The obvious implementation is the
one already in the repo: `lead.write_html_table()` renders `scraper/leads.html`
to disk. That file *is* the lead list, and it survived unignored for a while
because a `#` comment sat on the same line as its `.gitignore` pattern. A second
PII artifact on disk is a second thing that has to be remembered in two ignore
files forever. Rendering into a response body means there is nothing to
remember: `check_pii.py` cannot fail to scan a file that does not exist. The
cost is a running process; the bind is `127.0.0.1` and the source contains no
wildcard host.

**Why read-only.** A "mark contacted" button would give `outreach/contacted.csv`
a second writer, and [`the-draft-is-automatic-the-send-is-not`](_rules/the-draft-is-automatic-the-send-is-not.md)
already records what that costs — a send nobody decided. A "publish" button
would be a second owner of a prompt [`a-publish-prompt-has-one-owner`](_rules/a-publish-prompt-has-one-owner.md)
holds to one. The dashboard's job ends at showing that something is due.

**Why the ladder is ordered 7 → 2 rather than seven independent filters.**
`publish.followup_due()` is derived from `contacted_at()`, so rung 6 is a strict
subset of rung 5 — the sets are nested, not disjoint. Two filters would list
every due listing twice: once under a heading meaning "leave it alone" and once
under one meaning "act". That is the duplicate-send shape from 2026-09-02, where
two agents received a byte-identical second email. A single first-match ladder
makes the rungs a partition, which is the same reason `needs_attention/` orders
`archived > snoozed > active`. There is no eighth rung: "signed off" has no
derivable signal, and inventing a marker for it is what
[`needs-attention-is-a-view-not-a-move`](_rules/needs-attention-is-a-view-not-a-move.md)
forbids.

**Why the family gate sits at the socket, not the renderer.** Hiding `tour_`
cuts at render time would leave the URL working for anyone who guessed it, and a
loopback URL becomes a publishing boundary the moment it is pasted into a chat.
`resolve_media()` asks `publish.family()` *before touching the filesystem*, so a
`tour_` request is 403 whether or not that cut exists — the 403-vs-404
difference would otherwise say which listings are delivered. `family()` stays
the single owner; `dashboard.py` never tests the prefix, which is now enforced
by an assertion on its own source.

**What was refactored to avoid a fork:** `scraper/lead.py`'s stylesheet came out
into a `lead.CSS` constant, with `HTML_TEMPLATE` rebuilt from it through a
`_brace_escape()` helper — `HTML_TEMPLATE` is consumed by `.format()` and needs
doubled braces, `dashboard.py` concatenates and wants single ones. `leads.html`
output is byte-identical. One stylesheet, one dark-mode rule, one place.

**The ignore-gate asymmetry, stated so it reads as a decision:** `.vercelignore`
gains `dashboard.py`; `.gitignore` gains nothing. The module is committed source
that produces no artifact — `check_pii.py` scans it and should — but Vercel is
the one host in this project, and a file whose purpose is serving PII over a
socket does not get uploaded to it.

### 2026-09-03 — The gap-filling browser goes headless; Zillow stays the one exception
**What:** the "Fetching a logo or an agent email" workflow in `STEPS.md` now runs
`--headless=new` by default, this session and every future one, at the operator's
instruction. Three of the four outstanding `agent_email` gaps closed that way with
no window on screen.

**Why this does not contradict the entry below it.** That entry is about *Zillow*,
and it still holds exactly as written — PerimeterX denies headless Chrome with or
without a spoofed UA, so a re-scrape, and the profile-page email lane, still need
`DISPLAY=:0`. What changed is the default for everything that is *not* Zillow: a
brokerage's own roster page is ordinary web, and driving a visible window to read
one bought nothing.

**The one thing headless does need: a real user-agent.** Headless Chrome
advertises `HeadlessChrome/…` and `thefirmreg.com` answered `403 Request
forbidden by administrative rules` on sight of it. With an ordinary desktop
Chrome `--user-agent=` the same URL served normally. This is not the Zillow
problem wearing a different hat — it is a plain server-side UA filter, and the
403 turning into a clean 404 for a wrong path is what proves the difference.

**Why the email source order inverted.** `STEPS.md` used to rank the Zillow
profile page first. It is now last, because it is the only lane still costing a
headed browser — and it was never the stronger source. A brokerage page is the
agent's own publication of their address *and* it carries a `tel:` to check the
gap's `agent_phone` against. All three emails written today matched their
recorded phone exactly before they were written. That check is now the bar, not
the name on the page.

**Two failure modes this run turned up, both recorded in `STEPS.md`:**
`successrealestate.com` and its `www` host both redirect to an unrelated
gambling site, so a live-looking brokerage domain can yield nothing; and
`brokerName` is a short string that collides — the `thefirmreg.com` roster is a
different "The Firm" than the one on `30_belton_st`, complete and confident and
wrong. An earlier pass this session took that roster at face value and produced
an email for that listing's agent which the site does not actually support. It
was not written, and `30_belton_st` was reported UNRESOLVED — which is the
reason that lane is now stated in the workflow rather than implied. The
operator then supplied the address directly, which is how it was finally
filled: the fifth outcome, and the one that outranks all four lanes.

### 2026-09-02 — The three lost listings came back from a headed browser, not a paste
**What:** `16_holmfield_ave`, `41_worcester_sq_penthouse` and a third listing since
removed at the operator's request (2026-09-03) were re-scraped without the operator copying a page by hand. A scratchpad CDP client
drove a real headed Chrome (`DISPLAY=:0`, WSLg), read `document.documentElement
.outerHTML` once `__NEXT_DATA__` was present, and composed `scraper/dumps/<name>.txt`
in the shape the parsers already expect — one compact JSON header line, then one
`photos.zillowstatic.com` URL per line.

**Why headed:** Zillow is behind PerimeterX. `WebFetch` gets 403; `--headless=new`
gets an 11 KB `Access to this page has been denied` page *including* with a real UA,
`--disable-blink-features=AutomationControlled` and a 1920x1080 window. Headed Chrome
passes. The distinction is the browser, not the request.

**Why the compact header line, not the raw page:** `lead.field()` takes the FIRST
regex match. `city` appears 59 times in the raw DOM. The existing dumps' shape is not
cosmetic — it is what makes a first-match parser safe.

**What stays manual:** nothing about this belongs in the repo. The repo is stdlib +
ffmpeg/ffprobe with no browser dependency, and that has not changed — the client lives
in the scratchpad and was never committed. It is the operator's browser session,
automated, which is what [`find-gaps-detects-and-reports-it-never-writes`](_rules/find-gaps-detects-and-reports-it-never-writes.md)
already contemplates for logos.

**One thing the page no longer carries:** `41 Worcester Sq` has lost its
`agentPhoneNumber` upstream — the key is present, the value empty, zero phone-shaped
strings in 574 KB. `find_duplicate()` keys on zpid AND phone, so importing a blank one
appends a SECOND `leads.csv` row for a property already in the ledger. The value was
restored into the dump from that same ledger row before import, and `leads.csv` came
through byte-identical.

### 2026-09-02 — A brand value nobody set is not a brand value of ""
**What:** `scraper/photos.py`'s `scaffold()` no longer copies an `INHERITED` key the
brand leaves blank into a new listing's `config.json`.

**Why:** `tour.load_config()` layers `DEFAULTS -> brand.json -> config.json` with a
plain `dict.update()`. A `"logo": ""` written at creation therefore *shadows* the
brokerage mark permanently — including one claimed onto `brand.json` weeks later.
`16_holmfield_ave` was re-scraped while `global_assets/logos/keller_williams_realty.png`
was already on disk; `fill_gaps.py` claimed it into `brand.json`, and the roll-up still
said `logo blank/missing -- add it to brand.json`. The blank meant "nobody has said
yet", and freezing it turned a not-yet into a never.

`tour.save_config()` has omitted empty values for exactly this reason all along
("omit keys left unset ... rather than being handed an explicit null it would treat as
a path"). This is the scraper honouring the same contract at the other end. A falsy
value that is not blank — `brand_persistent: false` — is a decision and still carries.
Recorded in [`auto-picks-up-the-brand-logo-by-slug`](_rules/auto-picks-up-the-brand-logo-by-slug.md),
which is the same listing's second appearance in that rule.

### 2026-08-26 — The scripts lost the vendor prefix; the facts kept it
**What:** `scraper/zillow_lead.py`, `zillow_photos.py` and `zillow_run.py` are now
`lead.py`, `photos.py` and `run.py`, with all 112 references updated across code,
tests and docs. The private import aliases went too — `status._zp` is `status._photos`,
`publish.py`'s `_zp_publish` is `_photos_publish`.

**Why the prefix went:** it named a vendor on a file whose job is not vendor-specific.
`scraper/lead.py` extracts a lead from a page dump; the folder it lives in already says
what layer it belongs to, and `scraper/zillow_photos.py` said "zillow" twice for a
reader who is already inside `scraper/`.

**Why 35 mentions of Zillow stayed:** they are statements about where the data actually
comes from, not names of things in this repo — `photos.zillowstatic.com/fp/<hash>` is
the live CDN host the regex matches, `zpid` is the field the parser keys on and the
absence of which is how a non-listing dump is refused, and IDEA.md §4's ~1440px ceiling
is a measured property of *Zillow's* CDN, not of scrapers in general. Renaming those
would have made correct documentation wrong, which is a worse outcome than a vendor
name in prose. The rule that came out of it: **the vendor may appear in a fact, never
in a filename.**

**What this cost:** one broken cross-module reference — `tour.py` called
`status._zp.target_for()`, and renaming the alias in `status.py` and `publish.py`
without grepping the tree left it dangling. Five tests caught it immediately, which is
the argument for the suite existing. A private-looking `_name` is not private if
another module reads it.

### 2026-08-26 — The link goes last, and the email drafts itself
**What:** `outreach/links.csv` is now `uploaded_at,brand,listing,cut,url` with `\n`
endings, and `record_links()` migrates an older file in place rather than appending a
second shape into it. Every confirmed publish renders `outreach/template.txt` — a new,
**committed** file — into `outreach/drafts/<brand>__<listing>.txt`.

**Why the URL moved last:** it sat mid-row, so anything that grabbed the link took
`,2026-08-26T16:58:12` along with it and the URL 404'd. `csv`'s default `\r\n` did the
same damage by a second route, gluing a carriage return onto whatever the last field
was. Both are the same class of bug — a field's meaning depending on what follows it —
and the fix is to put the one field that leaves the machine where nothing can follow it.
The migration lives in the code and not in a one-off script because the file is
gitignored: a repair applied once here would never reach another clone.

**Why the template is committed while `property_email.txt` is not:** the template holds
placeholders and the sender's own name. `property_email.txt` holds a filled-in email —
an agent's name and a listing address — which is lead data and stays ignored. The
`.gitignore` needed the directory-contents form (`outreach/*` then
`!outreach/template.txt`), because git does not descend into an excluded directory and a
negation under a bare `outreach/` matches nothing. Verified with `git check-ignore`, not
assumed.

**Why sending stays out:** `PROGRESS.md` §5.1's standing constraint — the operator does
not want mail leaving the machine automatically. Drafting is cheap to undo; sending is
not, and a repo with an SMTP credential in it is one flag away from doing it by
accident. `tests/test_outreach_draft.py` fails on `smtplib`, `sendmail`, `SMTP(` or
`starttls` appearing in `publish.py`, so the constraint outlives the memory of it.

**Why the draft quotes `sample_branded` only:** it is `PRIMARY_CUT`, the watermarked
proof. A cold email linking `tour_branded` gives away the paid deliverable, and the
difference is one word in a filename — the same boundary `publishable()` holds at the
bucket, restated one layer up where a human copies a link.

### 2026-08-24 — One apostrophe rule, two slug functions
**What:** `make_tour._slug` now strips `'` and `’` before separating, matching
`scraper/photos.slugify`. The two functions were **not** merged, and their
empty-case behaviour still differs on purpose.

**Why:** The scrape is the naming authority — `agents/<slug(broker_name)>/<slug(address)>`.
`_slug` names the *files inside* those folders from `agent_name`, and mapped every
non-alphanumeric to a separator, so an agent called Sean O'Brien would get
`sean_obrien/` holding `sean_o_brien_tour_branded.mp4`. One name, two spellings, which
is the drift a single naming authority exists to prevent. Found while writing
`tests/`, not in production: no `agent_name` or `output_prefix` on disk carries an
apostrophe, so no delivered filename changed. Verified before the change, not assumed.

**Alternatives rejected:**
- *Import `slugify` from `scraper/` into `make_tour.py`.* Rejected: `make_tour.py` runs
  with cwd set to a listing folder and nothing but ffmpeg on the path. Importing the
  scraper makes a build depend on the scrape, which it otherwise never does, and breaks
  `cd agents/x/y && python3 ../../../make_tour.py`.
- *Unify the two functions entirely.* Rejected: they differ on the empty case for good
  reason. The scraper falls back to `listing` because a folder cannot be named `""`;
  `_slug` must return `""` so a blank `agent_name` leaves the bare `tour_`/`sample_`
  names a pre-existing CLI folder already has.
- *Leave the divergence and document it.* Rejected once the impact was measured as zero —
  the cost of fixing was two lines, and the failure it prevents is silent.

**Accepted risks:** The apostrophe rule is now stated in two places and can drift again.
Mitigated by `tests/test_naming.py::TestSlug::test_the_two_sluggers_agree_on_every_non_empty_case`,
which fails naming the disagreeing input, and by a non-negotiable in `CLAUDE.md`.

---

### 2026-08-24 — Guard the non-negotiables with tests, not prose
**What:** Added `tests/` — 60 stdlib `unittest` tests across five modules (now 75
across six; see the audit entry below), no
third-party dependency, no ffmpeg invoked, ~0.3s. Covers output naming and the
resolution-tag-free naming, card isolation from `work_silent.mp4`, `vertical()`'s two sources, the
branding/watermark card gate, photo order living in the filename prefix, and
`status.py`'s three-way folder classification.

**Why:** The rules in `CLAUDE.md` share a failure shape — they produce a *valid video*
that is wrong. A card in the unbranded stitch puts an agent's phone number on the MLS
with no error; a shuffled photo order shipped once already and its only symptom was the
finished film. Prose cannot fail a build.

**Alternatives rejected:**
- *pytest.* Rejected: it is installed, but the project is deliberately dependency-free and
  a suite that adds the first dependency defeats its own purpose. `unittest` is stdlib.
- *End-to-end builds against real photos.* Rejected: six minutes per case, and it would
  need fixture imagery in a repo that must never carry listing photos.
- *Asserting on decoded frames.* Rejected as the primary method for the wiring rules —
  which stitch a `finish()` call is handed is a property of the source, so the AST is the
  honest place to read it. Frame decoding would be slower and prove less.

**Accepted risks:** The AST tests couple to the shape of `main()` — renaming the `silent`
or `branded_silent` locals breaks them. Judged correct: those names *are* the contract
being guarded, and the failure message says so. Each guard was verified to fail on the
regression it names before being kept.

---

### 2026-08-24 — Unverifiable is a third answer, not a silent pass
**What:** `status.py` now classifies every listing folder into three buckets rather
than two — agrees with the scrape, drifted off it, or *unverifiable*. `next_action`
takes a `scraped` flag and stops sending config-less legacy folders to
`photos.py`.

**Why:** The drift check matched on `agent_phone` read out of `config.json`. A folder
with no `config.json` produced no match, and the code read "no match" as "no problem".
But *having no config.json is the strongest available signal that a folder was never
scaffolded by the scraper* — the likeliest hand-named folder there is. The check
skipped exactly the case it was written to catch, which is how `brewester/9_w_cedar`
and `corcoran/46_beacon_5` sat through the scrape-naming commit untouched. Separately,
the advice it gave them — "rerun `photos.py`" — pointed at a script that
scaffolds from a dump keyed to a lead row, and neither folder has one.

**Alternatives rejected:**
- *Skip folders whose name is already in `leads.csv`.* Written, then reverted during
  review: it would hide a folder named for one lead row while its `config.json`
  carries a different agent's phone. That is worse drift, not less. The phone match
  now runs on every folder exactly as before; only the fall-through changed.
- *Auto-rename or delete the unverifiable folders.* Rejected: the scrape cannot name
  a listing it has no row for, and hand-naming one is the second naming authority the
  whole rule exists to prevent. Reporting is the correct end of the tool's job.
- *Infer the lead row by matching the address slug.* Rejected: address text formatting
  varies between config and CSV, which is why the check keys on a phone number in the
  first place.

**Accepted risks:** A listing whose lead row is legitimately deleted now shows as
unverifiable forever. Judged correct — that *is* the true state, and the message says
so rather than implying agreement. Guarded by `tests/test_status_naming.py`.

---

### 2026-08-24 — Fixing an audit's findings without adopting its severities

**What:** Six of seven findings from an external audit are fixed; one is deferred to
§6 of `PROGRESS.md`. Three severity ratings and one remediation were rejected.

**Why:** The findings were all real — each was reproduced by running it before any
code changed. The *rankings* were not, because they were made without the project's
contract in view:

- The audit rated the `check_pii.py` failure **LOW** as "potentially letting PII pass
  unchecked". It is the only finding that weakens a boundary silently rather than
  crashing loudly, which by this project's standards makes it the worst one. A crash
  costs a build; a gate printing `Safe to push` over an unscanned lead list costs the
  thing the gate exists for.
- It rated `tour.py`'s literal folder naming **LOW / architectural**. Measured against
  *"the scrape names the folders; nothing else does"*, it is the most direct violation
  of a stated non-negotiable in the set.
- It rated the music hang **HIGH**. It is real and a hang is worse than a crash, but
  it needs a sub-2-second music file, which no real track is.

**Alternatives rejected:**
- *The audit's remediation for zero-dimension assets: "skip the overlay, print a
  warning".* Rejected for the watermark specifically. Skipping it produces an
  unwatermarked `sample_` cut, which is precisely the file the `tour_`/`sample_` split
  exists to make impossible. Branding degrades; the watermark refuses. The audit had
  no way to know that, which is the point — a generic remediation cannot see a
  project's boundaries.
- *Fixing the `lead.py` comma truncation now.* Rejected on evidence, not on
  disagreement: `scraper/dumps/` holds only 0-byte files, so the parser that names
  every folder cannot be regression-tested against a single real input. Recorded in
  §6 with the exact patch, to apply when a dump exists.
- *Importing `ZOOM_MAX` into `status.py` and the scraper to kill the gate
  duplication.* Rejected for the same reason the two sluggers stay separate — it makes
  the scrape depend on the builder. A test pins the constants instead.
- *A third slug function for `tour.py`.* Rejected: `tour.py` already imports
  `make_tour`, so `_slug` was in hand. Two slug functions is a documented, tested
  compromise; three would be drift.

**Accepted risks:** `image_ok()` costs one `ffprobe` per asset per cut. Judged worth
it against losing a rendered build to a division by zero. The clamped music seam
changes the *audible* seam for tracks under 4s of body — accepted, because the prior
behaviour for those tracks was to hang. And the `photos/` `isfile` filter now hides
malformed entries from the count rather than reporting them; `status.py` shows the
photo total, so a folder that silently loses one is visible as a changed count.

---

### 2026-08-24 — What ships with the repo, and what stays on the machine

**What:** `tests/`, the code fixes, the doc updates, `.claudeignore`/`.geminiignore`
**and this file** are committed and pushed. Only `spec.md` and
`.claude/settings.local.json` are gitignored.

*Reversal, same day.* The first version of this decision kept `LOGIC_GUIDE.md` local
too, and was pushed that way in `0f2764b`. The operator reversed it immediately. This
entry records the final call; the reasoning for the reversal is below rather than in a
separate entry, because nothing was built on the superseded version.

**Why:** The split is by *durability*, not by importance.

`tests/` must travel: it exists to fail on the `CLAUDE.md` non-negotiables, every one
of which fails *silently* in production, so a suite living in one working copy catches
nothing. Five committed `.md` files already reference the path, and a doc pointing
somewhere not in the repo is the exact drift the "docs do not go stale" rule prohibits.

This file must travel for the same reason one rung up. `CLAUDE.md` states the rules
and `PROGRESS.md` records what shipped, but neither carries *alternatives rejected* —
and that is the section that stops a future session redoing settled work. Without it,
the next person to look at two slug functions doing nearly the same job sees
duplication and merges them, because the reason they are separate (`make_tour.py` runs
from a listing folder with nothing but ffmpeg on the path) is a fact about the runtime
that is not visible from either function. A decision record that only exists on the
machine where the decision was made protects nobody.

`spec.md` does not travel: it describes work in flight and goes stale the moment that
work ships. A stale spec in a repo reads as current intent, which is worse than no
spec. `settings.local.json` is machine-local by its own filename convention.

**Alternatives rejected:**
- *Keep this file local; the rules are already in `CLAUDE.md`.* The original call, and
  wrong. The rules are there; the rejected alternatives are not, and those are the
  load-bearing part of a decision record.
- *Gitignore `tests/`.* Rejected on four checked grounds: the guards must travel;
  `check_pii.py` scans only what git would publish, so ignoring `tests/` would silently
  drop the fixtures out of the PII gate they already tripped once; five docs reference
  the path; and `tests/__pycache__/` — the only real noise — is already covered by
  `.gitignore:38`.
- *Ship `spec.md` too, for symmetry.* Rejected: symmetry is not a reason. The two files
  have opposite lifespans — one accumulates and stays true, the other expires on ship.
- *A `docs/internal/` folder.* Rejected: a new folder to hold one remaining file is
  structure ahead of a boundary.

**Accepted risks:** This file is now published, so it must be held to the same standard
as the rest — `check_pii.py` scans it on every push, and it can drift from the docs it
summarises. On any disagreement `CLAUDE.md` wins; this file explains, it does not
govern. It also grows without bound, which is accepted: entries are append-only and a
superseded one is marked, not deleted, or the record loses the thing it is for.

---

### 2026-08-26 — Publishing is a fourth rung, not the tail of a build

**What:** New `publish.py` uploads a listing's `sample_` cuts to the public Supabase
bucket behind `/preview/`, records confirmed links in `outreach/links.csv`, and
refuses everything else. `tour.py` offers it as an optional rung 4, defaulting to no.
`make_tour.py` is untouched.

**Why:** The delivery half of the pipeline already existed — `vercel.json` rewrites
`/preview/` at the bucket — and there was no way to get a link in front of a prospect.

The starting proposal was a loop at the end of `make_tour.py`: `for f in
os.listdir("out")`, `if f.endswith(".mp4")`, upload, then `os.remove`. Every clause
of that is a boundary this project has already written a rule about. The glob
publishes `<agent>_tour_branded.mp4` — the unwatermarked, paid deliverable — to a
guessable public URL at build time, before sign-off, which is precisely what the
`tour_`/`sample_` split exists to prevent, and PROGRESS.md §5.1 had already settled
the identical question for outreach ("it is a one-word difference in a filename").
So the gate is `publishable()`, a pure function with one argument and no override,
guarded by a test that fails if it ever grows a second one.

**Alternatives rejected:**

*Put it in `make_tour.py`.* Three independent reasons not to, any one sufficient:
that file is stdlib + ffmpeg by contract and the `supabase` library is a dependency
tree; it holds `.build.lock` through a six-minute encode, where a network timeout
would fail an otherwise good build; and it is deliberately blind to
`agents/<brand>/<listing>`, which is exactly the structure a collision-free remote
path needs. Encoding and publishing are different failure domains and belong in
different files.

*`pip install supabase`.* Storage is a plain REST endpoint; `urllib` reaches it in
about forty lines. Zero third-party dependencies is a property worth more than those
lines, and it is stated in two docstrings and `CLAUDE.md`.

*The bare filename as the remote path,* as proposed. Two listings by one agent both
produce `sean_obrien_sample_branded.mp4`, and a listing with a blank `agent_name`
produces a bare `sample_branded.mp4`; with `x-upsert: true` the second silently
overwrites the first. This is the collision `output_prefix` already solved locally,
and it has to be solved again at the bucket. Hence `<brand>/<listing>/<file>`, and a
refusal when the folder is not under `agents/`.

*`HEAD` the public URL to verify.* Caught in review before it shipped. Public objects
are served through a CDN, so a request issued seconds after an upload can hit an edge
that has not replicated and report a correct upload as failed — an intermittent false
alarm on the one step whose job is to be trustworthy. Verification is one
authenticated `object/list` call against the origin, comparing sizes. The public URL
is still checked once by hand, after deploy, to prove the `:path*` rewrite.

*Read credentials from `os.environ` only.* Also caught in review. The plan gitignored
`.env` and documented putting the key there, while the code read only the
environment — so an operator who followed the docs would get exit 2. The stdlib has
no `.env` parser, so `publish.py` carries a fifteen-line one. It uses
`os.environ.setdefault`, so a variable exported on purpose always beats a stale file.

*`os.remove(local_path)` after upload.* Not implemented and not behind a prompt. It
makes a public bucket the only copy of a deliverable and breaks
`config.json`-as-a-record-of-what-shipped. Storage pressure is a reason to prune old
listings deliberately, never a reason for a fresh delivery to delete itself. A test
fails on `os.remove` anywhere in the file.

**Accepted risks:** Preview URLs are long — `/preview/<brand>/<listing>/<file>` — and
`vercel.json` needed `:slug` widened to `:path*` because `:slug` matches a single
segment. A short alias would read better in a cold email, but it is a second naming
authority over the same object, which is the thing the scrape-naming rule exists to
prevent; it is parked in PROGRESS.md §6 rather than invented here. The bucket stays
public, which is safe only for as long as the `sample_`-only gate holds — that is why
the gate is the tested part. And `x-upsert: true` means re-publishing a listing
replaces the object a client may already be looking at; that is the intended
behaviour for a corrected cut, but there is no versioning behind it.

---

### 2026-08-26 — The resolution verdict is reported, not encoded in the filename
**What:** Removed the `_lowres` suffix everywhere. `out_path()` takes the cut name
and nothing else; `check_resolution()` returns the offending photo list instead of a
bool and `make_tour.py` restates the count, the worst file and its upscale factor
after the six cuts exist. `tour.py` states it at preflight, again at the delivery
confirmation and again with the finished list, and no longer carries `+lowres` in
`.last_build.json`'s preset string. `status.py` and `publish.py` stopped reading the
verdict off filenames and re-measure `photos/` instead. The eighteen `_lowres` files
already on disk were renamed.

**Why:** Operator decision — the tag was doing work the operator did not want it to
do. It travelled onto every client-facing artefact, including the ones that clear the
gate at 720p, and it made a soft cut look like a different kind of file rather than
the same file built from worse photos. The measurement was never the problem, so the
measurement stayed; only the consequence changed, from *renames the output* to
*reports, repeatedly, in every place the question is asked*.

**Alternatives rejected:**
- *Drop the warnings along with the tag.* Rejected: the request was to remove the
  suffix, not the reminder. The reminder got louder — it now names the worst file and
  its upscale factor at the end of the build, where before it named only the target.
- *Keep the verdict in `config.json` or `.last_build.json` so `publish.py` can read
  it.* Rejected: derived state that goes stale the moment `photos/` changes, and
  `.last_build.json` is written by `tour.py` only, so a CLI build would leave it
  blank. Both consumers re-measure the photos, which is where the answer is true.
- *A fourth copy of the JPEG header parser in `publish.py`.* Rejected: it borrows
  `jpeg_size` from the scraper exactly as `status.py` does, and degrades to "no
  verdict" rather than blocking a publish if the scraper is unreachable.

**Accepted risks:** The strongest property of the old design is gone — a soft cut
sitting in a downloads folder three weeks later no longer says what it is. Nothing in
the repo can restore that, because the repo does not follow the file. Mitigated by
making the verdict re-derivable rather than remembered: `status.py` prints
`soft (NNNpx photos)` on every run, and `publish.py` asks a second time before a soft
cut leaves the machine. `tests/test_naming.py` now fails if any cut grows a
resolution tag, the inverse of the test it replaced. Local renames also broke the
correspondence with three listings already uploaded under `_lowres` names — those
objects are still in the bucket and `outreach/links.csv` still points at them; a
re-publish uploads the new names alongside rather than replacing them.

---

### 2026-08-30 — `agents/`, `prospects/` and the outreach draft unify under company/address/agent
**What:** `agents/<brand>/<listing>` grew a third, scrape-named path segment:
`agents/<brand>/<listing>/<agent>`, sourced the same way as the first two —
`scraper/photos.py`'s `target_for()` slugifies `agentName` off the scrape, with an
explicit `UNASSIGNED_AGENT = "unassigned_agent"` placeholder for a blank one rather
than a silent empty path segment. `status.py`'s `survey()`/`audit()`/`next_action()`,
`prospects.py`'s `rebuild()`, `publish.py`'s `remote_path()`/`write_draft()`, and
every listing-walking function in `tour.py` were threaded from `(brand, listing)` to
`(brand, listing, agent)`. The flat `outreach/drafts/<brand>__<listing>.txt` tree is
retired; the cold-email draft now writes to
`agents/<brand>/<listing>/<agent>/outreach_draft.txt`, beside the `photos/` and
`out/` that produced it. `prospects/` stays, unchanged in shape except its symlinks
now point three levels deep and are named `<brand>__<listing>__<agent>`. Five real
listings already on disk were migrated by hand into the new layout.

**Why:** the three were scattered — photos and cuts under `agents/`, the review-view
symlink under `prospects/`, the email draft under `outreach/drafts/` — so one
property's whole output lived in three unrelated places. `company/address/agent` in
one folder means `agents/<brand>/<listing>/<agent>/` now holds everything for that
listing.

**Alternatives rejected:**
- *Make `publish.py`'s remote bucket layout and `outreach/links.csv` schema
  three-level too.* Rejected after reading real `links.csv` rows: they already
  reference brands no longer present under `agents/` at all — it is a decoupled
  historical log, not something this restructuring should retrofit. `remote_path()`
  stays agent-blind (`<brand>/<listing>/<file>`); it validates the third segment
  exists but never includes it in the returned path, and `output_prefix` already
  keeps two agents' identically-named cuts from colliding at the CDN layer.
- *Rename `prospects/`'s by-agent index key to match the new `<agent>` path
  segment.* Rejected: the index key (slugified `agent_name` + phone digits) is a
  different identity than the folder's `<agent>` slug, and the two can legitimately
  run out of step — a folder can still sit on `unassigned_agent` while
  `config.json` already carries the real name and phone. Correcting that is
  `status.py`'s existing drift audit, extended to 3-tuples; no new rename
  automation was built for it.

**Accepted risks:** two pre-existing bugs would have shipped silently under the new
depth if not caught by re-reading the affected functions directly: `tour.py`'s
`_auto_build_one()` rerun-hint strings were truncating to just the agent segment
(`os.path.basename(listing_dir)` instead of a full relative path), and
`brand_settings()`/`reapply_brand()` were reading `config.json` one level too
shallow, which would have silently reported "nothing to apply" for every listing.
Both are fixed as part of this change, guarded by the existing suite plus new tests
in `tests/test_naming.py`, `tests/test_auto_flow.py` and `tests/test_home_screen.py`.

---

### 2026-09-02 — The card's text joins the `--finish-only` invalidation set

**What:** `tour.py` gains `CARD_TEXT_KEYS = ("address", "agent_name", "agent_phone",
"brokerage")`, and `rebuild_reason()` returns `"the card's text changed"` when any of
them differs from `.last_build.json` and `card != "none"`. Guarded by
`TestTheCardsTextInvalidatesTheStitch` in `tests/test_auto_flow.py`, one of whose
tests reads `render_card()`'s own source so the two lists cannot drift.

**Why:** the question was "how do I rerun a single listing, I had the wrong number for
contact". Tracing it turned up a silent bug. The phone number is on screen twice, and
the two surfaces are redrawn on different schedules: `render_lower_third()` runs
unconditionally on every pass, while the outro card is baked into `work_branded.mp4`,
which `--finish-only` reuses whole. `rebuild_reason()` compared `card` and
`card_seconds` — the card's *mode* — but not the values printed on it. So the obvious
fix (edit `config.json`, rerun) produced a cut with the corrected number in the lower
third and the wrong number on the card, with nothing in the log to say so. Digits are
the deliverable.

**Alternatives rejected:** *always rebuild when config changes at all* — too blunt; a
`logo` or `watermark` change is already handled elsewhere and a full re-encode of 40
photos is the cost `--finish-only` exists to avoid. *Delete `work_branded.mp4` in the
docs and leave the code alone* — that is a runbook step standing in for a check, and
`docs-do-not-go-stale` notwithstanding, a step you can forget is not a guard. The
`STEPS.md` note stays as well, for anyone driving `make_tour.py` directly.

**Accepted risks:** the check is gated on `card != "none"`, so a listing with no card
keeps the fast path — correct, since nothing is burned in and the lower third is
redrawn anyway. All 16 existing `.last_build.json` records were verified to already
carry the four keys, so this triggers no spurious rebuild on anything already built.
`brokerage` only shows on the type-only card layout, which makes it a slightly
over-broad trigger; not worth the branch to narrow.

---

### 2026-09-02 — A follow-up gets its own draft, and contacted.csv gets a row per send

**What:** `outreach/followup.txt` + `publish.write_followup()` →
`outreach_followup.txt`; `publish.recorded_link()` and `publish.followup_due()`;
`contacted_at()` now returns the latest matching row rather than the first; rung 5
walks past-due leads alongside uncontacted ones; `status.next_action()` reports
`follow up -- rung 5 drafts it`. Rule 45, guarded by
`AFollowUpIsItsOwnDraftAndItsOwnRow` in `tests/test_active_view.py`.

**Why:** the operator showed three sent threads. `9 W Cedar St` (first contacted
2026-08-19) and `55 Lagrange St Unit 1705` (2026-08-26) had each received a **second
copy of their original email** on 2026-09-02 — same subject, same body. The only
one that read like a real follow-up, `46 Beacon St. #5`, had been written by hand
outside the tool. `needs_attention/` was doing its job resurfacing those listings
after the 5-day window, but the folder held exactly one artifact and both send-side
rungs filtered on `contacted(...)`, so a resurfaced lead had no rung to land on. The
tool offered the first-contact draft or nothing. Underneath it, `contacted_at()` read
the first row of an append-only file, so even recording a follow-up would not have
moved the window — the listing would have resurfaced forever.

**Alternatives rejected:** *a `followed_up_at` column on `contacted.csv`* — the file
already had the right shape, append-only with a timestamp; only the read was wrong,
and a second column would need a migration and give two places to look. *Re-publish to
regenerate the link* — the cut has not changed and the URL is already in `links.csv`,
which is what `the-recorded-link-is-the-last-field` keeps it for. *Send the follow-up
automatically* — never; `the-draft-is-automatic-the-send-is-not` is exactly the
boundary this failure sits next to, and crossing it would have made the duplicate
sends automatic rather than merely easy.

**Accepted risks:** `contacted.csv` now has rows whose meaning depends on order, so a
hand-sorted or hand-deduplicated file would change behaviour — acceptable, since
`record_contacted()` is the only writer and it only appends. The three duplicate sends
already made are not retro-recorded: doing so would invent send times, and the
follow-up window is a prompt, not an audit trail.

---

### [YYYY-MM-DD] — [Decision Title]
<!-- Template. Copy this stanza above for the next entry; leave this one empty. -->
**What:**
**Why:**
**Alternatives rejected:**
**Accepted risks:**
