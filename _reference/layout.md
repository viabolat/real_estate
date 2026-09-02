---
name: layout
type: reference
---

# Layout — where things live, and what names them

The tree, the naming authority, and the six cuts a build produces. Rules that
constrain any of it live in [`../_rules/`](../_rules/CONTEXT.md); this file is the
shape, not the law.

```
agents/<brand>/brand.json           per-brand defaults — tour.py ONLY, see below
agents/<brand>/<listing>/<agent>/   photos/, config.json, out/, outreach_draft.txt, outreach_followup.txt  — cwd for a build
prospects/<agent>__<phone>/         agents/ viewed by agent instead of brand — symlinks, gitignored
needs_attention/<brand>/<listing>/  agents/ filtered to what's not archived or snoozed — symlinks, gitignored
global_assets/logos/                shared branding, referenced by config.json
global_assets/music/
global_assets/lower_thirds/
scraper/                            Zillow dump -> leads.csv + a scaffolded listing
publish.py                          sample_ cuts -> the public review bucket. NEVER tour_
status.py                           read-only: every listing and its one next action.
dashboard.py                        the same rows in a browser -- 127.0.0.1 only,
                                    rendered in memory, adds no folder and writes
                                    nothing. sample_ cuts stream; tour_ is 403
                                    Names the run each is on -- see the two-run rule
floorplan.py                        flags a likely floor plan/site map photo -- never
                                    reorders or deletes. Called from tour.py --auto
hooks/pre-push                      runs check_pii.py. Arm per clone -- see Running it
tests/                              stdlib unittest guards for the non-negotiables below
```

`<brand>`, `<listing>` and `<agent>` are **not named by hand.** All three are
slugified straight from the scrape — `broker_name`, `address` and `agent_name` in
`scraper/leads.csv` — by `scraper/photos.py`'s `target_for()`, so the folder and the
lead row can never disagree. The slug drops apostrophes rather than turning them into
separators, so `Gibson Sotheby's International Realty` is
`gibson_sothebys_international_realty`, not `gibson_sotheby_s_...`. A blank
`agentName` (Zillow does not always expose one, especially for a team listing) gets
the explicit placeholder `unassigned_agent` rather than a silent empty path segment
— see [`a-blank-agent-name-gets-a-placeholder-slug`](../_rules/a-blank-agent-name-gets-a-placeholder-slug.md).
`status.py` re-checks every folder against `leads.csv` on each run — matched on
agent phone, since address text formatting varies and a phone number does not — and
prints the `mv` for anything that has drifted, agent included: a folder still sitting
on `unassigned_agent` once the phone resolves to a lead row with a real name drifts
like any other mismatch.

One consequence, accepted deliberately: `Coldwell Banker Realty - Boston` and
`Coldwell Banker Realty - Waltham` are two brand folders with two `brand.json` files,
because that is what the scrape says. Set the logo twice rather than maintaining an
alias table, which is a second naming authority and would drift.

`brand.json` holds what is identical across every listing a brokerage owns — logo,
music, pacing, lower-third timing, the card mode. It holds **no agent identity.**
`leads.csv` already lists two agents under `Coldwell Banker Realty - Boston` and two
under `Gibson Sotheby's International Realty`, so a brand-level `agent_name` /
`agent_phone` puts one agent's phone number on another agent's video. Those two keys
live in the listing's `config.json`, written from the scrape, and nowhere else.
**`make_tour.py` never reads it.** `tour.py`
resolves `DEFAULTS → brand.json → listing config.json` and writes the effective
values into the listing's `config.json`, which stays the single source of truth for
a build. That keeps the script's contract intact — read the working directory, know
nothing about the `agents/<brand>/<listing>` layout — and keeps `config.json` an
accurate record of what produced a delivered video months later. A new listing
inherits at creation — but only values the brand actually *has*: a key the brand
leaves blank is left out of the listing config entirely, so a logo or music bed
set on the brand later still reaches it. Changing a brand default does **not**
otherwise retroactively alter existing listings, which is what the explicit
"Re-apply brand defaults" action
under **Brand settings** on `tour.py`'s home screen is for. It shows every key it
would change, per listing, and asks before writing — it is the one action in the
tool that edits files the operator is not looking at.


## What a listing folder holds

`agents/<brand>/<listing>/<agent>/` is the working directory for a build, and
everything under `agents/` is gitignored — it holds client photos and, in
`config.json`, an agent's name and phone number. Nothing in it travels to another
clone, which is why no contract file lives there: it would be invisible the moment
the repo was cloned. Company, address and agent sit in one folder on purpose — the
photos, the build, and the cold-email draft that follows from it are one deliverable,
not three things scattered across the repo.

```
agents/<brand>/brand.json            the factory layer for one brokerage. NO agent identity
agents/<brand>/<listing>/<agent>/
   photos/                           numbered in tour order; the prefix IS the order
   config.json                       the per-listing schema -- the single record of a build
   out/                              the six cuts. Its contents ARE the build stage
   outreach_draft.txt                the cold-email draft, written by publish.py
   outreach_followup.txt             the follow-up draft, written by rung 5 once due
   .last_build.json                  can the stitch be reused? Not which family
   .build.lock                       held by a running build, O_EXCL, released via atexit
   draft.mp4                         only from --draft. Deliberately NOT in out/
```

### How the walkers recognise the agent level

The `<agent>/` level is not identified by position alone. `_dirs()` at the listing
level cannot tell `<agent>/` from the `photos/`, `clips/`, `clips_draft/`, `out/`
and `work_text/` a build writes *inside* one, so `tour.is_agent_dir()` and
`status._agent_dirs()` admit a subdirectory only if it **holds a `config.json` or a
`photos/`** — the two things `scaffold()` always writes and no intermediate has.

The first version of the code put `config.json` and `photos/` directly under
`agents/<brand>/<listing>/`. A folder left in that shape reads as a listing whose
agent is named `photos`, and `--auto`, `status.py`, `needs_attention/` and
`find_gaps.py` each invented something different in its place. `status.py` now names
it — `legacy layout -- migrate to <agent>/` — and `python3 migrate_layout.py` moves
it with `os.rename`, deriving the destination from `leads.csv` like every other
folder name. See
[`an-agent-folder-is-one-that-holds-a-config`](../_rules/an-agent-folder-is-one-that-holds-a-config.md).

## `prospects/` — the same listings, viewed by agent

`agents/<brand>/<listing>/<agent>` is grouped by brokerage first, which cannot
answer "everything tied to one agent" — a brand.json holds no agent identity
(above), and one brokerage can have several agents. `prospects/` is that other
view: one directory per agent, holding a symlink to every listing folder that
agent is behind.

```
prospects/<agent_slug>__<phone_digits>/<brand>__<listing>__<agent>   -> ../../agents/<brand>/<listing>/<agent>
```

Keyed on slugified `agent_name` **and** the digits of `agent_phone`, not name alone
— `leads.csv` already has two agents named the same at different brokerages, and
name-only would merge them. That index key is a different identity than the
`<agent>` path segment: a folder can still sit on the `unassigned_agent` placeholder
while `config.json` already carries the real `agent_name`/`agent_phone`, so the
symlink can legitimately point at a folder one step ahead of its own name — the
correction path is `status.py`'s drift audit, not a rename here. Built and rebuilt
by `prospects.py`, called from `tour.py`'s home screen and from `status.py`'s own
`__main__` — never hand-maintained, the same way `leads.html` is regenerated from
`leads.csv` rather than patched. Wiped and rewritten from scratch on every call: a
listing removed from `agents/` just stops appearing here, no separate cleanup
needed. It is gitignored like `agents/` itself — the directory names carry an
agent's name and phone number, which is exactly the PII `agents/` is already
gitignored to keep off the repo.

## `needs_attention/` — `agents/`, filtered to what still needs a look

`agents/` holds every listing forever, active and delivered side by side, which is
exactly what makes it cluttered as more agents are added. `needs_attention/` is a
second view over the same tree, filtered by [`needs-attention-is-a-view-not-a-move`](../_rules/needs-attention-is-a-view-not-a-move.md)'s
three-tier rule, keeping the `agents/` tree shape rather than `prospects/`'s
flattened agent-keyed one:

```
needs_attention/<brand>/<listing>/<agent>   -> ../../../agents/<brand>/<listing>/<agent>
```

Only **active** listings get a symlink here — not yet contacted, or contacted and
past the follow-up window, and with no `tour_` cut yet. A listing just marked
contacted, or already delivered (a `tour_` cut exists), simply has no entry until
it becomes active again on its own; nothing is ever moved out of `agents/` to put
it here or take it away. Built and rebuilt by `active_view.py`, called from the
same `tour.py` roll-up call site as `prospects.rebuild()`, and read by `tour.py`'s
own picker by default — `--show-all` reaches `agents/` directly, the only way in
during a snooze window a client responds early. Gitignored and excluded from
`.vercelignore` exactly like `prospects/`, for the same reason: it is a second
path to the PII `agents/` already holds, not a new category of data.

## What a build reads

Reads from the **working directory**, which is normally a listing folder:

| Path | Required | Purpose |
|---|---|---|
| `photos/` | yes | Numbered in tour order; the prefix *is* the order |
| `music.mp3` | no | Licensed track. `--no-music` to skip. |
| `lower_third.png` | no | Agent + listing info |
| `logo.png` | no | Brokerage mark, top-left |
| `viabolat.png` | no | Proofing watermark, centered, `sample_` cuts only |
| `config.json` | no | Per-listing overrides — timing, pacing, asset paths |

Any asset path that does not resolve against the working directory is retried
beside `make_tour.py`, so the shared library and `viabolat.png` keep working from
any listing folder. All are read fresh every build — swapping any of them needs
only `--finish-only`.

## What a build writes

Outputs **six** cuts to `out/`, in two families — but not in one run. `tour.py`
builds the `sample_` trio first and the `tour_` trio only after the client signs
off; see the two-run rule below. Every name is prefixed with the
agent's own name — `output_prefix`, or `agent_name` slugified when that is blank —
because six listings all producing a `tour_branded.mp4` collide the moment the
files leave `out/` for a downloads folder or an email thread. Both blank leaves the
bare names, so a pre-existing folder built from the CLI is unchanged. The slug is
the folder rule applied to a filename — apostrophes drop rather than separate, so
`Sean O'Brien` signs `sean_obrien_tour_branded.mp4` inside `sean_obrien/` and not
`sean_o_brien_...`:

**Delivery** — clean, what the client gets on sign-off:
- `<agent>_tour_branded.mp4`   — card + lower third + top-left logo, for social /
  your own channels. Longer than the unbranded cut by the card(s) it carries
- `<agent>_tour_unbranded.mp4` — no branding, MLS/IDX-safe
- `<agent>_tour_vertical.mp4`  — 9:16 portrait, branded centre, clean blurred bands

**Sample** — identical edit plus a centered proofing watermark (`viabolat.png`),
what the client reviews before paying:
- `<agent>_sample_branded.mp4`
- `<agent>_sample_unbranded.mp4`
- `<agent>_sample_vertical.mp4`

Plus one more, only from `--draft`, and deliberately outside `out/`:

- `draft.mp4` — 720p at a fast x264 preset, branded **and** watermarked, one cut,
  written to the listing root. A review rung, never a deliverable. Its
  intermediates (`work_draft.mp4`, `clips_draft/`) are named apart from the
  delivery ones so a draft-quality stitch can never feed a delivery build.

See [`draft-mp4-is-not-a-deliverable`](../_rules/draft-mp4-is-not-a-deliverable.md).

## The card, and why a build stitches twice

The intro/outro card is drawn by ffmpeg from `config.json` — logo (or brokerage type
when there is no logo) over address, agent and phone. Nothing is exported from Canva
any more; the lower third is drawn the same way from the same three fields, and a
`lower_third.png` that exists still wins, so a hand-authored plate stays available
for a listing that earns it.

The card is branding, so it must never reach the MLS cut. That is why a build with a
card stitches twice:

| Stitch | Contents | Feeds |
|---|---|---|
| `work_silent.mp4` | photos only | `tour_unbranded`, `sample_unbranded` |
| `work_branded.mp4` | `[intro]` + photos + `[outro]` | `tour_branded`, `sample_branded`, `draft.mp4` |

With no card configured the second stitch is skipped and both read the same file — a
no-card build is byte-identical to one from before cards existed, verified against
`0722f52`. The cost when there *is* a card is one extra stitch, ~26s on a 6-minute
build.
