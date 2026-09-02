---
name: nothing-invariant-becomes-a-control
area: interface
type: non-negotiable
guarded_by: []
source: CLAUDE.md@717ce32 L14-38 (stated as design intent, not as a rule)
---

# Anything with the same answer on every listing is inherited or derived, and never becomes a control

`tour.py` replaced a Streamlit dashboard that put thirteen controls on screen and
still left the operator to remember which of them mattered. The rule that came out
of that: a setting whose answer is the same on every listing is inherited from
`brand.json` or derived from the photos. It does not become a question, and it does
not become a flag on the home screen.

So `tour.py` picks the listing, imports and numbers the photos, names what is
missing *before* anything encodes, asks only what actually varies, and walks the
three rungs — *is the order right, does the edit feel right, ship it* — running
`make_tour.py` for each.

This is why the question set is short and why it must stay short. Adding a control
is the easy way to answer "should this be configurable?" and it is almost always the
wrong one: the operator then carries the decision on every listing forever. Three
places absorb that instead, in order of preference:

1. **Derived from the photos or the folder** — the photo order, the build stage, the
   resolution verdict, which dumps are pending. Nothing to ask and nothing to store.
2. **Inherited from `brand.json`** — the logo, the music, the pacing, the card mode.
   Asked once per brokerage.
3. **A `config.json` key with a default** — reachable from the CLI for the listing
   that earns it, never surfaced in the question set.

Everything `tour.py` does can still be done from the CLI. The tool is a path through
`make_tour.py`, not a layer above it, and a control added here is a control that
`make_tour.py` did not need.
