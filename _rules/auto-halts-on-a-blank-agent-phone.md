---
name: auto-halts-on-a-blank-agent-phone
area: card
type: non-negotiable
guarded_by:
  - tests/test_auto_flow.py
source: PROGRESS.md@this-change — "The first --auto listing shipped with no way to call back", 2026-08-30
---

# `--auto` halts a listing with no `agent_phone`, the same way it halts on a floor plan

The first real listing run through `--auto` start to finish belonged to a team
agent whose `leads.csv` row had no `agent_phone` — Zillow does not always
expose one for a team listing — and `questions(auto=True)` silently kept that
blank default, exactly as it silently keeps any other already-known value. The
card and lower third built and published with an address, a name and a
brokerage, and no number. The operator only noticed after the cuts were
already on the public bucket.

`_auto_build_one()` checks `cfg.get("agent_phone")` right after
`questions(auto=True)` returns — before the contact sheet, before any encode.
A blank phone halts that one listing: printed, not guessed at, and the rest of
the batch keeps going. Nothing about the halt is recorded — no marker file, no
`config.json` key beyond `agent_phone` itself — so filling it in and
re-running `--auto` (bare or scoped to `brand/listing`) is the entire resume
mechanism, the same "derive, never record" discipline
[`floor-plan-detection-is-flag-only`](floor-plan-detection-is-flag-only.md)
already uses. `--ignore-missing-phone-check` is the same shape as
`--ignore-floorplan-check`: read once from argv, always requires a
`brand/listing` scope (refusing to silently waive the check across a whole
batch), and never reaches what `save_config()`/`save_state()` write to disk.

This does not touch the interactive flow: `questions(auto=False)` already asks
"Agent phone" directly (`tour.py` — `ask("Agent phone", ...)`), so a human
running `tour.py` without `--auto` sees the blank field and can fill it in, or
knowingly leave it, in the moment. The halt exists only because `--auto`
removes that moment — it never calls `input()` — so a blank value that would
otherwise get a human's attention needs an explicit check standing in its
place.
