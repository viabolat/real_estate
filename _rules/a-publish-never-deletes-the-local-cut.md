---
name: a-publish-never-deletes-the-local-cut
area: publishing
type: non-negotiable
guarded_by:
  - tests/test_publish_gate.py
source: CLAUDE.md@717ce32 L315-321
---

# A publish never deletes the local cut

`out/` stays the copy of record after an upload; a public bucket must not become the
only place a deliverable exists, and `config.json` is meant to still explain what
shipped months later. Storage pressure is a reason to prune old listings
deliberately, never a reason for a fresh delivery to remove itself.
`tests/test_publish_gate.py` fails on an `os.remove` anywhere in `publish.py`.

The one file `publish.py` does delete is not a deliverable: an oversized upload's
temporary compressed copy (see
[`an-oversized-upload-compresses-a-review-copy`](an-oversized-upload-compresses-a-review-copy.md)),
which never lives in `out/` and never is the thing `config.json` records as
shipped. Its cleanup rides `NamedTemporaryFile`'s own teardown rather than a
literal delete call, which is exactly what keeps this file's guard test honest
instead of forcing a workaround around it.
