#!/usr/bin/env python3
"""dashboard.py — local Streamlit front end for make_tour.py.

    pip install -r requirements.txt
    streamlit run dashboard.py

What it does, and why it exists:

  * keeps branding assets in one shared library (global_assets/) instead of
    shuffling logo.png / lower_third.png / music.mp3 in and out of a build folder
  * writes each listing's choices to <listing>/config.json, so the settings that
    produced a delivered video are still on disk months later
  * turns the lower-third timing constants into UI controls, so changing when the
    lower third appears no longer means editing the script
  * runs make_tour.py with cwd set to the listing folder and streams its output

Listings live at agents/<brand>/<listing>/, each holding photos/ and, after a
build, out/. This file is the only part of the project that needs a third-party
package -- make_tour.py still runs on nothing but ffmpeg and ffprobe.

It reuses make_tour's ffprobe helpers rather than reimplementing them. Note that
importing make_tour executes that module's own config load against THIS process's
working directory, so per-listing values are always read from the listing's
config.json here -- never from make_tour's module constants.
"""

import json
import os
import subprocess
import sys
import time

import streamlit as st

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
# reason: these two reshape work_silent.mp4 itself, so changing either invalidates
# the stitched intermediate and rules out the fast --finish-only path.
PACING_KEYS = ("clip_seconds", "xfade_seconds")

DEFAULTS = {
    "clip_seconds": 4.0,
    "xfade_seconds": 0.5,
    "brand_persistent": True,
    "brand_in": 0.8,
    "brand_out": 6.5,
    "lower_third": None,
    "logo": None,
    "music": None,
}


# ---- filesystem -------------------------------------------------------------

def brands():
    if not os.path.isdir(LISTINGS_ROOT):
        return []
    return sorted(d for d in os.listdir(LISTINGS_ROOT)
                  if os.path.isdir(os.path.join(LISTINGS_ROOT, d))
                  and not d.startswith("."))


def listings(brand):
    d = os.path.join(LISTINGS_ROOT, brand)
    if not os.path.isdir(d):
        return []
    return sorted(x for x in os.listdir(d)
                  if os.path.isdir(os.path.join(d, x)) and not x.startswith("."))


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


def photos(listing_dir):
    d = os.path.join(listing_dir, "photos")
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d)
                  if os.path.splitext(f)[1].lower() in make_tour.PHOTO_EXTS)


def photo_state(listing_dir):
    d = os.path.join(listing_dir, "photos")
    return [[f, os.path.getmtime(os.path.join(d, f)),
             os.path.getsize(os.path.join(d, f))] for f in photos(listing_dir)]


def load_config(listing_dir):
    cfg = dict(DEFAULTS)
    p = os.path.join(listing_dir, "config.json")
    if os.path.exists(p):
        try:
            with open(p) as f:
                cfg.update(json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            st.error(f"config.json is unreadable ({e}) — showing defaults.")
    return cfg


def save_config(listing_dir, cfg):
    # reason: omit keys left unset so make_tour falls back to its own constants
    # rather than being handed an explicit null it would treat as a path.
    out = {k: v for k, v in cfg.items() if v is not None}
    with open(os.path.join(listing_dir, "config.json"), "w") as f:
        json.dump(out, f, indent=2)
        f.write("\n")


def runtime(n, clip, xfade):
    """Finished length, same arithmetic make_tour prints at the end of a build."""
    return max(n * clip - (n - 1) * xfade, 0.0) if n else 0.0


# ---- validation -------------------------------------------------------------

def check_image(path, kind):
    """(ok, [messages]) for an uploaded PNG."""
    msgs = []
    w, h = make_tour.dimensions(path)
    if not w:
        return False, ["Not a readable image — ffprobe could not decode it."]
    box = make_tour.alpha_bbox(path)
    if box is None:
        msgs.append("No alpha channel found. Branding PNGs should be RGBA, or the "
                    "overlay will paint an opaque rectangle over the video.")
    msgs.append(f"{w}x{h}")
    if kind == "lower_third":
        # reason: finish() switches layout on this exact threshold, and getting it
        # wrong is the most confusing failure -- the art lands off-register with no
        # error at all. Say which mode the file will trigger, at upload time.
        if w >= 0.9 * 1920:
            msgs.append("Full-frame plate: placed at 0,0 and resampled to the "
                        "output preset. Position comes from the artwork itself.")
        else:
            msgs.append("Strip: inset from the bottom-left corner by the script's "
                        "margin. Widen past 1728px to be treated as a full plate.")
    if kind == "logo":
        aw, ah = (box[2], box[3]) if box else (w, h)
        msgs.append(f"Trimmed art {aw}x{ah}, fitted into a "
                    f"{make_tour.LOGO_W}x{make_tour.LOGO_H} box at 1080p.")
        # reason: same principle as the build's watermark warning -- say it at
        # upload time rather than let a soft 4x upscale reach a delivery cut.
        fit = min(make_tour.LOGO_W / aw, make_tour.LOGO_H / ah)
        if fit > 1.5:
            msgs.append(f"Upscales {fit:.1f}x and will look soft. Supply at least "
                        f"{make_tour.LOGO_W}px on the long edge.")
    return True, msgs


def check_music(path):
    if not make_tour.music_ok(path):
        return False, ["Not a decodable audio file — missing, empty, or no audio "
                       "stream."]
    total = make_tour.duration(path)
    start, end = make_tour.music_span(path)
    return True, [f"{total:.1f}s long, content from {start:.1f}s to {end:.1f}s.",
                  "Shorter than the tour? The build loops it with a crossfade."]


# ---- build ------------------------------------------------------------------

def build_flags(listing_dir, cfg, preset, no_music, allow_lowres):
    """(flags, full_rebuild_reason or None)."""
    flags = []
    if preset == "720p":
        flags.append("--720p")
    if no_music:
        flags.append("--no-music")
    if allow_lowres:
        flags.append("--allow-lowres")

    reason = None
    silent = os.path.join(listing_dir, "work_silent.mp4")
    state_path = os.path.join(listing_dir, STATE)
    if not os.path.exists(silent):
        reason = "no work_silent.mp4 to reuse"
    elif not os.path.exists(state_path):
        reason = "no record of the previous build"
    else:
        with open(state_path) as f:
            last = json.load(f)
        if last.get("preset") != preset:
            reason = "output preset changed"
        elif any(last.get("cfg", {}).get(k) != cfg[k] for k in PACING_KEYS):
            reason = "clip pacing changed"
        elif last.get("photos") != photo_state(listing_dir):
            reason = "photos changed"

    # reason: --finish-only reuses the stitched cut, so it can only ever apply
    # branding, music and timing. Anything upstream of the stitch needs a full run.
    flags.append("--keep-work" if reason else "--finish-only")
    return flags, reason


def run_build(listing_dir, flags, log_area):
    """Stream make_tour.py into log_area. Returns the exit code."""
    lines = []
    # reason: make_tour reports progress with bare print(), which block-buffers once
    # stdout is a pipe -- without -u the whole log lands at once when it finishes.
    # stderr is merged because run() lets ffmpeg write its errors straight to it.
    proc = subprocess.Popen(
        [sys.executable, "-u", SCRIPT] + flags,
        cwd=listing_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1)
    for line in proc.stdout:
        lines.append(line.rstrip())
        log_area.code("\n".join(lines[-200:]), language="text")
    proc.wait()
    return proc.returncode


def outputs(listing_dir):
    d = os.path.join(listing_dir, "out")
    if not os.path.isdir(d):
        return []
    return sorted(f for f in os.listdir(d) if f.endswith(".mp4"))


# ---- ui ---------------------------------------------------------------------

st.set_page_config(page_title="Tour Builder", page_icon="🏠", layout="wide")

with st.sidebar:
    st.header("Listing")
    bs = brands()
    brand = st.selectbox("Brand", bs + ["+ New brand"], index=0 if bs else 0)
    if brand == "+ New brand":
        new_brand = st.text_input("New brand name")
        if st.button("Create brand", disabled=not new_brand):
            os.makedirs(os.path.join(LISTINGS_ROOT, new_brand.strip()),
                        exist_ok=True)
            st.rerun()
        st.stop()

    ls = listings(brand)
    listing = st.selectbox("Listing", ls + ["+ New listing"], index=0 if ls else 0)
    if listing == "+ New listing":
        new_listing = st.text_input("New listing name")
        if st.button("Create listing", disabled=not new_listing):
            d = os.path.join(LISTINGS_ROOT, brand, new_listing.strip())
            os.makedirs(os.path.join(d, "photos"), exist_ok=True)
            st.rerun()
        st.stop()

    listing_dir = os.path.join(LISTINGS_ROOT, brand, listing)
    pics = photos(listing_dir)
    st.caption(f"{len(pics)} photo(s) in photos/")
    st.divider()
    st.header("Asset library")
    up_kind = st.selectbox("Add to", list(KINDS), format_func=lambda k: KINDS[k][0])
    up = st.file_uploader("Upload", type=KINDS[up_kind][1],
                          label_visibility="collapsed")
    if up is not None:
        sub = KINDS[up_kind][0]
        os.makedirs(os.path.join(ASSETS_ROOT, sub), exist_ok=True)
        # reason: validate before it enters the library. A rejected file that is
        # already on disk will be picked from a dropdown later and fail mid-build.
        tmp = os.path.join(ASSETS_ROOT, sub, f".incoming_{up.name}")
        with open(tmp, "wb") as f:
            f.write(up.getbuffer())
        ok, msgs = (check_music(tmp) if up_kind == "music"
                    else check_image(tmp, up_kind))
        if ok:
            os.replace(tmp, os.path.join(ASSETS_ROOT, sub, up.name))
            st.success(f"Added {up.name}")
        else:
            os.remove(tmp)
            st.error(f"Rejected {up.name}")
        for m in msgs:
            st.caption(m)

st.title(f"{brand} — {listing}")

if not pics:
    st.warning(f"No photos in `{os.path.relpath(listing_dir, ROOT)}/photos/`. "
               "Name them in tour order — the numeric prefix **is** the order: "
               "`01_exterior_front.jpg`, `02_entry.webp`, …")

cfg = load_config(listing_dir)

left, right = st.columns(2)

with left:
    st.subheader("Branding")
    for kind, label in (("logo", "Logo (top-left)"),
                        ("lower_third", "Lower third"),
                        ("music", "Music")):
        available = assets(kind)
        current = os.path.basename(cfg.get(kind) or "")
        idx = available.index(current) + 1 if current in available else 0
        pick = st.selectbox(label, ["— none —"] + available, index=idx, key=kind)
        cfg[kind] = asset_path(kind, None if pick == "— none —" else pick)
        if pick != "— none —":
            full = os.path.join(ROOT, cfg[kind])
            if kind == "music":
                st.audio(full)
            else:
                st.image(full)

with right:
    st.subheader("Lower-third timing")
    cfg["brand_persistent"] = st.checkbox(
        "Persistent — on screen for the whole video",
        value=bool(cfg["brand_persistent"]))

    total = runtime(len(pics), float(cfg["clip_seconds"]),
                    float(cfg["xfade_seconds"]))
    if cfg["brand_persistent"]:
        st.caption("The lower third stays up from the first frame to the last.")
    elif total <= 0:
        st.info("Add photos to set a timing window — the sliders are bounded by "
                "the finished runtime.")
    else:
        # reason: bounding by the real runtime is what stops the most common
        # mistake -- a window that ends after the video does, which ffmpeg accepts
        # silently and which just leaves the overlay up to the end.
        cfg["brand_in"] = st.slider(
            "Show at (s)", 0.0, float(total),
            min(float(cfg["brand_in"]), total), 0.1)
        cfg["brand_out"] = st.slider(
            "Hide at (s)", 0.0, float(total),
            min(float(cfg["brand_out"]), total), 0.1)
        if cfg["brand_out"] <= cfg["brand_in"]:
            st.error("Hide must come after show, or the lower third never appears.")

    st.subheader("Pacing")
    cfg["clip_seconds"] = st.number_input(
        "Seconds per photo", 1.0, 15.0, float(cfg["clip_seconds"]), 0.5)
    cfg["xfade_seconds"] = st.number_input(
        "Crossfade (s)", 0.0, 3.0, float(cfg["xfade_seconds"]), 0.1)
    st.caption(f"Finished runtime: **{total:.1f}s** from {len(pics)} photo(s). "
               "Changing either value forces a full rebuild.")

st.divider()
st.subheader("Build")

c1, c2, c3 = st.columns(3)
preset = c1.radio("Preset", ["1080p", "720p"], horizontal=True)
no_music = c2.checkbox("Silent build (--no-music)")
allow_lowres = c3.checkbox("Bypass the resolution gate (--allow-lowres)")
if allow_lowres:
    # reason: this is the project's loudest non-negotiable. It belongs next to the
    # checkbox, not only in the docs -- that is where the decision is being made.
    st.error("**PREVIEW ONLY — never for a client or the MLS.** The gate exists "
             "because an upscaled photo ships a soft, fabricated-looking room. If "
             "a build needs this flag, the photos are not ready: get the "
             "photographer's originals or the MLS export instead. (IDEA.md §4)")

flags, full_reason = build_flags(listing_dir, cfg, preset, no_music, allow_lowres)
if full_reason:
    st.info(f"Full build — {full_reason}.")
else:
    st.success("Fast path — reusing work_silent.mp4, redoing music and branding "
               "only (--finish-only).")
st.code(f"cd {os.path.relpath(listing_dir, ROOT)} && "
        f"python3 ../../../make_tour.py {' '.join(flags)}", language="bash")

lock_path = os.path.join(listing_dir, LOCK)
locked = os.path.exists(lock_path)
if locked:
    # reason: make_tour has no locking of its own and cleans up by glob, so two
    # runs in one folder delete each other's intermediates mid-build.
    st.warning("A build is already running in this listing. If that is wrong — a "
               "previous run was killed — clear the lock.")
    if st.button("Clear stale lock"):
        os.remove(lock_path)
        st.rerun()

b1, b2 = st.columns([1, 3])
if b1.button("Save settings"):
    save_config(listing_dir, cfg)
    st.toast("config.json written")

bad_window = not cfg["brand_persistent"] and cfg["brand_out"] <= cfg["brand_in"]
if b2.button("Save and build", type="primary",
             disabled=locked or not pics or bad_window):
    save_config(listing_dir, cfg)
    with open(lock_path, "w") as f:
        f.write(str(os.getpid()))
    try:
        with st.status(f"Building {listing}…", expanded=True) as status:
            log = st.empty()
            code = run_build(listing_dir, flags, log)
            if code == 0:
                with open(os.path.join(listing_dir, STATE), "w") as f:
                    json.dump({"preset": preset,
                               "cfg": {k: cfg[k] for k in PACING_KEYS},
                               "photos": photo_state(listing_dir),
                               "finished": time.time()}, f, indent=2)
                status.update(label="Build finished", state="complete")
            else:
                status.update(label=f"Build failed (exit {code}) — "
                                    "intermediates kept for inspection",
                              state="error")
    finally:
        if os.path.exists(lock_path):
            os.remove(lock_path)

files = outputs(listing_dir)
if files:
    st.divider()
    st.subheader("Outputs")
    d = os.path.join(listing_dir, "out")
    dl, sm = st.columns(2)
    with dl:
        st.markdown("### Delivery — `tour_*`")
        st.caption("Clean. Send **only after sign-off**.")
        for f in [x for x in files if x.startswith("tour_")]:
            st.caption(f"{f} · {os.path.getsize(os.path.join(d, f)) / 1e6:.1f} MB")
            st.video(os.path.join(d, f))
    with sm:
        st.markdown("### Sample — `sample_*`")
        st.caption("Watermarked. Send **for review**. Never as a deliverable.")
        for f in [x for x in files if x.startswith("sample_")]:
            st.caption(f"{f} · {os.path.getsize(os.path.join(d, f)) / 1e6:.1f} MB")
            st.video(os.path.join(d, f))
