#!/usr/bin/env python3
"""
active_view.py

Regenerates needs_attention/ -- agents/'s own tree shape (brand/listing/agent),
holding a symlink to every agents/<brand>/<listing>/<agent> folder that still
needs the operator's attention right now. Three tiers, derived entirely from
facts already recorded elsewhere -- nothing new is invented or stored:

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

Archived and snoozed listings simply get no symlink -- this is a single,
active-only view, same as the user asked for. Nothing here is authoritative:
agents/<brand>/<listing>/<agent> is still the only place a listing actually
lives, and the scrape is still the only thing allowed to name that folder --
see the-scrape-names-the-folders.md. This is a second VIEW, not a second copy:
needs_attention/ is wiped and rewritten from scratch on every call, the same
way prospects.py's rebuild() already works.

A listing the operator cannot act on without being told what is wrong also gets
a flag.txt beside its symlink -- needs_attention/<brand>/<listing>/flag.txt,
naming what is missing and the exact command that fixes it. It is written only
while the problem is still true, from status.blocker(), and is wiped with the
rest of the tree on the next rebuild. A listing with nothing blocking it gets no
file, so the presence of one is itself the signal.

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
Written by tour.py, never by hand.

It exists only while what it describes is still true -- fix the listing, run
tour.py again, and it is not written back. Deleting this file, this folder, or
all of needs_attention/ breaks nothing: the whole tree is wiped and rebuilt
from agents/ on every run.

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


def _write_flag(link_dir, agent, found):
    """Append one agent's block to this listing's flag.txt.

    Appended, not written: a listing with two agents under it shares one
    directory in the view, and the second block must not erase the first.
    rebuild() has already wiped the whole tree, so there is never a stale block
    to append to.
    """
    path = os.path.join(link_dir, FLAG_FILE)
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as f:
        if new:
            f.write(FLAG_HEADER)
        f.write(f"\n{agent}\n")
        for missing, fix in found:
            f.write(f"  missing: {missing}\n")
            f.write(f"  fix:     {fix}\n")


def rebuild(rows, built_families, agents_dir=AGENTS, dest_dir=NEEDS_ATTENTION,
            blocker=None, scraped_keys=None, extra=None):
    """Wipe and rewrite dest_dir/ from a status.survey() rows list.

    agents_dir/dest_dir default to the real agents/ and needs_attention/ --
    every real call site takes the defaults. They are parameters, not module
    constants read directly, only so a test can point both at a temp dir
    instead of writing into the actual repo.

    blocker: status.blocker, injected for the same reason built_families is --
    see the module docstring. Omit it and the symlinks are written exactly as
    before, with no flag.txt anywhere; a listing is never hidden for the lack
    of one.

    scraped_keys: status.survey()'s `known`, so blocker() can tell a folder
    that lost its config.json from one that never had a lead row behind it.

    extra: {(brand, listing, agent): [(missing, fix), ...]} for a finding this
    view cannot derive on its own. --auto passes its floor-plan hits here: that
    check costs an ffmpeg decode per photo (~45s across agents/), far too much
    for a rebuild that runs on every home-screen render, but --auto has already
    paid for it on the listing it just walked.
    """
    if os.path.islink(dest_dir):
        os.unlink(dest_dir)
    elif os.path.isdir(dest_dir):
        shutil.rmtree(dest_dir)

    for brand, listing, agent, n, _w, best, _a, bcfg, cfg in rows:
        if listing == "-" or agent == "-":    # placeholder rows, nothing to link
            continue
        listing_dir = os.path.join(agents_dir, brand, listing, agent)
        if tier(listing_dir, brand, listing, agent, built_families) != "active":
            continue
        link_dir = os.path.join(dest_dir, brand, listing)
        os.makedirs(link_dir, exist_ok=True)
        link = os.path.join(link_dir, agent)
        os.symlink(os.path.relpath(listing_dir, link_dir), link)

        found = list((extra or {}).get((brand, listing, agent), ()))
        if blocker:
            stuck = blocker(listing_dir, cfg, n, best,
                            (brand, listing, agent) in (scraped_keys or ()),
                            bcfg)
            if stuck:
                found.insert(0, flag_text(*stuck, brand=brand, listing=listing,
                                          agent=agent))
        if found:
            _write_flag(link_dir, agent, found)
