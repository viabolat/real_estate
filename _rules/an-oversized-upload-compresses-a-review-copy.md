---
name: an-oversized-upload-compresses-a-review-copy
area: publishing
type: non-negotiable
guarded_by:
  - tests/test_publish_gate.py
source: PROGRESS.md@this-change — "keller_williams_realty/16_holmfield_ave: two of three sample_ cuts 413'd on publish", 2026-08-30
---

# An upload over the bucket's cap gets a compressed copy, not a silent failure

The Supabase project has no per-bucket `file_size_limit` override on `listing-media`
— checked directly against the Storage API's own bucket record — so the cap
enforced on every `PUT` is the platform default, roughly 50MB. A two-minute 720p
`sample_` cut at `make_tour.py`'s `CRF 18` routinely lands well past that: the
first real publish of `16_holmfield_ave` put 77.8MB and 74.5MB cuts against it and
got `HTTP 400 EntityTooLarge` on both, and `PRIMARY_CUT` (`sample_branded`) was
one of them — so no email draft was written even though the build had succeeded
and the operator had already confirmed the upload.

`upload()` still returns immediately on any `HTTP < 500` for every other failure —
retrying the identical bytes at an auth or path error cannot help. `_too_large()`
carves out the one `HTTP < 500` that retrying *can* fix, just not with the same
bytes: a 413 means the file, not the request, was the problem. `main()` then walks
`UPLOAD_CRF_LADDER` (`23, 28, 32`), re-encoding `out/`'s file smaller with
`_compressed_copy()` and retrying the same `PUT` at each rung until one clears the
cap or the ladder runs out. `out/` is never touched — the ladder always re-encodes
the same local master into a temp file, uploads that, and discards it once the
`PUT` resolves either way.

This is why verification (`present.get(name) != size`) reads from `actual_size`,
the size actually written to the wire, instead of the tuple `survey()` built from
`out/`. Restoring that comparison to `out/`'s size would make every compressed
upload report `UNVERIFIED` against a size it was never going to match, because the
object at the origin is legitimately smaller than the local master by design.

The trade-off is a public copy that is not byte-identical to `out/` — the CDN link
a client watches is a re-encode, not the same file the operator has locally. That
is disclosed at the end of a publish run (`N cut(s) were over the bucket's upload
cap...`) rather than left silent, and `out/` keeps the original quality either way,
so nothing about the paid `tour_` deliverable is touched by this at all — only a
`sample_` cut can reach this path, since `publishable()` refuses everything else
before an upload is ever attempted. See
[`a-publish-never-deletes-the-local-cut`](a-publish-never-deletes-the-local-cut.md)
for why the temp file's own cleanup does not count as this file deleting a
deliverable.
