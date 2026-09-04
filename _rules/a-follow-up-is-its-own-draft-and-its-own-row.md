---
name: a-follow-up-is-its-own-draft-and-its-own-row
area: outreach
type: non-negotiable
guarded_by:
  - tests/test_active_view.py
source: PROGRESS.md@this-change — three agents received a byte-identical duplicate of an email from two weeks earlier, 2026-09-02
---

# A follow-up is its own draft and its own row

A contacted listing becomes active again — offered by the build picker — once its
`FOLLOW_UP_DAYS` window passes. That is what the window is **for**
([needs-attention-is-a-view-not-a-move](needs-attention-is-a-view-not-a-move.md)).
But the folder held one artifact — `outreach_draft.txt`, the first-contact draft — and
both send-side rungs skipped anything already in `contacted.csv`. So a resurfaced lead
had no rung at all. Following up meant sending the first email again.

That is exactly what happened on 2026-09-02. `2 Commonwealth Ave` (first contacted
2026-08-21) at 17:21:42, `9 W Cedar St` (2026-08-19) at 17:22:17 — one minute apart —
and `55 Lagrange St Unit 1705` (2026-08-26) each received a second copy of their
original email, same subject, same body. The one follow-up that read correctly —
`46 Beacon St. #5`, 17:23:15 — was written by hand outside the tool.

`2 Commonwealth Ave` was not in the first account of this failure, which named two
agents. It surfaced on 2026-09-04, from the same Sent folder, when its thread was
pasted in for an unrelated reason: one more send, of the same email, in the same
two-minute burst, that nobody had counted. A failure whose own record undercounts it
is the argument for `contacted.csv` carrying one row per send rather than one row per
lead — the ledger is the only place a duplicate can be seen after the fact.

A second, quieter bug made it permanent: `contacted_at()` returned the **first**
matching row of an append-only file, so even a recorded follow-up left
`follow_up_date()` answering with a date already in the past. The listing would have
resurfaced every render, forever.

## The rule

**One row per send.** `contacted.csv` is append-only and `contacted_at()` returns the
**latest** row. A recorded follow-up re-arms the window exactly as the first contact
armed it. No schema change, no `followed_up_at` column — the file already had the
shape, only the read was wrong.

**One draft per wording.** `outreach/followup.txt` renders to `outreach_followup.txt`
through the same `draft_text()` as the first contact. Two files, two names. A test
asserts they never render identically, because the moment they do, sending the
follow-up *is* sending the first email again.

**The link is recovered, not regenerated.** `recorded_link()` reads the branded URL out
of `links.csv`
([the-recorded-link-is-the-last-field](the-recorded-link-is-the-last-field.md)). A
follow-up points at the cut the agent already has; re-publishing to obtain a URL that
has not changed is a round trip for nothing.

**The recorded link outlives a folder rename.** The cut filename carries whatever
`agent_name` `config.json` held at *build* time, which is not necessarily today's
folder name. `recorded_link()` prefers the agent-prefixed cut and falls back to any
`_sample_branded` row for that `(brand, listing)`. Without that fallback, renaming a
drifted folder to match the scrape
([the-scrape-names-the-folders](the-scrape-names-the-folders.md)) would orphan its own
link and silently skip the follow-up.

**The send is still human.** Drafting the follow-up is automatic, the same as the first
draft; rung 5 offers it and records it only after the operator confirms the mail
actually went out
([the-draft-is-automatic-the-send-is-not](the-draft-is-automatic-the-send-is-not.md)).

**One key, two readers.** `contacted.csv` is keyed by folder name for
`status.contacted()` and rung 5; `leads.html` looks the same row up by the key it
derives from the leads.csv row. Those agree only while every folder matches the
scrape, which is what `status.py`'s drift check enforces — so re-keying a row without
renaming its folder, or renaming a folder without re-keying its row, breaks one reader
or the other. Do both, in the same pass. `status.audit()`'s third report,
`orphaned_marks()`, names any row no scraped name matches.

## Where it shows

`status.py`'s NEXT column reads `follow up -- rung 5 drafts it` instead of
`sample published -- awaiting sign-off`. That string was the terminal rung, so a lead
that had gone quiet for three weeks read exactly like one emailed an hour ago.
