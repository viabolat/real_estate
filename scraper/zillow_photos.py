#!/usr/bin/env python3
"""
zillow_photos.py

Saves every listing photo straight out of a raw Zillow HDP page-text dump
(the same __NEXT_DATA__ blob paste.txt already holds for zillow_lead.py).
The dump already embeds every photo's full-resolution URL and a photoCount
field, so there's no need to open a browser, log in, or click through the
gallery -- just parse the text and download.

Photos land in the build tree, not beside this script:

    agents/<broker_name>/<street_address>/photos/

which is exactly the layout make_tour.py expects as its working directory, so a
scrape drops in ready to build with no moving or renaming. Both folder names are
slugified straight from the same dump fields zillow_lead.py writes to the
broker_name and address columns, so the folder and the CSV row always agree -- the
scrape is the naming authority and nothing renames these by hand. status.py
re-checks it on every run.

Also scaffolds the two config files from the dump, never overwriting either:
agents/<broker_name>/brand.json (pacing and card defaults; logo and music left
blank for the operator, and no agent identity -- a brokerage has many agents) and
the listing's config.json (brokerage, full display address, agent, phone, and a
pinned watermark path). Then prints the resolution verdict make_tour.py's gate
would give, while the photos are already on disk and it costs nothing.

Usage:
    python3 zillow_photos.py paste.txt
    python3 zillow_photos.py paste.txt --out-dir some/other/folder
"""

import re
import argparse
import json
import os
import struct
import urllib.request

PHOTO_PATTERN = re.compile(
    r'photos\.zillowstatic\.com/fp/([a-f0-9]+)-uncropped_scaled_within_(\d+)_(\d+)\.jpg'
)


# reason: field() was a byte-identical second copy of zillow_lead's. Two copies of a
# regex that has already been tightened twice (the (?![A-Za-z0-9_]) guard) is a drift
# hazard, and both scripts run from the same folder off the same dump. One copy.
from zillow_lead import field, extract_zip_city_state


def extract_photo_urls(text: str) -> list:
    """All full-res photo URLs, in gallery order, deduped by hash (largest variant wins)."""
    best = {}
    order = []
    for hash_, w, h in PHOTO_PATTERN.findall(text):
        width = int(w)
        if hash_ not in best:
            order.append(hash_)
        if hash_ not in best or width > best[hash_][0]:
            best[hash_] = (width, f"https://photos.zillowstatic.com/fp/{hash_}-uncropped_scaled_within_{w}_{h}.jpg")
    return [best[h][1] for h in order]


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
# CLAUDE.md ("a new listing inherits at creation").
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
              f"named _lowres, and the best photo still upscales "
              f"{1920 / best:.1f}x at 1080p.")
    if 1920 / best > 3:
        print("    NOT usable, even as a watermarked sample. get the "
              "photographer's originals -- see IDEA.md section 4.")


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
    cfg = {k: brand[k] for k in INHERITED if k in brand}
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
    broker = field(text, "brokerName")
    agent = field(text, "agentName")
    phone = field(text, "agentPhoneNumber")
    zip_, city, state = extract_zip_city_state(text)
    display_address = compose_address(address, city, state, zip_)
    urls = extract_photo_urls(text)
    expected = field(text, "photoCount")

    # reason: the repo root is this script's parent -- agents/ is a sibling of
    # scraper/, not a child of it.
    repo_root = os.path.dirname(script_dir)
    out_dir = args.out_dir or os.path.join(
        repo_root, "agents", slugify(broker, "unknown_brokerage"),
        slugify(address), "photos")
    # reason: same guard as zillow_lead.py. With no photo URLs and no address
    # there is nothing to name the folder after, and the slug defaults turn a
    # garbage dump into agents/unknown_brokerage/listing/ complete with a
    # brand.json -- a folder the naming authority can never match, created
    # silently. Refuse before making any directory.
    if not urls and not address:
        print(f"{args.file}: no photo URLs and no address -- this is not a "
              f"Zillow listing dump. Nothing written.")
        sys.exit(2)

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
    if expected is not None and str(len(urls)) != str(expected):
        print(f"  WARNING: photoCount says {expected} but found {len(urls)} photo URLs in the dump")
    print(f"  {len(urls)} photo(s) found, {downloaded} newly downloaded, saved to {out_dir}")

    # reason: only scaffold the folder we actually own the layout of. With
    # --out-dir the operator has pointed us somewhere arbitrary and there is no
    # agents/<broker>/<listing> above it to write a brand.json into.
    if not args.out_dir:
        listing_dir = os.path.dirname(out_dir)
        scaffold(repo_root, os.path.dirname(listing_dir), listing_dir,
                 broker, address, agent, phone, display_address)
    report_resolution(out_dir)


if __name__ == "__main__":
    main()
