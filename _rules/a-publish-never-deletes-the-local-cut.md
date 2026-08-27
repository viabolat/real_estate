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
