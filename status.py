#!/usr/bin/env python3
"""
status.py

One read-only view of every listing under agents/, and the single next action
each one is waiting on. survey() itself writes, encodes, and downloads nothing.
Running this file does one thing beyond that: it rebuilds prospects/, a view of
the same rows keyed by agent instead of brokerage -- see prospects.py.

reason: the pipeline now spans a scrape, a per-brokerage brand.json, a per-listing
config.json, a photo set with its own resolution verdict, and six output cuts. Any
one of those can be the thing holding a listing up, and finding out which meant
opening three files per listing by hand. With one brokerage that is fine; the
lead list already covers five.

It also re-checks every folder name against scraper/leads.csv -- the scrape is the
naming authority for agents/<broker_name>/<address>/<agent_name> -- and prints the
mv for any folder that has drifted off it. A folder with no lead row behind it at
all is reported separately as unverifiable rather than passing silently: the check
keys on agent_phone out of config.json, so a folder that never had a config.json was
exactly the hand-named case it could not see. A blank agent_name scrapes to the
UNASSIGNED_AGENT placeholder rather than a silent empty path segment; the same
drift check is how a placeholder gets corrected once the real name is known.

Being the read-only overview, it has to survive whatever is actually in a folder:
a directory named 01_front.jpg, an unreadable or truncated photo, a broken symlink.
Those are dropped from the photo count rather than raising and killing the whole
report over one bad entry -- the count itself is what surfaces the loss.

The out/ states name the FAMILY, not just a count. A first run writes three cuts
on purpose now, so a bare "built, 3 cuts" was indistinguishable from a six-cut
build that died halfway, exactly where the operator needs to know which run is
next:

    ready to build                          nothing in out/ yet
    sample built -- publish the review link  the three sample_ cuts exist
    sample published -- awaiting sign-off    a cut is on the review bucket
    delivered, N cuts                        a tour_ cut exists

"Published" is derived from outreach/links.csv, which publish.py already writes on
every confirmed upload -- no marker file is invented to hold it, and a missing file
means "nothing published" exactly as a missing leads.csv means "nothing scraped".
The soft-photo verdict rides along on all of them and is measured from photos/,
never read off a filename.

Usage:
    python3 status.py
    python3 status.py --long     # also show what each listing inherits
"""

import argparse
import csv
import importlib.util
import json
import os
import re
import struct
import subprocess
import sys

import prospects

ROOT = os.path.dirname(os.path.abspath(__file__))
AGENTS = os.path.join(ROOT, "agents")

# Mirrors make_tour.py's gate (OUT_W * ZOOM_MAX) -- see scraper/photos.py.
GATE_1080P = 2150
GATE_720P = 1433
# Past this the photos are not worth a build at all, not even a sample cut.
HOPELESS_UPSCALE = 3.0


def _load_scraper():
    """Borrow the scraper's pure-stdlib helpers rather than keeping a third copy of
    them, or shelling out to ffprobe once per photo."""
    path = os.path.join(ROOT, "scraper", "photos.py")
    spec = importlib.util.spec_from_file_location("_photos", path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, os.path.dirname(path))     # photos.py imports lead.py
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.pop(0)
    return mod


_photos = _load_scraper()
jpeg_size, slugify = _photos.jpeg_size, _photos.slugify
UNASSIGNED_AGENT = _photos.UNASSIGNED_AGENT


def _load_publish():
    """publish.py, or None. It owns the sample_/tour_ boundary and links.csv.

    reason: this module needs two facts publish.py already holds -- which family
    a cut in out/ belongs to, and which listings have had a link sent. Asking it
    keeps one implementation of each; re-deriving them here is the drift the
    naming rules exist to prevent. Guarded the same way the scraper is, because
    status.py is the read-only overview and must survive a partial tree.
    """
    try:
        import publish
        return publish
    except Exception:
        return None


_publish = _load_publish()


def scraped_names():
    """{normalized agent phone: (brand_slug, listing_slug, agent_slug)} from leads.csv.

    reason: the scrape is the naming authority -- agents/<slug(broker_name)>/
    <slug(address)>/<slug(agent_name)>, all three columns straight out of
    leads.csv. Folders were hand-named before that rule existed and drifted
    (coldwell_banker/2_comm_ave against a lead row reading "Coldwell Banker
    Realty - Boston" / "2 Commonwealth Ave"). Renaming them once fixes today;
    checking it on every status run is what keeps it fixed. Matched on agent
    phone rather than address text, because address formatting varies between
    the config and the CSV and a phone number does not.
    """
    path = os.path.join(ROOT, "scraper", "leads.csv")
    if not os.path.isfile(path):
        return {}
    out = {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            digits = re.sub(r"\D", "", r.get("agent_phone") or "")
            if digits:
                out[digits] = (slugify(r["broker_name"], "unknown_brokerage"),
                               slugify(r["address"]),
                               slugify(r.get("agent_name"), UNASSIGNED_AGENT))
    return out


def _dirs(path):
    if not os.path.isdir(path):
        return []
    return sorted(d for d in os.listdir(path)
                  if os.path.isdir(os.path.join(path, d)) and not d.startswith("."))


def _json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def resolves(listing_dir, path):
    """Same two-step make_tour._asset() uses: the listing folder, then the repo root."""
    if not path:
        return False
    return os.path.exists(os.path.join(listing_dir, path)) or os.path.exists(os.path.join(ROOT, path))


# reason: mirrors make_tour.py's PHOTO_EXTS. This used to be (".jpg", ".jpeg") only,
# which reported brewester/9_w_cedar -- 17 real .png/.webp photos -- as "no photos --
# scrape it", i.e. it told the operator to re-download a folder that was already
# complete. Zillow serves .webp now, so this is the common case, not the edge one.
PHOTO_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".heic")


def _size(path):
    """Long edge of any photo make_tour.py would accept.

    jpeg_size() is the no-cost path for the JPEGs the scraper writes; anything else
    falls back to ffprobe, which the project already requires. Returns None only if
    both fail, so an unreadable file is dropped from the stats rather than counted
    as zero pixels.
    """
    if path.lower().endswith((".jpg", ".jpeg")):
        # reason: jpeg_size() opens the path with no error handling of its own, so
        # a directory named 01_front.jpg raised IsADirectoryError and an
        # unreadable file raised PermissionError -- either one killed the whole
        # report over a single bad entry. status.py is the read-only overview; it
        # has to survive whatever is in the folder and say so.
        try:
            wh = jpeg_size(path)
        except (OSError, ValueError, struct.error):
            wh = None
        if wh:
            return max(wh)
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", path],
            capture_output=True, text=True, timeout=15)
        w, h = out.stdout.strip().split("x")[:2]
        return max(int(w), int(h))
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def photo_stats(listing_dir):
    d = os.path.join(listing_dir, "photos")
    if not os.path.isdir(d):
        return 0, None, None
    sizes = []
    for name in sorted(os.listdir(d)):
        full = os.path.join(d, name)
        if name.lower().endswith(PHOTO_EXTS) and os.path.isfile(full):
            px = _size(full)
            if px:
                sizes.append(px)
    if not sizes:
        return 0, None, None
    return len(sizes), min(sizes), max(sizes)


def built_families(listing_dir):
    """({"sample": n, "tour": n}, total mp4s) for what is in out/.

    reason: this used to be a bare len(os.listdir(out)), which counted build.log
    as a cut and -- now that a first run writes only the three sample_ cuts --
    reported "built, 3 cuts", indistinguishable from a six-cut build that died
    halfway. The families are the whole point of the two-run split, so the count
    has to name them. publish.family() is the authority on which prefix is which.
    """
    out = os.path.join(listing_dir, "out")
    if not os.path.isdir(out):
        return {"sample": 0, "tour": 0}, 0
    names = [f for f in sorted(os.listdir(out))
             if f.endswith(".mp4") and os.path.isfile(os.path.join(out, f))]
    counts = {"sample": 0, "tour": 0}
    for f in names:
        kind = _publish.family(f) if _publish else None
        if kind in counts:
            counts[kind] += 1
    return counts, len(names)


def published(brand, listing):
    """Has a cut for this listing been confirmed onto the review bucket?

    Derived from outreach/links.csv, which publish.py already writes on every
    confirmed upload -- no marker file is invented to hold it. A missing file is
    "nothing published", exactly as a missing leads.csv is "nothing scraped".
    """
    if not _publish:
        return False
    try:
        return (brand, listing) in _publish.published_listings()
    except Exception:
        return False


def next_action(listing_dir, cfg, n, worst, best, scraped=True, bcfg=None):
    """The one thing standing between this listing and a deliverable.

    scraped: whether this folder's own name appears in leads.csv. A folder that
    predates the scrape has no lead row behind it, and telling its operator to
    rerun photos.py sends them to a script that has nothing to work with.

    bcfg: the brand.json one level up. tour.py layers it UNDER the listing's own
    config.json, so the asset checks below have to see the same two layers or a
    listing that inherits its logo reads as missing one.
    """
    # reason: a config-less folder with NO lead row used to end the ladder here,
    # reporting its provenance as though provenance were the blocker. It is not:
    # there is no dump to rerun, tour.py's question set writes the config.json,
    # and photos are what make a listing buildable. So the fact travels as a
    # suffix on whatever the real next action is, and the folder can reach "ready
    # to build" like any other. A SCRAPED folder still goes back to photos.py --
    # there the scrape can fill in the address, agent, phone and watermark path
    # properly, which beats retyping them. The folder name is never touched
    # either way, and audit() still reports the folder as unverifiable.
    origin = "" if cfg or scraped else "   [no leads.csv row]"
    if n == 0:
        return "no photos -- scrape it" + origin
    if best and 1920.0 / best > HOPELESS_UPSCALE:
        return f"photos only {best}px -- get the originals, do not build{origin}"
    if not cfg and scraped:
        return "no config.json -- rerun photos.py"
    merged = dict(bcfg or {})
    merged.update(cfg or {})
    if not resolves(listing_dir, merged.get("logo")):
        return "logo blank/missing -- add it to brand.json" + origin
    if not resolves(listing_dir, merged.get("music")):
        return "music blank/missing -- add it to brand.json" + origin
    if not resolves(listing_dir, merged.get("watermark") or "viabolat.png"):
        return "watermark will not resolve -- the sample build will refuse" + origin
    counts, total = built_families(listing_dir)
    # reason: the output filenames used to carry a _lowres suffix and this read it
    # back off them. They no longer say anything about resolution, so the verdict
    # is measured from photos/ -- the same place it was always measured from.
    soft = " -- soft ({}px photos)".format(best) if best and best < GATE_720P else ""
    if not counts["sample"] and not counts["tour"]:
        tag = f" (soft: photos {best}px)" if best and best < GATE_1080P else ""
        return f"ready to build{tag}{origin}"
    if counts["tour"]:
        return f"delivered, {total} cuts{soft}{origin}"
    listing = os.path.basename(os.path.dirname(listing_dir))
    brand = os.path.basename(os.path.dirname(os.path.dirname(listing_dir)))
    if published(brand, listing):
        return f"sample published -- awaiting sign-off{soft}{origin}"
    return f"sample built -- publish the review link{soft}{origin}"


def survey():
    """(rows, truth, known) -- one row per listing, plus the naming authority.

    reason: split out of main() so tour.py's home screen renders the SAME rows
    and runs the SAME audit rather than growing a second copy of them. Two
    implementations of the scrape-naming check is the drift the check exists to
    catch, one level up. status.py is still the script; this is just where its
    body now lives.
    """
    # reason: read once, up front -- next_action needs to know whether a folder
    # is in leads.csv at all, and the drift report below needs the same table.
    truth = scraped_names()
    known = set(truth.values())

    rows = []
    for brand in _dirs(AGENTS):
        brand_dir = os.path.join(AGENTS, brand)
        bcfg = _json(os.path.join(brand_dir, "brand.json"))
        listed = _dirs(brand_dir)
        if not listed:
            rows.append((brand, "-", "-", 0, None, None, "no listings yet", bcfg, {}))
        for listing in listed:
            listing_dir = os.path.join(brand_dir, listing)
            agents = _dirs(listing_dir)
            if not agents:
                rows.append((brand, listing, "-", 0, None, None,
                             "no agent folder -- rerun photos.py", bcfg, {}))
                continue
            for agent in agents:
                ld = os.path.join(listing_dir, agent)
                cfg = _json(os.path.join(ld, "config.json"))
                n, worst, best = photo_stats(ld)
                rows.append((brand, listing, agent, n, worst, best,
                             next_action(ld, cfg, n, worst, best,
                                         scraped=(brand, listing, agent) in known,
                                         bcfg=bcfg),
                             bcfg, cfg))
    return rows, truth, known


def audit(rows, truth, known):
    """(drift, unverifiable) -- folders whose names the scrape does not agree with.

    reason: the drift check matches on agent_phone out of config.json, so a
    folder with no config.json -- which is the strongest signal it was never
    scaffolded by the scraper, i.e. the likeliest hand-named folder there is --
    produced no match and fell silently through the check built to catch it.
    brewester/9_w_cedar sat through the scrape-naming commit that way. Report
    unverifiable separately rather than letting absence read as agreement.
    """
    drift, unverifiable = [], []
    for brand, listing, agent, _n, _w, _b, _a, _bc, cfg in rows:
        if listing == "-" or agent == "-":       # placeholder rows, nothing to check
            continue
        # reason: the phone match is unchanged and still runs on every folder,
        # including ones whose *name* matches the scrape -- a folder called
        # gibson/169_k_st_1/j_doe carrying another agent's phone is worse drift,
        # not less, and skipping it on the name alone would have hidden exactly
        # that. This is also the correction path for a placeholder agent slug:
        # once the real agent_phone resolves to a lead row, "unassigned_agent"
        # drifts against the real agent slug like any other mismatch.
        want = truth.get(re.sub(r"\D", "", cfg.get("agent_phone") or ""))
        if want and (brand, listing, agent) != want:
            drift.append((brand, listing, agent, want))
        elif not want and (brand, listing, agent) not in known:
            unverifiable.append((brand, listing, agent, bool(cfg)))
    return drift, unverifiable


def print_audit(drift, unverifiable, out=print):
    """The two naming reports, printed identically wherever they are shown."""
    if drift:
        out(f"\n{len(drift)} folder name(s) do not match the scrape "
            f"(leads.csv is the naming authority):")
        for brand, listing, agent, (tb, tl, ta) in drift:
            out(f"  agents/{brand}/{listing}/{agent}")
            out(f"    mv agents/{brand}/{listing}/{agent} agents/{tb}/{tl}/{ta}")
    if unverifiable:
        out(f"\n{len(unverifiable)} folder(s) have no lead row to check against "
            f"(not renamed -- unverifiable):")
        for brand, listing, agent, has_cfg in unverifiable:
            why = ("config.json has no agent_phone matching leads.csv"
                   if has_cfg else "no config.json, so nothing to match on")
            out(f"  agents/{brand}/{listing}/{agent} -- {why}")
        out("  These predate the scrape or their lead row is gone. The scrape "
            "cannot name them; renaming by hand would invent a second "
            "authority. Leave them, or re-scrape the listing.")


def print_rows(rows, long=False, out=print):
    """The table, and the one-line summary of what a brand still owes.

    reason: split out of main() for the same reason audit()/print_audit() were --
    tour.py's home screen renders this table too, and it had grown its own copy
    of the header, the column widths and the row format. That copy had already
    drifted: it omitted the "N brokerage(s) need a logo" line entirely, so the
    home screen told the operator to add a logo per listing and never said it is
    set once per brand -- which is exactly what its Brand settings action does.
    """
    w = max(len(f"{b}/{l}/{a}") for b, l, a, *_ in rows)
    out(f"{'BROKERAGE / LISTING / AGENT'.ljust(w)}  PHOTOS  SMALLEST  NEXT")
    out("-" * (w + 40))
    for brand, listing, agent, n, worst, best, action, bcfg, cfg in rows:
        name = f"{brand}/{listing}/{agent}".ljust(w)
        px = f"{worst}px".rjust(8) if worst else "".rjust(8)
        out(f"{name}  {str(n).rjust(6)}  {px}  {action}")
        if long and cfg:
            out(f"{' ' * w}          logo={cfg.get('logo') or '(blank)'} "
                f"music={cfg.get('music') or '(blank)'} card={cfg.get('card')}")

    brands_missing = sorted({r[0] for r in rows if "brand.json" in r[6]})
    if brands_missing:
        out(f"\n{len(brands_missing)} brokerage(s) need a logo or music set once: "
            f"{', '.join(brands_missing)}")


def main():
    ap = argparse.ArgumentParser(description="What every listing is waiting on.")
    ap.add_argument("--long", action="store_true", help="also show inherited settings")
    args = ap.parse_args()

    rows, truth, known = survey()

    if not rows:
        print("No listings under agents/.")
        return

    print_rows(rows, long=args.long)
    print_audit(*audit(rows, truth, known))
    try:
        prospects.rebuild(rows, slugify)
    except OSError as e:
        print(f"\nprospects/ index did not rebuild ({type(e).__name__}: {e}).")


if __name__ == "__main__":
    main()
