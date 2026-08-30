---
name: only-sample-cuts-publish
area: publishing
type: non-negotiable
guarded_by:
  - tests/test_publish_gate.py
source: CLAUDE.md@717ce32 L294-308
---

# Only `sample_` cuts publish, and `make_tour.py` never uploads

The bucket behind `/preview/` is public, so `publish.py` refuses anything that is
not `sample_*` — there is no `--force`, and `tests/test_publish_gate.py` fails if
`publishable()` grows an override. The obvious implementation, a `for f in
out/*.mp4` loop at the end of a build, would put the unwatermarked
`tour_branded.mp4` on a guessable public URL *before sign-off*: the exact boundary
the two families exist to hold. Publishing also stays out of `make_tour.py` for
three separate reasons — it is stdlib + ffmpeg only, it holds `.build.lock` through
a six-minute encode where a network timeout would fail a good build, and it is
contractually blind to the `agents/<brand>/<listing>/<agent>` layout that a
collision-free remote path needs. The remote path is `<brand>/<listing>/<file>`,
agent-blind on purpose — never the bare
filename: with `x-upsert` a flat bucket lets one listing silently overwrite
another's, which is the collision `output_prefix` already solved locally.

`publish.family()` is the **single owner** of which prefix means what. `status.py`
and `tour.py` both ask it rather than testing the prefix themselves: a second
implementation of that boundary would drift, and the drift would be an unwatermarked
deliverable counted as a proof.
