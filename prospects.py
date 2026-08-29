#!/usr/bin/env python3
"""
prospects.py

Regenerates prospects/ -- one directory per agent, holding a symlink to every
agents/<brand>/<listing> folder that agent is behind. Keyed on agent name AND
phone, not name alone, because two different agents at two different
brokerages can share a name -- the phone is what status.py's own drift check
already treats as an agent's real identity (see audit() in status.py).

Nothing here is authoritative. agents/<brand>/<listing> is still the only
place a listing actually lives, and the scrape is still the only thing
allowed to name that folder -- see the-scrape-names-the-folders.md. This is a
second VIEW of those folders, not a second copy of them: prospects/ is wiped
and rewritten from scratch on every call, the same way leads.html is
regenerated from leads.csv rather than hand-maintained. A listing moved or
removed from agents/ simply stops appearing here on the next rebuild.

status.py's own docstring is explicit that it writes nothing, so the rebuild
does not live in survey() -- tour.py's roll_up() calls it once per home-screen
render, and status.py's own __main__ calls it once for parity when status.py
runs standalone. Both pass in status.py's own slugify (loaded once, from
scraper/photos.py) rather than this module importing a third copy of it --
see two-slug-functions-one-apostrophe-rule.md.
"""

import os
import re
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
AGENTS = os.path.join(ROOT, "agents")
PROSPECTS = os.path.join(ROOT, "prospects")


def _digits(s):
    return re.sub(r"\D", "", s or "")


def rebuild(rows, slugify, agents_dir=AGENTS, dest_dir=PROSPECTS):
    """Wipe and rewrite dest_dir/ from a status.survey() rows list.

    agents_dir/dest_dir default to the real agents/ and prospects/ -- every real
    call site takes the defaults. They are parameters, not module constants read
    directly, only so a test can point both at a temp dir instead of writing into
    the actual repo.
    """
    if os.path.islink(dest_dir):
        os.unlink(dest_dir)
    elif os.path.isdir(dest_dir):
        shutil.rmtree(dest_dir)

    for brand, listing, _n, _w, _b, _a, _bc, cfg in rows:
        if listing == "-":                       # "no listings yet" placeholder
            continue
        agent = (cfg.get("agent_name") or "").strip()
        slug = slugify(agent, default="")
        if not slug:
            continue
        phone = _digits(cfg.get("agent_phone"))
        key = f"{slug}__{phone}" if phone else slug
        key_dir = os.path.join(dest_dir, key)
        os.makedirs(key_dir, exist_ok=True)
        target = os.path.join(agents_dir, brand, listing)
        link = os.path.join(key_dir, f"{brand}__{listing}")
        os.symlink(os.path.relpath(target, key_dir), link)
