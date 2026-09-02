#!/usr/bin/env python3
"""
find_gaps.py

Reports two gaps the rest of the pipeline can't fill on its own: a brokerage
whose brand.json has no resolvable logo, and a listing whose config.json still
has a blank agent_email. Read-only -- it never writes a brand.json, a
config.json, or a logo file, and it never touches leads.csv. See
_rules/find-gaps-detects-and-reports-it-never-writes.md.

Reuses scraper/photos.py's slugify()/UNASSIGNED_AGENT (flat import, the same
pattern photos.py already uses for lead.py) so a leads.csv row's
(broker_name, address, agent_name) maps to the exact same agents/<brand>/
<listing>/<agent>/ key target_for() would derive from the raw dump --
target_for() itself can't be reused here since it parses dump text, not a
CSV row.

A missing brand logo sorts into four buckets:
  ok         brand.json's own logo already resolves
  available  nothing set, but global_assets/logos/<brand>.png already exists
             unclaimed -- point brand.json at it, no fetch needed
  near_miss  nothing exact, but a plausible existing file (substring or
             acronym match, or a close difflib ratio) -- worth a human eyeball,
             never auto-adopted
  gap        nothing exact or plausible -- an actual fetch target

--open/--open-all only call webbrowser.open() on a real gap's search results --
they open tabs, they do not fetch or download anything. The actual logo file
landing on disk, and the actual config.json.agent_email write, both happen in
a live Claude Code + Chrome session under the workflow in STEPS.md.

Usage:
    python3 find_gaps.py
    python3 find_gaps.py --json
    python3 find_gaps.py --open [--open-all]
"""

import argparse
import csv
import difflib
import json
import os
import sys
import urllib.parse
import webbrowser

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
from photos import slugify, UNASSIGNED_AGENT

ROOT = os.path.dirname(SCRIPT_DIR)
LEADS_CSV = os.path.join(SCRIPT_DIR, "leads.csv")
AGENTS_DIR = os.path.join(ROOT, "agents")
LOGOS_DIR = os.path.join(ROOT, "global_assets", "logos")

# reason: a threshold below this starts matching brokerages that just happen
# to share a few letters (see the "compass" / "corcoran" near-collision this
# was tuned against). Above it, the substring and acronym checks below still
# catch the real near-misses (coldwell_banker.png, tcc.png) outright, since
# both are forced to at least this score.
NEAR_MISS_RATIO = 0.6


def load_leads(csv_path=LEADS_CSV):
    """Every row in leads.csv, or [] if it does not exist yet (nothing scraped)."""
    if not os.path.isfile(csv_path):
        return []
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def row_key(row):
    """(brand, listing, agent) slugs for one leads.csv row -- the same triple
    photos.py's target_for() derives from the raw dump, reproduced here from
    the CSV columns since target_for() itself needs dump text to run."""
    return (slugify(row.get("broker_name"), "unknown_brokerage"),
            slugify(row.get("address")),
            slugify(row.get("agent_name"), UNASSIGNED_AGENT))


def _json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _acronym(slug):
    """First letter of each word in a >=2-word slug, else None.

    reason: a single-word brand (e.g. "compass") has a one-letter "acronym"
    that would spuriously match any single-letter-prefixed file; requiring at
    least two words is what makes tcc.png / the_collaborative_companies a
    real signal instead of noise.
    """
    parts = [p for p in slug.split("_") if p]
    if len(parts) < 2:
        return None
    return "".join(p[0] for p in parts)


def _logo_candidate(brand_slug, logos_dir=LOGOS_DIR):
    """(status, filename_or_None) for what's sitting in logos_dir -- shared by
    logo_status() and brand_gaps() so the two can never name a different file
    for the same brand."""
    exact = f"{brand_slug}.png"
    if os.path.isfile(os.path.join(logos_dir, exact)):
        return "available", exact
    if not os.path.isdir(logos_dir):
        return "gap", None

    acro = _acronym(brand_slug)
    best_name, best_score = None, 0.0
    for name in sorted(os.listdir(logos_dir)):
        if not name.lower().endswith(".png"):
            continue
        stem = name[:-4].lower()
        if stem == brand_slug:
            continue
        score = difflib.SequenceMatcher(None, stem, brand_slug).ratio()
        # reason: a stem under 3 chars (e.g. a single-letter file) is a
        # substring of nearly anything -- "c.png" inside "compass" -- so the
        # substring boost only applies once it is long enough to mean
        # something.
        if len(stem) >= 3 and (stem in brand_slug or brand_slug in stem):
            score = max(score, 0.75)
        if acro and stem == acro:
            score = max(score, 0.75)
        if score > best_score:
            best_score, best_name = score, name
    if best_name and best_score >= NEAR_MISS_RATIO:
        return "near_miss", best_name
    return "gap", None


def logo_status(brand_slug, agents_dir=AGENTS_DIR, logos_dir=LOGOS_DIR, repo_root=ROOT):
    """"ok" / "available" / "near_miss" / "gap" for one brand slug's logo."""
    bcfg = _json(os.path.join(agents_dir, brand_slug, "brand.json"))
    logo = (bcfg.get("logo") or "").strip()
    if logo and os.path.exists(os.path.join(repo_root, logo)):
        return "ok"
    return _logo_candidate(brand_slug, logos_dir)[0]


def brand_gaps(rows, agents_dir=AGENTS_DIR, logos_dir=LOGOS_DIR, repo_root=ROOT):
    """One row per distinct brand slug in leads.csv with an agents/<brand>/
    brand.json on disk, whose logo_status() isn't already "ok"."""
    seen = {}
    for row in rows:
        brand, _listing, _agent = row_key(row)
        if brand in seen:
            continue
        if not os.path.isfile(os.path.join(agents_dir, brand, "brand.json")):
            continue
        status = logo_status(brand, agents_dir, logos_dir, repo_root)
        if status == "ok":
            seen[brand] = None
            continue
        _, candidate = _logo_candidate(brand, logos_dir)
        seen[brand] = {
            "brand": brand,
            "broker_name": row.get("broker_name") or "",
            "status": status,
            "candidate": os.path.join("global_assets", "logos", candidate) if candidate else None,
        }
    return [g for g in seen.values() if g]


def email_gaps(rows, agents_dir=AGENTS_DIR):
    """One row per listing whose config.json exists and has a blank
    agent_email. A lead row with no listing folder yet is skipped -- that is
    photos.py's job to scaffold, not this script's to report."""
    gaps = []
    for row in rows:
        brand, listing, agent = row_key(row)
        cfg_path = os.path.join(agents_dir, brand, listing, agent, "config.json")
        if not os.path.isfile(cfg_path):
            continue
        cfg = _json(cfg_path)
        if (cfg.get("agent_email") or "").strip():
            continue
        gaps.append({
            "brand": brand, "listing": listing, "agent": agent,
            "agent_name": row.get("agent_name") or "",
            "broker_name": row.get("broker_name") or "",
            "agent_phone": row.get("agent_phone") or "",
            "config_path": cfg_path,
        })
    return gaps


def open_tabs(logo_gaps, mail_gaps, cap=5, open_all=False):
    """webbrowser.open() one search tab per real gap -- an image search for a
    logo "gap" (never "available"/"near_miss", which need an eyeball, not a
    fetch), a general search for an email gap. Opens tabs; fetches or
    downloads nothing itself."""
    urls = []
    for g in logo_gaps:
        if g["status"] != "gap":
            continue
        q = urllib.parse.quote(f"{g['broker_name']} logo png")
        urls.append(f"https://www.google.com/search?tbm=isch&q={q}")
    for g in mail_gaps:
        q = urllib.parse.quote(f"{g['agent_name']} {g['broker_name']} email real estate agent")
        urls.append(f"https://www.google.com/search?q={q}")

    if not open_all:
        urls = urls[:cap]
    for u in urls:
        webbrowser.open(u)
    return urls


def print_table(logo_gaps, mail_gaps, out=print):
    if not logo_gaps:
        out("No brand logo gaps.")
    else:
        w = max(len(g["brand"]) for g in logo_gaps)
        out(f"\n{len(logo_gaps)} brokerage logo gap(s):")
        out(f"{'BRAND'.ljust(w)}  STATUS      CANDIDATE")
        for g in logo_gaps:
            out(f"{g['brand'].ljust(w)}  {g['status'].ljust(10)}  {g['candidate'] or ''}")

    if not mail_gaps:
        out("\nNo agent_email gaps.")
    else:
        w = max(len(f"{g['brand']}/{g['listing']}/{g['agent']}") for g in mail_gaps)
        out(f"\n{len(mail_gaps)} agent_email gap(s):")
        out(f"{'BROKERAGE / LISTING / AGENT'.ljust(w)}  AGENT NAME            PHONE")
        for g in mail_gaps:
            name = f"{g['brand']}/{g['listing']}/{g['agent']}".ljust(w)
            out(f"{name}  {g['agent_name'].ljust(20)}  {g['agent_phone']}")


def main():
    ap = argparse.ArgumentParser(
        description="Report brand-logo and agent_email gaps. Read-only -- writes nothing.")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--open", action="store_true", help="open up to 5 search tabs for the gaps")
    ap.add_argument("--open-all", action="store_true", help="with --open, no cap")
    args = ap.parse_args()

    rows = load_leads()
    logo_gaps = brand_gaps(rows)
    mail_gaps = email_gaps(rows)

    if args.json:
        print(json.dumps({"logo_gaps": logo_gaps, "email_gaps": mail_gaps}, indent=2))
    else:
        print_table(logo_gaps, mail_gaps)

    if args.open or args.open_all:
        opened = open_tabs(logo_gaps, mail_gaps, open_all=args.open_all)
        print(f"\nOpened {len(opened)} tab(s). Nothing downloaded or written.")

    sys.exit(0)


if __name__ == "__main__":
    main()
