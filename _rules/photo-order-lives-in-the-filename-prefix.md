---
name: photo-order-lives-in-the-filename-prefix
area: photos
type: non-negotiable
guarded_by:
  - tests/test_photo_order.py
  - tests/test_home_screen.py
source: CLAUDE.md@717ce32 L234-242
---

# Photo order lives in the filename prefix and nowhere else

No sidecar file, no manifest, no lookup table — those drift out of sync with the
folder. Rename to reorder. `config.json` and `.last_build.json` carry timing,
pacing, asset paths and build state **only**; neither may ever gain a photo order or
selection key. Because sorting the filenames *is* the ordering mechanism, a folder
with no numeric prefixes still builds — it just builds in alphabetical order. Every
build prints the resolved order first and warns when nothing authored it; `tour.py`
shows the same list and offers to add prefixes. Keep all three. That silent failure
shipped once already.
