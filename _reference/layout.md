---
name: layout
type: reference
---

# Layout — where things live, and what names them

The tree, the naming authority, and the six cuts a build produces. Rules that
constrain any of it live in [`../_rules/`](../_rules/CONTEXT.md); this file is the
shape, not the law.

```
agents/<brand>/brand.json     per-brand defaults — tour.py ONLY, see below
agents/<brand>/<listing>/     photos/, config.json, out/  — cwd for a build
global_assets/logos/          shared branding, referenced by config.json
global_assets/music/
global_assets/lower_thirds/
scraper/                      Zillow dump -> leads.csv + a scaffolded listing
publish.py                    sample_ cuts -> the public review bucket. NEVER tour_
status.py                     read-only: every listing and its one next action.
                              Names the run each is on -- see the two-run rule
hooks/pre-push                runs check_pii.py. Arm per clone -- see Running it
tests/                        stdlib unittest guards for the non-negotiables below
```

`<brand>` and `<listing>` are **not named by hand.** Both are slugified straight from
the scrape — `broker_name` and `address` in `scraper/leads.csv` — by
`scraper/photos.py`, so the folder and the lead row can never disagree. The
slug drops apostrophes rather than turning them into separators, so
`Gibson Sotheby's International Realty` is `gibson_sothebys_international_realty`,
not `gibson_sotheby_s_...`. `status.py` re-checks every folder against `leads.csv` on
each run — matched on agent phone, since address text formatting varies and a phone
number does not — and prints the `mv` for anything that has drifted.

One consequence, accepted deliberately: `Coldwell Banker Realty - Boston` and
`Coldwell Banker Realty - Waltham` are two brand folders with two `brand.json` files,
because that is what the scrape says. Set the logo twice rather than maintaining an
alias table, which is a second naming authority and would drift.

`brand.json` holds what is identical across every listing a brokerage owns — logo,
music, pacing, lower-third timing, the card mode. It holds **no agent identity.**
`leads.csv` already lists two agents under `Coldwell Banker Realty - Boston` and two
under `Gibson Sotheby's International Realty`, so a brand-level `agent_name` /
`agent_phone` puts one agent's phone number on another agent's video. Those two keys
live in the listing's `config.json`, written from the scrape, and nowhere else.
**`make_tour.py` never reads it.** `tour.py`
resolves `DEFAULTS → brand.json → listing config.json` and writes the effective
values into the listing's `config.json`, which stays the single source of truth for
a build. That keeps the script's contract intact — read the working directory, know
nothing about the `agents/<brand>/<listing>` layout — and keeps `config.json` an
accurate record of what produced a delivered video months later. A new listing
inherits at creation; changing a brand default does **not** retroactively alter
existing listings, which is what the explicit "Re-apply brand defaults" action
under **Brand settings** on `tour.py`'s home screen is for. It shows every key it
would change, per listing, and asks before writing — it is the one action in the
tool that edits files the operator is not looking at.


## What a listing folder holds

`agents/<brand>/<listing>/` is the working directory for a build, and everything
under `agents/` is gitignored — it holds client photos and, in `config.json`, an
agent's name and phone number. Nothing in it travels to another clone, which is why
no contract file lives there: it would be invisible the moment the repo was cloned.

```
agents/<brand>/brand.json          the factory layer for one brokerage. NO agent identity
agents/<brand>/<listing>/
   photos/                         numbered in tour order; the prefix IS the order
   config.json                     the per-listing schema -- the single record of a build
   out/                            the six cuts. Its contents ARE the build stage
   .last_build.json                can the stitch be reused? Not which family
   .build.lock                     held by a running build, O_EXCL, released via atexit
   draft.mp4                       only from --draft. Deliberately NOT in out/
```

## What a build reads

Reads from the **working directory**, which is normally a listing folder:

| Path | Required | Purpose |
|---|---|---|
| `photos/` | yes | Numbered in tour order; the prefix *is* the order |
| `music.mp3` | no | Licensed track. `--no-music` to skip. |
| `lower_third.png` | no | Agent + listing info |
| `logo.png` | no | Brokerage mark, top-left |
| `viabolat.png` | no | Proofing watermark, centered, `sample_` cuts only |
| `config.json` | no | Per-listing overrides — timing, pacing, asset paths |

Any asset path that does not resolve against the working directory is retried
beside `make_tour.py`, so the shared library and `viabolat.png` keep working from
any listing folder. All are read fresh every build — swapping any of them needs
only `--finish-only`.

## What a build writes

Outputs **six** cuts to `out/`, in two families — but not in one run. `tour.py`
builds the `sample_` trio first and the `tour_` trio only after the client signs
off; see the two-run rule below. Every name is prefixed with the
agent's own name — `output_prefix`, or `agent_name` slugified when that is blank —
because six listings all producing a `tour_branded.mp4` collide the moment the
files leave `out/` for a downloads folder or an email thread. Both blank leaves the
bare names, so a pre-existing folder built from the CLI is unchanged. The slug is
the folder rule applied to a filename — apostrophes drop rather than separate, so
`Sean O'Brien` signs `sean_obrien_tour_branded.mp4` inside `sean_obrien/` and not
`sean_o_brien_...`:

**Delivery** — clean, what the client gets on sign-off:
- `<agent>_tour_branded.mp4`   — card + lower third + top-left logo, for social /
  your own channels. Longer than the unbranded cut by the card(s) it carries
- `<agent>_tour_unbranded.mp4` — no branding, MLS/IDX-safe
- `<agent>_tour_vertical.mp4`  — 9:16 portrait, branded centre, clean blurred bands

**Sample** — identical edit plus a centered proofing watermark (`viabolat.png`),
what the client reviews before paying:
- `<agent>_sample_branded.mp4`
- `<agent>_sample_unbranded.mp4`
- `<agent>_sample_vertical.mp4`

Plus one more, only from `--draft`, and deliberately outside `out/`:

- `draft.mp4` — 720p at a fast x264 preset, branded **and** watermarked, one cut,
  written to the listing root. A review rung, never a deliverable. Its
  intermediates (`work_draft.mp4`, `clips_draft/`) are named apart from the
  delivery ones so a draft-quality stitch can never feed a delivery build.

See [`draft-mp4-is-not-a-deliverable`](../_rules/draft-mp4-is-not-a-deliverable.md).

## The card, and why a build stitches twice

The intro/outro card is drawn by ffmpeg from `config.json` — logo (or brokerage type
when there is no logo) over address, agent and phone. Nothing is exported from Canva
any more; the lower third is drawn the same way from the same three fields, and a
`lower_third.png` that exists still wins, so a hand-authored plate stays available
for a listing that earns it.

The card is branding, so it must never reach the MLS cut. That is why a build with a
card stitches twice:

| Stitch | Contents | Feeds |
|---|---|---|
| `work_silent.mp4` | photos only | `tour_unbranded`, `sample_unbranded` |
| `work_branded.mp4` | `[intro]` + photos + `[outro]` | `tour_branded`, `sample_branded`, `draft.mp4` |

With no card configured the second stitch is skipped and both read the same file — a
no-card build is byte-identical to one from before cards existed, verified against
`0722f52`. The cost when there *is* a card is one extra stitch, ~26s on a 6-minute
build.
