#!/usr/bin/env python3
"""dashboard.py — local Streamlit front end for make_tour.py.

    pip install -r requirements.txt
    streamlit run dashboard.py

This is an internal tool. Nothing it renders reaches a client except the finished
video, so it is shaped around the loop the operator actually runs -- is the order
right, does the edit feel right, ship it -- and each rung costs what the question
is worth:

    Check order   ~1s     contact sheet straight off photos/, no encoding
    Draft         ~50s    one 720p cut: order, pacing, lower third, logo, music
    Deliver       ~6min   all six cuts at full quality, once, at the end

Everything that has the same answer on every listing has been moved off the main
view. Logo, music and pacing live in agents/<brand>/brand.json and are inherited;
the output preset is derived from what the photos can actually feed; the lower
third is the one asset that genuinely changes per property, so it is the one
control that stays. The rest sit under Advanced.

make_tour.py does not read brand.json. The dashboard resolves
DEFAULTS -> brand.json -> listing config.json and writes the effective values into
the listing's config.json, which stays the single source of truth for a build.
That keeps the script's contract intact -- read the working directory, know nothing
about the agents/<brand>/<listing> layout -- and keeps config.json an accurate
record of what produced a delivered video months later.

Locking is make_tour.py's job now: it takes .build.lock with O_EXCL and releases it
on any exit. This file only READS the lock to report it, and must never write it --
doing so would lock the build out of its own folder.

It reuses make_tour's ffprobe helpers and its resolution gate rather than
reimplementing them. Note that importing make_tour executes that module's own
config load against THIS process's working directory, so per-listing values are
always read from the listing's config.json here -- never from make_tour's module
constants.
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
BRAND_FILE = "brand.json"
SHEET = "contact_sheet.png"
DRAFT_OUT = "draft.mp4"
NONE = "— none —"
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
    "lower_third": None,
    "logo": None,
    "music": None,
}
# What a brand sets once and every listing under it inherits.
BRAND_KEYS = ("logo", "music", "clip_seconds", "xfade_seconds",
              "brand_persistent", "brand_in", "brand_out")


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


def asset_picker(kind, label, current, key, help=None):
    """Selectbox over the shared library. Returns a repo-relative path or None."""
    available = assets(kind)
    name = os.path.basename(current or "")
    idx = available.index(name) + 1 if name in available else 0
    pick = st.selectbox(label, [NONE] + available, index=idx, key=key, help=help)
    return asset_path(kind, None if pick == NONE else pick)


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


def _read_json(path, label):
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        st.error(f"{label} is unreadable ({e}) — falling back to defaults.")
        return {}


def load_brand(brand):
    return _read_json(os.path.join(LISTINGS_ROOT, brand, BRAND_FILE), BRAND_FILE)


def save_brand(brand, cfg):
    out = {k: v for k, v in cfg.items() if k in BRAND_KEYS and v is not None}
    with open(os.path.join(LISTINGS_ROOT, brand, BRAND_FILE), "w") as f:
        json.dump(out, f, indent=2)
        f.write("\n")


def listing_overrides(listing_dir):
    """Raw config.json, for reporting which values the listing set for itself."""
    return _read_json(os.path.join(listing_dir, "config.json"), "config.json")


def load_config(listing_dir, brand):
    """Effective settings: DEFAULTS -> brand.json -> the listing's own config.json.

    reason: the brokerage logo and the music bed are identical on every listing that
    brokerage owns; only the lower third really changes per property. Inheriting
    them removes both the repeated work and the repeated controls.
    """
    cfg = dict(DEFAULTS)
    cfg.update(load_brand(brand))
    cfg.update(listing_overrides(listing_dir))
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


# ---- readiness --------------------------------------------------------------

def gate_report(listing_dir):
    """{preset: [(path, "WxH", upscale)]} — which photos block which preset.

    reason: reuses make_tour.gate_failures so the page and the build apply one rule,
    and answers on page load what used to surface only after a five-minute render
    had already failed.
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

def load_state(listing_dir):
    return _read_json(os.path.join(listing_dir, STATE), STATE)


def save_state(listing_dir, rung, record):
    # reason: draft and delivery keep separate records because they stitch separate
    # intermediates. One shared record would let a draft's state authorise a
    # --finish-only delivery build, which is exactly how a soft cut ships.
    state = load_state(listing_dir)
    state[rung] = record
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
    if last.get("photos") != photo_state(listing_dir):
        return "photos changed"
    return None


def delivery_flags(listing_dir, cfg, preset, no_music, allow_lowres):
    """(flags, full_rebuild_reason or None) for the six-cut delivery build."""
    flags = []
    if preset == "720p":
        flags.append("--720p")
    if no_music:
        flags.append("--no-music")
    if allow_lowres:
        flags.append("--allow-lowres")
    reason = rebuild_reason(listing_dir, cfg, preset, "delivery", "work_silent.mp4")
    # reason: --finish-only reuses the stitched cut, so it can only ever apply
    # branding, music and timing. Anything upstream of the stitch needs a full run.
    flags.append("--keep-work" if reason else "--finish-only")
    return flags, reason


def draft_flags(listing_dir, cfg, no_music):
    """(flags, full_rebuild_reason or None) for the one-cut draft.

    reason: a draft is a preview by definition, so it always carries
    --allow-lowres. That is the flag's actual purpose, and routing it here is what
    removes the temptation to tick the bypass box on a build a client will see.
    """
    flags = ["--draft", "--allow-lowres"]
    if no_music:
        flags.append("--no-music")
    reason = rebuild_reason(listing_dir, cfg, "720p", "draft", "work_draft.mp4")
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
        # reason: redrawing the whole block on every line is O(n^2) in the log
        # length and stalls the page on a large listing. Throttle, then flush.
        if len(lines) % 5 == 0:
            log_area.code("\n".join(lines[-200:]), language="text")
    proc.wait()
    log_area.code("\n".join(lines[-200:]), language="text")
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
            # reason: seed from the brand so a new listing needs no branding clicks.
            seeded = dict(DEFAULTS)
            seeded.update(load_brand(brand))
            save_config(d, seeded)
            st.rerun()
        st.stop()

listing_dir = os.path.join(LISTINGS_ROOT, brand, listing)
rel = os.path.relpath(listing_dir, ROOT)
pics = photos(listing_dir)
brand_cfg = load_brand(brand)
overrides = listing_overrides(listing_dir)
cfg = load_config(listing_dir, brand)
report = gate_report(listing_dir)
derived = best_preset(report)

st.title(f"{brand} — {listing}")
build_tab, assets_tab, brand_tab = st.tabs(["Build", "Asset library", "Brand"])

# ---- Build ------------------------------------------------------------------
with build_tab:
    if not pics:
        st.warning(f"No photos in `{rel}/photos/`. Name them in tour order — the "
                   "numeric prefix **is** the order: `01_exterior_front.jpg`, "
                   "`02_entry.webp`, …")
    else:
        # reason: order is the sort of the filenames and nothing else, so a folder
        # of CDN hashes builds a shuffled tour whose only symptom is the video.
        unprefixed = [f for f in pics if not f[:1].isdigit()]
        if unprefixed:
            st.warning(f"**{len(unprefixed)} of {len(pics)} photos have no numeric "
                       "prefix**, so the order below is alphabetical, not authored "
                       "— the tour will play in whatever sequence the filenames "
                       "happen to sort into. Rename them `01_`, `02_`, … in "
                       "walkthrough order before building anything a client sees.")

        total = runtime(len(pics), float(cfg["clip_seconds"]),
                        float(cfg["xfade_seconds"]))
        if derived:
            st.success(f"**{len(pics)} photos · {total:.0f}s · {derived} ready**")
        else:
            st.error(f"**{len(pics)} photos · {total:.0f}s · neither preset is "
                     "deliverable** — every option would upscale.")
        for name in PRESETS:
            bad = report[name]
            if bad:
                with st.expander(f"{name} blocked by {len(bad)} photo(s)"):
                    for path, dims, scale in bad:
                        st.write(f"`{os.path.basename(path)}` — {dims}, would "
                                 f"upscale {scale:.1f}x")
                    st.caption("Get the photographer's originals or the MLS "
                               "export. Upscaling is not a fix — IDEA.md §2-3.")

        order_col, lt_col = st.columns([3, 2])
        with order_col:
            st.subheader("Order")
            sheet = os.path.join(listing_dir, SHEET)
            if os.path.exists(sheet):
                st.image(sheet)
                stamp = time.strftime("%d %b %H:%M",
                                      time.localtime(os.path.getmtime(sheet)))
                st.caption(f"Contact sheet generated {stamp}.")
            else:
                st.caption("No contact sheet yet — run **Check order**.")
            with st.expander(f"{len(pics)} photo(s), in build order",
                             expanded=bool(unprefixed)):
                st.caption("Rename to reorder. The prefix is the only source of "
                           "order.")
                for i, f in enumerate(pics, 1):
                    st.write(f"{i}. `{f}`")

        with lt_col:
            st.subheader("Lower third")
            st.caption("The one asset that changes per property.")
            cfg["lower_third"] = asset_picker(
                "lower_third", "Lower third", cfg.get("lower_third"),
                key=f"lt:{brand}:{listing}")
            if cfg["lower_third"]:
                st.image(os.path.join(ROOT, cfg["lower_third"]))
            st.caption("**Inherited from brand**")
            for key in ("logo", "music"):
                val = cfg.get(key)
                src = ("listing override"
                       if key in overrides and overrides[key] != brand_cfg.get(key)
                       else "brand" if key in brand_cfg else "unset")
                shown = os.path.basename(val) if val else NONE
                st.caption(f"{key}: `{shown}` ({src})")

        with st.expander("Advanced — pacing, timing, overrides"):
            a1, a2 = st.columns(2)
            with a1:
                cfg["clip_seconds"] = st.number_input(
                    "Seconds per photo", 1.0, 15.0, float(cfg["clip_seconds"]),
                    0.5, key=f"clip:{brand}:{listing}")
                cfg["xfade_seconds"] = st.number_input(
                    "Crossfade (s)", 0.0, 3.0, float(cfg["xfade_seconds"]), 0.1,
                    key=f"xf:{brand}:{listing}")
                cfg["logo"] = asset_picker(
                    "logo", "Logo override", cfg.get("logo"),
                    key=f"logo:{brand}:{listing}",
                    help="Overrides the brand default for this listing only.")
                cfg["music"] = asset_picker(
                    "music", "Music override", cfg.get("music"),
                    key=f"music:{brand}:{listing}",
                    help="Overrides the brand default for this listing only.")
            with a2:
                cfg["brand_persistent"] = st.checkbox(
                    "Lower third persistent — whole video",
                    value=bool(cfg["brand_persistent"]),
                    key=f"persist:{brand}:{listing}")
                if not cfg["brand_persistent"] and total > 0:
                    # reason: bounding by the real runtime stops the most common
                    # mistake -- a window ending after the video does, which ffmpeg
                    # accepts silently and which leaves the overlay up to the end.
                    cfg["brand_in"] = st.slider(
                        "Show at (s)", 0.0, float(total),
                        min(float(cfg["brand_in"]), total), 0.1,
                        key=f"bin:{brand}:{listing}")
                    cfg["brand_out"] = st.slider(
                        "Hide at (s)", 0.0, float(total),
                        min(float(cfg["brand_out"]), total), 0.1,
                        key=f"bout:{brand}:{listing}")
                    if cfg["brand_out"] <= cfg["brand_in"]:
                        st.error("Hide must come after show, or the lower third "
                                 "never appears.")
                # reason: the preset is derived from the photos, so the radio only
                # offers what they can actually feed. Defaulting to the derived
                # value is also what stops it resetting to 1080p on every page load
                # and forcing a spurious full rebuild.
                options = [p for p in PRESETS if not report[p]] or list(PRESETS)
                preset = st.radio(
                    "Preset", options,
                    index=options.index(derived) if derived in options else 0,
                    horizontal=True, key=f"preset:{brand}:{listing}")
                no_music = st.checkbox("Silent build (--no-music)",
                                       key=f"nomusic:{brand}:{listing}")
                allow_lowres = st.checkbox(
                    "Bypass the resolution gate (--allow-lowres)",
                    key=f"lowres:{brand}:{listing}")
            if allow_lowres:
                # reason: this is the project's loudest non-negotiable. It belongs
                # next to the checkbox, not only in the docs -- this is where the
                # decision is actually being made.
                st.error("**PREVIEW ONLY — never for a client or the MLS.** The "
                         "gate exists because an upscaled photo ships a soft, "
                         "fabricated-looking room. If a build needs this flag, the "
                         "photos are not ready: get the photographer's originals "
                         "or the MLS export instead. (IDEA.md §4) Use **Draft** "
                         "instead — it previews at 720p without touching `out/`.")

        d_flags, d_reason = delivery_flags(listing_dir, cfg, preset, no_music,
                                           allow_lowres)
        dr_flags, _ = draft_flags(listing_dir, cfg, no_music)
        bad_window = (not cfg["brand_persistent"]
                      and cfg["brand_out"] <= cfg["brand_in"])

        # reason: make_tour owns .build.lock now (O_EXCL, released on any exit).
        # This page only reports it -- writing it here would lock the build out of
        # its own folder.
        lock_path = os.path.join(listing_dir, LOCK)
        locked = os.path.exists(lock_path)
        if locked:
            st.warning("A build is already running in this listing. If that is "
                       "wrong — a previous run was killed — clear the lock.")
            if st.button("Clear stale lock"):
                os.remove(lock_path)
                st.rerun()

        st.subheader("Build")
        b1, b2, b3 = st.columns(3)
        go_order = b1.button("Check order · ~1s", disabled=locked,
                             use_container_width=True)
        b1.caption("Contact sheet straight off `photos/`. No encoding.")
        go_draft = b2.button("Draft · ~1min", disabled=locked or bad_window,
                             use_container_width=True)
        b2.caption("One watermarked 720p cut. Review on this machine only.")
        go_deliver = b3.button(
            "Build delivery · ~6min", type="primary",
            disabled=locked or bad_window or not (derived or allow_lowres),
            use_container_width=True)
        b3.caption(f"All six cuts at {preset}." if derived or allow_lowres
                   else "Blocked — the photos cannot feed either preset.")
        if d_reason:
            st.caption(f"Delivery will be a full build — {d_reason}.")
        else:
            st.caption("Delivery will take the fast path — reusing "
                       "`work_silent.mp4`, redoing music and branding only.")

        if go_order or go_draft or go_deliver:
            save_config(listing_dir, cfg)
            rung = "order" if go_order else "draft" if go_draft else "delivery"
            flags = (["--contact-sheet"] if go_order else
                     dr_flags if go_draft else d_flags)
            with st.status(f"{rung.title()} — {listing}…", expanded=True) as status:
                st.code(f"cd {rel} && python3 ../../../make_tour.py "
                        f"{' '.join(flags)}", language="bash")
                code = run_build(listing_dir, flags, st.empty())
                if code == 0:
                    if rung in ("draft", "delivery"):
                        save_state(listing_dir, rung, {
                            "preset": "720p" if rung == "draft" else preset,
                            "cfg": {k: cfg[k] for k in PACING_KEYS},
                            "photos": photo_state(listing_dir),
                            "finished": time.time()})
                    status.update(label=f"{rung.title()} finished",
                                  state="complete")
                else:
                    status.update(label=f"{rung.title()} failed (exit {code}) — "
                                        "intermediates kept for inspection",
                                  state="error")

        draft_path = os.path.join(listing_dir, DRAFT_OUT)
        if os.path.exists(draft_path):
            st.subheader("Draft")
            st.caption("720p at a fast preset, watermarked. **Review only — not a "
                       "deliverable, and it never enters `out/`.**")
            st.video(draft_path)

        files = outputs(listing_dir)
        if files:
            st.subheader("Delivery outputs")
            last = load_state(listing_dir).get("delivery", {})
            if last.get("finished"):
                st.caption(f"Built at {last.get('preset', '?')} on "
                           + time.strftime("%d %b %H:%M",
                                           time.localtime(last["finished"])))
            # reason: six st.video calls push ~50MB into the browser on every
            # rerun. One at a time keeps the page usable.
            choice = st.selectbox("Cut", files, key=f"cut:{brand}:{listing}")
            d = os.path.join(listing_dir, "out")
            if choice.startswith("tour_"):
                st.caption("**Delivery — clean. Send only after sign-off.**")
            else:
                st.caption("**Sample — watermarked. Send for review. Never as a "
                           "deliverable.**")
            size = os.path.getsize(os.path.join(d, choice)) / 1e6
            st.caption(f"{choice} · {size:.1f} MB")
            st.video(os.path.join(d, choice))

# ---- Asset library ----------------------------------------------------------
with assets_tab:
    st.caption("Shared across every brand and listing. Validated on arrival — a "
               "rejected file is never written into the library.")
    up_kind = st.selectbox("Add to", list(KINDS),
                           format_func=lambda k: KINDS[k][0])
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

    for kind, (sub, _) in KINDS.items():
        names = assets(kind)
        with st.expander(f"{sub}/ — {len(names)} file(s)"):
            for name in names:
                st.write(f"`{name}`")

# ---- Brand ------------------------------------------------------------------
with brand_tab:
    st.caption(f"Defaults for **{brand}**, inherited by every listing created "
               "under it. Set once here instead of on every property. "
               f"`make_tour.py` never reads `{BRAND_FILE}` — the dashboard resolves "
               "it into each listing's `config.json`, which stays the single "
               "source of truth for a build.")
    bcfg = dict(DEFAULTS)
    bcfg.update(brand_cfg)
    c1, c2 = st.columns(2)
    with c1:
        bcfg["logo"] = asset_picker("logo", "Logo", bcfg.get("logo"),
                                    key=f"brandlogo:{brand}")
        bcfg["music"] = asset_picker("music", "Music", bcfg.get("music"),
                                     key=f"brandmusic:{brand}")
    with c2:
        bcfg["clip_seconds"] = st.number_input(
            "Seconds per photo", 1.0, 15.0, float(bcfg["clip_seconds"]), 0.5,
            key=f"brandclip:{brand}")
        bcfg["xfade_seconds"] = st.number_input(
            "Crossfade (s)", 0.0, 3.0, float(bcfg["xfade_seconds"]), 0.1,
            key=f"brandxf:{brand}")
        bcfg["brand_persistent"] = st.checkbox(
            "Lower third persistent", value=bool(bcfg["brand_persistent"]),
            key=f"brandpersist:{brand}")

    if st.button("Save brand defaults"):
        save_brand(brand, bcfg)
        st.toast(f"{BRAND_FILE} written")

    st.divider()
    # reason: changing a brand default must not silently change what an already
    # delivered listing would rebuild to. Propagating is an explicit action.
    st.caption("Existing listings keep the settings they were built with. Push "
               "these defaults into them only when you mean to.")
    chosen = st.multiselect("Re-apply to", listings(brand))
    if st.button("Re-apply brand defaults", disabled=not chosen):
        for name in chosen:
            d = os.path.join(LISTINGS_ROOT, brand, name)
            merged = load_config(d, brand)
            merged.update({k: v for k, v in bcfg.items()
                           if k in BRAND_KEYS and v is not None})
            save_config(d, merged)
        st.toast(f"Re-applied to {len(chosen)} listing(s)")
