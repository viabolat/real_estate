---
name: one-dump-per-file
area: scrape
type: non-negotiable
guarded_by:
  - tests/test_home_screen.py
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

A dump is a `.txt` **or** a `.json` file — both read as raw text by the same
regexes, since the `__NEXT_DATA__` blob saved on its own is the same bytes the
full page dump carries inside it. Which extensions count lives in exactly one
place, `scraper/photos.py`'s `is_dump()`, because `scraper/run.py` and
`tour.py`'s pending count both answer that question: a list that drifted between
them would offer an import the batch run never makes, or import a file the home
screen never counts. The extension decides only what is *read*; whether a file is
a listing is still `target_for()`'s refusal, unchanged.
