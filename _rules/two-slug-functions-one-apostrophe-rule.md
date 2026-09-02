---
name: two-slug-functions-one-apostrophe-rule
area: naming
type: non-negotiable
guarded_by:
  - tests/test_naming.py
source: CLAUDE.md@717ce32 L450-462
---

# The two slug functions agree on apostrophes, and are still two functions

`scraper/photos.slugify` names the folders; `make_tour._slug` names the files inside
them. Both drop apostrophes rather than turning them into separators, or one agent's
name gets two spellings — `sean_obrien/sean_o_brien_tour_branded.mp4`. They stay
separate on purpose: `make_tour.py` runs with cwd set to a listing folder and
nothing but ffmpeg on the path, so importing the scraper would make a build depend
on the scrape, which it otherwise never does. They also differ on the empty case on
purpose — the scraper falls back to `listing` because a folder cannot be named `""`,
while `_slug` returns `""` so a blank `agent_name` leaves the bare `tour_`/`sample_`
names. Change one apostrophe rule, change both; `tests/test_naming.py` fails if they
drift.
