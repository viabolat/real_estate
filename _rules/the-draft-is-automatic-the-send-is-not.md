---
name: the-draft-is-automatic-the-send-is-not
area: outreach
type: non-negotiable
guarded_by:
  - tests/test_outreach_draft.py
source: CLAUDE.md@717ce32 L332-343
---

# The draft is written automatically; the send is not, and never becomes a flag

`PROGRESS.md` §5.1 settled that mail leaving the machine is a deliberate act. There
is no SMTP credential anywhere in this repo and `tests/test_outreach_draft.py` fails
on `smtplib`, `sendmail`, `SMTP(` or `starttls` appearing in `publish.py`. The draft
also quotes the `sample_branded` cut and only that — `PRIMARY_CUT` — because a cold
email linking a `tour_` file is the paid deliverable given away in a one-word
filename difference, the same boundary `publishable()` holds at the bucket. A blank
`agent_name` or `address` leaves the `{placeholder}` visibly in the file and says so
on the console: a gap you can see beats one silently filled with an empty string.

`outreach/contacted.csv` (`publish.record_contacted()`/`publish.contacted()`) sits
on the same side of this boundary — it only ever records that a human has already
sent the draft, from a prompt that defaults to No, exactly like every other prompt
that follows this one. It is never the thing that sends, and nothing calls
`record_contacted()` except that confirmation and `tour.py`'s
`mark_contacted_action()` home-screen sweep, which asks the same question one
listing at a time.
