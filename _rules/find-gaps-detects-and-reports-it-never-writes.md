---
name: find-gaps-detects-and-reports-it-never-writes
area: scrape
type: non-negotiable
guarded_by:
  - tests/test_find_gaps.py
source: PROGRESS.md@this-change — "Chrome-assisted logo fetching, consciously overriding 'logos and music are the operator's to supply'", 2026-09-01
---

# `find_gaps.py` detects and reports; it never writes

`find_gaps.py` reports two gaps the rest of the pipeline can't fill on its
own — a brokerage with no logo `brand.json` can resolve, and a listing with a
blank `agent_email` — and writes nothing. No `save_brand()`, no `config.json`
opened in write mode, no logo file downloaded. `--open`/`--open-all` hand a
search URL to `webbrowser.open()` and stop there; a tab landing open in the
browser is not a file landing on disk.

Acting on what this module reports is
[`fill_gaps.py`](fill-gaps-acts-only-on-what-find-gaps-named.md)'s job, and only
its job — that split is what keeps this rule true as the pipeline gets more
headless. Nothing below is relaxed by it: the per-file permission requirement
here governs the live session's own fetches and is untouched.

The two gaps resolve through two different gates, and nothing in this repo is
allowed to merge them:

- **A logo.** A PNG landing on disk from the network is a download, and every
  download needs the live session's explicit per-file permission, every time,
  one file at a time. That rule lives in the Claude Code environment itself,
  not in this repo, and no amount of documentation here can waive or batch
  it — see the "Fetching a logo or an agent email" workflow in `STEPS.md`.
- **An `agent_email`.** Writing it into an already-gitignored `config.json` is
  a plain file edit, not a download. The documented workflow skips a
  per-agent confirmation for it, on the operator's own instruction — but the
  source tier (Zillow's own profile page, the brokerage's site/team page, or
  a general web search, checked in that order) should still read as such in
  that run's summary, so a lower-confidence guess stays distinguishable even
  though nothing blocks any of them from being written.

**Standing-preference override, stated once, in writing.** `PROGRESS.md` §7
records *"Logos and music are the operator's to supply; automate the rest."*
Chrome-assisted logo fetching directly overrides that half of the sentence.
The operator confirmed it explicitly rather than having it happen quietly —
see the footnote on that bullet and the dated entry this rule's `source` line
points at. `find_gaps.py` itself stays on the safe side of the override: it
only ever *detects* a logo gap and reports where to look next. The fetch, and
the download permission it requires, live entirely in the live session that
reads its output.
