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


def rebuild(rows, built_families, agents_dir=AGENTS, dest_dir=NEEDS_ATTENTION):
    """Wipe and rewrite dest_dir/ from a status.survey() rows list.

    agents_dir/dest_dir default to the real agents/ and needs_attention/ --
    every real call site takes the defaults. They are parameters, not module
    constants read directly, only so a test can point both at a temp dir
    instead of writing into the actual repo.
    """
    if os.path.islink(dest_dir):
        os.unlink(dest_dir)
    elif os.path.isdir(dest_dir):
        shutil.rmtree(dest_dir)

    for brand, listing, agent, _n, _w, _b, _a, _bc, _cfg in rows:
        if listing == "-" or agent == "-":    # placeholder rows, nothing to link
            continue
        listing_dir = os.path.join(agents_dir, brand, listing, agent)
        if tier(listing_dir, brand, listing, agent, built_families) != "active":
            continue
        link_dir = os.path.join(dest_dir, brand, listing)
        os.makedirs(link_dir, exist_ok=True)
        link = os.path.join(link_dir, agent)
        os.symlink(os.path.relpath(listing_dir, link_dir), link)
