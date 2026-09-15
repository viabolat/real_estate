# The pipeline

The repeating unit is a **listing**. It moves through four stages, each ending at a
gate a person passes. Nothing about the stage is recorded anywhere: every one of
them is derived from what exists on disk, which is why there is no manifest, no
marker file and no status key in `config.json`.

| # | Stage | Runs | Writes | Gate |
|---|---|---|---|---|
| 1 | Scrape | `scraper/run.py` | `leads.csv` row + `agents/<brand>/<listing>/<agent>/` | photos land, and the resolution verdict is printed before anything is worth building |
| 2 | Build | `make_tour.py --samples-only` | the three `sample_` cuts in `out/` | the operator walks the three rungs below |
| 3 | Publish | `publish.py` | the cuts to the review bucket + `outreach/links.csv` + an email draft | **the client signs off.** Nothing is sent by the machine |
| 4 | Deliver | `make_tour.py --delivery-only` | the three `tour_` cuts in `out/` | the paid deliverable leaves |

`tour.py` is the runner for all four. `status.py` is the read-only roll-up that says
which stage every listing is on. Both derive; neither records.

## The three rungs inside stage 2

Each costs what its question is worth, and the cheap one comes first:

| Rung | Command | Cost | Question |
|---|---|---|---|
| 1 | `make_tour.py --contact-sheet` | ~1s | is the order right? |
| 2 | `make_tour.py --draft` | ~1min | does the edit feel right? |
| 3 | `make_tour.py --samples-only` | ~6min | ship it to the client for review |

Rung 1 runs *before* the resolution gate on purpose — "are these in the right order"
is worth answering on photos that are not yet good enough to build with.

## How each stage's state is derived

| Question | Answered by | Never by |
|---|---|---|
| Which photos, in what order? | sorting `photos/` filenames | a manifest or an order key |
| Which dumps are still unimported? | whether `agents/<brand>/<listing>/<agent>` exists, for every `.txt`/`.json` in `scraper/dumps/` | a marker file |
| Which run is this listing on? | what is in `out/` — nothing / `sample_` / `tour_`, falling back to `outreach/links.csv` when `out/` has neither | a stage key in `config.json` |
| Has it been published? | `outreach/links.csv`, read by header name | a marker file |
| Can the stitch be reused? | `.last_build.json` vs `photo_state()` | assumption |
| Are the photos good enough? | re-measuring `photos/` on every read | a suffix in a filename |
| Does a photo look like a floor plan? | re-scoring `photos/` on every `--auto` run (`floorplan.py`) | a marker, a rename, or a `config.json` key |
| Is there a way to call the agent? | re-reading `config.json`'s `agent_phone` on every `--auto` run | a separate "has a phone" flag |

The last column is the whole design. A fact stored beside the artifact drifts out of
sync with it and is then wrong in a way nothing detects.

`status.py`'s `out/` states name the **family**, not just a count — a first run
writes three cuts on purpose, so a bare `built, 3 cuts` was indistinguishable from a
six-cut build that died halfway:

| State | Means |
|---|---|
| `ready to build` | nothing in `out/` yet |
| `sample built -- publish the review link` | run 1 done |
| `sample published -- awaiting sign-off` | a cut is on the review bucket |
| `delivered, N cuts` | a `tour_` cut exists |

*Published* is derived from `outreach/links.csv`, which `publish.py` already writes
on every confirmed upload, read **by header name** — no marker file is invented to
hold it, and a missing file means "nothing published" exactly as a missing
`leads.csv` means "nothing scraped". The soft-photo verdict rides along on every
state and is still measured from `photos/`.

## The home screen

`tour.py` opens on `status.py`'s roll-up — every listing and its one next action,
plus the scrape-naming drift report — then offers: **1** build a tour, **2** import
the dumps that have no listing folder yet, **3** publish a review link, **4** brand
settings, **5** mark leads as contacted, **6** open the dashboard. Which dumps
are pending is *derived* from
whether `agents/<brand>/<listing>/<agent>` exists; there is no marker file and no
manifest, for the same reason photo order lives in the filename prefix. `--build`
skips the screen when you already know the listing.

Each item picks from the *active* set — neither delivered nor snoozed inside its
follow-up window — except **3**, which narrows that to listings holding a
`sample_` cut in `out/` right now (`choose_listing(keep=…)`). A published,
contacted listing is active again the day its follow-up comes due, and its cuts
were cleared by the publish that confirmed, so the publish rung would have offered
listings it could do nothing with. See
[`needs-attention-is-a-view-not-a-move`](_rules/needs-attention-is-a-view-not-a-move.md).

`outreach/contacted.csv` (`marked_at,brand,listing,agent`) is a manual annotation,
never a pipeline gate: it records that a human sent the draft `publish_rung()`
already wrote, nothing more. `publish_rung()` asks once, right after a publish
succeeds, defaulting to No; item **5** walks every published, not-yet-contacted
listing and asks the same question one at a time. See
[`the-draft-is-automatic-the-send-is-not`](_rules/the-draft-is-automatic-the-send-is-not.md).

## The dashboard: the same derivation, on one page

`dashboard.py` is the browser view of everything above — read-only, bound to
`127.0.0.1`, rendered in memory and never written to a file. It re-asks the same
helpers on every request and stores nothing: `status.survey()` and
`status.audit()` for the rows and the drift, `tour.stage()`/`tour.sample_cuts()`
for what is in `out/`, `status.published()`/`contacted()`/`followup_due()` for
the ledger, `find_gaps.brand_gaps()`/`email_gaps()` for the open gaps. Each
listing lands on exactly one of seven rungs, tested highest-first:

| # | Rung | Derived from |
|---|---|---|
| 7 | Delivered | `tour.stage(d) == "delivered"` — a `tour_` cut exists |
| 6 | Follow-up due | `status.followup_due(brand, listing, agent)` |
| 5 | Contacted | `status.contacted(brand, listing, agent)` |
| 4 | Published | `status.published(brand, listing)` |
| 3 | Sample built | `tour.sample_cuts(d)` is non-empty |
| 2 | Ready to build | everything else |
| 1 | Unimported | `tour.unimported_dumps()` — a dump with no folder |

The order is the point. `followup_due()` already implies contacted, so testing 6
before 5 is what makes the rungs a partition rather than a double count — the
same `archived > snoozed > active` ordering `needs_attention/` uses, and the
same reason. There is no "signed off" rung: it has no derivable signal, and a
`tour_` cut already stands in for it.

Sample cuts play in the page; `tour_` cuts are refused at the socket with a 403
before the filesystem is touched. Nothing on this screen writes — every mutation
is still made from `tour.py`'s menu. See
[`the-dashboard-reads-it-never-writes`](_rules/the-dashboard-reads-it-never-writes.md).

## Two runs, and how the tool knows which one it is on

`--samples-only` and `--delivery-only` build one family instead of both. A bare
`make_tour.py` still builds all six, unchanged; the staging is `tour.py`'s. The two
flags are opposites and passing both **exits 2** — "build neither family" is not a
request.

| Run | What it writes | Cost |
|---|---|---|
| 1 — proofing | the three `sample_` cuts | full build, ~6 min |
| 2 — after sign-off | the three `tour_` cuts | `--finish-only`, ~1 min |

The `tour_` trio is the paid deliverable and only ever leaves after sign-off, so
building it during cold outreach spends half a six-minute encode, and ~200 MB, on a
listing that may never reply.

**The stage is derived from `out/`, and is never recorded.** Nothing built → run 1;
`sample_` cuts alone → run 2 is next; any `tour_` cut → delivered. Same rule as the
photo order: a marker file beside the artifacts drifts out of sync with them and is
then wrong in a way nothing detects. There is no stage key in `config.json` and
there must never be one.

A confirmed sample publish clears its own `sample_` cuts from `out/` once the
upload is verified against the bucket (`tour.py`'s `publish_rung()`, via
`clear_published_cuts()`) — the CDN copy is the record from then on. That makes
"nothing built" and "published, then swept" look identical to the rule above, so
`tour.stage()` and `status.py`'s `next_action()` both fall back to
`outreach/links.csv` before concluding "ready to build." See
[`a-confirmed-sample-publish-clears-its-own-cuts`](_rules/a-confirmed-sample-publish-clears-its-own-cuts.md).
`tour.py --sweep-published-samples [--yes]` applies the same cleanup
retroactively, across every listing, dry-run by default.

**`.last_build.json` gains no new rung, and that is the point.** Its top-level key
names the *intermediate lineage* — `draft` ↔ `work_draft.mp4`, `delivery` ↔
`work_silent.mp4` — not the cut family. Both runs write `delivery`, so run 2 finds
run 1's record with preset, pacing, card and `photo_state()` unchanged and takes
`--finish-only`. Change the photos or the pacing in between and `rebuild_reason()`
correctly forces a full rebuild. Two orthogonal questions, two mechanisms that
already existed: `out/` answers *which run is this*, `.last_build.json` answers
*can the stitch be reused*. Splitting the rung per family would leave run 2 with no
record and re-stitch photos that never moved.

Staging is a default, never a restriction: `build_choice()` keeps *all six now* and
a rebuild of either family reachable from every stage, because a client who has
already paid should not have to build a proof first.

A build from photos that miss the resolution gate names all six exactly the same
way. The shortfall is reported to the console — at preflight, and again once the
cuts exist — and never written into a filename. See
[`below-par-photos-build-and-are-reported`](_rules/below-par-photos-build-and-are-reported.md).

The watermark is deliberately **not** gated on the `branded` flag — it is the entire
reason a sample cut exists, so it appears on `sample_unbranded.mp4` too.


## What is stable vs. what is per-run

**Factory** — configured once, identical across runs: `global_assets/` (logos, music,
lower thirds, `viabolat.png`), `agents/<brand>/brand.json`, `outreach/template.txt`,
`_rules/`, `_reference/`, `IDEA.md`, `STEPS.md`.

**Product** — new every listing: `agents/<brand>/<listing>/<agent>/` — `photos/`,
`config.json`, `out/`, and `outreach_draft.txt`, the email draft, right beside them.

`brand.json` is the factory layer for one brokerage. It holds what every listing that
brokerage owns shares — and **no agent identity**, because a brokerage has many
agents. See
[`brand-json-carries-no-agent-identity`](_rules/brand-json-carries-no-agent-identity.md).
