#!/usr/bin/env python3
"""
photos.py

Saves every listing photo straight out of a raw Zillow HDP page-text dump
(the same __NEXT_DATA__ blob paste.txt already holds for lead.py).
The dump already embeds every photo's full-resolution URL and a photoCount
field, so there's no need to open a browser, log in, or click through the
gallery -- just parse the text and download.

Zillow serves two listing shapes and they carry different photo URL families: a
regular listing has both -uncropped_scaled_within_<w>_<h>.jpg and -cc_ft_<w>.jpg,
a Showcase listing has only cc_ft (plus sc_/sr_, which over-collect). So the
uncropped pass runs first and cc_ft is appended only for what it missed --
never merged, never widened. A dump whose photoCount says it has photos but
yields no URLs at all exits 4 without writing anything, because that means the
patterns no longer describe what Zillow serves. The same shape split renames attribution, so the brokerage is read the same
way -- see lead.broker_name() and
_rules/a-second-listing-shape-is-a-fallback-never-a-replacement.md.

Photos land in the build tree, not beside this script:

    agents/<broker_name>/<street_address>/<agent_name>/photos/

which is exactly the layout make_tour.py expects as its working directory, so a
scrape drops in ready to build with no moving or renaming. All three folder
names are slugified straight from the same dump fields lead.py writes to the
broker_name, address and agent_name columns, so the folder and the CSV row
always agree -- the scrape is the naming authority and nothing renames these by
hand. A blank agent name gets the UNASSIGNED_AGENT placeholder rather than a
silent empty path segment. status.py re-checks it on every run.

Also scaffolds the two config files from the dump, never overwriting either:
agents/<broker_name>/brand.json (pacing and card defaults; logo and music left
blank for the operator, and no agent identity -- a brokerage has many agents) and
the listing's config.json (brokerage, full display address, agent, phone, and a
pinned watermark path). Then prints the resolution verdict make_tour.py's gate
would give, while the photos are already on disk and it costs nothing.

Usage:
    python3 photos.py paste.txt
    python3 photos.py paste.txt --out-dir some/other/folder
"""

import re
import argparse
import json
import os
import struct
# reason: sys.exit(2) is the refusal for a dump that is not a listing, and
# sys was never imported -- so that path raised NameError instead. It still
# exited non-zero and still wrote nothing, which is why it went unnoticed,
# but it exited 1 with a traceback where the contract says 2.
import sys
import urllib.request

PHOTO_PATTERN = re.compile(
    r'photos\.zillowstatic\.com/fp/([a-f0-9]+)-uncropped_scaled_within_(\d+)_(\d+)\.jpg'
)

# reason: Zillow serves two listing shapes and they do not carry the same photo
# URL families. A regular listing (GraphQL ForSalePriorityQuery) has both
# -uncropped_scaled_within_<w>_<h> and -cc_ft_<w>; a Showcase listing
# (ViewShowcasePriorityQuery) has NO uncropped variant at all, only cc_ft plus
# the sc_/sr_ families. PHOTO_PATTERN alone therefore returned [] for every
# Showcase listing -- the dump held all 33 URLs and the download saved none.
#
# This is a SECOND pass, never a merge of the two into one width-ranked regex.
# On a regular listing both families exist at width 1536, so a widest-wins tie
# would silently hand back cropped variants in place of the uncropped originals
# across the entire existing photo library. Measured on all 9 dumps on hand
# (5 regular, 4 Showcase): the cc_ft hash set is exactly equal to the uncropped
# set on every regular listing and in the same first-appearance order, so this
# fallback appends nothing there -- byte-identical output is structural, not
# luck. On Showcase it supplies the whole gallery, matching photoCount exactly.
#
# Not widened to sc_/sr_ as a general defence against the next variant: those
# over-collect by 8-15 non-gallery images per Showcase listing. A narrow match
# plus photo_count_verdict()'s loud failure is the correct shape.
CC_FT_PATTERN = re.compile(
    r'photos\.zillowstatic\.com/fp/([a-f0-9]+)-cc_ft_(\d+)\.jpg'
)


# reason: field() was a byte-identical second copy of lead.py's. Two copies of a
# regex that has already been tightened twice (the (?![A-Za-z0-9_]) guard) is a drift
# hazard, and both scripts run from the same folder off the same dump. One copy.
from lead import field, broker_name, extract_zip_city_state


def extract_photo_urls(text: str) -> list:
    """All full-res photo URLs, in gallery order, deduped by hash (largest variant wins).

    The uncropped pass runs first and unchanged; cc_ft is only consulted for
    hashes it did not find, so a regular listing's output is exactly what it was
    before Showcase support existed. See CC_FT_PATTERN for why the two families
    are two passes and not one regex.

    Known limitation: on a listing that mixed the two -- some photos uncropped,
    some cc_ft-only -- the cc_ft tail would land after the uncropped block rather
    than in its true gallery position. No such listing exists in the nine
    measured; the two sets are either equal or disjoint.
    """
    best = {}
    order = []
    for hash_, w, h in PHOTO_PATTERN.findall(text):
        width = int(w)
        if hash_ not in best:
            order.append(hash_)
        if hash_ not in best or width > best[hash_][0]:
            best[hash_] = (width, f"https://photos.zillowstatic.com/fp/{hash_}-uncropped_scaled_within_{w}_{h}.jpg")
    # Snapshot before the second pass mutates `best`: only hashes the uncropped
    # pass never saw may be appended. An uncropped URL already chosen is never
    # replaced by a cc_ft one, whatever its width.
    uncropped = set(best)
    for hash_, w in CC_FT_PATTERN.findall(text):
        if hash_ in uncropped:
            continue
        width = int(w)
        if hash_ not in best:
            order.append(hash_)
        if hash_ not in best or width > best[hash_][0]:
            best[hash_] = (width, f"https://photos.zillowstatic.com/fp/{hash_}-cc_ft_{w}.jpg")
    return [best[h][1] for h in order]


def photo_count_verdict(found: int, expected):
    """None, "warn" or "fail" -- whether the URL count contradicts photoCount.

    reason: main() printed "WARNING: photoCount says 33 but found 0 photo URLs"
    and carried straight on. That line had been firing on roughly 40% of dumps
    -- every Showcase listing -- for as long as Showcase listings existed, and
    a warning nobody acts on is not a guard: the run reported success, the
    folder was scaffolded, and the gallery was empty. Finding zero URLs in a
    dump that says it has photos means the regexes above no longer describe
    what Zillow serves, which is a fact about the scraper, not about the
    listing. It has to stop the dump.

    Split three ways rather than two because the three cases are not the same
    failure. Zero-of-many is an unknown URL variant. Any other disagreement --
    fewer than photoCount, or MORE than it -- stays the warning it has always
    been: the photos that were found are real and downloading them is right,
    and over-collection is what a too-broad pattern looks like (the sc_/sr_
    families run 8-15 images over on a Showcase listing), so it must not go
    quiet just because the zero case now shouts. A dump whose photoCount is
    absent or 0 is not this bug at all -- a listing may legitimately have no
    photos, and target_for() still refuses it when it has no address either.

    `expected` arrives as field()'s string or None, so it is normalised here
    rather than at each call site.
    """
    try:
        expected = int(expected)
    except (TypeError, ValueError):
        return None
    if expected <= 0:
        return None
    if found == 0:
        return "fail"
    if found != expected:
        return "warn"
    return None


def slugify(text: str, default: str = "listing") -> str:
    """Lowercase underscore slug of a CSV column value.

    reason: apostrophes are dropped rather than turned into separators. Broker
    names reach the filesystem now, and the straight non-alphanumeric rule turns
    "Gibson Sotheby's International Realty" into gibson_sotheby_s_international_realty.
    No address in leads.csv contains an apostrophe, so this only ever changes a
    broker slug.
    """
    text = (text or "").replace("'", "").replace("\u2019", "")
    slug = re.sub(r'[^A-Za-z0-9]+', '_', text).strip('_').lower()
    return slug or default


# reason: these mirror make_tour.py's resolution gate (OUT_W * ZOOM_MAX) so the
# verdict can be given at scrape time instead of 20 minutes into a build. If the
# gate there ever moves, these move with it.
GATE_1080P = 2150
GATE_720P = 1433

# What a brokerage sets once and every listing under it inherits. Deliberately
# excludes agent_name / agent_phone: leads.csv already shows two agents under
# "Coldwell Banker Realty - Boston" and two under "Gibson Sotheby's", and folders
# are slugged from broker_name, so a brand-level agent would put one agent's phone
# number on another agent's video.
BRAND_STUB = {
    "clip_seconds": 4.0,
    "xfade_seconds": 0.5,
    "brand_persistent": False,
    "brand_in": 0.8,
    "brand_out": 6.5,
    "card": "outro",
    "card_seconds": 5.0,
    "logo": "",
    "music": "",
}
# Inherited into a new listing at creation, matching the documented model in
# _reference/layout.md ("a new listing inherits at creation").
INHERITED = tuple(BRAND_STUB) + ("card_style", "card_theme", "accent", "font")


def jpeg_size(path):
    """(width, height) from a JPEG's SOF marker. Pure stdlib -- the scraper has no
    third-party dependencies and this keeps it that way."""
    with open(path, "rb") as f:
        if f.read(2) != b"\xff\xd8":
            return None
        while True:
            b = f.read(1)
            while b and b != b"\xff":
                b = f.read(1)
            marker = f.read(1)
            while marker == b"\xff":
                marker = f.read(1)
            if not marker:
                return None
            m = marker[0]
            if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
                f.read(3)
                h, w = struct.unpack(">HH", f.read(4))
                return w, h
            size = f.read(2)
            if len(size) < 2:
                return None
            f.seek(struct.unpack(">H", size)[0] - 2, 1)


# reason: an agent-blank dump still has to land somewhere the naming authority
# can find again. "unknown_brokerage" is the same fallback one line down, for
# the same reason: a silent empty path segment cannot be told apart from a
# missing folder, but this placeholder can be searched for and corrected once
# the real name is known (status.py's drift audit is the correction path).
UNASSIGNED_AGENT = "unassigned_agent"


DUMP_EXTENSIONS = (".txt", ".json")


def is_dump(name: str) -> bool:
    """True for a filename in dumps/ that is offered to the parsers at all.

    reason: the same answer is needed in two places -- run.py picking a folder's
    dumps up, and tour.py deciding which have no folder yet -- and a mismatch
    between the two lists reads as a dump that imports fine but is never
    offered, or is offered forever after it was imported. One predicate, both
    callers, exactly as target_for() is one namer for both.

    .json is accepted beside .txt because the parsers are regexes over the whole
    text and never over parsed HTML: the __NEXT_DATA__ blob saved on its own is
    the same bytes the page dump carries inside it. Nothing else is guessed at
    -- the extension only decides what is READ; whether a file is a listing is
    still target_for()'s refusal.
    """
    return (not name.startswith(".")
            and name.lower().endswith(DUMP_EXTENSIONS))


def target_for(text: str):
    """(brand, listing, agent) -- the folder this dump scaffolds -- or None if
    it is not one.

    reason: main() derived this inline, and tour.py's home screen has to derive
    the SAME tuple to decide whether a dump has already been imported. Two
    copies of the folder-naming decision is a second naming authority, which is
    what _rules/the-scrape-names-the-folders.md forbids, and a near-miss would
    report an imported listing as
    pending forever. One function, both callers.

    None is the refusal: with no photo URLs and no address there is nothing to
    name the folder after, and the slug defaults would turn a garbage dump into
    agents/unknown_brokerage/listing/unassigned_agent/ -- a folder the naming
    authority can never match.
    """
    address = field(text, "streetAddress")
    if not extract_photo_urls(text) and not address:
        return None
    return (slugify(broker_name(text), "unknown_brokerage"),
            slugify(address),
            slugify(field(text, "agentName"), UNASSIGNED_AGENT))


def report_resolution(out_dir):
    """Say at scrape time what make_tour.py's gate would say at build time.

    reason: the photo URL's variant name is a ceiling, not a promise --
    uncropped_scaled_within_1536_1152 returns the original untouched when the
    original is smaller. One listing scraped here came back at 346px from a URL
    advertising 1536. Finding that out after downloading, numbering and sitting
    through a build is the expensive way; the files are already on disk here, so
    it costs nothing to measure them now.
    """
    sizes = []
    for name in sorted(os.listdir(out_dir)):
        if name.lower().endswith(".jpg"):
            wh = jpeg_size(os.path.join(out_dir, name))
            if wh:
                sizes.append(max(wh))
    if not sizes:
        return
    worst, best = min(sizes), max(sizes)
    under = sum(1 for s in sizes if s < GATE_1080P)
    if under == 0:
        print(f"  resolution: all {len(sizes)} photos clear the 1080p gate ({GATE_1080P}px)")
        return
    print(f"  resolution: {under} of {len(sizes)} photos below the 1080p gate "
          f"({GATE_1080P}px). smallest {worst}px, largest {best}px")
    if best < GATE_720P:
        print(f"    below the 720p gate ({GATE_720P}px) too. every cut would be "
              f"soft -- the best photo still upscales {1920 / best:.1f}x at "
              f"1080p, and the filenames will not say so.")
    if 1920 / best > 3:
        print("    NOT usable, even as a watermarked sample. get the "
              "photographer's originals -- see IDEA.md section 4.")


def already_scraped(out_dir, urls):
    """How many of this dump's photos are already on disk, or 0.

    reason: the per-file `os.path.exists(dest)` skip in the download loop
    already makes a rerun cheap, but it still walks every URL and prints as
    though something happened. A dump pasted twice for the same
    company/address/agent is not a resumed download, it is a no-op -- the
    caller uses a nonzero return to say so loudly and stop before the loop
    runs at all. A folder with FEWER photos than this dump has URLs is a
    partial/interrupted run, not a duplicate, and must fall through to the
    ordinary download loop so it can finish.
    """
    if not urls or not os.path.isdir(out_dir):
        return 0
    existing = [n for n in os.listdir(out_dir) if n.lower().endswith(".jpg")]
    return len(existing) if len(existing) >= len(urls) else 0


def compose_address(street, city, state, zip_):
    """The full one-line address for the card and lower third, from the dump."""
    tail = " ".join(p for p in [state, zip_] if p)
    return ", ".join(p for p in [street, city, tail.strip()] if p)


def scaffold(repo_root, brand_dir, listing_dir, broker, address, agent, phone,
             display_address):
    """Write the brand.json stub and the listing config.json, never overwriting.

    reason: every field here is already sitting in the dump. Retyping an agent's
    phone number into a config by hand is a transcription error that ships on a
    finished client video, and the wrong number is invisible in review because it
    still looks like a phone number.
    """
    brand_path = os.path.join(brand_dir, "brand.json")
    if os.path.exists(brand_path):
        brand = json.load(open(brand_path, encoding="utf-8"))
        print(f"  brand.json: already exists, left alone")
    else:
        brand = dict(BRAND_STUB, brokerage=broker or "")
        os.makedirs(brand_dir, exist_ok=True)
        with open(brand_path, "w", encoding="utf-8") as f:
            json.dump(brand, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"  brand.json: created -- logo and music are blank, "
              f"fill them in once for this brokerage")

    cfg_path = os.path.join(listing_dir, "config.json")
    if os.path.exists(cfg_path):
        print("  config.json: already exists, left alone")
        return
    # reason: a brand.json created in this same run has logo and music blank, and
    # freezing that "" into the listing's config.json makes it SHADOW the brand
    # forever -- tour.load_config() layers DEFAULTS -> brand.json -> config.json,
    # so the empty string wins over a path set on the brand later. 16_holmfield_ave
    # was re-scraped while global_assets/logos/keller_williams_realty.png was
    # already on disk; fill_gaps.py duly claimed it into brand.json, and the
    # roll-up still read "logo blank/missing -- add it to brand.json". An unset
    # value is left out, matching tour.save_config()'s own contract.
    cfg = {k: brand[k] for k in INHERITED if k in brand and brand[k] != ""}
    cfg.update({
        "brokerage": broker or "",
        # reason: streetAddress alone is what names the folder (it has to match
        # leads.csv's address column), but it is not what should print on the card
        # -- "2 Commonwealth Ave" with no city reads like an unfinished draft. The
        # dump already carries city/state/zip, so compose the display line here
        # rather than leaving it to be typed in by hand later.
        "address": display_address,
        "agent_name": agent or "",
        "agent_phone": phone or "",
        # reason: the default "viabolat.png" resolves against the listing folder
        # then beside make_tour.py, and this repo keeps it in global_assets/logos/.
        # When it does not resolve the build prints one line and drops the mark,
        # so an unwatermarked sample_ cut ships silently. Pin it at creation.
        "watermark": "global_assets/logos/viabolat.png",
    })
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("  config.json: created from the dump "
          "(address, agent, phone, brokerage, watermark)")
    if not cfg.get("logo"):
        print("    logo is blank -> the card falls back to the type-only design")
    if not cfg.get("music"):
        print("    music is blank -> the build will be silent until you set one")


def main():
    parser = argparse.ArgumentParser(description="Save all listing photos from a Zillow HDP dump.")
    parser.add_argument("file", help="Path to the pasted Zillow page text file")
    parser.add_argument("--out-dir",
                        help="Directory to save photos into "
                             "(default: agents/<broker_name>/<address>/photos)")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))

    with open(args.file, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    address = field(text, "streetAddress")
    broker = broker_name(text)
    agent = field(text, "agentName")
    phone = field(text, "agentPhoneNumber")
    zip_, city, state = extract_zip_city_state(text)
    display_address = compose_address(address, city, state, zip_)
    urls = extract_photo_urls(text)
    expected = field(text, "photoCount")

    # reason: the repo root is this script's parent -- agents/ is a sibling of
    # scraper/, not a child of it.
    repo_root = os.path.dirname(script_dir)
    # reason: same guard as lead.py, and the same one tour.py's home
    # screen applies -- target_for() owns both the refusal and the folder names
    # so the two callers cannot disagree. Refuse before making any directory.
    target = target_for(text)
    if target is None:
        print(f"{args.file}: no photo URLs and no address -- this is not a "
              f"Zillow listing dump. Nothing written.")
        sys.exit(2)
    out_dir = args.out_dir or os.path.join(repo_root, "agents", *target, "photos")

    # reason: refuse before makedirs and before scaffold() -- a dump whose photo
    # URLs we cannot read must leave nothing behind, not an empty photos/ folder
    # with a brand.json and config.json beside it that read as a finished import.
    # Exit 4, not 2: run.py treats everything outside (0, 3) as a failed dump and
    # keeps going either way, but 2 already means "not a listing dump" and an
    # operator running photos.py by hand has to be able to tell the two apart.
    if photo_count_verdict(len(urls), expected) == "fail":
        print(f"{args.file}: photoCount says {expected} but no photo URLs matched. "
              f"Zillow is serving a URL variant this scraper does not know -- see "
              f"PHOTO_PATTERN / CC_FT_PATTERN. Nothing written.")
        sys.exit(4)

    if not args.out_dir:
        dup_count = already_scraped(out_dir, urls)
        if dup_count:
            banner = f"{'/'.join(target)} already has {dup_count} photo(s) on disk."
            rule = "=" * max(60, len(banner))
            print(rule)
            print("DUPLICATE -- NOTHING DOWNLOADED")
            print(banner)
            print(rule)
            sys.exit(3)

    os.makedirs(out_dir, exist_ok=True)

    pad = len(str(len(urls)))
    downloaded = 0
    for i, url in enumerate(urls, start=1):
        dest = os.path.join(out_dir, f"{i:0{pad}d}.jpg")
        if os.path.exists(dest):
            continue
        urllib.request.urlretrieve(url, dest)
        downloaded += 1

    print(f"{address or 'unknown address'} -- {broker or 'unknown brokerage'}")
    if photo_count_verdict(len(urls), expected) == "warn":
        print(f"  WARNING: photoCount says {expected} but found {len(urls)} photo URLs in the dump")
    print(f"  {len(urls)} photo(s) found, {downloaded} newly downloaded, saved to {out_dir}")

    # reason: only scaffold the folder we actually own the layout of. With
    # --out-dir the operator has pointed us somewhere arbitrary and there is no
    # agents/<broker>/<listing> above it to write a brand.json into.
    if not args.out_dir:
        listing_dir = os.path.dirname(out_dir)                    # agents/brand/listing/agent
        brand_dir = os.path.dirname(os.path.dirname(listing_dir))  # agents/brand
        scaffold(repo_root, brand_dir, listing_dir,
                 broker, address, agent, phone, display_address)
    report_resolution(out_dir)


if __name__ == "__main__":
    main()
