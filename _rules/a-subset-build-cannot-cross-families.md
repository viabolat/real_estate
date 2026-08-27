---
name: a-subset-build-cannot-cross-families
area: delivery
type: non-negotiable
guarded_by:
  - tests/test_build_stage.py
  - tests/test_card_isolation.py
source: CLAUDE.md@717ce32 L278-289
---

# A subset build must be structurally incapable of crossing families

The `--samples-only` / `--delivery-only` guards in `main()` are the
`sample_`/`tour_` boundary expressed as build wiring, upstream of the one
`publishable()` holds at the bucket. Each of the six call sites stays exactly where
it was and is only *nested*: `tests/test_card_isolation.py` walks `main()` with
`ast.walk` and asserts **four** `finish()` calls with a `cuts[...]` target and
**two** `vertical()` calls — that is the guard keeping the card off the MLS, and
deleting or restructuring a call site breaks it. `tests/test_build_stage.py` reads
the guards themselves and fails if a `tour_` cut is reachable under
`--samples-only`. Do not reach for `argparse` here either: unrecognised argv is
silently ignored today, and argparse would start rejecting it.
