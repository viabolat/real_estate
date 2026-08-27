---
name: a-publish-verifies-against-the-storage-api
area: publishing
type: non-negotiable
guarded_by: []
source: CLAUDE.md@717ce32 L309-314
---

# A publish verifies against the storage API, never the public URL

Objects are served through a CDN, so a `HEAD` on the `/preview/` link seconds after
an upload can hit an edge that has not replicated and report a correct upload as
failed. `publish.py` confirms with one authenticated `object/list` call against the
origin and compares sizes. Do not replace it with a fetch of the public link.
