# LOGIC_GUIDE.md

## Purpose
Tracks architectural decisions, non-obvious tradeoffs, and resolved bugs across sessions.
Update immediately when: architecture shifts, a tradeoff is made, a recurring bug is resolved.
Do not defer updates to end-of-session.

## Entries

### 2026-08-24 — One apostrophe rule, two slug functions
**What:** `make_tour._slug` now strips `'` and `’` before separating, matching
`scraper/zillow_photos.slugify`. The two functions were **not** merged, and their
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
**What:** Added `tests/` — 60 stdlib `unittest` tests across five modules, no
third-party dependency, no ffmpeg invoked, ~0.3s. Covers output naming and the
`_lowres` tag, card isolation from `work_silent.mp4`, `vertical()`'s two sources, the
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
`zillow_photos.py`.

**Why:** The drift check matched on `agent_phone` read out of `config.json`. A folder
with no `config.json` produced no match, and the code read "no match" as "no problem".
But *having no config.json is the strongest available signal that a folder was never
scaffolded by the scraper* — the likeliest hand-named folder there is. The check
skipped exactly the case it was written to catch, which is how `brewester/9_w_cedar`
and `corcoran/46_beacon_5` sat through the scrape-naming commit untouched. Separately,
the advice it gave them — "rerun `zillow_photos.py`" — pointed at a script that
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

### [YYYY-MM-DD] — [Decision Title]
<!-- Template. Copy this stanza above for the next entry; leave this one empty. -->
**What:**
**Why:**
**Alternatives rejected:**
**Accepted risks:**
