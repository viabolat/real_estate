---
name: auto-picks-up-the-brand-logo-by-slug
area: card
type: non-negotiable
guarded_by:
  - tests/test_auto_flow.py
source: PROGRESS.md@this-change — "16 Holmfield Ave built with no logo, and no brand.json ever pointed at one", 2026-08-30
---

# `--auto` adopts a brand's own logo by slug, and halts rather than ship the type-only card silently

`questions()`'s interactive picker offers every file in `global_assets/logos/`
and asks a human to choose — guessing among several unrelated brokerage marks
is not a call `--auto` should make silently, which is why that picker is
skipped outright under `auto=True` (see
[`nothing-invariant-becomes-a-control`](nothing-invariant-becomes-a-control.md)'s
sibling reasoning). But a brokerage's *own* mark is not one of several
choices — it lives at exactly one predictable path,
`global_assets/logos/<brand>.png`, the same slug as the `agents/<brand>`
folder it belongs to. `keller_williams_realty/brand.json` had never set
`"logo"`, even though `global_assets/logos/keller_williams_realty.png` had
sat there the whole time — the first `--auto` run of `16_holmfield_ave`
built and published with the type-only card, and nobody had decided that on
purpose.

`_auto_build_one()` now tries that fixed path before `preflight()` runs: if
`cfg["logo"]` does not already resolve and
`global_assets/logos/<brand>.png` does, it adopts that path and saves it as
the brand default with `save_brand()` — the same mechanism `questions()`
already uses to persist a confirmed brokerage name, so every other listing
under that brand inherits it from then on without repeating the lookup.

When neither `cfg["logo"]` nor that fixed path resolves, the listing halts —
after the phone check, before the contact sheet — the same shape as
[`auto-halts-on-a-blank-agent-phone`](auto-halts-on-a-blank-agent-phone.md):
printed, nothing built, the rest of the batch keeps going, and nothing about
the halt is recorded anywhere. Add the file at that path, or force the
type-only card through once with `--ignore-missing-logo-check` — read once
from argv, always requires a `brand/listing` scope, and never reaches what
`save_config()`/`save_state()`/`save_brand()` write to disk.

This does not touch the interactive flow: a human running `tour.py` without
`--auto` still sees `questions()`'s own picker when nothing resolves, and can
knowingly leave a brand with no mark. The halt exists only because `--auto`
removes that moment, the same reasoning
[`auto-halts-on-a-blank-agent-phone`](auto-halts-on-a-blank-agent-phone.md)
already states for the phone number.
