#!/usr/bin/env python3
"""tour.py — the one command. Photos in a folder, a few questions, an mp4 out.

    python3 tour.py                 # the wizard
    python3 tour.py --check-photos  # optional: ask Claude to read the contact sheet

This replaced the Streamlit dashboard, which put thirteen controls on screen and
still left the operator to remember which of them mattered. The shape here is the
opposite: everything with the same answer on every listing is inherited from
agents/<brand>/brand.json or derived from the photos, everything missing is named
up front rather than discovered five minutes into an encode, and what is left is
a short question set — where the photos are, what the card says, how long it runs.

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

  The resolution verdict. When neither preset clears, this used to REFUSE, at the
  end of a run, after the question set and a draft had already been paid for,
  having computed the identical answer at preflight in the first second. It now
  states the count, the worst file and its upscale factor, then builds all six at
  720p named _lowres. The gate is unchanged as a measurement; what changed is that
  it decides what the files are CALLED rather than whether they exist. A console
  refusal survives nothing once the operator reaches for the flag; a filename
  survives being emailed.
"""

import glob
import json
import os
import shutil
import subprocess
import sys

import make_tour
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
}
# What a brand sets once and every listing under it inherits. The address is the
# one field that is genuinely per-property, so it is the one field never inherited.
BRAND_KEYS = ("logo", "music", "clip_seconds", "xfade_seconds",
              "brand_persistent", "brand_in", "brand_out",
              "card", "card_seconds", "card_style", "card_theme", "accent",
              "font", "agent_name", "agent_phone", "brokerage")

CARD_MODES = [("outro", "Outro card only (recommended)"),
              ("both", "Intro and outro"),
              ("intro", "Intro card only"),
              ("none", "No card")]


# ---- asking -----------------------------------------------------------------

def say(msg=""):
    print(msg, flush=True)


def rule(title):
    say(f"\n\033[1m{title}\033[0m\n" + "-" * max(len(title), 20))


def ask(question, default=""):
    hint = f" [{default}]" if default != "" else ""
    try:
        answer = input(f"{question}{hint}: ").strip()
    except EOFError:
        raise SystemExit("\nNo input available. Run tour.py in a terminal.")
    return answer or default


def confirm(question, default=True):
    d = "Y/n" if default else "y/N"
    while True:
        a = ask(f"{question} ({d})", "y" if default else "n").lower()
        if a in ("y", "yes"):
            return True
        if a in ("n", "no"):
            return False
        say("  Answer y or n.")


def pick(question, options, default=0, extra=None):
    """Numbered menu. options is [(value, label)]. extra adds a trailing choice."""
    items = list(options) + ([extra] if extra else [])
    say(f"\n{question}")
    for i, (_, label) in enumerate(items, 1):
        say(f"  {i}. {label}" + ("   (default)" if i - 1 == default else ""))
    while True:
        a = ask("Choose", str(default + 1))
        if a.isdigit() and 1 <= int(a) <= len(items):
            return items[int(a) - 1][0]
        say(f"  Enter 1-{len(items)}.")


def number(question, default, lo, hi):
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
    return _read_json(os.path.join(LISTINGS_ROOT, brand, BRAND_FILE), BRAND_FILE)


def save_brand(brand, cfg):
    out = {k: v for k, v in cfg.items()
           if k in BRAND_KEYS and v is not None and v != ""}
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
                 "sample_ cuts will NOT be watermarked -- fix before proofing"))
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
        say("  These will still build, at 720p, named _lowres so the shortfall "
            "travels\n  with the file. They will be soft. To fix it properly you "
            "need the\n  photographer's originals or the MLS back end -- see "
            "IDEA.md 4.")

    say("")
    for label, path, note in check_assets(listing_dir, cfg):
        where = os.path.relpath(path, ROOT) if path else "MISSING"
        say(f"{label:<17} {where}" + (f"   ({note})" if note else ""))

    if os.path.exists(os.path.join(listing_dir, LOCK)):
        say(f"\nWARNING: {LOCK} is present -- another build may be running here.")
    return report


# ---- questions --------------------------------------------------------------

def questions(listing_dir, brand, cfg):
    """The short set: what the card says, what shape it is, how long it runs."""
    rule("What goes on screen")
    before = {k: cfg.get(k) for k in ("agent_name", "agent_phone", "brokerage")}
    cfg["address"] = ask("Property address", cfg.get("address", ""))
    cfg["agent_name"] = ask("Agent name", cfg.get("agent_name", ""))
    cfg["agent_phone"] = ask("Agent phone", cfg.get("agent_phone", ""))
    cfg["brokerage"] = ask("Brokerage (card only, used when there is no logo)",
                           cfg.get("brokerage", ""))
    if any(cfg[k] != before[k] for k in before) and \
            confirm(f"Save the name, phone and brokerage as {brand} defaults?", True):
        save_brand(brand, {**load_brand(brand), **{k: cfg[k] for k in before}})

    if not resolve(listing_dir, cfg.get("logo")):
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
                                                                        "outro")))
    if cfg["card"] != "none":
        cfg["card_seconds"] = number("Card length in seconds",
                                     cfg.get("card_seconds", 5.0), 2.0, 10.0)
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
        default_persistent)
    if not cfg["brand_persistent"]:
        cfg["brand_in"] = number("  Lower third in at", cfg.get("brand_in", 0.8),
                                 0.0, 60.0)
        cfg["brand_out"] = number("  and out at", cfg.get("brand_out", 6.5),
                                  cfg["brand_in"] + 0.5, 120.0)

    if not resolve(listing_dir, cfg.get("music") or "music.mp3"):
        available = assets("music")
        if available and confirm("No music set. Pick a track?", True):
            cfg["music"] = asset_path(
                "music", pick("Track", [(f, f) for f in available]))

    cfg["clip_seconds"] = number("Seconds per photo", cfg.get("clip_seconds", 4.0),
                                 1.0, 15.0)
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


def offer_prefixes(listing_dir):
    """Renumber photos/ in its current alphabetical order, on confirmation.

    reason: the filename prefix IS the tour order -- there is no manifest and there
    is never going to be one, because a sidecar drifts out of sync with the folder.
    A folder with no prefixes still builds, it just builds alphabetically, and that
    silent failure has shipped once already. So offer the prefixes out loud.
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
                   "(rename them later to reorder)", True):
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


def delivery_flags(listing_dir, cfg, preset, lowres=False):
    """(flags, full_rebuild_reason or None) for the six-cut delivery build.

    reason: lowres rides in the state's preset string, not beside it. It changes
    every output filename, so a build that flips it must not be allowed to take
    --finish-only and leave the previous run's differently-named cuts sitting in
    out/ looking current.
    """
    flags = ["--720p"] if preset == "720p" else []
    if lowres:
        flags.append("--allow-lowres")
    if not resolve(listing_dir, cfg.get("music") or "music.mp3"):
        flags.append("--no-music")
    reason = rebuild_reason(listing_dir, cfg, preset + ("+lowres" if lowres else ""),
                            "delivery", "work_silent.mp4")
    # reason: --finish-only reuses the stitched cut, so it can only ever apply
    # branding, music and timing. Anything upstream of the stitch needs a full run.
    flags.append("--keep-work" if reason else "--finish-only")
    return flags, reason


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


def outputs(listing_dir):
    d = os.path.join(listing_dir, "out")
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d) if f.endswith(".mp4"))


# ---- rung 4: publish ---------------------------------------------------------

def publish_rung(listing_dir):
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
        return
    cuts = [f for f in outputs(listing_dir) if publish.publishable(f)[0]]
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


def choose_listing():
    """(brand, listing_dir), creating either inline."""
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
    name = pick("Listing", [(x, x) for x in ls] or [], default=0,
                extra=("+", "+ New listing")) if ls else "+"
    if name == "+":
        raw = ask("New listing folder name (e.g. 46_beacon_5)").strip()
        if not raw:
            raise SystemExit("No listing name given.")
        name = _new_folder_name(raw, "Listing name")
        made_by_hand = True
    listing_dir = os.path.join(LISTINGS_ROOT, brand, name)
    os.makedirs(os.path.join(listing_dir, "photos"), exist_ok=True)
    if made_by_hand:
        # reason: say it once, here, rather than letting status.py be the first
        # thing that mentions it. A hand-named folder has no lead row behind it,
        # which is a real state with a real consequence, not a warning to bury.
        say("  Note: named by hand, so there is no leads.csv row behind it. "
            "status.py will list it as unverifiable until the listing is "
            "scraped. Run scraper/zillow_run.py instead if you have the dump.")
    return brand, listing_dir


def main():
    args = sys.argv[1:]
    if args and args[0] not in ("--check-photos",):
        raise SystemExit(__doc__.strip().splitlines()[0] +
                         "\n\n    python3 tour.py [--check-photos]")

    rule("Tour builder")
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
    rule("3. Deliver")
    # reason: this used to refuse outright when the photos missed 720p, at the END
    # of a run, after the question set and a draft had already been paid for. The
    # verdict was known at preflight, second one. Refusing late threw away the work
    # AND told the operator nothing they could act on. So: build it, name it
    # _lowres, and say plainly what is wrong with it. The gate still exists -- it
    # decides what the files are CALLED, which is a boundary that survives being
    # emailed, where a console refusal is a boundary that survives nothing.
    preset = best_preset(report)
    lowres = preset is None
    if lowres:
        preset = "720p"
        n_bad, n_all = len(report["720p"]), len(photos(listing_dir))
        say(f"These photos are below par: {n_bad} of {n_all} miss 720p.")
        say("The six cuts will build at 720p and be named _lowres. They will be "
            "soft.\nDo not send a _lowres cut to the MLS -- reshoot or get the "
            "originals first.")
    n = len(photos(listing_dir))
    say(f"Six cuts at {preset}{' (_lowres)' if lowres else ''}, "
        f"about {runtime(n, cfg):.0f}s each. This takes a few minutes.")
    if not confirm("Build the delivery?", True):
        return
    flags, reason = delivery_flags(listing_dir, cfg, preset, lowres)
    if reason:
        say(f"  Full rebuild: {reason}.")
    if run_build(listing_dir, flags) != 0:
        say("\nThe build failed. The intermediates were kept for inspection.")
        return
    save_state(listing_dir, "delivery", cfg,
               preset + ("+lowres" if lowres else ""))

    rule("Done")
    for f in outputs(listing_dir):
        say(f"  out/{f}")
    say("\nsample_ cuts carry the proofing watermark -- those are what the client "
        "reviews.\ntour_ cuts are the delivery, and only after sign-off.")
    if lowres:
        say("\n_lowres means these were upscaled past what the photos hold. "
            "Watchable for\na review, not sharp enough for the MLS. See IDEA.md 4 "
            "for how to source better.")

    publish_rung(listing_dir)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        say("\nStopped. Nothing was left running.")
