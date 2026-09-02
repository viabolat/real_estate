---
name: the-scrape-names-the-folders
area: naming
type: non-negotiable
guarded_by:
  - tests/test_status_naming.py
  - tests/test_naming.py
source: CLAUDE.md@717ce32 L390-405
---

# The scrape names the folders; nothing else does

`agents/<brand>/<listing>/<agent>` is
`slugify(broker_name)/slugify(address)/slugify(agent_name)` from
`scraper/leads.csv`, all three produced by one function —
`scraper/photos.py`'s `target_for()`, returning a `(brand, listing, agent)`
3-tuple — so `main()`'s scaffolding and `tour.py`'s home-screen pending-dump
detection can never compute two different answers for the same dump. Do not
hand-name a listing or agent folder, and do not add an alias table mapping a
scraped brokerage or agent onto a shorter hand-picked name — that is a second
naming authority, and the two drift the moment a brokerage is renamed.
`coldwell_banker/2_comm_ave` sat beside a lead row reading `Coldwell Banker Realty -
Boston` / `2 Commonwealth Ave` for exactly that reason. `status.py` prints the `mv`
when a folder no longer matches its lead row. A folder with **no** lead row behind
it is reported separately as *unverifiable*, not passed: the check keys on
`agent_phone` out of `config.json`, so a folder that never had a `config.json` — the
strongest signal it was never scaffolded by the scraper, and so the likeliest
hand-named folder there is — used to fall silently through the check built to catch
it. `brewester/9_w_cedar` and `corcoran/46_beacon_5` sat through the scrape-naming
commit that way. They are left alone deliberately: the scrape cannot name a listing
it has no row for, and hand-naming one is the second authority this rule exists to
prevent.

A scrape with no `agentName` is not a missing row — it is a placeholder:
`agent` slugifies to `UNASSIGNED_AGENT` (`"unassigned_agent"`) rather than
leaving a silent empty path segment, which could not be told apart from a
missing folder. See
[`a-blank-agent-name-gets-a-placeholder-slug`](a-blank-agent-name-gets-a-placeholder-slug.md).
Correcting a folder still sitting on the placeholder once the real agent name is
known goes through `status.py`'s drift audit like any other naming drift — never
a hand rename.
