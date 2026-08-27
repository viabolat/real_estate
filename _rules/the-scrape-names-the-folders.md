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

`agents/<brand>/<listing>` is `slugify(broker_name)/slugify(address)` from
`scraper/leads.csv`. Do not hand-name a listing folder, and do not add an alias
table mapping a scraped brokerage onto a shorter hand-picked name — that is a second
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
