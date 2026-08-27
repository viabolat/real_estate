---
name: below-par-photos-build-and-are-reported
area: photos
type: non-negotiable
guarded_by:
  - tests/test_naming.py
source: CLAUDE.md@717ce32 L214-225
---

# Below-par photos build, and the shortfall is reported, never encoded in a filename

The gate does not refuse and does not rename: it measures and says so, out loud,
more than once. A build that needs `--allow-lowres` produces the same six names as
any other build, and `tour.py` passes the flag only after stating the count, the
worst offender and its upscale factor. The verdict is printed at preflight, restated
before the delivery build is confirmed, and restated again with the finished file
list. It used to refuse outright at the *end* of a run, after the question set and a
draft had already been paid for, having known the verdict at preflight — second one.
That threw the work away and gave the operator nothing to act on. Do not restore the
refusal, and do not reintroduce a filename suffix: `out_path()` takes the cut name
and nothing else, and `tests/test_naming.py` fails if any cut grows a resolution
tag.
