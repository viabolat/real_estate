#!/usr/bin/env python3
"""
fill_gaps.py

Closes, headlessly, what find_gaps.py reports. find_gaps.py stays what it is --
read-only, the detector -- and this is the only module allowed to act on its
findings. See _rules/find-gaps-detects-and-reports-it-never-writes.md and
_rules/fill-gaps-acts-only-on-what-find-gaps-named.md.

Three lanes, ordered by how much each can go wrong:

  emails   leads.csv's agent_email -> the listing's config.json. lead.py
           already parsed it out of the dump (field "agentEmail"), so this is
           a local copy between two files that are both already on disk. No
           network. Source tier "dump" -- Zillow's own listing data, a
           stronger source than the profile-page guess STEPS.md ranks first.
  claim    a logo_status() of "available" -> point brand.json's logo at the
           unclaimed global_assets/logos/<brand>.png already sitting there.
           No network, no download, one JSON key.
  fetch    a logo_status() of "gap" -> derive the brokerage's own domain from
           broker_name, verify the page really is that brokerage, then verify
           the ELEMENT too: a candidate is taken only when an attribute names
           the brokerage or the page labels it generically, because a page is
           full of other people's marks and every one of them downloads clean.
           The only lane that reaches the network, and it is off unless
           --fetch is passed. See
           _rules/a-fetched-logo-names-the-brokerage-or-it-is-not-fetched.md.

A "near_miss" logo is never touched by any lane. That bucket exists because a
plausible-but-wrong brokerage mark ships on a client's video, and find_gaps.py
already refuses to auto-adopt it -- adopting it here would just move the same
mistake one file over.

Every write is reported with the source tier that produced it, so a
lower-confidence value stays distinguishable in the run summary.

Usage:
    python3 fill_gaps.py                  # emails + claim, report what it did
    python3 fill_gaps.py --dry-run        # plan only, write nothing
    python3 fill_gaps.py --fetch          # also try the network for logo gaps
    python3 fill_gaps.py --json
"""

import argparse
import json
import os
import re
import struct
import sys
import urllib.error
import urllib.parse
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import find_gaps as fg

ROOT = fg.ROOT
LOGOS_DIR = fg.LOGOS_DIR
AGENTS_DIR = fg.AGENTS_DIR

TIMEOUT = 15
UA = "real-estate-tour-generator/1.0 (+brand logo lookup)"

# reason: a brokerage's legal tail is never in its domain ("Arborview Realty
# Inc" -> arborviewrealty.com), so these are stripped before a candidate is
# built. Kept separate from the slug pipeline in photos.py, which must not
# change -- the folder name is the scrape's to own.
LEGAL_TAIL = {"inc", "llc", "llp", "ltd", "co", "corp", "incorporated", "pllc"}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


# ---------------------------------------------------------------- emails ----

def email_fills(rows, agents_dir=AGENTS_DIR):
    """One planned config.json write per email gap that leads.csv can already
    close. A gap with no CSV email is returned with email=None -- it is
    reported, never guessed at."""
    by_key = {}
    for r in rows:
        addr = (r.get("agent_email") or "").strip()
        if addr:
            by_key.setdefault(fg.row_key(r), addr)

    plans = []
    for g in fg.email_gaps(rows, agents_dir=agents_dir):
        addr = by_key.get((g["brand"], g["listing"], g["agent"]))
        plans.append({
            "brand": g["brand"], "listing": g["listing"], "agent": g["agent"],
            "agent_name": g["agent_name"],
            "config_path": g["config_path"],
            "email": addr if addr and EMAIL_RE.fullmatch(addr) else None,
            "tier": "dump" if addr else None,
        })
    return plans


def apply_email_fills(plans, dry_run=False):
    """Write each plan's email into its config.json, leaving every other key
    exactly as it was. A plan with no email is skipped, not invented."""
    written = []
    for p in plans:
        if not p["email"]:
            continue
        if not dry_run:
            _patch_json(p["config_path"], {"agent_email": p["email"]})
        written.append(p)
    return written


# ----------------------------------------------------------------- logos ----

def claimable(logo_gaps):
    """The "available" bucket: a logo file is already on disk under the exact
    brand slug, nothing points at it yet. A pointer write, not a fetch."""
    return [g for g in logo_gaps if g["status"] == "available"]


def apply_claims(gaps, agents_dir=AGENTS_DIR, dry_run=False):
    """Point each brand.json's logo at the file find_gaps.py already named.
    Uses that candidate path verbatim so the two can never disagree."""
    done = []
    for g in gaps:
        rel = g["candidate"] or os.path.join("global_assets", "logos", f"{g['brand']}.png")
        if not os.path.exists(os.path.join(ROOT, rel)):
            continue
        if not dry_run:
            _patch_json(os.path.join(agents_dir, g["brand"], "brand.json"), {"logo": rel})
        done.append(dict(g, logo=rel, tier="on_disk"))
    return done


def domain_candidates(broker_name):
    """Plausible own-domain guesses for a brokerage, most specific first.
    Guesses only -- nothing is adopted until verify() confirms the page."""
    words = [w for w in re.split(r"[^a-z0-9]+", (broker_name or "").lower()) if w]
    words = [w for w in words if w not in LEGAL_TAIL]
    if not words:
        return []
    joined = "".join(words)
    out = [joined]
    if len(words) >= 2:
        out.append("".join(words[:2]))
    if len(words) >= 3:
        out.append("".join(words[:3]))
    out.append(words[0])
    seen, cands = set(), []
    for stem in out:
        if len(stem) < 4 or stem in seen:
            continue
        seen.add(stem)
        cands.append(f"{stem}.com")
    return cands


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.geturl(), r.read(400_000), dict(r.headers)


def verify(html, broker_name):
    """True when the page really belongs to this brokerage -- a distinctive
    word from broker_name has to appear in <title> or og:site_name.

    reason: "compass.com" resolves for a brokerage called Compass and for
    three unrelated companies. Downloading whatever mark the first responding
    domain serves is exactly the near_miss failure this module refuses to make
    in the other direction.
    """
    text = html.decode("utf-8", "replace")
    title = " ".join(re.findall(r"<title[^>]*>(.*?)</title>", text, re.S | re.I))
    site = " ".join(re.findall(r'property=["\']og:site_name["\'][^>]*content=["\']([^"\']+)', text, re.I))
    hay = (title + " " + site).lower()
    words = [w for w in re.split(r"[^a-z0-9]+", (broker_name or "").lower())
             if len(w) > 3 and w not in LEGAL_TAIL]
    return bool(words) and any(w in hay for w in words)


# reason: make_tour.py fits the mark into a 360x200 box for the persistent
# overlay and 760x300 on the card. Anything under this on its long side cannot
# fill even a third of that box without a visible upscale smear -- and a
# rel="icon" href is very often a 16px favicon. serhant.com served exactly that
# and it was accepted as the brokerage's logo, which is the near_miss failure
# this module refuses to make in the other direction.
MIN_LOGO_PX = 120


def png_size(blob):
    """(width, height) out of a PNG's IHDR, or None when it is not a PNG.

    reason: no Pillow, no ffprobe -- fetch_logo() runs in the scraper and this
    repo carries no image dependency. The IHDR is the first chunk of every PNG
    and its two big-endian uint32s sit at a fixed offset, so the header alone
    answers "is this a mark or a favicon".
    """
    if not blob.startswith(b"\x89PNG\r\n\x1a\n") or len(blob) < 24:
        return None
    return struct.unpack(">II", blob[16:24])


# reason: a page is full of other people's marks. serhant.com carries the
# NETFLIX wordmark (class="netflix-logo", for the show the brokerage appears
# in), two MLS marks and an RLS mark, and every one of them downloads clean,
# is a real PNG and clears the size gate. The page's OWN mark is the one it
# labels generically -- alt="Logo", class="heading-logo" -- because a site does
# not qualify its own identity. Strip the positional adjectives from a
# logo-ish attribute; whatever is left is a foreign owner's name, and if
# anything is left the candidate is not this brokerage's mark.
POSITIONAL = {"logo", "logos", "img", "image", "icon", "site", "header",
              "heading", "head", "nav", "navbar", "menu", "top", "main",
              "primary", "brand", "branding", "company", "wordmark", "mark",
              "link", "home", "wrapper", "container", "desktop", "mobile",
              "light", "dark", "white", "black", "svg", "png", "a", "the"}


def _img_tags(text):
    """(tag_text, {attr: value}) for every <img> on the page, in document order.

    reason: the old pattern required the logo-ish attribute to appear BEFORE
    src= in the tag, so serhant.com's own <img src=... alt="Logo"
    class="heading-logo"> never matched while <img class="netflix-logo"
    src=...> did. Attribute order is not a signal about anything.
    """
    for m in re.finditer(r"<img\b[^>]*>", text, re.I):
        tag = m.group(0)
        attrs = {k.lower(): v for k, v in
                 re.findall(r'([a-zA-Z_:-]+)\s*=\s*["\']([^"\']*)["\']', tag)}
        yield tag, attrs


def _words(name):
    """Distinctive words in a brokerage name -- the same set verify() uses."""
    return [w for w in re.split(r"[^a-z0-9]+", (name or "").lower())
            if len(w) > 3 and w not in LEGAL_TAIL]


def _tokens(value):
    return [t for t in re.split(r"[^a-z0-9]+", (value or "").lower()) if t]


def owns_the_mark(attrs, broker_name):
    """Does this <img> plausibly carry THIS brokerage\'s mark?

    Two ways to earn it, and nothing else counts:
      vouched  -- an attribute names the brokerage (remax..., serhant...)
      generic  -- a logo-ish attribute reduces to nothing but positional words,
                  so the page is calling it *the* logo rather than someone\'s
    """
    values = [v for k, v in attrs.items()
              if k in ("class", "id", "alt", "src", "title", "data-src")]
    words = _words(broker_name)
    for v in values:
        toks = set(_tokens(v))
        if words and any(w in toks or any(w in t for t in toks) for w in words):
            return "vouched"
    for k in ("class", "id", "alt", "title"):
        v = attrs.get(k)
        if not v:
            continue
        toks = set(_tokens(v))
        if "logo" in toks and not (toks - POSITIONAL):
            return "generic"
    return None


def logo_urls(html, base, broker_name=""):
    """The page\'s claims to its OWN mark, best first. Yields absolute URLs.

    reason: this returned only the first match and led with rel="icon", so a
    site declaring its favicon above its real mark handed back a 16x16 file and
    nothing further down the page was ever reached. Yield every candidate so
    fetch_logo() can fall past one that turns out too small or foreign, and
    order by how likely an element is to BE this brokerage\'s mark rather than
    by how explicit its markup is.

    og:image is deliberately NOT among these. It is a social share card, and a
    share card is chosen to sell the page, not to identify the company:
    serhant.com serves the NETFLIX wordmark there. It downloaded clean, was a
    real PNG and cleared the size gate at 384x120 -- a plausible-looking mark
    belonging to another company entirely, one build from a client\'s video. No
    byte or dimension check catches that; only not asking the question does.
    See _rules/a-fetched-logo-names-the-brokerage-or-it-is-not-fetched.md.
    """
    text = html.decode("utf-8", "replace")
    vouched, generic = [], []
    for _tag, attrs in _img_tags(text):
        src = attrs.get("src") or attrs.get("data-src")
        if not src or "{{" in src:
            continue
        owner = owns_the_mark(attrs, broker_name)
        if owner == "vouched":
            vouched.append(src)
        elif owner == "generic":
            generic.append(src)

    icons = []
    for pat in (r'rel=["\']apple-touch-icon["\'][^>]*href=["\']([^"\']+\.png)',
                r'href=["\']([^"\']+\.png)["\'][^>]*rel=["\']apple-touch-icon',
                r'rel=["\']icon["\'][^>]*href=["\']([^"\']+\.png)',
                r'href=["\']([^"\']+\.png)["\'][^>]*rel=["\']icon'):
        icons += [m.group(1) for m in re.finditer(pat, text, re.I)]

    seen = set()
    for raw in vouched + generic + icons:
        url = urllib.parse.urljoin(base, raw)
        if url not in seen:
            seen.add(url)
            yield url


def fetch_logo(brand_slug, broker_name, logos_dir=LOGOS_DIR, dry_run=False):
    """Try each candidate domain until one verifies and serves a PNG. Returns
    a result dict -- "ok" with the path written, or "skipped" with the reason,
    never an exception and never a half-written file."""
    for domain in domain_candidates(broker_name):
        for scheme in ("https://",):
            try:
                base, html, _ = _get(scheme + domain)
            except (urllib.error.URLError, OSError, ValueError):
                continue
            if not verify(html, broker_name):
                return {"brand": brand_slug, "status": "skipped",
                        "reason": f"{domain} did not verify as {broker_name}"}
            why = f"no logo element found on {domain}"
            for url in logo_urls(html, base, broker_name):
                try:
                    _final, blob, hdrs = _get(url)
                except (urllib.error.URLError, OSError, ValueError) as e:
                    why = f"logo download failed: {e}"
                    continue
                # reason: make_tour.py's gate resolves
                # global_assets/logos/<brand>.png and nothing in this repo can
                # transcode without adding a dependency, so a non-PNG mark is
                # reported for a session to handle rather than saved under a
                # name that lies about its type.
                size = png_size(blob)
                if size is None:
                    why = (f"not a PNG ({hdrs.get('Content-Type', 'unknown')})"
                           " -- needs a session")
                    continue
                if max(size) < MIN_LOGO_PX:
                    why = (f"{size[0]}x{size[1]} is a favicon, not a mark "
                           f"(needs {MIN_LOGO_PX}px) -- needs a session")
                    continue
                dest = os.path.join(logos_dir, f"{brand_slug}.png")
                if not dry_run:
                    os.makedirs(logos_dir, exist_ok=True)
                    tmp = dest + ".part"
                    with open(tmp, "wb") as f:
                        f.write(blob)
                    os.replace(tmp, dest)
                return {"brand": brand_slug, "status": "ok", "path": dest,
                        "size": f"{size[0]}x{size[1]}", "source": url,
                        "tier": "brokerage_site"}
            return {"brand": brand_slug, "status": "skipped", "reason": why}
    return {"brand": brand_slug, "status": "skipped",
            "reason": "no candidate domain responded"}


# ------------------------------------------------------------------ util ----

def _patch_json(path, updates):
    """Merge updates into a JSON file, preserving every other key. Written via
    a temp file and os.replace so an interrupted run cannot leave a truncated
    config.json where make_tour.py expects one."""
    data = fg._json(path)
    data.update(updates)
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    return data


def main():
    ap = argparse.ArgumentParser(
        description="Close the gaps find_gaps.py reports. near_miss is never touched.")
    ap.add_argument("--dry-run", action="store_true", help="plan only, write nothing")
    ap.add_argument("--fetch", action="store_true",
                    help="also try the network for logo gaps (off by default)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    rows = fg.load_leads()
    logo_gaps = fg.brand_gaps(rows)

    plans = email_fills(rows)
    emails = apply_email_fills(plans, dry_run=args.dry_run)
    claims = apply_claims(claimable(logo_gaps), dry_run=args.dry_run)

    fetched = []
    if args.fetch:
        for g in logo_gaps:
            if g["status"] == "gap":
                fetched.append(fetch_logo(g["brand"], g["broker_name"], dry_run=args.dry_run))

    unresolved = [p for p in plans if not p["email"]]
    near = [g for g in logo_gaps if g["status"] == "near_miss"]
    result = {"emails_written": emails, "logos_claimed": claims,
              "logos_fetched": fetched, "emails_unresolved": unresolved,
              "near_miss_untouched": near, "dry_run": args.dry_run}

    if args.json:
        print(json.dumps(result, indent=2))
        sys.exit(0)

    tag = " (dry run -- nothing written)" if args.dry_run else ""
    print(f"\nagent_email: {len(emails)} written{tag}")
    for e in emails:
        print(f"  {e['brand']}/{e['listing']}/{e['agent']}  [{e['tier']}]")
    for u in unresolved:
        print(f"  UNRESOLVED {u['brand']}/{u['listing']}/{u['agent']} "
              f"-- no email in leads.csv, needs a session")

    print(f"\nlogos claimed: {len(claims)}{tag}")
    for c in claims:
        print(f"  {c['brand']} -> {c['logo']}  [{c['tier']}]")

    if args.fetch:
        ok = [f for f in fetched if f["status"] == "ok"]
        print(f"\nlogos fetched: {len(ok)}/{len(fetched)}{tag}")
        for f in fetched:
            if f["status"] == "ok":
                print(f"  {f['brand']} -> {f['path']}  [{f['tier']}] {f['source']}")
            else:
                print(f"  SKIPPED {f['brand']} -- {f['reason']}")
    elif any(g["status"] == "gap" for g in logo_gaps):
        n = sum(1 for g in logo_gaps if g["status"] == "gap")
        print(f"\n{n} logo gap(s) need the network. Re-run with --fetch.")

    if near:
        print(f"\n{len(near)} near_miss left alone (a wrong mark ships on a video):")
        for g in near:
            print(f"  {g['brand']}  candidate {g['candidate']}")
    sys.exit(0)


if __name__ == "__main__":
    main()
