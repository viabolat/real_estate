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
"""

import glob
import json
import os
import shutil
import subprocess
import sys

import make_tour

ROOT = os.path.dirname(os.path.abspath(__file__))
LISTINGS_ROOT = os.path.join(ROOT, "agents")
ASSETS_ROOT = os.path.join(ROOT, "global_assets")
SCRIPT = os.path.join(ROOT, "make_tour.py")

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
        say(f"Resolution: too small for both presets -- "
            f"{len(report['720p'])} photo(s) fail even 720p:")
        for path, size, up in report["720p"][:5]:
            say(f"  {os.path.basename(path)}  {size}  would upscale {up}")
        say("  A draft can still be built for review. A delivery cannot.")

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
    cfg["brand_persistent"] = confirm(
        "Keep the lower third up for the whole tour? "
        "(n = it clears after the opening seconds)",
        bool(cfg.get("brand_persistent", True)))
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


def delivery_flags(listing_dir, cfg, preset):
    """(flags, full_rebuild_reason or None) for the six-cut delivery build."""
    flags = ["--720p"] if preset == "720p" else []
    if not resolve(listing_dir, cfg.get("music") or "music.mp3"):
        flags.append("--no-music")
    reason = rebuild_reason(listing_dir, cfg, preset, "delivery", "work_silent.mp4")
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

def choose_listing():
    """(brand, listing_dir), creating either inline."""
    bs = brands()
    brand = pick("Brand", [(b, b) for b in bs] or [], default=0,
                 extra=("+", "+ New brand")) if bs else "+"
    if brand == "+":
        brand = ask("New brand name").strip()
        if not brand:
            raise SystemExit("No brand name given.")
        os.makedirs(os.path.join(LISTINGS_ROOT, brand), exist_ok=True)

    ls = listings(brand)
    name = pick("Listing", [(x, x) for x in ls] or [], default=0,
                extra=("+", "+ New listing")) if ls else "+"
    if name == "+":
        name = ask("New listing folder name (e.g. 46_beacon_5)").strip()
        if not name:
            raise SystemExit("No listing name given.")
    listing_dir = os.path.join(LISTINGS_ROOT, brand, name)
    os.makedirs(os.path.join(listing_dir, "photos"), exist_ok=True)
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
    preset = best_preset(report)
    if not preset:
        say("Delivery refused: the photos do not clear 720p. --allow-lowres is for "
            "previews only, never for anything a client or the MLS sees.")
        say("Get the photographer's originals or the MLS back end. See IDEA.md 4.")
        return
    n = len(photos(listing_dir))
    say(f"Six cuts at {preset}, about {runtime(n, cfg):.0f}s each. "
        "This takes a few minutes.")
    if not confirm("Build the delivery?", True):
        return
    flags, reason = delivery_flags(listing_dir, cfg, preset)
    if reason:
        say(f"  Full rebuild: {reason}.")
    if run_build(listing_dir, flags) != 0:
        say("\nThe build failed. The intermediates were kept for inspection.")
        return
    save_state(listing_dir, "delivery", cfg, preset)

    rule("Done")
    for f in outputs(listing_dir):
        say(f"  out/{f}")
    say("\nsample_ cuts carry the proofing watermark -- those are what the client "
        "reviews.\ntour_ cuts are the delivery, and only after sign-off.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        say("\nStopped. Nothing was left running.")
