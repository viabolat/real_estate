# tests/

Regression guards for the non-negotiables in `CLAUDE.md`. **Stdlib `unittest`
only** — the project has no third-party dependencies and these must not add one.

```bash
python3 -m unittest discover -s tests -t .      # from the repo root
python3 -m unittest tests.test_card_isolation   # one file
```

No ffmpeg is invoked and nothing is encoded; the whole suite runs in under a
second.

## What each file guards, and why that rule exists

| File | Non-negotiable |
|---|---|
| `test_naming.py` | The `tour_`/`sample_` token survives whatever prefixes it, and no cut carries a resolution suffix. `draft.mp4` stays out of `out/`, and draft intermediates stay named apart from delivery ones. |
| `test_card_isolation.py` | The card never rides in `work_silent.mp4`; the unbranded cuts read the photos-only stitch. `vertical()` keeps two sources per family. The watermark is not gated on `branded`. |
| `test_finish_window.py` | Branding is held off wherever the card is on screen; the watermark is exempt. A no-card build is unchanged from before cards existed. |
| `test_photo_order.py` | Order lives in the filename prefix and nowhere else. The order is printed, an unauthored one warns, and `config.json` never gains an ordering key. |
| `test_status_naming.py` | `status.py` sorts every folder into agrees / drifted / unverifiable, and never sends a folder with no lead row to the scraper. Uses a synthetic phone table — `leads.csv` is PII and gitignored. `next_action()` never reports a blank music bed as the next action in any state — samples ship silent, so that check matched every listing in the ledger and hid the real one — while a missing logo stays a blocker. `orphaned_marks()` names a `contacted.csv` row whose key no scraped name produces -- the send is real but `leads.html` cannot find it, so the lead reads "open" forever and rung 5 re-offers it; a repeated key is reported once, and a missing file is no orphans rather than a crash. |
| `test_cleanup_lineage.py` | A successful delivery build clears `work_draft.mp4` + `clips_draft/` even under `--keep-work`, and never `draft.mp4`; a `--draft` run never touches the delivery lineage. |
| `test_review_cleanup.py` | `tour.py` clears `contact_sheet.png` + `draft.mp4` once the sample cuts exist, and never touches `work_draft.mp4`/`clips_draft/`/the delivery lineage -- that stays `make_tour.py`'s job alone. |
| `test_prospects.py` | `prospects/` is keyed on agent name AND phone so two agents cannot collide; a blank agent and the "no listings yet" placeholder are skipped; a removed listing disappears on the next rebuild. |
| `test_find_gaps.py` | `find_gaps.py` reuses `photos.slugify()`/`UNASSIGNED_AGENT` rather than a second copy, and never writes a `brand.json`, `config.json`, or logo file — `--open` only calls `webbrowser.open()`. `logo_status()` sorts a brand into `ok`/`available`/`near_miss`/`gap` correctly on a temp tree, including the substring and acronym near-miss cases. |
| `test_fill_gaps.py` | `fill_gaps.py` never adopts a `near_miss`, never invents an `agent_email` when `leads.csv` has none (or has a malformed one), keeps its email and claim lanes off the network, imports `find_gaps.py` rather than forking it, and refuses a non-PNG mark or a domain that does not verify as the brokerage. `logo_urls()` yields only marks the page vouches for by name or labels generically — never another company's (`netflix-logo`, `mls-logo`), never `og:image`, and never on the strength of attribute order — and `fetch_logo()` falls past a favicon-sized candidate to a real one instead of stopping at the first. |
| `test_guards.py` | The crashes and hangs from the 2026-08-24 audit: `prepare_music`'s loop terminates on a short track; a zero-dimension asset never reaches a fit box, and a broken watermark refuses while broken branding degrades; `photos/` listing survives a directory or an unreadable file; `check_pii.py` fails closed when it cannot enumerate; the hardcoded resolution gates still match `make_tour.gate_min`. |
| `test_floorplan.py` | `floorplan.py` flags a likely floor plan or site map only when a photo clears BOTH a high near-white fraction AND a high low-chroma fraction — either alone must not flag a genuinely bright room. `detect()` never touches the folder it scores, and the module's source text never contains a delete/rename/move call. |
| `test_auto_flow.py` | `ask`/`confirm`/`pick`/`number` never call `input()` under `auto=True`, and are unchanged under the default. `questions(auto=True)` leaves the logo and music unset rather than guessing. `auto_targets()` is re-derived from `out/` on every call — the resume mechanism after a manual floor-plan photo deletion. `auto_flow()`/`_auto_build_one()` never call `publish_rung` and never pass `--draft`; `--ignore-floorplan-check` and `--ignore-missing-phone-check` always need a scope and never reach `save_config()`/`save_state()`. A blank `agent_phone` halts before the contact sheet, the same way a flagged photo halts before delivery. `rebuild_reason()` refuses the `--finish-only` path when any value the outro card draws changes -- the card is baked into `work_branded.mp4` while the lower third is redrawn every pass, so a corrected phone number used to ship right in one place and wrong in the other. `CARD_TEXT_KEYS` is checked against `render_card()`'s own source. `scaffold()` never freezes a brand's blank `logo`/`music` into a new listing's `config.json` -- the empty string would shadow a path claimed onto the brand later, since `load_config()` layers config.json last -- while `brand_persistent: false` still carries. |
| `test_publish_pending.py` | `--publish-pending` walks candidates from `sample_cuts()`, not `stage()`, so a delivered-only or already-published-and-swept listing is never offered. It opens the `_branded` cut and calls `publish_rung()` per candidate — same as rung 4 — and its source contains no `--yes`/`--force` and never calls `confirm()` itself, so a batch loop can never answer its own publish prompt. |
| `test_migrate_layout.py` | `migrate_layout.py` derives its destination slug from `leads.csv` through `status.legacy_target()` and refuses a listing with no lead row rather than hand-naming it. Planning writes nothing; a move relocates every byte including `out/` and the work stitch; the only deletion is a legacy copy proven byte-identical to an already-migrated one, and a differing copy is a conflict, not a merge. Config normalisation drops only an empty value or a path with no file behind it. |
| `test_active_view.py` | `needs_attention/` links only what is neither archived (a `tour_` cut exists) nor snoozed (contacted and inside the 5-day follow-up window) — archived wins when both are true, and a listing that changes tier drops its stale link on the next rebuild. `follow_up_date()` matches `scraper/lead.py`'s own copy of the window, not a second constant. `choose_listing(show_all=False)` only reaches what's linked; `show_all=True` still reaches an archived one. `contacted.csv` carries one row per send and `contacted_at()` returns the latest, so a recorded follow-up re-arms the window instead of leaving the listing to resurface forever. `outreach_followup.txt` and `outreach_draft.txt` never render identically -- the moment they do, sending the follow-up is sending the first email again. `recorded_link()` recovers the branded URL from `links.csv` rather than re-publishing for it. |

## How they test

Three techniques, picked per rule:

- **Fresh import under a temp cwd** (`helpers.listing`). Every `[cfg]` constant in
  `make_tour.py` is a module-level global resolved from `config.json` at *import*
  time, so asking "what does this config produce" means importing the module
  again with that config in place.
- **A real `finish()` with ffmpeg stubbed** (`helpers.capture_finish`). The
  filtergraph *is* the deliverable — which overlay layer carries an `enable=`
  window is the whole of the card/branding rule — so the real function builds the
  real graph and the test reads it. No encode.
- **AST inspection of `main()`** (`test_card_isolation.py`). Which stitch each
  `finish()` call is handed, and which cut each `vertical()` layer comes from, is
  wiring rather than behaviour. A regression there produces a *valid video* with
  an agent's phone number on the MLS — no error, no crash, nothing to assert on
  at runtime short of decoding frames.

## Four things worth knowing before you edit these

**`test_the_known_config_surface_has_not_silently_grown` will fail when you add a
config key.** That is deliberate — it is the "docs do not go stale" rule made
executable. Add the key to `CLAUDE.md`, `IDEA.md`, `STEPS.md` and the module
docstring, then add it to the `documented` set in the same pass.

**`TestSlug` holds two slug functions to one apostrophe rule.**
`scraper/photos.slugify` names `agents/<brand>/<listing>/<agent>`;
`make_tour._slug` names the files inside. Both drop apostrophes rather than
separating on them, so one agent's name has one spelling. They remain separate
functions — `make_tour.py` must run from a listing folder with nothing but
ffmpeg on the path — and they differ on the empty case deliberately: the scraper
falls back to `listing`, `_slug` returns `""` so a blank `agent_name` leaves the
bare `tour_`/`sample_` names. `test_the_two_sluggers_agree_on_every_non_empty_case`
is the drift guard; the empty difference is pinned separately so nobody
"fixes" it.

**A fixture agent folder needs a `config.json`.** `tour.is_agent_dir()` and
`status._agent_dirs()` admit a subdirectory of a listing folder as an agent only if
it holds a `config.json` or a `photos/` — see
[`an-agent-folder-is-one-that-holds-a-config`](../_rules/an-agent-folder-is-one-that-holds-a-config.md).
A fixture that builds `<agent>/out/` and nothing else is not modelling anything the
walkers can see, and it went invisible to `auto_targets()`, `sample_cuts()` and
`clear_published_cuts()` the moment that check was tightened. A real folder always
has the config — `scaffold()` writes it and nothing ever deletes it — so write
`{}` into one and the fixture matches reality.

**Fixtures must not be phone-shaped or email-shaped.** `check_pii.py` scans every
publishable file for anything matching `\d{3}sep\d{3}sep\d{4}`, by shape and not
just against the real values in `leads.csv` — and it is right to, since a repo
that gets shared or opened up years later has nothing re-reviewing its history at
that moment. A fictional `555` number in a committed test still trips it. That
happened while writing `test_status_naming.py`; the fix was short synthetic ids
(`1001`, `2002`), which exercise the digits-only match identically. Run
`python3 check_pii.py` after touching fixtures, not just before a push.
