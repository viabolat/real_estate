---
name: needs-attention-is-a-view-not-a-move
area: naming
type: non-negotiable
guarded_by:
  - tests/test_active_view.py
source: PROGRESS.md@this-change — "a time-aware needs_attention/ view over
  agents/, filtered by tour_ cuts and the follow-up window", 2026-09-01
---

# `needs_attention/` is a view, not a move

`agents/<brand>/<listing>/<agent>` stays the one naming authority — see
[`the-scrape-names-the-folders`](the-scrape-names-the-folders.md). `needs_attention/`
never holds a real folder, only symlinks into it, and `active_view.rebuild()`
wipes and rewrites the whole tree from a fresh `status.survey()` on every call,
the same way [`prospects.py`](../prospects.py) already does for its own view keyed
by agent. Nothing is ever moved out of `agents/`, and no listing's tier is ever
recorded anywhere — it is derived fresh, every time, from facts that already
exist elsewhere:

- **archived** — `status.built_families(listing_dir)["tour"] > 0`. A `tour_` cut
  stands in for "delivered and paid": there is no separate payment tracking in
  this repo, and by [`never-cross-the-sample-tour-boundary`](never-cross-the-sample-tour-boundary.md)
  a `tour_` cut is only ever built after sign-off.
- **snoozed** — `publish.contacted_at(brand, listing, agent)` has a row, and
  `publish.follow_up_date(marked_at)` — the exact `FOLLOW_UP_DAYS` window
  `scraper/lead.py`'s own `leads.html` column already computes — has not
  arrived yet.
- **active** — everything else, including a published listing that has not yet
  been marked contacted. Only active listings get a symlink.

`flag.txt` is part of the view, not an exception to it. A listing that cannot be
built as it sits gets a `needs_attention/<brand>/<listing>/flag.txt` naming what
is missing and the command that fixes it, rendered from `status.blocker()` —
the same ladder `next_action()`'s first rungs read. It records nothing: it is
written only while the blocker is still true, it is wiped with the tree on every
rebuild, and no reader ever consults it. Deleting it by hand is a no-op, which
is the test of whether a file in a view is a view or a record. The one thing it
carries that is not re-derived on the spot is `--auto`'s floor-plan finding,
handed in through `rebuild(extra=...)` because that check costs an ffmpeg decode
per photo — and a rebuild that runs on every home-screen render cannot pay it.
The value still is not stored anywhere: skip the `--auto` run and the line is
simply absent, never stale.

Do not add a second directory for "archived" or "snoozed" state, and do not add
a marker file, a status field in `config.json`, or any other record of which
tier a listing is in. That is the same failure the folder-naming rule above
already guards against, one level up: a second place holding a fact that
`agents/`, `out/` and `outreach/contacted.csv` already hold means the two can
drift, and nothing would notice until a listing is hidden or shown wrong.

`tour.py`'s `choose_listing()` defaults to reading from `needs_attention/`
rather than `agents/` directly, and rebuilds it fresh on every call so a
`--build` run that skipped the home screen still sees a current view. It falls
back to `agents/` whenever the view can't be built, or is empty while `agents/`
is not — a picker must never look like "nothing here yet" just because
everything is snoozed or archived. `--show-all` skips straight to that
fallback. This is also the one gap this design accepts: a client can respond
and need a rebuild *during* the snooze window, and the default picker still
will not offer that listing again until its follow-up date arrives on its own
or `--show-all` is used to reach it early — see `STEPS.md`.

`needs_attention/` is gitignored and excluded from `.vercelignore` exactly like
`prospects/` — it is a second path to the same PII agents/ already holds, not a
new category of data.
