---
name: docs-do-not-go-stale
area: docs
type: non-negotiable
guarded_by:
  - tests/test_photo_order.py
source: CLAUDE.md@717ce32 L463-467
---

# Docs do not go stale

Any change to `make_tour.py` or `tour.py` — new feature, flag, output, renamed
constant, changed default — must be propagated in the *same* pass to every home
below that the change touches, and to the module docstring. `STEPS.md` is the
runbook someone else follows to produce client deliverables; drift there produces
bad work.

| Changed | Update |
|---|---|
| a `config.json` key | [`../_reference/config-schema.md`](../_reference/config-schema.md) — `tests/test_photo_order.py` fails on an undocumented key |
| a flag, an output name, a folder | [`../_reference/layout.md`](../_reference/layout.md) and `STEPS.md` |
| a rule, or the reason behind one | the file in [`../_rules/`](CONTEXT.md), then `python3 _rules/reindex.py` |
| a stage, a gate, or how a state is derived | [`../CONTEXT.md`](../CONTEXT.md) |
| a platform limit or a deliberate asymmetry | [`../_reference/constraints.md`](../_reference/constraints.md) |
| anything about photo sourcing or resolution | `IDEA.md` |
| where a reader should be sent | `CLAUDE.md` — the routing table, and nothing else |

`CLAUDE.md` is the exception that proves the rule: it is a catalog, so it changes
only when something moves, never when something is explained.
