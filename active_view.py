#!/usr/bin/env python3
"""
active_view.py

Regenerates needs_attention/ -- agents/'s own tree shape (brand/listing/agent),
holding one flag.txt for every listing that needs the operator's attention right
now and cannot be built as it stands. A warning light: it is there because
something is wrong, it goes out when that thing is fixed, and it comes back on
the next run if it was not. Three tiers, derived entirely from facts already
recorded elsewhere -- nothing new is invented or stored:

  * archived -- a tour_ cut already exists (built_families()["tour"] > 0).
    "Delivered" stands in for "purchased and paid": no separate payment
    tracking exists in this repo, and in the documented workflow a tour_ cut
    is only ever built after client sign-off (WALKTHROUGH.md Step 13).
  * snoozed -- the lead has been marked contacted (outreach/contacted.csv,
    via publish.contacted_at()) and its follow-up date (publish.follow_up_date(),
    the exact FOLLOW_UP_DAYS window scraper/lead.py's own leads.html column
    already computes) has not arrived yet.
  * active -- everything else. Not yet built, not yet published, published but
    not yet marked contacted, or contacted and past its follow-up date.

Archived and snoozed listings are never flagged, and neither is an active
listing with nothing blocking it: a folder existing under needs_attention/ and
a flag.txt existing inside it are the same fact. Empty tree, nothing is stuck.

The file names what is missing and the exact command that fixes it, from
status.blocker(). The fix itself is made in agents/<brand>/<listing>/<agent>/,
never here -- this tree holds text files and nothing else, so there is nothing
to edit through and no way to mistake the view for the listing. Nothing here is
authoritative: agents/ is still the only place a listing actually lives, and the
scrape is still the only thing allowed to name that folder -- see
the-scrape-names-the-folders.md. This is a second VIEW, not a second copy:
needs_attention/ is wiped and rewritten from scratch on every call, the same
way prospects.py's rebuild() already works, so deleting any part of it costs
nothing.

rebuild() returns the active keys rather than leaving the caller to walk the
tree for them. reason: the tree no longer answers "what can I pick to build?"
-- it lists only what is BLOCKED, which is the opposite set. tour.py's picker
used to read this directory for its menu; it takes the return value now, so a
directory the operator is invited to delete has no reader but their eyes.

tour.py's roll_up() calls this once per home-screen render, passing its own
status.built_families (loaded via load_status(), never imported here directly
-- status.py loads the scraper at module scope, which must stay optional the
same way prospects.rebuild()'s slugify is injected rather than imported).
choose_listing() calls it again on demand so a --build run that skipped the
home screen still sees a current view.
"""

import datetime
import os
import shutil

import publish

ROOT = os.path.dirname(os.path.abspath(__file__))
AGENTS = os.path.join(ROOT, "agents")
NEEDS_ATTENTION = os.path.join(ROOT, "needs_attention")


def tier(listing_dir, brand, listing, agent, built_families):
    """"archived" | "snoozed" | "active" for one listing.

    built_families: status.built_families, injected by the caller -- see the
    module docstring for why this is never imported here directly.
    """
    counts, _total = built_families(listing_dir)
    if counts["tour"]:
        return "archived"
    marked_at = publish.contacted_at(brand, listing, agent)
    if marked_at:
        due = publish.follow_up_date(marked_at)
        if due and due > _today():
            return "snoozed"
    return "active"


def _today():
    return datetime.date.today().isoformat()


FLAG_FILE = "flag.txt"

FLAG_HEADER = """\
This listing cannot be built as it stands. Written by tour.py, never by hand.

Make the fix in agents/<brand>/<listing>/<agent>/ -- this folder holds this file
and nothing else. Then run tour.py again: the whole tree is wiped and rebuilt
from agents/, so a fixed listing does not come back and an unfixed one does.
Deleting this file, this folder, or all of needs_attention/ breaks nothing.

Not checked here: whether a photo looks like a floor plan. That costs an ffmpeg
decode per photo, far too slow for a view this often rebuilt -- `python3
tour.py --auto` runs it and reports it there.
"""


def flag_text(key, detail, brand, listing, agent):
    """(missing, fix) -- one status.blocker() key rendered for a human.

    reason: the key is status.py's, so the two files cannot disagree about WHAT
    is wrong. The wording is this file's, because the audience is different: a
    table column has one line to say "logo blank/missing", a file the operator
    opened on purpose can name the exact path to create and the exact command
    to run next.
    """
    rerun = f"python3 tour.py --auto {brand}/{listing}"
    if key == "no_photos":
        return ("photos/ is empty -- nothing was downloaded for this listing",
                "re-save the Zillow dump into scraper/dumps/, then: "
                "python3 scraper/run.py")
    if key == "too_small":
        return (f"the photos are only {detail.get('best')}px on the long edge "
                f"-- too small to build from",
                "re-capture the listing at full size, then: "
                "python3 scraper/run.py")
    if key == "no_config":
        return ("no config.json in this folder",
                "python3 scraper/photos.py <this listing's dump>")
    if key == "no_logo":
        logo = f"global_assets/logos/{detail.get('brand', brand)}.png"
        return (f"no logo -- brand.json sets none and {logo} does not exist",
                f"add {logo}, then: {rerun}")
    if key == "no_watermark":
        return ("the watermark path does not resolve -- the sample build will "
                "refuse to run",
                'point "watermark" in brand.json at a file that exists under '
                "global_assets/logos/")
    if key == "no_phone":
        return (f"no agent_phone -- the card and lower third would show no way "
                f"to reach {detail.get('agent', 'this agent')}",
                f'add "agent_phone" to agents/{brand}/{listing}/{agent}/'
                f"config.json, then: {rerun}")
    return (key, rerun)


def _write_flag(flag_dir, found):
    """This agent's whole presence in the view: one folder, one file.

    reason: it used to append, because a listing's two agents shared one
    flag.txt beside their two symlinks. There are no symlinks now and the
    agent has a folder of its own, so the file is written once and whole --
    and creating the folder here, and only here, is what makes "a folder
    exists" and "something is blocking it" the same statement.
    """
    os.makedirs(flag_dir, exist_ok=True)
    with open(os.path.join(flag_dir, FLAG_FILE), "w", encoding="utf-8") as f:
        f.write(FLAG_HEADER)
        for missing, fix in found:
            f.write(f"\n  missing: {missing}\n")
            f.write(f"  fix:     {fix}\n")


def rebuild(rows, built_families, agents_dir=AGENTS, dest_dir=NEEDS_ATTENTION,
            blocker=None, scraped_keys=None, extra=None):
    """Wipe and rewrite dest_dir/ from a status.survey() rows list.

    Returns [(brand, listing, agent), ...] for every ACTIVE listing -- which is
    deliberately NOT what lands on disk. The tree holds the blocked subset; the
    return value holds everything still in play, blocked or not, because that is
    what tour.py's picker needs and it can no longer get it by walking the tree.

    agents_dir/dest_dir default to the real agents/ and needs_attention/ --
    every real call site takes the defaults. They are parameters, not module
    constants read directly, only so a test can point both at a temp dir
    instead of writing into the actual repo.

    blocker: status.blocker, injected for the same reason built_families is --
    see the module docstring. Omit it and nothing is written at all: the return
    value is still correct, so the picker still works, and the tree is simply
    empty rather than wrong.

    scraped_keys: status.survey()'s `known`, so blocker() can tell a folder
    that lost its config.json from one that never had a lead row behind it.

    extra: {(brand, listing, agent): [(missing, fix), ...]} for a finding this
    view cannot derive on its own. --auto passes its floor-plan hits here: that
    check costs an ffmpeg decode per photo (~45s across agents/), far too much
    for a rebuild that runs on every home-screen render, but --auto has already
    paid for it on the listing it just walked. FLAG_HEADER says so in the file,
    so a flag.txt never implies a floor-plan check that did not happen.
    """
    if os.path.islink(dest_dir):
        os.unlink(dest_dir)
    elif os.path.isdir(dest_dir):
        shutil.rmtree(dest_dir)

    active = []
    for brand, listing, agent, n, _w, best, _a, bcfg, cfg in rows:
        if listing == "-" or agent == "-":    # placeholder rows, nothing to flag
            continue
        listing_dir = os.path.join(agents_dir, brand, listing, agent)
        if tier(listing_dir, brand, listing, agent, built_families) != "active":
            continue
        active.append((brand, listing, agent))

        found = list((extra or {}).get((brand, listing, agent), ()))
        if blocker:
            stuck = blocker(listing_dir, cfg, n, best,
                            (brand, listing, agent) in (scraped_keys or ()),
                            bcfg)
            if stuck:
                found.insert(0, flag_text(*stuck, brand=brand, listing=listing,
                                          agent=agent))
        if found:
            _write_flag(os.path.join(dest_dir, brand, listing, agent), found)
    return active
