#!/usr/bin/env python3
"""tour.py — the one command. Photos in a folder, a few questions, an mp4 out.

    python3 tour.py                 # the home screen: where every listing is
    python3 tour.py --build         # skip it, go straight to the wizard
    python3 tour.py --check-photos  # optional: ask Claude to read the contact sheet
    python3 tour.py --auto          # hands-off: every pending dump through to 3 sample cuts

This replaced the Streamlit dashboard, which put thirteen controls on screen and
still left the operator to remember which of them mattered. The shape here is the
opposite: everything with the same answer on every listing is inherited from
agents/<brand>/brand.json or derived from the photos, everything missing is named
up front rather than discovered five minutes into an encode, and what is left is
a short question set — where the photos are, what the card says, how long it runs.

That rule was applied to the build and then not applied to the pipeline around
it, which grew back to eight commands an operator had to keep straight —
run.py, status, tour, publish, check_pii, make_tour, vercel, unittest — with
nothing saying which was a decision and which was a chore. Sorted by what they
actually are, only one is a decision:

  check_pii.py  is a gate and never has an interesting answer  -> hooks/pre-push
  npx vercel    is one-time setup, not per listing             -> out of the loop
  publish.py    was already rung 4 here                        -> also menu item 3
  status.py     is "where am I"                                -> the home screen
  run.py        is a real action, but a DETECTABLE one         -> offered, not
                                                                  remembered
  make_tour.py  is the engine                                  -> escape hatch
  unittest      is developer-only                              -> out of the loop

So this opens on status.py's roll-up and four choices: build, import the dumps
that have no folder yet, publish a review link, edit a brand. Nothing behind that
screen changed — every rung, prompt, default and refusal is what it was, and
every script named above still runs standalone exactly as documented.

Which dumps are pending is DERIVED, from whether agents/<brand>/<listing> exists.
There is no marker file and no manifest, for the same reason photo order lives in
the filename prefix: a record kept beside the artifacts drifts out of sync with
them and is then wrong in a way nothing detects.

Which RUN a listing is on is derived the same way, from out/:

    nothing in out/     -> run 1: build the three watermarked sample_ cuts,
                           publish the review link, send the draft email
    sample_ cuts only   -> run 2, once the client says yes: the three tour_
                           deliverables, off the stitch run 1 left behind
    any tour_ cut       -> delivered; either family can still be rebuilt

That staging is a default and never a restriction -- a client who has already paid
can take all six in one go from the same menu. It exists because the tour_ trio is
the paid deliverable, and building it before anyone has asked spends half a
six-minute encode on a listing that may never reply.

Both runs write the same .last_build.json rung, "delivery", because that key names
the intermediate lineage and not the cut family. That is what makes run 2 cheap:
it finds run 1's record with preset, pacing, card and photo_state() unchanged and
takes --finish-only, about a minute. Change the photos or the pacing in between
and rebuild_reason() correctly forces a full rebuild off the current photos. Two
orthogonal questions, two mechanisms that already existed: out/ answers "which run
is this", .last_build.json answers "can the stitch be reused".

It runs make_tour.py as a subprocess, exactly as the dashboard did, so the script's
contract is untouched: it reads the working directory and knows nothing about the
agents/<brand>/<listing> layout. Locking stays make_tour.py's job -- it takes
.build.lock with O_EXCL and releases it on exit. This file only READS the lock to
report it, and must never write it: doing so would lock the build out of its own
folder.

make_tour.py does not read brand.json. The wizard resolves
DEFAULTS -> brand.json -> the listing's config.json and writes the effective values
back into config.json, which stays the single record of what produced a delivered
video months later.

Importing make_tour executes that module's own config load against THIS process's
working directory, so per-listing values are always read from the listing's
config.json here -- never from make_tour's module constants.

Two things this file does that make_tour.py cannot:

  output_prefix. The cuts are named after the agent, but make_tour.py must not
  learn the agents/<brand>/<listing> layout. So the fallback for a blank agent_name
  -- the brand folder -- is resolved here and handed over as a plain config value.

  Folder naming for "+ New". A brokerage or listing typed at the prompt is passed
  through make_tour._slug -- the same function that names the output files -- so a
  hand-started folder still lands on the scrape's naming rule instead of carrying
  spaces, capitals and apostrophes into a path. It is the scraper that should be
  naming folders; this only keeps the manual door from producing a name the scrape
  could never agree with. A name that slugifies to nothing is refused.

  The PII gate's wiring. hooks/pre-push is committed but core.hooksPath is
  per-clone config, so a fresh clone has the gate present and OFF — which reads
  exactly like the gate passing. The home screen checks the wiring and shouts,
  and runs check_pii.py's own scan regardless, because libgit2-based clients do
  not run git hooks at all.

  A start line for a folder the scrape never named. A listing with photos and
  no config.json -- one that was downloaded by hand, or predates the scrape --
  used to read "not in leads.csv" in the roll-up forever and could never show as
  ready, although the picker already offered it and the question set already
  wrote its config. Provenance is a fact about the folder, not a blocker on it:
  it is reported beside the real next action, and again when the folder is
  picked. The folder is NOT renamed and status.py still reports it as
  unverifiable -- the scrape stays the only naming authority, and it cannot name
  a listing it has no row for.

  The resolution verdict. When neither preset clears, this used to REFUSE, at the
  end of a run, after the question set and a draft had already been paid for,
  having computed the identical answer at preflight in the first second. It now
  states the count, the worst file and its upscale factor, then builds all six at
  720p. The gate is unchanged as a measurement; what changed is that it reports
  rather than decides. The verdict is stated at preflight, before the build and
  again after it -- it is not carried in the output filenames.

  --auto answers the same short question set from config.json/brand.json alone
  -- never input() -- and walks every listing that has no cuts yet straight
  through to the 3 sample_ cuts, skipping the draft rung entirely. Before it
  stitches anything it scores every photo in photos/ for the one judgment call
  no default can safely make: whether it is a floor plan or whole-house layout
  image, which must never appear in the video (PROGRESS.md 4.2). A hit halts
  that one listing -- printed, never deleted or renamed -- and the rest of the
  batch keeps going. Delete the file by hand and rerun --auto, bare or scoped
  to that brand/listing, to pick back up; nothing about that halt is recorded
  anywhere, so re-running is the entire resume mechanism. It never builds a
  draft and never publishes -- the sample cuts already are the reviewed
  artifact, and publish.py's email draft can only be written from an
  already-uploaded public URL, so auto-publishing would skip the human look
  this feature exists to force. This is the one place PROGRESS.md 7's "do not
  run a video build without asking" is deliberately narrowed; the interactive
  flow above is unchanged, byte for byte, whenever --auto is not the argument
  typed.
"""

import glob
import importlib.util
import json
import os
import shutil
import subprocess
import sys

import floorplan
import make_tour
import prospects
import publish

ROOT = os.path.dirname(os.path.abspath(__file__))
LISTINGS_ROOT = os.path.join(ROOT, "agents")
ASSETS_ROOT = os.path.join(ROOT, "global_assets")
SCRIPT = os.path.join(ROOT, "make_tour.py")
PUBLISH = os.path.join(ROOT, "publish.py")

# kind -> (subdirectory of global_assets/, accepted extensions)
KINDS = {
    "logo": ("logos", ["png"]),
    "lower_third": ("lower_thirds", ["png"]),
    "music": ("music", ["mp3"]),
}
LOCK = ".build.lock"
STATE = ".last_build.json"
BRAND_FILE = "brand.json"
SHEET = "contact_sheet.png"
DRAFT_OUT = "draft.mp4"
# reason: these two reshape the stitched intermediate itself, so changing either
# invalidates it and rules out the fast --finish-only path.
PACING_KEYS = ("clip_seconds", "xfade_seconds")
PRESETS = {"1080p": (1920, 1080), "720p": (1280, 720)}

DEFAULTS = {
    "clip_seconds": 4.0,
    "xfade_seconds": 0.5,
    "brand_persistent": True,
    "brand_in": 0.8,
    "brand_out": 6.5,
    "card": "outro",
    "card_seconds": 5.0,
    "lower_third": None,
    "logo": None,
    "music": None,
    "agent_name": "",
    "agent_phone": "",
    "brokerage": "",
    "address": "",
    "output_prefix": "",
    # reason: DEFAULTS had no watermark key, questions() never asked for one, and
    # the bare fallback "viabolat.png" resolves nowhere -- the file lives only in
    # global_assets/logos/. Any listing whose config.json was not written by the
    # scraper therefore shipped UNWATERMARKED sample_ cuts, silently, and
    # publish.py uploads on the filename alone. The scraper already pins this
    # exact path (scraper/photos.py); this is the same pin for the other door in.
    "watermark": "global_assets/logos/viabolat.png",
}
# What a brand sets once and every listing under it inherits. The address is
# per-property and never inherited -- and neither is the agent.
#
# reason: agent_name and agent_phone were in this tuple, and questions() offered
# to save them as brand defaults with the confirm defaulting to YES. A brand
# folder is keyed on the BROKERAGE, and leads.csv currently lists two agents
# under Coldwell Banker Realty - Boston, two under Gibson Sotheby's and two under
# Serhant. So one operator answering yes once would have put their own phone
# number on the other agent's card, lower third and output filenames, on every
# listing that brokerage owns -- silently, because load_config() layers brand.json
# under config.json without saying so. See
# _rules/brand-json-carries-no-agent-identity.md.
# brokerage stays: it is the same string for every listing a brand owns, which is
# what a brand default IS. tests/test_brand_scope.py fails if the two agent keys
# come back.
BRAND_KEYS = ("logo", "music", "clip_seconds", "xfade_seconds",
              "brand_persistent", "brand_in", "brand_out",
              "card", "card_seconds", "card_style", "card_theme", "accent",
              "font", "brokerage")
# Never inherited from a brand, at either end -- stripped on read as well as on
# write, so a hand-edited or legacy brand.json cannot reintroduce them either.
AGENT_KEYS = ("agent_name", "agent_phone")

CARD_MODES = [("outro", "Outro card only (recommended)"),
              ("both", "Intro and outro"),
              ("intro", "Intro card only"),
              ("none", "No card")]


# ---- asking -----------------------------------------------------------------

def say(msg=""):
    print(msg, flush=True)


def rule(title):
    say(f"\n\033[1m{title}\033[0m\n" + "-" * max(len(title), 20))


def ask(question, default="", auto=False):
    if auto:
        return default
    hint = f" [{default}]" if default != "" else ""
    try:
        answer = input(f"{question}{hint}: ").strip()
    except EOFError:
        raise SystemExit("\nNo input available. Run tour.py in a terminal.")
    return answer or default


def confirm(question, default=True, auto=False):
    if auto:
        return default
    d = "Y/n" if default else "y/N"
    while True:
        a = ask(f"{question} ({d})", "y" if default else "n").lower()
        if a in ("y", "yes"):
            return True
        if a in ("n", "no"):
            return False
        say("  Answer y or n.")


def pick(question, options, default=0, extra=None, auto=False):
    """Numbered menu. options is [(value, label)]. extra adds a trailing choice."""
    items = list(options) + ([extra] if extra else [])
    if auto:
        return items[default][0]
    say(f"\n{question}")
    for i, (_, label) in enumerate(items, 1):
        say(f"  {i}. {label}" + ("   (default)" if i - 1 == default else ""))
    while True:
        a = ask("Choose", str(default + 1))
        if a.isdigit() and 1 <= int(a) <= len(items):
            return items[int(a) - 1][0]
        say(f"  Enter 1-{len(items)}.")


def number(question, default, lo, hi, auto=False):
    if auto:
        return float(default)
    while True:
        a = ask(question, str(default))
        try:
            v = float(a)
        except ValueError:
            say("  Enter a number.")
            continue
        if lo <= v <= hi:
            return v
        say(f"  Between {lo} and {hi}.")


# ---- filesystem -------------------------------------------------------------

def _dirs(path):
    if not os.path.isdir(path):
        return []
    return sorted(d for d in os.listdir(path)
                  if os.path.isdir(os.path.join(path, d)) and not d.startswith("."))


def brands():
    return _dirs(LISTINGS_ROOT)


def listings(brand):
    return _dirs(os.path.join(LISTINGS_ROOT, brand))


def assets(kind):
    sub, exts = KINDS[kind]
    d = os.path.join(ASSETS_ROOT, sub)
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d)
                  if f.rsplit(".", 1)[-1].lower() in exts)


def asset_path(kind, name):
    """Repo-relative path, the form written into config.json.

    reason: make_tour._asset() retries an unresolved path beside the script, so a
    repo-relative value stays readable in config.json AND resolves from a listing
    folder. An absolute path would break the moment the project is moved.
    """
    return f"global_assets/{KINDS[kind][0]}/{name}" if name else None


def resolve(listing_dir, path):
    """Where make_tour will actually find this asset, or None. Same two-step it
    uses: the listing folder first, then beside the script."""
    if not path:
        return None
    for candidate in (os.path.join(listing_dir, path), os.path.join(ROOT, path)):
        if os.path.exists(candidate):
            return candidate
    return None


def photos(listing_dir):
    d = os.path.join(listing_dir, "photos")
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d)
                  if os.path.splitext(f)[1].lower() in make_tour.PHOTO_EXTS)


def photo_paths(listing_dir):
    return [os.path.join(listing_dir, "photos", f) for f in photos(listing_dir)]


def photo_state(listing_dir):
    d = os.path.join(listing_dir, "photos")
    return [[f, os.path.getmtime(os.path.join(d, f)),
             os.path.getsize(os.path.join(d, f))] for f in photos(listing_dir)]


# ---- config -----------------------------------------------------------------

def _read_json(path, label):
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        say(f"  WARNING: {label} is unreadable ({e}) -- falling back to defaults.")
        return {}


def load_brand(brand):
    """A brand's shared defaults, with any agent identity stripped out.

    reason: save_brand() can no longer write agent_name or agent_phone, but nine
    brand.json files already exist and any of them can be hand-edited. Filtering
    on read too means a brand.json that carries an agent -- from an older build,
    an editor, or a copy-paste -- still cannot leak that agent onto a second
    agent's listing through load_config(). See AGENT_KEYS.
    """
    got = _read_json(os.path.join(LISTINGS_ROOT, brand, BRAND_FILE), BRAND_FILE)
    dropped = [k for k in AGENT_KEYS if got.get(k)]
    if dropped:
        say(f"  IGNORING {', '.join(dropped)} in {brand}/{BRAND_FILE}: a brand "
            f"has many agents. Those two live in the listing's config.json.")
    return {k: v for k, v in got.items() if k not in AGENT_KEYS}


def save_brand(brand, cfg):
    out = {k: v for k, v in cfg.items()
           if k in BRAND_KEYS and k not in AGENT_KEYS
           and v is not None and v != ""}
    with open(os.path.join(LISTINGS_ROOT, brand, BRAND_FILE), "w") as f:
        json.dump(out, f, indent=2)
        f.write("\n")


def load_config(listing_dir, brand):
    """Effective settings: DEFAULTS -> brand.json -> the listing's own config.json.

    reason: the brokerage logo, the music bed and the agent's own details are
    identical on every listing that brokerage owns; only the address and the photos
    really change. Inheriting them removes both the repeated typing and the
    repeated questions.
    """
    cfg = dict(DEFAULTS)
    cfg.update(load_brand(brand))
    cfg.update(_read_json(os.path.join(listing_dir, "config.json"), "config.json"))
    return cfg


def save_config(listing_dir, cfg):
    # reason: omit keys left unset so make_tour falls back to its own constants
    # rather than being handed an explicit null it would treat as a path.
    out = {k: v for k, v in cfg.items() if v is not None and v != ""}
    with open(os.path.join(listing_dir, "config.json"), "w") as f:
        json.dump(out, f, indent=2)
        f.write("\n")


def runtime(n, cfg):
    """Finished length, the same arithmetic make_tour prints at the end of a run."""
    clips = [cfg["clip_seconds"]] * n
    if cfg["card"] in ("intro", "both"):
        clips.insert(0, cfg["card_seconds"])
    if cfg["card"] in ("outro", "both"):
        clips.append(cfg["card_seconds"])
    if not clips:
        return 0.0
    return sum(clips) - (len(clips) - 1) * cfg["xfade_seconds"]


# ---- readiness --------------------------------------------------------------

def gate_report(listing_dir):
    """{preset: [(path, "WxH", upscale)]} — which photos block which preset.

    reason: reuses make_tour.gate_failures so the wizard and the build apply one
    rule, and answers before any encoding what used to surface only after a
    five-minute render had already failed.
    """
    paths = photo_paths(listing_dir)
    return {name: make_tour.gate_failures(paths, w, h)
            for name, (w, h) in PRESETS.items()}


def best_preset(report):
    """Highest preset the photos can actually feed, or None if they feed neither."""
    for name in PRESETS:                      # 1080p first, then 720p
        if not report[name]:
            return name
    return None


def check_assets(listing_dir, cfg):
    """[(label, resolved path or None, note)] for everything the build will read."""
    rows = []
    lt = resolve(listing_dir, cfg.get("lower_third") or "lower_third.png")
    rows.append(("lower third", lt,
                 "hand-made plate" if lt else
                 "drawn from the address, name and phone below"))
    logo = resolve(listing_dir, cfg.get("logo") or "logo.png")
    rows.append(("logo", logo,
                 "top-left, whole video" if logo else
                 "no mark -- the card falls back to the type-only design"))
    music = resolve(listing_dir, cfg.get("music") or "music.mp3")
    rows.append(("music", music, "" if music else "the tour will be silent"))
    wm = resolve(listing_dir, cfg.get("watermark") or "viabolat.png")
    rows.append(("sample watermark", wm, "" if wm else
                 "MISSING -- the sample build will refuse. Point 'watermark' at "
                 "global_assets/logos/viabolat.png"))
    return rows


def preflight(listing_dir, cfg):
    """Everything worth knowing before an encode starts. Returns the gate report."""
    names = photos(listing_dir)
    rule("Preflight")
    say(f"{len(names)} photo(s), in this order:")
    for i, f in enumerate(names, 1):
        say(f"  {i:>3}. {f}")
    if names and not any(f[:1].isdigit() for f in names):
        say("  NOTE: no numeric prefixes -- this is plain alphabetical order.")

    report = gate_report(listing_dir)
    preset = best_preset(report)
    say("")
    if preset:
        say(f"Resolution: clears {preset}.")
        if preset == "720p":
            worst = min(report["1080p"], key=lambda r: r[1])
            say(f"  1080p is blocked by {len(report['1080p'])} photo(s), "
                f"smallest {worst[1]}. See IDEA.md 4.")
    else:
        worst = max(report["720p"], key=lambda r: r[2])
        say(f"Resolution: BELOW PAR. {len(report['720p'])} of {len(names)} "
            f"photo(s) miss even 720p, which needs "
            f"{make_tour.gate_min(*PRESETS['720p'])}px on the long edge:")
        for path, size, up in report["720p"][:5]:
            say(f"  {os.path.basename(path):<32} {size:>10}  "
                f"would upscale {up:.1f}x")
        if len(report["720p"]) > 5:
            say(f"  ... and {len(report['720p']) - 5} more")
        say(f"  Worst: {os.path.basename(worst[0])} at {worst[1]}, "
            f"upscaled {worst[2]:.1f}x.")
        say("  These will still build, at 720p, and they will be soft. The "
            "shortfall is\n  reported here and again when the build finishes; it "
            "is not in the\n  filenames. To fix it properly you need the "
            "photographer's originals or\n  the MLS back end -- see IDEA.md 4.")

    say("")
    for label, path, note in check_assets(listing_dir, cfg):
        where = os.path.relpath(path, ROOT) if path else "MISSING"
        say(f"{label:<17} {where}" + (f"   ({note})" if note else ""))

    if os.path.exists(os.path.join(listing_dir, LOCK)):
        say(f"\nWARNING: {LOCK} is present -- another build may be running here.")
    return report


# ---- questions --------------------------------------------------------------

def questions(listing_dir, brand, cfg, auto=False):
    """The short set: what the card says, what shape it is, how long it runs.

    auto=True answers every prompt below from cfg alone -- see the module
    docstring's --auto paragraph. The logo pick and the music pick are the two
    exceptions: each only fires when nothing already resolves, and guessing
    which brokerage mark or which track is a choice only a human should make,
    so under auto they are skipped outright and cfg["logo"]/cfg["music"] are
    left unset rather than defaulted.
    """
    rule("What goes on screen")
    was_brokerage = cfg.get("brokerage")
    cfg["address"] = ask("Property address", cfg.get("address", ""), auto=auto)
    cfg["agent_name"] = ask("Agent name", cfg.get("agent_name", ""), auto=auto)
    cfg["agent_phone"] = ask("Agent phone", cfg.get("agent_phone", ""), auto=auto)
    cfg["brokerage"] = ask("Brokerage (card only, used when there is no logo)",
                           cfg.get("brokerage", ""), auto=auto)
    # reason: the agent's name and phone are deliberately NOT offered as brand
    # defaults. This prompt used to save all three, defaulting to yes, which put
    # one agent's phone number on every other agent's listing at the same
    # brokerage. See AGENT_KEYS.
    if cfg["brokerage"] != was_brokerage and cfg["brokerage"] and \
            confirm(f"Save the brokerage as the {brand} default?", True, auto=auto):
        save_brand(brand, {**load_brand(brand), "brokerage": cfg["brokerage"]})

    if not auto and not resolve(listing_dir, cfg.get("logo")):
        available = assets("logo")
        if available:
            choice = pick("No logo set for this brand. Pick one?",
                          [(f, f) for f in available], default=0,
                          extra=(None, "No logo -- use the type-only card"))
            cfg["logo"] = asset_path("logo", choice)

    rule("The edit")
    cfg["card"] = pick("Intro / outro card?",
                       CARD_MODES,
                       default=[m[0] for m in CARD_MODES].index(cfg.get("card",
                                                                        "outro")),
                       auto=auto)
    if cfg["card"] != "none":
        cfg["card_seconds"] = number("Card length in seconds",
                                     cfg.get("card_seconds", 5.0), 2.0, 10.0,
                                     auto=auto)
    # reason: the drawn lower third and the card carry the SAME three lines, by
    # construction -- both are rendered from address/agent_name/agent_phone. A
    # persistent lower third plus an outro card therefore shows the operator's
    # details twice in one video. finish() already keeps the two from overlapping
    # in TIME, but that rule says nothing about the redundancy across the whole
    # cut. So when a card is carrying those lines, the lower third defaults to
    # introducing the property and then getting out of the way. Still overridable:
    # a hand-made lower_third.png says something the card does not, so it is
    # exempt.
    # reason: `or "lower_third.png"` is not optional here. cfg["lower_third"] is
    # None until someone sets a path, so resolving the bare key misses a plate
    # sitting at the default filename -- which is where every hand-made one sits.
    # check_assets() resolves it the same way; the two must not diverge.
    duplicated = (cfg["card"] != "none" and
                  not resolve(listing_dir,
                              cfg.get("lower_third") or "lower_third.png"))
    default_persistent = bool(cfg.get("brand_persistent", True))
    if duplicated:
        say(f"\n  Note: the {cfg['card']} card already carries the address, name "
            f"and phone.\n  A lower third up for the whole tour prints them a "
            f"second time.")
        default_persistent = False
    cfg["brand_persistent"] = confirm(
        "Keep the lower third up for the whole tour? "
        "(n = it clears after the opening seconds)",
        default_persistent, auto=auto)
    if not cfg["brand_persistent"]:
        cfg["brand_in"] = number("  Lower third in at", cfg.get("brand_in", 0.8),
                                 0.0, 60.0, auto=auto)
        cfg["brand_out"] = number("  and out at", cfg.get("brand_out", 6.5),
                                  cfg["brand_in"] + 0.5, 120.0, auto=auto)

    if not auto and not resolve(listing_dir, cfg.get("music") or "music.mp3"):
        available = assets("music")
        if available and confirm("No music set. Pick a track?", True):
            cfg["music"] = asset_path(
                "music", pick("Track", [(f, f) for f in available]))

    cfg["clip_seconds"] = number("Seconds per photo", cfg.get("clip_seconds", 4.0),
                                 1.0, 15.0, auto=auto)
    # reason: make_tour names the cuts after the agent, but it does not know the
    # agents/<brand>/<listing> layout and must not learn it. So the fallback for a
    # blank agent_name is resolved HERE, where the brand IS known, and handed over
    # as a plain config value like every other inherited setting.
    cfg["output_prefix"] = "" if cfg.get("agent_name", "").strip() else brand
    save_config(listing_dir, cfg)
    n = len(photos(listing_dir))
    say(f"\nSaved to config.json. {n} photo(s) -> about "
        f"{runtime(n, cfg):.0f}s of video.")
    return cfg


# ---- photos in ---------------------------------------------------------------

def import_photos(listing_dir):
    """Copy a folder of photos in, and offer to number them in tour order."""
    dest = os.path.join(listing_dir, "photos")
    os.makedirs(dest, exist_ok=True)
    src = os.path.expanduser(ask("Folder with the photos (blank to skip)"))
    if not src:
        return
    if not os.path.isdir(src):
        say(f"  {src} is not a folder.")
        return import_photos(listing_dir)
    found = sorted(f for f in os.listdir(src)
                   if os.path.splitext(f)[1].lower() in make_tour.PHOTO_EXTS)
    if not found:
        say(f"  No photos in {src}.")
        return
    for f in found:
        shutil.copy2(os.path.join(src, f), os.path.join(dest, f))
    say(f"  Copied {len(found)} photo(s).")


def offer_prefixes(listing_dir, auto=False):
    """Renumber photos/ in its current alphabetical order, on confirmation.

    reason: the filename prefix IS the tour order -- there is no manifest and there
    is never going to be one, because a sidecar drifts out of sync with the folder.
    A folder with no prefixes still builds, it just builds alphabetically, and that
    silent failure has shipped once already. So offer the prefixes out loud.

    auto=True still renames -- alphabetical is the correct order once numbered,
    just not silently -- it only skips asking first.
    """
    names = photos(listing_dir)
    if not names or any(f[:1].isdigit() for f in names):
        return
    say("\nThese photos have no number prefixes, so they would build in plain "
        "alphabetical order:")
    for f in names[:5]:
        say(f"  {f}")
    if len(names) > 5:
        say(f"  ... and {len(names) - 5} more")
    if not confirm("Add 010_, 020_ ... prefixes in that order? "
                   "(rename them later to reorder)", True, auto=auto):
        return
    d = os.path.join(listing_dir, "photos")
    for i, f in enumerate(names, 1):
        os.rename(os.path.join(d, f), os.path.join(d, f"{i * 10:03d}_{f}"))
    say(f"  Renamed {len(names)} photo(s).")


# ---- build ------------------------------------------------------------------

def load_state(listing_dir):
    return _read_json(os.path.join(listing_dir, STATE), STATE)


def save_state(listing_dir, rung, cfg, preset):
    # reason: draft and delivery keep separate records because they stitch separate
    # intermediates. One shared record would let a draft's state authorise a
    # --finish-only delivery build, which is exactly how a soft cut ships.
    state = load_state(listing_dir)
    state[rung] = {"preset": preset, "cfg": cfg, "photos": photo_state(listing_dir)}
    with open(os.path.join(listing_dir, STATE), "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


def rebuild_reason(listing_dir, cfg, preset, rung, silent_name):
    """Why this rung cannot take the fast --finish-only path, or None if it can."""
    if not os.path.exists(os.path.join(listing_dir, silent_name)):
        return f"no {silent_name} to reuse"
    last = load_state(listing_dir).get(rung)
    if not last:
        return "no record of the previous build"
    if last.get("preset") != preset:
        return "output preset changed"
    if any(last.get("cfg", {}).get(k) != cfg[k] for k in PACING_KEYS):
        return "clip pacing changed"
    # reason: the card rides in the stitched branded cut, so changing it or its
    # length invalidates that intermediate exactly like the pacing keys do.
    if any(last.get("cfg", {}).get(k) != cfg[k] for k in ("card", "card_seconds")):
        return "the card changed"
    if last.get("photos") != photo_state(listing_dir):
        return "photos changed"
    return None


def delivery_flags(listing_dir, cfg, preset, lowres=False, cuts="both"):
    """(flags, full_rebuild_reason or None) for a full-quality build.

    cuts: "sample" | "delivery" | "both" -- which output family to write. The
    stitch is the same either way, which is what makes the second run cheap: a
    sample-only run has no record yet and takes --keep-work, so work_silent.mp4
    and work_branded.mp4 survive; the delivery run that follows finds that same
    "delivery" record unchanged and takes --finish-only. The rung key names the
    intermediate lineage, not the cut family -- so it stays "delivery" for both,
    and no new state is invented to hold the difference.

    reason: --allow-lowres permits the build and changes nothing about the encode
    or the output names, so it is deliberately absent from the state's preset
    string. The verdict only flips when the photo set changes, and photo_state()
    already forces a full rebuild on that.
    """
    flags = ["--720p"] if preset == "720p" else []
    if lowres:
        flags.append("--allow-lowres")
    if not resolve(listing_dir, cfg.get("music") or "music.mp3"):
        flags.append("--no-music")
    if cuts == "sample":
        flags.append("--samples-only")
    elif cuts == "delivery":
        flags.append("--delivery-only")
    reason = rebuild_reason(listing_dir, cfg, preset, "delivery",
                            "work_silent.mp4")
    # reason: --finish-only reuses the stitched cut, so it can only ever apply
    # branding, music and timing. Anything upstream of the stitch needs a full run.
    flags.append("--keep-work" if reason else "--finish-only")
    return flags, reason


def build_choice(st):
    """Which family to write now -- "sample" | "delivery" | "both" -- or None.

    reason: this is the confirm for rung 3, not an extra prompt on top of one.
    The stage derived from out/ picks the default; every other route stays
    reachable, because a client who has already paid should not have to build a
    proof first, and a rebuild of either family must remain possible.
    """
    if st == "sample":
        return pick("No cuts built yet.", [
            ("sample", "Sample cuts -- the 3 watermarked cuts the client reviews"),
            ("both", "All six now -- sample and delivery together"),
            (None, "Not now"),
        ], default=0)
    if st == "delivery":
        return pick("The sample cuts are built. Has the client signed off?", [
            ("delivery", "Yes -- build the 3 tour_ deliverables"),
            ("sample", "No -- rebuild the sample cuts"),
            (None, "Not now"),
        ], default=0)
    return pick("All six cuts exist. Rebuild which?", [
        (None, "Nothing -- leave them"),
        ("sample", "The 3 sample_ cuts"),
        ("delivery", "The 3 tour_ deliverables"),
        ("both", "All six"),
    ], default=0)


def draft_flags(listing_dir, cfg):
    """(flags, full_rebuild_reason or None) for the one-cut draft.

    reason: a draft is a preview by definition, so it always carries
    --allow-lowres. That is the flag's actual purpose, and routing it here is what
    removes the temptation to reach for the bypass on a build a client will see.
    """
    flags = ["--draft", "--allow-lowres"]
    if not resolve(listing_dir, cfg.get("music") or "music.mp3"):
        flags.append("--no-music")
    reason = rebuild_reason(listing_dir, cfg, "720p", "draft", "work_draft.mp4")
    flags.append("--keep-work" if reason else "--finish-only")
    return flags, reason


def run_build(listing_dir, flags):
    """Stream make_tour.py straight through to this terminal. Returns exit code."""
    say(f"\n$ python3 make_tour.py {' '.join(flags)}\n")
    # reason: make_tour reports progress with bare print(), which block-buffers the
    # moment stdout is not a tty -- -u keeps the log arriving while it works.
    return subprocess.run([sys.executable, "-u", SCRIPT] + flags,
                          cwd=listing_dir).returncode


def clear_review_artifacts(listing_dir):
    """Delete rung-1/rung-2 review files once the sample cuts exist to replace them.

    reason: contact_sheet.png answered "is the order right" and draft.mp4 answered
    "does the edit feel right" -- once out/ holds the sample_ cuts those questions
    are settled and both files are pure carry-weight. work_draft.mp4/clips_draft/
    are NOT this function's job: a delivery build already clears that lineage
    itself, regardless of --keep-work -- see a-build-deletes-its-own-intermediates.md.
    Duplicating that removal here would be a second place doing one thing.
    Returns the names actually removed.
    """
    removed = []
    for name in (SHEET, DRAFT_OUT):
        p = os.path.join(listing_dir, name)
        if os.path.exists(p):
            os.remove(p)
            removed.append(name)
    return removed


def outputs(listing_dir):
    d = os.path.join(listing_dir, "out")
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d) if f.endswith(".mp4"))


def cut_families(listing_dir):
    """{"sample": [...], "tour": [...]} -- what is already in out/.

    publish.family() is the single authority on which prefix means what. Asking
    it rather than testing the prefix here keeps one implementation of the
    sample_/tour_ boundary, which is the boundary the whole two-family split
    exists to hold.
    """
    fams = {"sample": [], "tour": []}
    for f in outputs(listing_dir):
        kind = publish.family(f)
        if kind in fams:
            fams[kind].append(f)
    return fams


def stage(listing_dir):
    """"sample" | "delivery" | "delivered" -- which run this listing is on.

    Derived from out/ and nothing else. No marker file, no stage key in
    config.json: the cuts on disk ARE the record of what has been built, the same
    way the photo order is the filename prefix and nothing else. .last_build.json
    answers a different question -- whether the STITCH can be reused -- and its
    rung key names the intermediate lineage, not the cut family. The two stay
    orthogonal on purpose.
    """
    fams = cut_families(listing_dir)
    if fams["tour"]:
        return "delivered"
    if fams["sample"]:
        return "delivery"
    return "sample"


# ---- rung 4: publish ---------------------------------------------------------

def sample_cuts(listing_dir):
    """The cuts in out/ that publish.py would accept. publish.py is the gate."""
    return [f for f in outputs(listing_dir) if publish.publishable(f)[0]]


def publish_rung(listing_dir, quiet=True):
    """Offer to put the sample_ cuts on the review bucket. Optional, and silent
    when there is no key configured.

    reason: publishing leaves the machine, so it is the one rung that defaults to
    NO. The gate itself lives in publish.py -- this only offers it, and asks the
    uninformed half of the question ("do you want to do this at all"). publish.py
    prints the file list, the exact remote paths and the URLs, then asks the
    informed half. Two prompts is the right number when the second one is the
    first sight of what actually goes public.

    An operator with no Supabase key is not nagged about it on every build.
    """
    publish.load_dotenv()
    if not (os.environ.get("SUPABASE_URL")
            and os.environ.get("SUPABASE_SERVICE_KEY")):
        # reason: quiet after a build -- an operator with no Supabase key is not
        # nagged on every delivery. Not quiet when publishing is the thing they
        # asked for from the menu, where silence would read as "it worked".
        if not quiet:
            say("\n  No Supabase credentials, so nothing can be published.")
            say("  Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env beside "
                "publish.py -- see\n  .env.example. Missing either is exit 2, "
                "never a quiet no-op.")
        return
    cuts = sample_cuts(listing_dir)
    if not cuts:
        return
    rule("4. Publish")
    say("These are the watermarked review cuts. tour_ cuts never publish from "
        "here --\nthe deliverable goes out after sign-off, by hand.")
    for f in cuts:
        say(f"  out/{f}")
    if not confirm("\nPublish the sample cuts?", False):
        say("Nothing was uploaded. Run publish.py from the listing folder any "
            "time.")
        return
    subprocess.run([sys.executable, "-u", PUBLISH, listing_dir])


# ---- the optional pair of eyes ----------------------------------------------

CHECK_PROMPT = (
    "contact_sheet.png in this folder is a numbered grid of real estate listing "
    "photos, in the order they will appear in a video tour. Read it and reply with "
    "a plain list: for each numbered cell, the room you actually see, and whether "
    "the filename under it agrees. Then say whether the running order makes sense "
    "for a walkthrough (exterior or main living space first, bedrooms and baths in "
    "the middle, never opening or closing on a bathroom). Propose renames only "
    "where the filename is wrong. Do not rename anything yourself."
)


def check_photos(listing_dir):
    """Ask Claude to read the contact sheet. Optional, degrades, renames nothing.

    reason: this catches exactly one failure that no amount of Python can see -- a
    filename that describes the wrong room. One listing here shipped 16 of 17
    photos mislabelled, opening and closing on a bedroom, and only a human eye on
    the contact sheet caught it. It reuses the Claude Code login already on this
    machine; there is no key to set up and nothing to install.
    """
    if run_build(listing_dir, ["--contact-sheet"]) != 0:
        return False
    if not shutil.which("claude"):
        say("\nclaude is not on PATH, so the automatic check is unavailable. "
            f"Open {SHEET} and read it yourself -- that is the check that matters.")
        return False
    say("\nAsking Claude to read the contact sheet (this takes a minute)...\n")
    try:
        r = subprocess.run(["claude", "-p", CHECK_PROMPT,
                            "--allowedTools", "Read"],
                           cwd=listing_dir, text=True, timeout=300)
        if r.returncode != 0:
            say(f"\nThe check exited {r.returncode}. Read {SHEET} yourself.")
            return False
    except (OSError, subprocess.TimeoutExpired) as e:
        say(f"\nThe check could not run ({e}). Read {SHEET} yourself.")
        return False
    say("\nNothing was renamed. Photo order lives in the filename prefix -- "
        "rename the files to act on any of that.")
    return True


# ---- the home screen ---------------------------------------------------------
#
# reason: the pipeline worked, but its SURFACE grew back into the thing tour.py
# was built to kill. An operator had eight commands to remember -- run.py,
# status, tour, publish, check_pii, make_tour, vercel, unittest -- and nothing
# told them which was a decision and which was a chore. Sorted by what they
# actually are, only one is a decision. check_pii is a gate, so it became a
# pre-push hook. vercel is one-time setup, so it left the recurring runbook.
# publish was already a rung. status is "where am I", so it is the screen this
# opens on. run.py is a real action, but a DETECTABLE one. What is left is
# one command, a roll-up and four choices. Nothing behind this screen changed:
# every rung, prompt, default and refusal in the build flow is what it was, and
# every script still runs standalone from the CLI.

CHECK_PII = os.path.join(ROOT, "check_pii.py")
DUMPS = os.path.join(ROOT, "scraper", "dumps")
RUN_SCRAPER = os.path.join(ROOT, "scraper", "run.py")

_STATUS = ()        # () = not tried yet; (module, None) or (None, why) after


def _sibling(name, relpath):
    """Import a module beside this one under a private name."""
    path = os.path.join(ROOT, relpath)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    # reason: scraper/photos.py imports lead as a flat sibling --
    # there is no package -- so its own folder has to be importable while it
    # executes. Same two lines status.py uses for the same reason.
    sys.path.insert(0, os.path.dirname(path))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.pop(0)
    return mod


def load_status():
    """(status module, None) or (None, why). Never raises, cached.

    reason: status.py runs _load_scraper() at module scope, so importing it
    loads the scraper. In a tree copied without scraper/ that raises, and an
    exception on the way to the menu would take a build down with it. This
    mirrors the project's existing asymmetry: a broken cosmetic layer warns and
    drops out, only a broken watermark stops a build. A roll-up is cosmetic --
    say why it is missing, then carry on to the listing picker.
    """
    global _STATUS
    if _STATUS == ():
        try:
            _STATUS = (_sibling("status_for_tour", "status.py"), None)
        except Exception as e:              # noqa: BLE001 -- deliberately broad
            _STATUS = (None, f"{type(e).__name__}: {e}")
    return _STATUS


def unimported_dumps():
    """[(filename, brand, listing)] for dumps with no folder under agents/.

    reason: DERIVED, never recorded. The alternative -- a .processed marker, or
    a manifest of handled dumps -- is the photo-order failure one level up:
    state kept beside the artifacts drifts out of sync with them, and then the
    record is wrong in a way nothing detects. A folder either exists or it does
    not, and that answer cannot go stale. It also means deleting a listing
    folder correctly re-offers its dump, which a marker file would not.

    Names are not derived here at all: photos.py's target_for() is the one
    function that turns a dump into the folder it scaffolds, and the scraper
    calls the same one. A second copy of that decision would be a second naming
    authority, and a near-miss would report an imported listing as pending
    forever.
    """
    status, _why = load_status()
    if status is None or not os.path.isdir(DUMPS):
        return []
    out = []
    for name in sorted(os.listdir(DUMPS)):
        if not name.lower().endswith(".txt") or name.startswith("."):
            continue
        try:
            with open(os.path.join(DUMPS, name), encoding="utf-8",
                      errors="ignore") as f:
                text = f.read()
        except OSError:
            continue
        # reason: None IS photos.py's own refusal -- a dump with neither
        # photo URLs nor an address is not a listing dump, both scraper scripts
        # exit non-zero on it, and counting it here would offer an import that
        # can only fail.
        target = status._photos.target_for(text)
        if target is None:
            continue
        brand, listing = target
        if not os.path.isdir(os.path.join(LISTINGS_ROOT, brand, listing)):
            out.append((name, brand, listing))
    return out


def hook_state():
    """(wired, why_not) for the pre-push PII gate IN THIS CLONE.

    reason: hooks/pre-push is committed, but core.hooksPath is per-clone config,
    so a fresh clone has the file present and the gate OFF -- which on screen
    looks exactly like the gate passing. That is this project's stated failure
    shape: "nothing to scan" and "nothing found" read identically and mean
    opposite things. A test cannot check the operator's clone, so this does.
    """
    hook = os.path.join(ROOT, "hooks", "pre-push")
    if not os.path.isfile(hook):
        return False, "hooks/pre-push is missing from this tree"
    if not os.access(hook, os.X_OK):
        return False, "hooks/pre-push is not executable"
    try:
        r = subprocess.run(["git", "-C", ROOT, "config", "--get",
                            "core.hooksPath"], capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"git could not be asked about core.hooksPath ({e})"
    got = r.stdout.strip() if r.returncode == 0 else ""
    if got != "hooks":
        return False, f"core.hooksPath is {got or 'unset'}, not hooks/"
    return True, None


def pii_scan():
    """(exit code, one line of detail) from check_pii.py's real scan.

    reason: defense in depth, and not theatre. The pre-push hook only fires for
    pushes that go through the git CLI; libgit2-based clients -- most IDE git
    integrations -- do not run git hooks at all, and this repo has been pushed
    by something that was not this shell. Running the same scan here does not
    depend on identifying the pusher. check_pii.py is unmodified: 0 is clean,
    1 is findings, 2 is could-not-scan, which it treats as worse than findings.
    """
    try:
        r = subprocess.run([sys.executable, CHECK_PII],
                           capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        return 2, f"could not run check_pii.py ({e})"
    if r.returncode == 0:
        return 0, None
    lines = [l.strip() for l in r.stdout.splitlines() if l.strip()]
    refusal = next((l for l in lines if "REFUSING" in l), None)
    finding = next((l for l in lines if "finding(s)" in l), None)
    return r.returncode, refusal or finding or (lines[-1] if lines else
                                                "run python3 check_pii.py")


def gate_banner():
    """One block, and only when something is wrong. Silence means armed."""
    wired, why = hook_state()
    code, detail = pii_scan()
    if code == 1:
        say(f"\n  \033[1mPII GATE: {detail}\033[0m")
        say("  Something git would publish holds a lead, a phone number or a "
            "key.\n  See it masked with:  python3 check_pii.py")
    elif code == 2:
        say(f"\n  \033[1mPII gate could not run: {detail}\033[0m")
        say("  It fails closed on purpose -- 'nothing scanned' must not read as "
            "clean.")
    if not wired:
        say(f"\n  \033[1mPII gate is NOT wired into git push here\033[0m ({why}).")
        say("  The hook is committed; enabling it is per clone:\n"
            "      git config core.hooksPath hooks")


def _indent(msg):
    return "\n".join(("  " + l if l else l) for l in msg.splitlines())


def _say_indented(msg):
    """The out= status.py's printers take, so their output lands in this menu."""
    say(_indent(msg))


def roll_up(status):
    """status.py's own rows and its own naming audit, rendered here."""
    rows, truth, known = status.survey()
    if not rows:
        say("  No listings under agents/ yet. Drop a Zillow dump in "
            "scraper/dumps/ and pick 2.")
        return
    # reason: printed through status.py's own print_rows/print_audit rather
    # than re-rendered here. Two implementations of the scrape-naming check is
    # the exact drift the check exists to catch, one level up -- and the same
    # went for the table: the copy that used to live here had already lost the
    # "N brokerage(s) need a logo" line.
    status.print_rows(rows, out=_say_indented)
    status.print_audit(*status.audit(rows, truth, known), out=_say_indented)
    try:
        prospects.rebuild(rows, status.slugify)
    except OSError as e:
        say(f"\n  prospects/ index did not rebuild ({type(e).__name__}: {e}).")


def import_dumps():
    """Rung zero: turn the pending dumps into listings. run.py, as-is."""
    pending = unimported_dumps()
    if not pending:
        say("\n  Nothing pending. Save a Zillow page dump as a .txt in "
            "scraper/dumps/ first.")
        return
    say(f"\n  This downloads photos for {len(pending)} listing(s) and appends "
        f"to leads.csv.\n  It never overwrites an existing brand.json or "
        f"config.json, so it is safe to rerun.")
    if not confirm("Run the scraper now?", True):
        return
    subprocess.run([sys.executable, "-u", RUN_SCRAPER])


def publish_action():
    """Menu route to rung 4, for a listing that is already built."""
    _brand, listing_dir = choose_listing()
    if not sample_cuts(listing_dir):
        say(f"\n  No sample_ cuts in "
            f"{os.path.relpath(listing_dir, ROOT)}/out/ -- build it first.\n"
            "  Only sample_ cuts publish. A tour_ cut goes out after sign-off, "
            "by hand.")
        return
    publish_rung(listing_dir, quiet=False)


# ---- --auto: hands-off run from pasted dump to 3 sample cuts -----------------

def auto_targets(scope=None):
    """[(brand, listing_dir)] not yet at the sample stage, optionally narrowed
    to one "brand/listing". Re-derived from out/ on every call -- see stage()
    -- so nothing about a halted listing is ever recorded, and a manual photo
    deletion needs no separate "resume" state to pick back up from.
    """
    if scope:
        brand, _, name = scope.partition("/")
        listing_dir = os.path.join(LISTINGS_ROOT, brand, name)
        if not os.path.isdir(listing_dir):
            raise SystemExit(f"No such listing: {scope}")
        return [(brand, listing_dir)] if stage(listing_dir) == "sample" else []
    return [(brand, os.path.join(LISTINGS_ROOT, brand, name))
            for brand in brands() for name in listings(brand)
            if stage(os.path.join(LISTINGS_ROOT, brand, name)) == "sample"]


def _auto_build_one(brand, listing_dir, ignore_floorplan):
    """Run one listing through --auto: contact sheet, the floor-plan check,
    then -- if clean -- the 3 sample_ cuts. Returns "built" / "flagged" /
    "error".
    """
    rule(os.path.relpath(listing_dir, ROOT))
    if not photos(listing_dir):
        say("  photos/ is empty -- nothing to build yet.")
        return "error"
    offer_prefixes(listing_dir, auto=True)
    cfg = load_config(listing_dir, brand)
    report = preflight(listing_dir, cfg)
    cfg = questions(listing_dir, brand, cfg, auto=True)

    if run_build(listing_dir, ["--contact-sheet"]) != 0:
        say("  The contact sheet failed.")
        return "error"

    if not ignore_floorplan:
        flagged = floorplan.detect(photo_paths(listing_dir))
        if flagged:
            say(f"\n  Halted -- {len(flagged)} photo(s) look like a floor plan "
                "or site map:")
            for name, why in flagged:
                say(f"    {name}  ({why})")
            say(f"  Delete the file(s) by hand, then rerun:\n"
                f"    python3 tour.py --auto "
                f"{brand}/{os.path.basename(listing_dir)}\n"
                "  A false positive can be forced through once with "
                "--ignore-floorplan-check.")
            return "flagged"

    preset = best_preset(report)
    lowres = preset is None
    if lowres:
        preset = "720p"
    flags, reason = delivery_flags(listing_dir, cfg, preset, lowres, cuts="sample")
    if reason:
        say(f"  Full rebuild: {reason}.")
    if run_build(listing_dir, flags) != 0:
        say("  The build failed. Intermediates were kept for inspection.")
        return "error"
    save_state(listing_dir, "delivery", cfg, preset)
    clear_review_artifacts(listing_dir)
    say(f"  Built {len(sample_cuts(listing_dir))} sample cut(s) in out/.")
    return "built"


def auto_flow(args):
    """python3 tour.py --auto [brand/listing] [--ignore-floorplan-check]

    Imports pending dumps, then walks every listing with no cuts yet straight
    through to the 3 sample_ cuts -- stopping a listing only on a photo the
    floor-plan detector flags. See the module docstring's --auto paragraph for
    what this deliberately does not do.
    """
    ignore_floorplan = "--ignore-floorplan-check" in args
    scope = next((a for a in args if not a.startswith("--")), None)
    if ignore_floorplan and not scope:
        raise SystemExit(
            "--ignore-floorplan-check needs a brand/listing scope:\n"
            "    python3 tour.py --auto <brand>/<listing> --ignore-floorplan-check")

    pending = unimported_dumps()
    if pending:
        say(f"Importing {len(pending)} pending dump(s)...")
        subprocess.run([sys.executable, "-u", RUN_SCRAPER])

    targets = auto_targets(scope)
    if not targets:
        say((f"{scope} already has sample cuts, or further along -- nothing "
             "for --auto to do.") if scope else
            "Nothing to build -- every listing already has sample cuts, or "
            "further.")
        return

    built = flagged = errors = 0
    for brand, listing_dir in targets:
        result = _auto_build_one(brand, listing_dir, ignore_floorplan)
        built += result == "built"
        flagged += result == "flagged"
        errors += result == "error"

    rule("Done")
    say(f"{built} built, {flagged} flagged for review, {errors} failed.")

    status, _why = load_status()
    if status is not None:
        try:
            rows, _truth, _known = status.survey()
            prospects.rebuild(rows, status.slugify)
        except OSError as e:
            say(f"prospects/ index did not rebuild ({type(e).__name__}: {e}).")


# ---- brand settings ----------------------------------------------------------

def brand_settings():
    """Edit what a brokerage sets once, and optionally push it down.

    reason: _reference/layout.md promises an explicit "Re-apply brand defaults" action
    since the Streamlit dashboard was deleted, and it has not existed anywhere
    since. A new listing inherits brand.json at creation; changing a brand
    default deliberately does NOT reach back into listings already scaffolded,
    because config.json is meant to still explain what produced a delivered
    video months later. That is the right default and the reason the explicit
    action has to exist -- otherwise fixing a brokerage's logo means hand-editing
    every config.json under it.
    """
    bs = brands()
    if not bs:
        say("\n  No brands yet. They are named by the scrape -- import a dump "
            "first.")
        return
    brand = pick("Brand", [(b, b) for b in bs], default=0)
    bcfg = load_brand(brand)
    rule(f"{brand}/brand.json")
    if bcfg:
        for k in sorted(bcfg):
            say(f"  {k} = {bcfg[k]}")
    else:
        say("  (nothing set yet -- every listing falls back to the built-in "
            "defaults)")
    say("\n  A brand holds what every listing this brokerage owns shares.")
    say("  Not the agent: leads.csv lists two agents under some brokerages, so "
        "a\n  brand-level name or phone would put one agent's details on "
        "another's video.\n  Those live in the listing's config.json.")

    for kind, label in (("logo", "Logo"), ("music", "Music bed")):
        available = assets(kind)
        if not available:
            continue
        current = bcfg.get(kind)
        options = [(f, f + ("  (current)" if asset_path(kind, f) == current
                            else "")) for f in available]
        choice = pick(f"{label}", options,
                      default=next((i for i, f in enumerate(available)
                                    if asset_path(kind, f) == current), 0),
                      extra=(None, f"No {label.lower()}"))
        bcfg[kind] = asset_path(kind, choice) if choice else None

    bcfg["brokerage"] = ask("Brokerage name (card only, when there is no logo)",
                            bcfg.get("brokerage", ""))
    bcfg["card"] = pick("Default card", CARD_MODES,
                        default=[m[0] for m in CARD_MODES].index(
                            bcfg.get("card", DEFAULTS["card"])))
    bcfg["clip_seconds"] = number("Seconds per photo",
                                  bcfg.get("clip_seconds",
                                           DEFAULTS["clip_seconds"]), 1.0, 15.0)
    save_brand(brand, bcfg)
    say(f"\n  Saved agents/{brand}/{BRAND_FILE}.")

    ls = listings(brand)
    if not ls:
        return
    say(f"\n  {len(ls)} existing listing(s) keep the values they were scaffolded "
        f"with.\n  That is deliberate -- config.json is the record of what "
        f"produced a delivered\n  video. Re-applying overwrites those keys.")
    if confirm(f"Re-apply {brand} defaults to its {len(ls)} listing(s)?", False):
        reapply_brand(brand, ls)


def reapply_brand(brand, ls):
    """Push the brand's keys down into each listing, showing every change first.

    reason: shown before written, per listing, per key. This is the one action
    in the whole tool that edits files the operator is not looking at, and a
    silent bulk write over the record of what produced a delivered video is not
    something to find out about later.
    """
    bcfg = load_brand(brand)
    # reason: AGENT_KEYS can never be here -- load_brand strips them and
    # save_brand refuses to write them -- but re-applying is the exact operation
    # that would spread them across every listing a brokerage owns if they ever
    # came back, so the filter is restated at the point of the blast radius.
    push = {k: v for k, v in bcfg.items()
            if k in BRAND_KEYS and k not in AGENT_KEYS}
    if not push:
        say("  Nothing set on the brand to apply.")
        return
    planned = []
    for name in ls:
        listing_dir = os.path.join(LISTINGS_ROOT, brand, name)
        cfg = _read_json(os.path.join(listing_dir, "config.json"), "config.json")
        changes = {k: (cfg.get(k), v) for k, v in push.items() if cfg.get(k) != v}
        if changes:
            planned.append((name, listing_dir, cfg, changes))
    if not planned:
        say("  Every listing already matches the brand. Nothing to write.")
        return
    say("")
    for name, _dir, _cfg, changes in planned:
        say(f"  {brand}/{name}")
        for k, (was, now) in sorted(changes.items()):
            say(f"    {k}: {was if was not in (None, '') else '(unset)'} -> {now}")
    if not confirm(f"\nWrite these to {len(planned)} config.json file(s)?", False):
        say("  Nothing was written.")
        return
    for _name, listing_dir, cfg, changes in planned:
        cfg.update({k: now for k, (_was, now) in changes.items()})
        save_config(listing_dir, cfg)
    say(f"  Updated {len(planned)} listing(s).")


def home():
    """The one screen: where every listing is, then the four things to do."""
    status, why = load_status()
    # reason: the roll-up opens every photo in every listing, the dump scan
    # re-reads scraper/dumps/, and the gate banner spawns check_pii.py over the
    # whole repo. That is worth paying once, and again after an action that
    # could have changed the answer -- but it was being paid to reprint four
    # lines after a mistyped menu key. The flag, not a timer: correctness here
    # is "recompute after anything that writes", which is every action.
    stale, pending = True, []
    while True:
        if stale:
            rule("Tour builder")
            if status is None:
                say(f"  The listing roll-up is unavailable ({why}).")
                say("  status.py loads scraper/photos.py at import, and "
                    "that is what failed.\n  Building is unaffected -- pick 1 "
                    "and the listing picker works as always.")
            else:
                roll_up(status)
            pending = unimported_dumps()
            if pending:
                say(f"\n  {len(pending)} dump(s) in scraper/dumps/ have no "
                    f"listing folder yet:")
                for name, brand, listing in pending:
                    say(f"    {name}  ->  agents/{brand}/{listing}")
            gate_banner()
            stale = False

        menu = [
            ("1", "Build a tour", None),
            ("2", f"Import {len(pending)} new dump(s)" if pending
             else "Import new dumps (none pending)", import_dumps),
            ("3", "Publish a review link", publish_action),
            ("4", "Brand settings", brand_settings),
        ]
        say("")
        for key, label, _ in menu:
            say(f"  {key}. {label}")
        say("  q. quit")
        choice = ask("\nWhich", "1").strip().lower()
        if choice in ("q", "quit", "exit"):
            return
        if choice == "1":
            build_flow([])
            return
        action = next((f for k, _, f in menu if k == choice), None)
        if action is None:
            say("  Pick 1-4, or q to quit.")
            continue
        action()
        say("")
        stale = True


# ---- the wizard -------------------------------------------------------------

def _new_folder_name(raw, what):
    """Slugify a hand-typed folder name the same way the scrape would.

    reason: this took the operator's text literally, so typing "Coldwell Banker
    Realty - Boston" made agents/Coldwell Banker Realty - Boston/ -- a folder
    with spaces that no scrape could ever produce and that status.py reports as
    drifted or unverifiable forever after. The scrape is the naming authority;
    when there is no lead row to derive a name from, the least this can do is
    apply the authority's own rule to the text. make_tour._slug IS that rule --
    tour.py already imports make_tour, so this adds no third slug function and
    no dependency on the scraper.
    """
    slug = make_tour._slug(raw)
    if not slug:
        raise SystemExit(f"{what} \"{raw}\" has no usable characters for a "
                         f"folder name.")
    if slug != raw:
        say(f"  Using \"{slug}\" -- folder names follow the scrape's rule.")
    return slug


def listing_actions():
    """({(brand, listing): next_action}, {scraped names}) -- never raises.

    reason: the picker used to list bare folder names, so a folder holding 39
    photos and one holding none looked identical and the operator had to guess
    which was worth opening. status.py already computes the one next action per
    listing; showing it here costs one survey() and means the picker and the
    home screen can never disagree about what a listing is waiting on.
    """
    mod, _ = load_status()
    if mod is None:
        return {}, None
    try:
        rows, _truth, known = mod.survey()
    except Exception:
        return {}, None
    return {(r[0], r[1]): r[5] for r in rows if r[1] != "-"}, known


def choose_listing():
    """(brand, listing_dir), creating either inline."""
    actions, known = listing_actions()
    bs = brands()
    brand = pick("Brand", [(b, b) for b in bs] or [], default=0,
                 extra=("+", "+ New brand")) if bs else "+"
    made_by_hand = False
    if brand == "+":
        raw = ask("New brand name").strip()
        if not raw:
            raise SystemExit("No brand name given.")
        brand = _new_folder_name(raw, "Brand name")
        made_by_hand = True
        os.makedirs(os.path.join(LISTINGS_ROOT, brand), exist_ok=True)

    ls = listings(brand)
    labelled = [(x, f"{x}   -- {actions[(brand, x)]}" if (brand, x) in actions
                 else x) for x in ls]
    name = pick("Listing", labelled or [], default=0,
                extra=("+", "+ New listing")) if ls else "+"
    if name == "+":
        raw = ask("New listing folder name (e.g. 46_beacon_5)").strip()
        if not raw:
            raise SystemExit("No listing name given.")
        name = _new_folder_name(raw, "Listing name")
        made_by_hand = True
    listing_dir = os.path.join(LISTINGS_ROOT, brand, name)
    os.makedirs(os.path.join(listing_dir, "photos"), exist_ok=True)
    # reason: the note below used to fire only for a folder created in THIS
    # session, so picking an existing hand-named one said nothing and the state
    # first surfaced in status.py's audit long afterwards. Picking it is the
    # moment the operator can act on it.
    if not made_by_hand and known is not None and (brand, name) not in known:
        say(f"  Note: no leads.csv row behind {brand}/{name}, so status.py lists "
            f"it as\n  unverifiable. It builds normally -- the question set will "
            f"ask for the address,\n  agent and phone. The folder name is left "
            f"alone: the scrape is what names folders.")
    if made_by_hand:
        # reason: say it once, here, rather than letting status.py be the first
        # thing that mentions it. A hand-named folder has no lead row behind it,
        # which is a real state with a real consequence, not a warning to bury.
        say("  Note: named by hand, so there is no leads.csv row behind it. "
            "status.py will list it as unverifiable until the listing is "
            "scraped. Run scraper/run.py instead if you have the dump.")
    return brand, listing_dir


def main():
    args = sys.argv[1:]
    if args and args[0] == "--auto":
        auto_flow(args[1:])
        return
    if args and args[0] not in ("--check-photos", "--build"):
        raise SystemExit(
            __doc__.strip().splitlines()[0] +
            "\n\n    python3 tour.py [--build | --check-photos | --auto]")
    # reason: --check-photos and --build are the two ways past the home screen.
    # The roll-up is worth a second of startup when you are deciding what to
    # work on and pure noise when you already know, so it is skippable -- but
    # only explicitly. The default is still the screen that answers "where am I".
    if args:
        build_flow(args)
    else:
        home()


def build_flow(args):
    """Pick a listing, ask the short set, walk the three rungs. Unchanged.

    reason: this is the whole of what main() used to be, moved down a level so a
    home screen could sit in front of it. Every rung, prompt, default, refusal
    and flag below is byte-for-byte what it was.
    """
    brand, listing_dir = choose_listing()
    say(f"\n{os.path.relpath(listing_dir, ROOT)}")

    if not photos(listing_dir):
        say("\nphotos/ is empty.")
        import_photos(listing_dir)
        if not photos(listing_dir):
            raise SystemExit(f"Nothing to build. Put photos in "
                             f"{os.path.join(listing_dir, 'photos')} and rerun.")
    offer_prefixes(listing_dir)

    cfg = load_config(listing_dir, brand)
    report = preflight(listing_dir, cfg)

    if args == ["--check-photos"]:
        check_photos(listing_dir)
        return

    cfg = questions(listing_dir, brand, cfg)

    # ---- rung 1: is the order right? (~1s) ----
    rule("1. Check the order")
    if confirm(f"Build {SHEET} -- a numbered grid of photos/ in build order?", True):
        if run_build(listing_dir, ["--contact-sheet"]) == 0:
            say(f"\nOpen {os.path.join(listing_dir, SHEET)} and check it.")
            if not confirm("Is the order right?", True):
                say("Rename the files to fix it -- the prefix IS the order -- "
                    "then run tour.py again.")
                return

    # ---- rung 2: does the edit feel right? (~50s) ----
    rule("2. Draft")
    while confirm("Build a 720p watermarked draft to review?", True):
        flags, reason = draft_flags(listing_dir, cfg)
        if reason:
            say(f"  Full draft rebuild: {reason}.")
        if run_build(listing_dir, flags) != 0:
            say("\nThe draft failed. The intermediates were kept for inspection.")
            return
        save_state(listing_dir, "draft", cfg, "720p")
        say(f"\nWatch {os.path.join(listing_dir, DRAFT_OUT)}. "
            "It is a draft: 720p, watermarked, never a deliverable.")
        if confirm("Does the edit feel right?", True):
            break
        cfg = questions(listing_dir, brand, load_config(listing_dir, brand))

    # ---- rung 3: ship it (~6min) ----
    # reason: the rung is named for what this run actually writes. A listing with
    # nothing in out/ is being proofed, not delivered, and calling that step
    # "Deliver" is how the tour_ cuts got built for every listing that never
    # replied. The stage is derived from out/ -- see stage().
    st = stage(listing_dir)
    rule({"sample": "3. Sample", "delivery": "3. Deliver",
          "delivered": "3. Rebuild"}[st])
    # reason: this used to refuse outright when the photos missed 720p, at the END
    # of a run, after the question set and a draft had already been paid for. The
    # verdict was known at preflight, second one. Refusing late threw away the work
    # AND told the operator nothing they could act on. So: build it, and say
    # plainly what is wrong with it -- the count, the worst file, the upscale --
    # here, and again once the cuts exist. The gate is a measurement that reports.
    preset = best_preset(report)
    lowres = preset is None
    if lowres:
        preset = "720p"
        n_bad, n_all = len(report["720p"]), len(photos(listing_dir))
        worst = max(report["720p"], key=lambda r: r[2])
        say(f"These photos are below par: {n_bad} of {n_all} miss 720p. "
            f"Worst {os.path.basename(worst[0])}\nat {worst[1]}, upscaled "
            f"{worst[2]:.1f}x.")
        say("The cuts will build at 720p and will be soft. Nothing in their "
            "names says\nso -- do not send these to the MLS. Reshoot or get the "
            "originals first.")
    what = build_choice(st)
    if what is None:
        return
    n = len(photos(listing_dir))
    n_cuts = 6 if what == "both" else 3
    say(f"\n{n_cuts} cuts at {preset}{' (below par)' if lowres else ''}, "
        f"about {runtime(n, cfg):.0f}s each. This takes a few minutes.")
    flags, reason = delivery_flags(listing_dir, cfg, preset, lowres, cuts=what)
    if reason:
        say(f"  Full rebuild: {reason}.")
    else:
        say("  Reusing the stitch from the last build -- branding only.")
    if run_build(listing_dir, flags) != 0:
        say("\nThe build failed. The intermediates were kept for inspection.")
        return
    # reason: the rung key names the stitch lineage, not the cut family, so a
    # sample-only run records "delivery" too -- that is exactly what lets the
    # delivery run that follows take --finish-only off the same intermediates.
    save_state(listing_dir, "delivery", cfg, preset)

    # reason: once the sample_ cuts exist, the questions draft.mp4 and
    # contact_sheet.png answered are settled -- see clear_review_artifacts().
    # A delivery-only rebuild (what == "delivery") leaves them alone: they were
    # already cleared the first time this listing's samples were built.
    cleared = clear_review_artifacts(listing_dir) if what in ("sample", "both") else []

    rule("Done")
    for f in outputs(listing_dir):
        say(f"  out/{f}")
    if cleared:
        say(f"\nCleared {' and '.join(cleared)} -- the sample cuts answer what "
            "they were for.")
    say("\nsample_ cuts carry the proofing watermark -- those are what the client "
        "reviews.\ntour_ cuts are the delivery, and only after sign-off.")
    if what == "sample":
        say("The tour_ deliverables are not built yet. Run this again once the "
            "client says\nyes -- it reuses this stitch and takes about a minute.")
    if lowres:
        say(f"\nBELOW PAR: built at {preset} from photos that do not reach it, so "
            f"these were\nupscaled past what the photos hold. Watchable for a "
            f"review, not sharp enough\nfor the MLS, and the filenames do not say "
            f"so. See IDEA.md 4 for how to source\nbetter.")

    # reason: only offer the bucket when this run actually wrote a sample. After a
    # delivery-only run the sample cuts are still sitting in out/ from last time,
    # and offering to publish them again reads as though something new is ready.
    if what == "delivery":
        say("\nThe deliverables are in out/. Send those three by hand -- nothing "
            "here uploads\na tour_ cut, and publish.py refuses to.")
    else:
        publish_rung(listing_dir)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        say("\nStopped. Nothing was left running.")
