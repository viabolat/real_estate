#!/usr/bin/env python3
"""
make_tour.py — build one real estate walkthrough video from still photos.

Three rungs, each costing what the question is worth:

    python3 make_tour.py --contact-sheet # ~1s   is the order right?
    python3 make_tour.py --draft         # ~1min does the edit feel right?
    python3 make_tour.py                 # ~6min ship it

    python3 make_tour.py --no-music      # build without a soundtrack
    python3 make_tour.py --finish-only   # reuse the stitch, redo the tail
    python3 make_tour.py --allow-lowres  # build even from undersized photos
    python3 make_tour.py --720p          # 1280x720, for sources under 2150px
    python3 make_tour.py --keep-work     # keep intermediates so --finish-only works

--contact-sheet writes contact_sheet.png -- one numbered grid of photos/ in build
order -- and exits. It encodes nothing and runs before the resolution gate, since
"are these in the right order" is worth answering on photos that are not yet good
enough to build with.

--draft forces 720p at a fast x264 preset and builds ONE cut, draft.mp4, in the
listing root: lower third + logo + the centered proofing watermark, so every
branding decision shows at once. It is a preview, never a deliverable. It keeps
its intermediates strictly separate -- work_draft.mp4 and clips_draft/ -- so a
draft-quality stitch can never be picked up by a delivery build, and it never
writes into out/, so the tour_/sample_ filename boundary stays intact.

A successful build deletes its own intermediates (clips/, work_silent.mp4,
work_music_*.m4a). Pass --keep-work when you intend to iterate on music or
branding with --finish-only. A FAILED build keeps everything for inspection.

Only one build may run in a folder at a time: the script takes .build.lock with
O_EXCL on startup and releases it on any exit, clean or not. A second run refuses
immediately, naming the pid that holds it, rather than deleting intermediates the
first run is still using.

Expects, in the working directory:
    photos/          numbered jpgs in tour order: 01_exterior.jpg, 02_entry.jpg ...
                     The numeric prefix IS the order. Every build prints the
                     resolved order first, and warns when filenames carry no
                     prefix -- that order is alphabetical, not authored.
    music.mp3        a LICENSED track, longer than the finished video
    lower_third.png  optional RGBA branding: either a full-frame
                     1920x1080 plate or a small lower-third strip
    logo.png         optional RGBA brokerage logo, pinned top-left. Transparent
                     padding is trimmed automatically, then the art is fitted
                     into a 360x200 box (1080p-relative), aspect preserved.
    viabolat.png     optional RGBA proofing watermark for the sample_ cuts only.
                     Centered, 45% of frame, 35% opacity. Wants a source at
                     least 864px on the long edge.
    config.json      optional per-listing overrides -- see below.

Run it from the folder holding photos/. That is normally a listing folder such as
brewester/9_w_cedar/, in which case the four branding files above are usually
supplied by config.json instead. Any asset path that does not resolve against the
working directory is retried beside this script, so a shared global_assets/ library
and the fixed viabolat.png keep working from any listing folder.

config.json -- every key optional, every default is the constant in the source:

    clip_seconds      4.0    seconds per photo, before crossfade overlap
    xfade_seconds     0.5    crossfade length
    brand_persistent  true   false = show the lower third only between the times below
    brand_in          0.8    only read when brand_persistent is false
    brand_out         6.5    ditto; must be greater than brand_in
    lower_third       "lower_third.png"
    logo              "logo.png"
    music             "music.mp3"
    watermark         "viabolat.png"

Photo order is NOT a config key and never will be -- it lives in the filename
prefix and nowhere else. Changing clip_seconds or xfade_seconds invalidates
work_silent.mp4, so those changes need a full build, not --finish-only. So does
renaming photos to reorder them: --finish-only reuses the earlier stitch and
would reship the old order, which is why that path warns.

dashboard.py is a local Streamlit front end over all of the above: it manages the
shared asset library, writes config.json, and runs this script per listing. It
also keeps per-brand defaults in agents/<brand>/brand.json, which THIS script
never reads -- the dashboard resolves them into each listing's config.json, so
config.json stays the single record of what produced a delivered video.

Outputs -- six cuts, two families:

    DELIVERY (clean, what the client gets on sign-off)
    out/tour_branded.mp4      music + branding
    out/tour_unbranded.mp4    music, no branding  (MLS/IDX safe)
    out/tour_vertical.mp4     portrait, blur-padded for Reels/TikTok

    SAMPLE (same edit + centered proofing watermark, what the client reviews)
    out/sample_branded.mp4
    out/sample_unbranded.mp4
    out/sample_vertical.mp4

    DRAFT (--draft only, never a deliverable)
    draft.mp4                 listing root, NOT out/

The watermark is NOT gated on branding -- it is the reason a sample exists, so it
appears on the unbranded sample too. Never send a sample_ file as a deliverable
and never send a tour_ file before sign-off. draft.mp4 is neither: it is a
720p/fast-preset review cut and does not leave the machine that built it.

Landscape is 1920x1080, or 1280x720 with --720p or --draft; the portrait cut and
the branding overlay follow whichever preset is active.

Requires ffmpeg with libx264 and aac.
"""

import atexit
import glob
import json
import os
import subprocess
import sys

# ---- config.json ------------------------------------------------------------
# A listing folder may carry a config.json overriding the values marked [cfg]
# below. An absent file, or an absent key, falls back to the default written
# here -- running the bare CLI in a folder with no config behaves exactly as it
# always has. config.json carries timing, pacing and asset paths ONLY: photo
# order lives in the filename prefix and nowhere else.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = "config.json"


def _asset(path):
    """Resolve an asset path: as given (relative to cwd), else beside the script.

    reason: a build may run with cwd set to a listing folder, where the shared
    global_assets/ library and the fixed viabolat.png sit beside the script, not
    beside the photos. Trying cwd first keeps a per-listing override working.
    """
    if not path or os.path.exists(path):
        return path
    beside = os.path.join(SCRIPT_DIR, path)
    return beside if os.path.exists(beside) else path


_cfg = {}
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE) as f:
        _cfg = json.load(f)

# ---- tune these -------------------------------------------------------------
CLIP_SECONDS = _cfg.get("clip_seconds", 4.0)     # [cfg] per photo, pre-crossfade
XFADE_SECONDS = _cfg.get("xfade_seconds", 0.5)   # [cfg] crossfade length
FPS = 30
ZOOM_MAX = 1.12        # 12% push. Above ~1.20 it starts to look cheap.
MUSIC_VOLUME = 0.55
MUSIC_XFADE = 2.0      # crossfade length when a short track has to loop
# [cfg] True = lower third on screen the whole video
BRAND_PERSISTENT = _cfg.get("brand_persistent", True)
BRAND_IN = _cfg.get("brand_in", 0.8)    # [cfg] only when BRAND_PERSISTENT is False
BRAND_OUT = _cfg.get("brand_out", 6.5)  # [cfg] ditto
LOGO_PERSISTENT = True           # brokerage mark: normally up for the whole video
LOGO_BOX_W, LOGO_BOX_H = 360, 200  # 1080p-relative box; ~19% of frame width
# [cfg] Branding inputs. A config.json points these at the shared global_assets/
# library; with no config they are the plain filenames this folder always used.
LOWER_THIRD = _asset(_cfg.get("lower_third", "lower_third.png"))
LOGO = _asset(_cfg.get("logo", "logo.png"))
MUSIC = _asset(_cfg.get("music", "music.mp3"))
# Sample cuts: a centered proofing watermark. Obscuring the room is the POINT here
# -- these go to the client for approval, the tour_ cuts are the delivery.
SAMPLE_WATERMARK = _asset(_cfg.get("watermark", "viabolat.png"))   # [cfg]
# reason: Zillow and most CDNs serve .webp now; globbing only jpg/png made a full
# folder of photos look empty. Module level so dashboard.py shares one list.
PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".heic"}
SAMPLE_WM_FRAC = 0.45            # fraction of the frame it may occupy
SAMPLE_WM_OPACITY = 0.35         # 0-1. Readable, still see-through.

# reason: a draft answers "is the edit right?", never "is the picture good?", so it
# is pinned to the cheap preset and a fast encoder regardless of what the delivery
# build will use. Measured on 8 photos: delivery 5m50s, draft ~45s.
DRAFT = "--draft" in sys.argv

# 1080p needs 2150px sources; 720p needs 1434px. Pick the one your photos can
# actually feed -- a crisp downscale beats a soft upscale every time.
# reason: 1536px sources upscale 1.4x to 1080p (soft) but downscale to 720p (crisp).
OUT_W, OUT_H = (1280, 720) if ("--720p" in sys.argv or DRAFT) else (1920, 1080)

# Encoder settings. Delivery values are the ones every cut shipped with to date --
# changing them changes what the client receives, so they are named, not inline.
CRF = 20 if DRAFT else 18
X264_PRESET = "veryfast" if DRAFT else "medium"
VERTICAL_CRF = 20                # portrait cut re-encodes an already-encoded source

# A draft must never feed a delivery build: it is 720p at a fast preset, and a
# stale intermediate silently reused is exactly how the wrong photo order shipped.
# Separate filenames are what keep the two families from ever touching.
SILENT_WORK = "work_draft.mp4" if DRAFT else "work_silent.mp4"
DRAFT_OUT = "draft.mp4"          # listing root, NOT out/ -- out/ holds real cuts only
CLIPS_DIR = "clips_draft" if DRAFT else "clips"
SHEET_OUT = "contact_sheet.png"
LOCK_FILE = ".build.lock"
# -----------------------------------------------------------------------------

# ---- everything below derives from OUT_W/OUT_H; do not hardcode a size ------
# reason: zoompan truncates its crop origin AND crop size to whole integers.
# At 3x supersampling the push is only ~1.7px/frame, so rounding stalls the crop
# for a frame then jumps two -- visible as camera shake. Measured frame-to-frame
# spread: 3x = 55%, 6x = 21%, 8x = 22% (no further gain). A constant 7680px work
# width lands on that knee for both presets. Post-downscale filtering does not
# help: zoompan has already snapped the crop before any scaler sees it.
WORK_W = 7680
WORK_H = round(WORK_W * OUT_H / OUT_W / 2) * 2   # even, matches output aspect
MIN_PHOTO_W = int(OUT_W * ZOOM_MAX)     # below this, the zoom crop upscales
VERT_W, VERT_H = OUT_H, OUT_W           # portrait cut: 1080x1920 or 720x1280
SCALE = OUT_W / 1920.0                  # 1080p-relative, for overlay + blur sizing
MARGIN = round(70 * SCALE)              # overlay inset from frame edge
# reason: a logo PNG's native size is arbitrary -- a wordmark and a square badge
# have nothing in common. Fit into a box instead of scaling by a fixed factor so
# both land at a sane on-screen size without per-file tuning.
LOGO_W = round(LOGO_BOX_W * SCALE)
LOGO_H = round(LOGO_BOX_H * SCALE)
WM_W = round(OUT_W * SAMPLE_WM_FRAC)    # watermark fit box, both presets
WM_H = round(OUT_H * SAMPLE_WM_FRAC)
BLUR_SIGMA = round(28 * SCALE, 1)       # portrait backdrop blur

FRAMES = int(CLIP_SECONDS * FPS)
PREP = (f"scale={WORK_W}:{WORK_H}:force_original_aspect_ratio=increase,"
        f"crop={WORK_W}:{WORK_H}")
TAIL = f"s={OUT_W}x{OUT_H}:fps={FPS}"
CENTER_X = "iw/2-(iw/zoom/2)"
CENTER_Y = "ih/2-(ih/zoom/2)"
STEP = round((ZOOM_MAX - 1.0) / FRAMES, 6)

# Four motion styles, cycled so no two neighbouring clips move the same way.
MOTIONS = [
    # push in — good for a focal point: fireplace, island, view out a window
    f"zoompan=z='min(zoom+{STEP},{ZOOM_MAX})':d={FRAMES}:x='{CENTER_X}':y='{CENTER_Y}':{TAIL}",
    # pan right — good for wide living rooms and open plans
    f"zoompan=z='{ZOOM_MAX}':d={FRAMES}:x='(iw-iw/zoom)*on/{FRAMES-1}':y='{CENTER_Y}':{TAIL}",
    # pull out — good for reveals: step into a room, then show the whole thing
    f"zoompan=z='{ZOOM_MAX}-{STEP}*on':d={FRAMES}:x='{CENTER_X}':y='{CENTER_Y}':{TAIL}",
    # tilt up — good for exteriors, stairwells, vaulted ceilings
    f"zoompan=z='{ZOOM_MAX}':d={FRAMES}:x='{CENTER_X}':y='(ih-ih/zoom)*(1-on/{FRAMES-1})':{TAIL}",
]


def run(cmd):
    print("  $", " ".join(str(c) for c in cmd)[:150], "...")
    subprocess.run(cmd, check=True)


def duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def build_clips(photos):
    os.makedirs(CLIPS_DIR, exist_ok=True)
    paths = []
    for i, photo in enumerate(photos):
        out = f"{CLIPS_DIR}/{i:03d}.mp4"
        vf = f"{PREP},{MOTIONS[i % len(MOTIONS)]},setsar=1,format=yuv420p"
        run(["ffmpeg", "-y", "-loglevel", "error",
             "-loop", "1", "-i", photo, "-t", str(CLIP_SECONDS),
             "-filter_complex", vf,
             "-c:v", "libx264", "-crf", str(CRF), "-preset", X264_PRESET,
             "-r", str(FPS), out])
        paths.append(out)
        print(f"  [{i+1}/{len(photos)}] {os.path.basename(photo)}")
    return paths


def stitch(clips, out=None):
    out = SILENT_WORK if out is None else out
    """Chain xfade transitions. offset_i = i * (CLIP - XFADE)."""
    if len(clips) == 1:
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", clips[0],
             "-c", "copy", out])
        return out
    inputs, filt, prev = [], [], "0:v"
    for c in clips:
        inputs += ["-i", c]
    for i in range(1, len(clips)):
        offset = i * (CLIP_SECONDS - XFADE_SECONDS)
        label = f"v{i}"
        filt.append(f"[{prev}][{i}:v]xfade=transition=fade:"
                    f"duration={XFADE_SECONDS}:offset={offset:.2f}[{label}]")
        prev = label
    run(["ffmpeg", "-y", "-loglevel", "error"] + inputs +
        ["-filter_complex", ";".join(filt), "-map", f"[{prev}]",
         "-c:v", "libx264", "-crf", str(CRF), "-preset", X264_PRESET,
         "-pix_fmt", "yuv420p", "-r", str(FPS), out])
    return out


def dimensions(path):
    """(width, height) of an image or video, or (0, 0) if unreadable."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        w, h = (int(x) for x in r.stdout.strip().split(",")[:2])
        return w, h
    except ValueError:
        return 0, 0


def gate_failures(photos, out_w=None, out_h=None):
    """[(path, "WxH", upscale_factor)] for photos too small to fill the frame.

    reason: separated from check_resolution so the dashboard can ask the same
    question -- "which photos block which preset?" -- without printing or exiting,
    and answer it on page load instead of after a five-minute render. One
    implementation of the rule, two callers.
    """
    out_w = OUT_W if out_w is None else out_w
    out_h = OUT_H if out_h is None else out_h
    bad = []
    for p in photos:
        w, h = dimensions(p)
        if not w:
            bad.append((p, "unreadable", 0)); continue
        # the frame is filled by the larger of the two scale factors
        scale = max(out_w * ZOOM_MAX / w, out_h * ZOOM_MAX / h)
        if scale > 1.0:
            bad.append((p, f"{w}x{h}", scale))
    return bad


def check_resolution(photos, allow_lowres=False):
    """Refuse to render photos too small to fill the frame.
    # reason: 384x288 sources were upscaled 5x to 1080p, which no crf/preset
    # setting can fix. Fail at second zero instead of after a 5-minute render.
    """
    bad = gate_failures(photos)
    if not bad:
        return
    print(f"\n{len(bad)} of {len(photos)} photos are below {MIN_PHOTO_W}px wide:")
    for p, dims, scale in bad:
        print(f"  {os.path.basename(p):<32} {dims:>10}  upscaled {scale:.1f}x")
    if not allow_lowres:
        sys.exit("\nThese will look soft or mushy at 1080p. Reshoot or re-export "
                 "at 3000px+ wide, or rerun with --allow-lowres to build anyway.")
    print("  --allow-lowres set: building anyway, expect soft output.\n")


def music_span(path):
    """(start, end) of actual content, ignoring leading/trailing silence."""
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", path, "-vn", "-af",
                        "silencedetect=noise=-50dB:d=0.3", "-f", "null", "-"],
                       capture_output=True, text=True)
    total = duration(path)
    spans, cur = [], None
    for line in r.stderr.splitlines():
        if "silence_start:" in line:
            cur = float(line.split("silence_start:")[1].split()[0])
        elif "silence_end:" in line and cur is not None:
            spans.append((cur, float(line.split("silence_end:")[1].split()[0])))
            cur = None
    if cur is not None:
        spans.append((cur, total))          # silence ran to end of file
    start, end = 0.0, total
    for a, b in spans:
        if a <= 0.05:
            start = max(start, b)           # leading silence
        if b >= total - 0.05:
            end = min(end, a)               # trailing silence
    return start, max(end, start + 1.0)


def prepare_music(src, need):
    """Trim silence off a track and loop it with crossfades to cover `need`.
    # reason: a 30s mp3 was really 24.8s of music plus 4.7s of dead air. Raw
    # -stream_loop repeated the dead air, leaving a 5s dropout mid-video.
    """
    a, b = music_span(src)
    body = b - a
    cur = "work_music_0.m4a"
    run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{a:.3f}",
         "-to", f"{b:.3f}", "-i", src, "-vn",
         "-c:a", "aac", "-b:a", "192k", cur])
    tail = duration(src) - b
    if a > 0.05 or tail > 0.05:
        print(f"  trimmed {a:.1f}s lead-in and {tail:.1f}s trailing silence "
              f"-> {body:.1f}s of music")
    length, i = body, 1
    while length < need + 1.0:
        nxt = f"work_music_{i}.m4a"
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", cur, "-i", cur,
             "-filter_complex", f"[0:a][1:a]acrossfade=d={MUSIC_XFADE}[a]",
             "-map", "[a]", "-c:a", "aac", "-b:a", "192k", nxt])
        length = length * 2 - MUSIC_XFADE
        print(f"  looped music -> {length:.1f}s "
              f"({MUSIC_XFADE}s crossfade at the seam)")
        cur, i = nxt, i + 1
    return cur


def music_ok(path):
    """True only if path is a real, decodable audio file.
    # reason: os.path.exists() passed on a 0-byte music.mp3 and ffmpeg died at
    # the very last step, after ~5 minutes of clip rendering. Validate up front.
    """
    if not path or not os.path.exists(path) or os.path.getsize(path) == 0:
        return False
    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0",
                        "-show_entries", "stream=codec_type", "-of", "csv=p=0",
                        path], capture_output=True, text=True)
    return p.returncode == 0 and "audio" in p.stdout


def alpha_bbox(path, thresh=8):
    """Tight bounds of a PNG's non-transparent pixels as (x, y, w, h), or None.

    reason: the fit box scales the whole canvas, so transparent padding baked
    into an export silently shrinks the mark and shoves it off its margin -- a
    684x438 logo whose art only fills 514x273 renders 33% smaller than asked,
    inset by the padding on top of MARGIN. Measure the art instead of trusting
    the canvas, so any logo drops in without hand-checking the file.
    """
    w, h = dimensions(path)
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", "alphaextract",
                        "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                       capture_output=True)
    a = p.stdout[:w * h]
    if p.returncode != 0 or len(a) < w * h:
        return None                      # no alpha channel -- nothing to trim
    # reason: max() over a bytes slice runs in C. A per-pixel Python loop over a
    # large logo is seconds; this is milliseconds. a[c::w] strides one column.
    rows = [r for r in range(h) if max(a[r * w:(r + 1) * w]) > thresh]
    if not rows:
        return None                      # fully transparent -- leave it alone
    cols = [c for c in range(w) if max(a[c::w]) > thresh]
    return cols[0], rows[0], cols[-1] - cols[0] + 1, rows[-1] - rows[0] + 1


def trim_filter(path):
    """(crop_filter_or_empty, (art_w, art_h)) for an overlay PNG.

    reason: logo and watermark both need padding trimmed before the fit box, and
    both need the art's true size to report upscale. One helper, one behaviour.
    """
    lw, lh = dimensions(path)
    box = alpha_bbox(path)
    if box and (box[2], box[3]) != (lw, lh):
        return f"crop={box[2]}:{box[3]}:{box[0]}:{box[1]},", (box[2], box[3])
    return "", (lw, lh)


def finish(silent, music, brand, out, branded=True, logo=None, watermark=None):
    dur = duration(silent)
    # reason: a brand_out past the end of the cut is not an ffmpeg error -- the
    # overlay just stays up to the last frame. Say so rather than let the operator
    # believe a window was applied that never closed.
    if not BRAND_PERSISTENT and BRAND_OUT > dur:
        print(f"    WARNING: brand_out {BRAND_OUT}s is past the {dur:.1f}s runtime -- "
              f"the lower third will stay up to the end.")
    use_brand = bool(branded and brand and os.path.exists(brand))
    use_logo = bool(branded and logo and os.path.exists(logo))
    # reason: NOT gated on `branded`. The proofing watermark is the whole reason a
    # sample cut exists, so it must survive onto the unbranded sample too.
    use_wm = bool(watermark and os.path.exists(watermark))

    # reason: the lower third carries per-listing agent info, the logo is the
    # constant brokerage mark. They are separate inputs so changing one does not
    # mean re-authoring the other. Both are branding, so both follow `branded`
    # and stay off the MLS/IDX cut.
    pre = []            # scale filter per overlay input
    layers = []         # (label, overlay position, persistent) in stacking order
    idx = 1             # ffmpeg input index; 0 is always the silent video

    if use_brand:
        bw, bh = dimensions(brand)
        # reason: a full-frame plate is already positioned by its own artwork --
        # insetting it by MARGIN shifts the design off-register. Only a small
        # strip PNG wants a margin. Either way it is resampled to the preset.
        full_frame = bw >= 0.9 * 1920
        if full_frame:
            pre.append(f"[{idx}:v]scale={OUT_W}:{OUT_H}[bp];")
            pos = "x=0:y=0"
        else:
            pre.append(f"[{idx}:v]scale=iw*{SCALE}:-1[bp];")
            pos = f"x={MARGIN}:y=H-h-{MARGIN}"
        layers.append(("bp", pos, BRAND_PERSISTENT))
        idx += 1

    if use_logo:
        trim, (aw, ah) = trim_filter(logo)
        fit = min(LOGO_W / aw, LOGO_H / ah)
        print(f"    logo art {aw}x{ah} -> renders "
              f"{round(aw * fit)}x{round(ah * fit)} top-left")
        pre.append(f"[{idx}:v]{trim}scale=w={LOGO_W}:h={LOGO_H}:"
                   f"force_original_aspect_ratio=decrease[lg];")
        layers.append(("lg", f"x={MARGIN}:y={MARGIN}", LOGO_PERSISTENT))
        idx += 1

    if use_wm:
        trim, (aw, ah) = trim_filter(watermark)
        fit = min(WM_W / aw, WM_H / ah)
        rw, rh = round(aw * fit), round(ah * fit)
        print(f"    watermark art {aw}x{ah} -> renders {rw}x{rh} centered "
              f"at {SAMPLE_WM_OPACITY:.0%} opacity")
        # reason: same principle as the photo gate -- say it out loud rather than
        # silently shipping a smeared 15x upscale of a tiny source.
        if fit > 1.5:
            print(f"    WARNING: watermark upscales {fit:.1f}x and will look soft. "
                  f"Supply at least {round(WM_W)}px on the long edge.")
        # reason: colorchannelmixer aa multiplies the existing alpha, so the mark's
        # own transparency and shape survive -- it does not fill the bounding box.
        pre.append(f"[{idx}:v]{trim}scale=w={WM_W}:h={WM_H}:"
                   f"force_original_aspect_ratio=decrease,"
                   f"format=rgba,colorchannelmixer=aa={SAMPLE_WM_OPACITY}[wm];")
        # reason: last = topmost. A proofing mark sits over the lower third so it
        # cannot be cropped or covered away.
        layers.append(("wm", "x=(W-w)/2:y=(H-h)/2", True))
        idx += 1

    # reason: overlay is binary, so N layers need N-1 intermediate labels chained
    # in order. The last one flows straight into the fades with no label.
    v = "".join(pre) + "[0:v]"
    for i, (label, pos, persistent) in enumerate(layers):
        v += f"[{label}]overlay={pos}"
        if not persistent:
            v += f":enable='between(t,{BRAND_IN},{BRAND_OUT})'"
        v += "," if i == len(layers) - 1 else f"[ov{i}];[ov{i}]"
    v += f"fade=t=in:st=0:d=1,fade=t=out:st={dur-1.5:.2f}:d=1.5[v]"

    audio_idx = idx
    if music:
        a = (f"[{audio_idx}:a]afade=t=in:st=0:d=2,"
             f"afade=t=out:st={dur-3:.2f}:d=3,volume={MUSIC_VOLUME}[a]")
    else:
        # silent stereo track so every output still carries an audio stream
        a = f"[{audio_idx}:a]anull[a]"

    inputs = ["-i", silent]
    # reason: must match the order idx was handed out above, or the overlay
    # inputs and the audio input index all point at the wrong stream.
    if use_brand:
        inputs += ["-i", brand]
    if use_logo:
        inputs += ["-i", logo]
    if use_wm:
        inputs += ["-i", watermark]
    if music:
        inputs += ["-i", music]     # already trimmed and looped by prepare_music
    else:
        inputs += ["-f", "lavfi", "-t", f"{dur:.2f}",
                   "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]

    run(["ffmpeg", "-y", "-loglevel", "error"] + inputs +
        ["-filter_complex", f"{v};{a}", "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-crf", str(CRF), "-preset", X264_PRESET,
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
         # reason: -shortest is unreliable with filter_complex (it stopped at
         # 50s on a 60s video). Pin the duration to the silent cut instead.
         "-t", f"{dur:.3f}", "-movflags", "+faststart", out])


def vertical(src, out):
    vf = (f"[0:v]split=2[bg][fg];"
          f"[bg]scale={VERT_W}:{VERT_H}:force_original_aspect_ratio=increase,"
          f"crop={VERT_W}:{VERT_H},gblur=sigma={BLUR_SIGMA},"
          f"eq=brightness=-0.12[bgb];"
          f"[fg]scale={VERT_W}:-2[fgs];"
          f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2[v]")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", src,
         "-filter_complex", vf, "-map", "[v]", "-map", "0:a",
         "-c:v", "libx264", "-crf", str(VERTICAL_CRF), "-preset", X264_PRESET,
         "-pix_fmt", "yuv420p", "-c:a", "copy",
         "-movflags", "+faststart", out])


CELL_W, CELL_H = 480, 270        # contact sheet cell; 4 across = a 1920px sheet


def contact_sheet(photos, out=None):
    """Tile the photos, numbered, into one image -- the cheapest order check there is.

    reason: verifying the running order used to mean sitting through a full build
    (5m50s for 8 photos at 1080p) because the order is only visible in the finished
    video. This answers the same question in well under a second, with no encoding.

    Takes the already-sorted list main() builds, and passes each file as an explicit
    -i rather than re-globbing: the sheet has to show the build's order, and glob
    would neither guarantee that nor cope with mixed extensions.
    """
    out = SHEET_OUT if out is None else out
    cols = min(4, len(photos))
    rows = -(-len(photos) // cols)
    inputs, parts, labels = [], [], []
    for i, photo in enumerate(photos):
        inputs += ["-i", photo]
        parts.append(
            f"[{i}:v]scale={CELL_W}:{CELL_H}:force_original_aspect_ratio=increase,"
            f"crop={CELL_W}:{CELL_H},"
            f"drawtext=text='{i + 1}':x=10:y=8:fontsize=34:fontcolor=yellow:"
            f"box=1:boxcolor=black@0.65:boxborderw=6[c{i}]")
        labels.append(f"[c{i}]")
    parts.append(f"{''.join(labels)}concat=n={len(photos)}:v=1:a=0[s];"
                 f"[s]tile={cols}x{rows}:color=black[v]")
    run(["ffmpeg", "-y", "-loglevel", "error", *inputs,
         "-filter_complex", ";".join(parts), "-map", "[v]",
         "-frames:v", "1", "-update", "1", out])
    print(f"Contact sheet -> {out}  ({cols}x{rows}, {len(photos)} photos)")
    return out


def acquire_lock():
    """Refuse to start a second build in the same folder.

    reason: cleanup() deletes by glob, so two concurrent runs in one listing remove
    each other's intermediates mid-encode. The lock lives here rather than in the
    dashboard because the dashboard builds by running this script -- a CLI run would
    not see a lock the dashboard held, and a dashboard-held lock would shut this
    process out of the folder it was launched to build. O_EXCL because
    check-then-create races exactly the two builds this guards.
    """
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            holder = open(LOCK_FILE).read().strip() or "unknown"
        except OSError:
            holder = "unknown"
        sys.exit(f"A build is already running here (pid {holder}). Wait for it, or "
                 f"delete {LOCK_FILE} if that process is gone.")
    with os.fdopen(fd, "w") as f:
        f.write(str(os.getpid()))
    # reason: atexit fires on a clean return, on sys.exit, and on an uncaught
    # exception -- every way this script ends short of SIGKILL, which no finally
    # would survive either. Avoids re-indenting main() into a try block.
    atexit.register(release_lock)


def release_lock():
    try:
        os.remove(LOCK_FILE)
    except OSError:
        pass


def cleanup(keep_work=False):
    """Delete regenerable build artifacts. Only ever called after a successful
    run -- run() raises on any ffmpeg failure, so a broken build keeps its
    intermediates for inspection.
    """
    junk = glob.glob("work_music_*.m4a")          # always regenerated
    if not keep_work:
        junk += glob.glob(f"{CLIPS_DIR}/*.mp4")
        if os.path.exists(SILENT_WORK):
            junk += [SILENT_WORK]
    for p in junk:
        os.remove(p)
    if os.path.isdir(CLIPS_DIR) and not os.listdir(CLIPS_DIR):
        os.rmdir(CLIPS_DIR)
    if junk:
        mb = "" if keep_work else " (rerun with --keep-work to keep them)"
        print(f"Cleaned up {len(junk)} intermediate file(s){mb}")
    if keep_work:
        print(f"  kept {SILENT_WORK} + {CLIPS_DIR}/ for --finish-only")


def tour_order(photos):
    """Print the resolved tour order, and warn when nothing actually authored it.

    reason: order is just the sort of the filenames, so a folder of CDN hashes or
    camera serials builds a shuffled tour whose only symptom is the finished video
    -- 46_beacon_5 was delivered that way. Printing the list puts the order in
    front of the operator before the encode, and the warning names the cause.
    """
    print(f"Tour order ({len(photos)} photos, from the filename prefix):")
    for i, photo in enumerate(photos, 1):
        print(f"  {i:>2}. {os.path.basename(photo)}")
    unprefixed = [x for x in photos if not os.path.basename(x)[:1].isdigit()]
    if unprefixed:
        print(f"    WARNING: {len(unprefixed)} of {len(photos)} filenames do not start "
              "with a number, so the order above is alphabetical, not authored.")
        print("    WARNING: rename them 01_, 02_, ... in walkthrough order before "
              "delivering. See IDEA.md 5 and 7.")


def main():
    photos = sorted(p for p in glob.glob("photos/*")
                    if os.path.splitext(p)[1].lower() in PHOTO_EXTS)
    if not photos:
        sys.exit("No photos found. Put them in ./photos/ named in tour order.")
    if _cfg:
        print(f"Config: {CONFIG_FILE} ({len(_cfg)} override(s))")
    tour_order(photos)
    # reason: the order check is deliberately upstream of the resolution gate. Its
    # whole job is to answer "are these the right photos in the right order?", and
    # that question is worth answering on photos that are not yet good enough to
    # build with -- which is exactly when you still have time to swap them.
    if "--contact-sheet" in sys.argv:
        contact_sheet(photos)
        return

    # reason: an inverted window builds a perfectly valid filtergraph in which
    # between(t,IN,OUT) is never true, so the lower third silently never appears.
    if not BRAND_PERSISTENT and BRAND_OUT <= BRAND_IN:
        sys.exit(f"brand_out ({BRAND_OUT}) must be greater than brand_in "
                 f"({BRAND_IN}). Fix {CONFIG_FILE} and rerun.")
    print(f"Output preset: {OUT_W}x{OUT_H} "
          f"(needs photos >= {MIN_PHOTO_W}px on the long edge)")
    check_resolution(photos, allow_lowres="--allow-lowres" in sys.argv)

    no_music = "--no-music" in sys.argv
    music = None if no_music else MUSIC
    if music and not music_ok(music):
        sys.exit(f"{MUSIC} is missing, empty, or has no audio stream. "
                 "Drop in a track you are licensed to use, or rerun with "
                 "--no-music to build silent versions.")

    acquire_lock()
    if not DRAFT:
        os.makedirs("out", exist_ok=True)
    silent = SILENT_WORK
    if "--finish-only" in sys.argv and os.path.exists(silent):
        print(f"Reusing {silent} ({duration(silent):.1f}s) - skipping clips.")
        # reason: the order printed above describes photos/ as it stands now, but
        # work_silent.mp4 was stitched by an earlier run. Renaming photos to fix the
        # order and then rebuilding with --finish-only silently reships the old order.
        print("    WARNING: --finish-only reuses that earlier stitch. If photos/ has "
              "changed since, the order above is NOT what renders -- drop the flag.")
    else:
        # reason: --finish-only with no work_silent.mp4 (a previous default build
        # cleaned it up) must fall back to a full build, not crash in finish().
        if "--finish-only" in sys.argv:
            print(f"--finish-only: no {silent} to reuse, building from photos.")
        print(f"Building {len(photos)} clips...")
        clips = build_clips(photos)

        print("Stitching with crossfades...")
        silent = stitch(clips)

    print("Adding music and branding..." if music else "Adding branding (silent)...")
    if music:
        music = prepare_music(music, duration(silent))
    # reason: every overlay is silently optional, which made a typo'd filename look
    # like a working build with no branding. Say what is actually applied.
    for name, path in (("lower third", LOWER_THIRD), ("logo", LOGO),
                       ("sample watermark", SAMPLE_WATERMARK)):
        print(f"  {name}: {path if os.path.exists(path) else 'not found - skipped'}")

    # reason: one cut, and it is the watermarked branded one -- that single file
    # shows the running order, the pacing, the lower third, the logo and the music
    # fit all at once, which is everything a draft is for. Encoding the other five
    # to answer those questions is the waste this flag exists to stop.
    if DRAFT:
        print(f"  {DRAFT_OUT} (720p draft, not a deliverable)...")
        finish(silent, music, LOWER_THIRD, DRAFT_OUT,
               branded=True, logo=LOGO, watermark=SAMPLE_WATERMARK)
        cleanup(keep_work=any(f in sys.argv
                              for f in ("--keep-work", "--finish-only")))
        total = len(photos) * CLIP_SECONDS - (len(photos) - 1) * XFADE_SECONDS
        print(f"\nDone. Runtime {total:.1f}s")
        print(f"  {DRAFT_OUT}  ({os.path.getsize(DRAFT_OUT)/1e6:.1f} MB)")
        print("  DRAFT -- 720p at a fast preset, for review on this machine only.")
        print("  Nothing here is a deliverable. Rebuild without --draft to ship.")
        return

    print("  tour_branded...")
    finish(silent, music, LOWER_THIRD,
           "out/tour_branded.mp4", branded=True, logo=LOGO)
    print("  tour_unbranded...")
    finish(silent, music, None,
           "out/tour_unbranded.mp4", branded=False, logo=None)

    # reason: sample cuts are the client proofing copy -- identical edit, plus a
    # centered watermark so an unapproved tour cannot be used as-is. The tour_
    # files are the delivery once they sign off.
    print("  sample_branded...")
    finish(silent, music, LOWER_THIRD, "out/sample_branded.mp4",
           branded=True, logo=LOGO, watermark=SAMPLE_WATERMARK)
    print("  sample_unbranded...")
    finish(silent, music, None, "out/sample_unbranded.mp4",
           branded=False, logo=None, watermark=SAMPLE_WATERMARK)

    print("Building vertical cuts...")
    vertical("out/tour_branded.mp4", "out/tour_vertical.mp4")
    vertical("out/sample_branded.mp4", "out/sample_vertical.mp4")

    # reason: --finish-only means the user is iterating on music/branding, so the
    # clips are still needed next run. Deleting them would force a full rebuild.
    cleanup(keep_work=any(f in sys.argv for f in ("--keep-work", "--finish-only")))

    total = len(photos) * CLIP_SECONDS - (len(photos) - 1) * XFADE_SECONDS
    print(f"\nDone. Runtime {total:.1f}s")
    for f in sorted(glob.glob("out/*.mp4")):
        print(f"  {f}  ({os.path.getsize(f)/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
