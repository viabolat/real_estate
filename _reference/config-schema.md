---
name: config-schema
type: reference
---

# `config.json` — the per-listing schema

Every key optional; the defaults are the constants in `make_tour.py`. This table is
the documented surface: `tests/test_photo_order.py` asserts that no `_cfg.get()` key
in `make_tour.py` is missing from it, so **a new key added to the source without a
row here fails the suite.** That is the "docs do not go stale" rule with teeth.

`make_tour.py` reads this file from the working directory and nothing else — it
never reads `brand.json`, and never learns the `agents/<brand>/<listing>/<agent>` layout.
`tour.py` resolves `DEFAULTS → brand.json → config.json` and writes the effective
values here, so `config.json` stays the single record of what produced a delivered
video months later.

| Key | Default | Note |
|---|---|---|
| `clip_seconds` | `4.0` | forces a full rebuild when changed |
| `xfade_seconds` | `0.5` | forces a full rebuild when changed |
| `brand_persistent` | `true` | `false` = lower third only inside the window below. `tour.py` defaults it to `false` when a card is carrying the same three lines — see below |
| `brand_in` / `brand_out` | `0.8` / `6.5` | only read when not persistent; out > in |
| `lower_third` / `logo` / `music` / `watermark` | the plain filenames | repo-relative paths into `global_assets/`. `tour.py`'s `DEFAULTS` pins `watermark` to `global_assets/logos/viabolat.png` — the bare filename does not resolve from a listing folder, and a watermark that will not resolve now refuses the sample build. `--auto` additionally resolves a blank `logo` against `global_assets/logos/<brand>.png` — the brand folder's own slug — before anything else runs, and saves it to `brand.json` when it exists; when it does not, and nothing else resolves either, `--auto` halts that listing rather than ship the type-only card unasked. See [`auto-picks-up-the-brand-logo-by-slug`](../_rules/auto-picks-up-the-brand-logo-by-slug.md) |
| `address` / `agent_name` / `agent_phone` | `""` | the lower third's three lines, and the card's body. Any may be blank |
| `brokerage` | `""` | card only, and only when there is no logo |
| `output_prefix` | `""` | what leads the output filenames. Blank derives it from `agent_name`; blank both leaves the bare `tour_`/`sample_` names. `tour.py` writes the brand folder here when `agent_name` is blank — `make_tour.py` must never learn the `agents/<brand>/<listing>/<agent>` layout itself |
| `card` | `"none"` | `intro` \| `outro` \| `both`. `tour.py` writes `outro` on a new listing; a bare CLI run in an older folder is unchanged |
| `card_seconds` | `5.0` | forces a full rebuild when changed |
| `card_style` | `"auto"` | `logo` when one resolves, `type` when none does |
| `card_theme` | `"auto"` | measures the logo against both grounds, takes the higher contrast |
| `accent` / `font` / `scrim` | `#C8A24A` / `Liberation Sans` / `black@0.55` | rule and phone line / any installed family / the lower third's panel |

Two keys are deliberately absent and must stay absent:

- **no photo order or selection key** — order lives in the filename prefix; see
  [`photo-order-lives-in-the-filename-prefix`](../_rules/photo-order-lives-in-the-filename-prefix.md)
- **no build-stage key** — the run is derived from `out/`; see
  [`../CONTEXT.md`](../CONTEXT.md)

And two that may never be inherited from `brand.json`: `agent_name` and
`agent_phone`. See
[`brand-json-carries-no-agent-identity`](../_rules/brand-json-carries-no-agent-identity.md).
