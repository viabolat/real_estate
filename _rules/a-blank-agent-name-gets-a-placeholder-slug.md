---
name: a-blank-agent-name-gets-a-placeholder-slug
area: naming
type: non-negotiable
guarded_by:
  - tests/test_naming.py
  - tests/test_status_naming.py
  - tests/test_home_screen.py
source: PROGRESS.md@this-change — "agents/, prospects/ and the outreach draft unify under company/address/agent", 2026-08-30
---

# A blank agent name gets `UNASSIGNED_AGENT`, never an empty path segment

`scraper/photos.py`'s `target_for()` names the third path segment the same way
it names the first two — `slugify(field(text, "agentName"), UNASSIGNED_AGENT)`
— so a scrape with no `agentName` still produces a real, three-segment folder:
`agents/<brand>/<listing>/unassigned_agent/`, not
`agents/<brand>/<listing>/`. A silent empty segment cannot be told apart from a
folder that was never scaffolded at all, which is exactly the failure
[`the-scrape-names-the-folders`](the-scrape-names-the-folders.md) exists to
catch — a folder that fell through a check because nothing distinguished
"no agent yet" from "no folder yet." `UNASSIGNED_AGENT` is a real, searchable
slug instead, mirroring the existing `"unknown_brokerage"` fallback for a
blank `brokerName`.

`tour.py` carries its own copy of the same constant rather than importing
`scraper.photos.UNASSIGNED_AGENT` or `status.py`'s re-export of it — the manual
listing picker (`choose_listing()`) has to keep working even when
`load_status()` fails to import, the same reasoning as
[`two-slug-functions-one-apostrophe-rule`](two-slug-functions-one-apostrophe-rule.md).
`choose_listing()`'s own "+ New agent" prompt applies the identical rule by
hand: a blank agent name typed at the prompt also becomes `UNASSIGNED_AGENT`,
not a `SystemExit` the way a blank brand or listing name is refused — an
agent, unlike a brand or a listing, is allowed to be genuinely unknown at
scaffold time.

Once the real agent name is known — a `config.json` written or corrected by
hand, or a later scrape carrying `agentName` — the folder is not renamed in
place. `status.py`'s drift audit reports the mismatch and prints the `mv`,
same as any other naming drift; there is no separate placeholder-resolution
path.
