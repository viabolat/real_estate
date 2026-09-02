# CLAUDE.md — Real Estate Photo Tour Generator

`make_tour.py` turns a folder of still listing photos into a branded walkthrough
video with music. `tour.py` is the interface: one command, a short question set, an
mp4. Stdlib only — no dependency beyond `ffmpeg` / `ffprobe`.

This file routes. It holds no rules, no schema and no runbook — those have their own
homes below, and this one stays small so every session does not pay for them.

## Start here

```bash
python3 tour.py       # the home screen: the roll-up, then four choices
```

Everything else is a gate, a one-time setup step, or an escape hatch.

## Where things live

| I need… | Go to |
|---|---|
| the pipeline: four stages, the gates, how each state is *derived* | [`CONTEXT.md`](CONTEXT.md) |
| a rule I must not break | [`_rules/CONTEXT.md`](_rules/CONTEXT.md) — 40 rules, by area |
| the `config.json` key surface | [`_reference/config-schema.md`](_reference/config-schema.md) |
| the folder tree, what a listing holds, the six cuts | [`_reference/layout.md`](_reference/layout.md) |
| a platform limit or a deliberate asymmetry | [`_reference/constraints.md`](_reference/constraints.md) |
| **photo quality — read before any work on image sourcing** | [`IDEA.md`](IDEA.md) §1–7 |
| every command, scenario and failure mode | [`STEPS.md`](STEPS.md) |
| the short start-to-finish version | [`WALKTHROUGH.md`](WALKTHROUGH.md) |
| why a past decision went the way it did | [`LOGIC_GUIDE.md`](LOGIC_GUIDE.md) |
| what is built, proposed, deferred, or still open | [`PROGRESS.md`](PROGRESS.md) |
| the scraper | [`scraper/README.md`](scraper/README.md) |
| the guards on the rules | [`tests/README.md`](tests/README.md) |

## Before you change code

1. Read the rules whose `area` matches what you are touching — the table in
   [`_rules/CONTEXT.md`](_rules/CONTEXT.md). Not all 40.
2. A rule is not advice. Most record a failure that already shipped. If a change
   contradicts one, say so and stop.
3. `python3 -m unittest discover -s tests -t .` — ~0.6s, no ffmpeg.
4. Propagate the change in the *same* pass: the relevant `_rules/` file,
   `_reference/config-schema.md`, `IDEA.md`, `STEPS.md`, and the module docstring.
   See [`docs-do-not-go-stale`](_rules/docs-do-not-go-stale.md).

## Before you push

`python3 check_pii.py` — no lead, phone number or email address is ever committed.
`hooks/pre-push` runs it, but `core.hooksPath` is per-clone config, so once per clone:

```bash
git config core.hooksPath hooks
```

## Two boundaries that must never move

- **`sample_` vs `tour_`.** Watermarked proof vs paid deliverable. Only `sample_`
  cuts publish; nothing goes out before sign-off.
- **The repo vs the machine.** Leads, phones, emails and keys stay on the machine.
  `.gitignore` and `.vercelignore` are two separate gates and both need updating.

## Commit messages

No `Co-Authored-By` trailer. The message ends with its last body paragraph.
