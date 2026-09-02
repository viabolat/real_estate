---
name: draft-mp4-is-not-a-deliverable
area: build
type: non-negotiable
guarded_by:
  - tests/test_naming.py
source: CLAUDE.md@717ce32 L364-370
---

# `draft.mp4` is not a deliverable and does not go in `out/`

`out/` holds real cuts only, which is what makes the `tour_`/`sample_` prefix a
reliable boundary. A draft is 720p at a fast preset and carries the watermark; do
not add a flag that removes it, and do not let `--draft` read or write
`work_silent.mp4`. A stale draft-quality intermediate silently feeding a delivery
build is the same failure shape as the shuffled photo order — it produces a bad
video with no error.
