---
name: a-sample-ships-silent-and-music-never-blocks
area: card
type: non-negotiable
guarded_by:
  - tests/test_status_naming.py
source: PROGRESS.md@this-change — "no music for any samples ... if there are any agents mp4 that have it please remove them (if not sent already)", 2026-09-02
---

# A `sample_` cut ships silent, and a blank music bed is never the next action

Standing operator instruction, 2026-09-02: **no music on any `sample_` cut.** The
proofing copy is about the photos and the branding; a music bed only invites a note
about the music. A silent build is the house style here, not a fallback.

`--auto` already behaved correctly — `questions(auto=True)` skips the music pick
outright rather than guess one, and `_auto_build_one()` appends `--no-music` when
nothing resolves. Every listing the scraper has ever scaffolded therefore built
silent. The one exception was `gibson.../169_k_st_1`, whose *listing* `config.json`
carried `global_assets/music/united.mp3` from before the scraper wrote these files;
it built with an audible bed and was rebuilt silent the same day.

## The failure this records

`status.py`'s `next_action()` ladder had music as a blocker one rung below the logo:

```python
if not resolves(listing_dir, merged.get("music")):
    return "music blank/missing -- add it to brand.json" + origin
```

Because music is deliberately never set, that line matched **every listing in the
ledger** — including all eleven already delivered and contacted — and returned the
nag in place of the real state. The NEXT column, which is the entire point of
`status.py` and the first thing `tour.py`'s home screen prints, said nothing useful
about any listing for as long as it stood there. The footer counted the same
listings into "N brokerage(s) need a logo or music set once".

The asymmetry with the logo is the whole distinction, and it is why the logo check
stays and the music check goes:

| | missing logo | missing music |
|---|---|---|
| effect on `--auto` | **halts the listing** ([`auto-picks-up-the-brand-logo-by-slug`](auto-picks-up-the-brand-logo-by-slug.md)) | appends `--no-music`, builds |
| effect on the cut | ships the type-only card, unasked | ships silent, as intended |
| is it a blocker | yes | **no** |

## What must stay true

- `next_action()` never returns a string naming music, in any state.
- The logo check stays a blocker; removing music does not soften it.
- Cuts still carry a *silent* AAC track, so nothing downstream special-cases a
  video with no audio stream. "Has an audio stream" is therefore **not** the test
  for whether a cut has music — measure it (`ffmpeg -af volumedetect`); true
  silence reads −91 dB and a bed reads about −19 dB.
- `the_collaborative_companies/brand.json` still points at `success.mp3` and is
  left alone deliberately: its sample was published and contacted before this
  instruction, so clearing the brand default would make a future paid `tour_` cut
  differ from the sample the client signed off on.
