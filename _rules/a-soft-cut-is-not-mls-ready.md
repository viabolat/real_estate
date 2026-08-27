---
name: a-soft-cut-is-not-mls-ready
area: photos
type: non-negotiable
guarded_by:
  - tests/test_status_naming.py
source: CLAUDE.md@717ce32 L226-231
---

# A soft cut is not MLS-ready, and its name will not tell you

The console is the warning. `status.py` and `publish.py` both re-measure `photos/`
rather than reading a verdict off a filename, so the reminder still arrives weeks
after the build — `status.py` prints `soft (NNNpx photos)` and `publish.py` asks a
second time before a soft cut goes to a client. If a delivery is soft, the photos
are not ready — get the photographer's originals. See `IDEA.md` §4.
