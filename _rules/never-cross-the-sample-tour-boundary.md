---
name: never-cross-the-sample-tour-boundary
area: delivery
type: non-negotiable
guarded_by:
  - tests/test_naming.py
  - tests/test_publish_gate.py
source: CLAUDE.md@717ce32 L290-293
---

# Never send a `sample_` file as a deliverable, and never send a `tour_` file before sign-off

The two families exist to keep that boundary enforceable by filename. Do not add a
flag that strips the watermark from a sample cut.
