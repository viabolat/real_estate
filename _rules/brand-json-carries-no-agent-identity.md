---
name: brand-json-carries-no-agent-identity
area: naming
type: non-negotiable
guarded_by:
  - tests/test_brand_scope.py
source: CLAUDE.md@717ce32 L418-434
---

# `brand.json` never carries `agent_name` or `agent_phone`

A brokerage has many agents; the folder is keyed on the brokerage. See the
`brand.json` note above. `tour.py` enforced this at neither end for a while:
`BRAND_KEYS` listed both keys and `questions()` offered *"Save the name, phone and
brokerage as {brand} defaults?"* with the confirm defaulting to **yes**. Nothing had
gone wrong yet — all nine `brand.json` files were clean — but `leads.csv` lists two
agents under `Coldwell Banker Realty - Boston`, two under `Gibson Sotheby's` and two
under `Serhant`, and `load_config()` layers `brand.json` *under* the listing's
`config.json` without printing anything. One yes would have put one agent's phone
number on the other agent's card, lower third and output filenames across every
listing that brokerage owns, silently. `save_brand()` now filters the two keys out
and `load_brand()` strips them on the way back in, so a hand-edited or legacy file
cannot reintroduce them either; `tests/test_brand_scope.py` fails if either returns
by any route. `brokerage` stays — it is the same string for every listing a brand
owns, which is what a brand default *is*.
