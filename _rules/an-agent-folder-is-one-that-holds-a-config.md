---
name: an-agent-folder-is-one-that-holds-a-config
area: naming
type: non-negotiable
guarded_by:
  - tests/test_auto_flow.py
  - tests/test_status_naming.py
  - tests/test_migrate_layout.py
source: 2026-09-02 transfer audit
---

# An agent folder is one that holds a `config.json` or a `photos/`

`_dirs()` lists subdirectories. At the listing level that is not enough to name
one: `agents/<brand>/<listing>/` holds `<agent>/`, and `<agent>/` in turn holds
`photos/`, `clips/`, `clips_draft/`, `out/` and `work_text/`. A listing folder
still in the pre-agent-level shape — `config.json` and `photos/` sitting directly
under the listing, which is what the first version of the code wrote — is
therefore indistinguishable from a listing whose agent is called `photos`.

It was not merely skipped. Every walker invented something in its place:

- `tour.py`'s `--auto` targeted `agents/<brand>/<listing>/photos/`, found no
  `photos/photos/`, and reported an `error` per listing.
- `status.py`'s `survey()` looked for a `config.json` inside `photos/`, found
  none, and filed the listing under **unverifiable** — while the config sat one
  level up carrying the `agent_phone` the drift audit keys on. Eight rows.
- `needs_attention/` symlinked raw `photos/`, `clips/` and `out/` directories.
- `find_gaps.py`'s `email_gaps()` reads the four-level path, so those listings
  reported **zero** email gaps. Invisible, not clean.

One bug, four faces. Admit a subdirectory as an agent only if it **holds a
`config.json` or a `photos/`** — `tour.is_agent_dir()` and `status._agent_dirs()`,
which must agree. `scraper/photos.py`'s `scaffold()` always writes both, and no
build intermediate has either.

Use that positive test, never a reserved-name blocklist. A blocklist drifts the
moment a new intermediate directory is added, and it fails silently in exactly
the direction that costs a listing.

`config.json` is the load-bearing half: nothing in the pipeline ever deletes one,
so it survives a delivery cleanup that has taken the cuts away. `photos/` is
there for a folder caught mid-scaffold. A test fixture that builds an agent
folder from an `out/` alone is not modelling anything the walkers can see — give
it a `config.json`, because a real one always has it.

## The legacy shape is a migration, not a missing scrape

Once the check is right, `survey()`'s empty-agents branch starts firing for these
folders, and "no agent folder — rerun photos.py" is the wrong advice: the scrape
already ran, and its output is one level off. `status.legacy_target()` reports the
destination instead — re-derived from `scraper/leads.csv` on `agent_phone`, the
same key the drift audit uses. Nothing there names a folder; it reports the name
the scrape already implies, per
[`the-scrape-names-the-folders`](the-scrape-names-the-folders.md). A listing with
no lead row keeps the "rerun photos.py" message and is never hand-named.

`migrate_layout.py` performs the move, and it moves with `os.rename` — bytes are
relocated, never rewritten and never dropped, so a listing that was already built
keeps its `out/` cuts and its reusable work stitch. The single exception is a
legacy copy sitting beside an `<agent>/` whose `photos/` are byte-identical: a
half-finished migration, deleted rather than merged, because merging two identical
trees can only produce the one already there. Anything else that differs is
reported as a conflict and left for a human. `agents/` is gitignored; a wrong
delete there is unrecoverable.
