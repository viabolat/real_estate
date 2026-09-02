---
name: the-recorded-link-is-the-last-field
area: outreach
type: non-negotiable
guarded_by:
  - tests/test_outreach_draft.py
source: CLAUDE.md@717ce32 L322-331
---

# The recorded link is the last field on its line, and nothing is ever appended after it

`outreach/links.csv` used to read `brand,listing,cut,url,uploaded_at`, so anything
that grabbed the link took `,2026-08-26T16:58:12` with it and the URL 404'd — and
`csv`'s default `\r\n` glued a carriage return onto the last field by a second
route. `LINK_COLUMNS` now ends in `url`, `record_links()` writes
`lineterminator="\n"`, and it migrates an older file in place rather than appending
a second shape into it — the file is gitignored, so a fix applied once here would
never reach another clone. `tests/test_outreach_draft.py` fails if a column is added
after `url`.
