---
name: no-pii-is-ever-committed
area: pii
type: non-negotiable
guarded_by:
  - tests/test_hook_wired.py
source: CLAUDE.md@717ce32 L379-389
---

# No lead, phone number or email address is ever committed

`leads.csv`, `leads.html`, the raw dumps, `agents.txt` and `property_email.txt` are
ignored by repo-level rules, not by a global `~/.gitignore_global` that does not
travel. `python3 check_pii.py` scans everything git would publish — against the real
values in `leads.csv`, not a guess — and exits non-zero. Run it before every push. A
private repo is an access-control boundary, not a redaction one: it gets shared,
cloned, or opened up years later, and nothing re-reviews the history at that moment.
Write `.gitignore` patterns on their own lines — git only honours `#` at the start
of a line, so a trailing comment turns the pattern into a literal that matches
nothing.

`outreach/template.txt` is the only committed thing under `outreach/`, and the way
that is written matters: `.gitignore` uses the directory-*contents* form
`outreach/*` plus `!outreach/template.txt`. Git does not descend into an excluded
directory, so a negation under a bare `outreach/` would match nothing and the
template would silently never be committed.
