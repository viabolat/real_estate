---
name: one-dump-per-file
area: scrape
type: non-negotiable
guarded_by: []
source: CLAUDE.md@717ce32 L371-378
---

# One dump per file, and a dump that is not a listing is refused

The parsers are first-match regexes over the whole text, so two dumps concatenated
into one file read the first listing's agent name and phone onto the second
listing's photos. Both scripts now exit non-zero on a dump with no `zpid` and no
address rather than writing a row of blanks and an
`agents/unknown_brokerage/listing/` folder — that exited 0, so a batch run reported
it as processed cleanly while poisoning `leads.csv`, which is also the naming
authority.
