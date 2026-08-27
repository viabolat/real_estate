---
name: a-folder-with-no-lead-row-still-starts
area: naming
type: non-negotiable
guarded_by:
  - tests/test_status_naming.py
source: CLAUDE.md@717ce32 L406-417
---

# A folder with no lead row still gets a start line

Provenance is a fact about a folder, not a blocker on it. `next_action()` used to
test `if not cfg:` *before* it looked at readiness, so a listing with photos and no
`config.json` reported `not in leads.csv` forever and could never read as ready —
while `tour.py`'s picker already offered it and its question set already wrote the
config. The roll-up was refusing to say what the tool would happily do. The fact now
travels as a suffix on the real next action instead of replacing it. A **scraped**
folder with no config is still sent back to `photos.py`, because there the scrape
can fill in the address, agent, phone and watermark path properly. Nothing about the
naming authority moves: the folder is not renamed, `audit()` is untouched, and it
keeps reporting as *unverifiable*.
