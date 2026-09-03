---
name: fill-gaps-acts-only-on-what-find-gaps-named
area: scrape
type: non-negotiable
guarded_by:
  - tests/test_fill_gaps.py
source: PROGRESS.md@this-change — "headless logo + agent_email fill on the automation branch", 2026-09-02
---

# `fill_gaps.py` acts only on what `find_gaps.py` named

`find_gaps.py` is the detector and stays read-only —
[find-gaps-detects-and-reports-it-never-writes](find-gaps-detects-and-reports-it-never-writes.md)
is unchanged and still guarded. `fill_gaps.py` is the only module allowed to act
on its findings, and it may not re-derive any of them. It imports
`find_gaps.brand_gaps()`, `email_gaps()`, `row_key()` and `load_leads()` rather
than reimplementing them, for the same reason `find_gaps.py` imports
`photos.slugify()`: two functions that name the same folder eventually name it
differently, and the one that is wrong is always the one nobody ran.

Three lanes, and the boundaries between them are the rule:

- **`agent_email`.** The value comes from `leads.csv`, where `lead.py` already
  parsed it out of the dump's `agentEmail` field. It is a copy between two files
  already on disk — no network, and a stronger source than the profile-page
  guess `STEPS.md` ranks first. **A gap with no `leads.csv` email is reported,
  never guessed.** So is a value that does not parse as an address. The tier
  that produced every written value appears in the run summary.
- **A logo in the `available` bucket.** Pointing `brand.json` at a file already
  sitting in `global_assets/logos/` under the exact brand slug is a one-key JSON
  write, not a fetch. No network.
- **A logo in the `gap` bucket.** The only lane that reaches the network, and it
  is off unless `--fetch` is passed. A candidate domain must *verify* — a
  distinctive word from `broker_name` in `<title>` or `og:site_name` — before
  anything is downloaded, and the payload must be a real PNG by magic bytes. A
  non-PNG mark is reported for a session to handle, never saved under a name
  that lies about its type, because `make_tour.py`'s gate resolves
  `global_assets/logos/<brand>.png` and nothing here can transcode without
  adding a dependency.

**`near_miss` is never adopted, by any lane.** `find_gaps.py` refuses to
auto-adopt it because a plausible-but-wrong brokerage mark ships on a client's
video; adopting it one file over is the same mistake with an extra hop. The
bucket is reported and left alone.

## What this does not touch

Nothing here goes near publishing, sending, or sign-off. `--auto` still never
reaches `publish_rung()`, mail still leaves the machine by hand, and only
`sample_` cuts publish — see
[a-publish-prompt-has-one-owner](a-publish-prompt-has-one-owner.md),
[the-draft-is-automatic-the-send-is-not](the-draft-is-automatic-the-send-is-not.md)
and [only-sample-cuts-publish](only-sample-cuts-publish.md). Those gates are
decisions, not gaps, and no amount of headlessness applies to them.

## The download boundary, stated once

`find-gaps-detects-and-reports-it-never-writes` says a logo PNG landing on disk
needs the live session's explicit per-file permission. That rule governs **the
Claude Code session's own fetches**, and it is untouched: it lives in that
environment, not in this repo, and nothing here waives or batches it.
`fill_gaps.py --fetch` is repo code downloading a file, the same category as
`photos.py`'s `urlretrieve` of every listing photo — which is why it is opt-in,
verifies the domain first, and prints its source URL for each file it writes.
