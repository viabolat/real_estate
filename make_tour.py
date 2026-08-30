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
    python3 make_tour.py --samples-only  # the 3 sample_ cuts only  (run 1)
    python3 make_tour.py --delivery-only # the 3 tour_ cuts only    (run 2)

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

A successful DELIVERY build additionally clears the draft lineage -- work_draft.mp4
and clips_draft/ -- regardless of --keep-work, because a delivery supersedes any
draft of the same listing and never reuses a draft stitch. draft.mp4 itself is
left alone: it is the review cut that was asked for, not an intermediate. The
reverse never happens -- a --draft run only ever clears what a draft wrote.

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
                     1920x1080 plate or a small lower-third strip. ABSENT, one is
                     drawn from the address, agent name and phone in config.json,
                     so a listing needs no hand-made plate at all.
    logo.png         optional RGBA brokerage logo, pinned top-left. Transparent
                     padding is trimmed automatically, then the art is fitted
                     into a 360x200 box (1080p-relative), aspect preserved.
    viabolat.png     optional RGBA proofing watermark for the sample_ cuts only.
                     Centered, 45% of frame, 35% opacity. Wants a source at
                     least 864px on the long edge.

Every image asset is probed before it is composited. A logo or lower third that
is present but unreadable -- 0 bytes, truncated, not actually an image -- is
dropped with a warning and the build continues without that layer; a card falls
back to its type layout. The WATERMARK is the exception and refuses the build
outright, because a sample_ cut without it is not a sample. That refusal covers a
watermark that is MISSING as well as one that is unreadable: an absent file used
to be skipped in silence, which wrote an unmarked sample_ cut that publish.py then
uploaded on the strength of its name. It is checked at PREFLIGHT -- before the
lock, the clips and the stitch -- and again in finish(). A --delivery-only run
needs no watermark and is unaffected.
    config.json      optional per-listing overrides -- see below.

Run it from the folder holding photos/. That is normally a listing folder such as
brewester/9_w_cedar/, in which case the four branding files above are usually
supplied by config.json instead. Any asset path that does not resolve against the
working directory is retried beside this script, so a shared global_assets/ library
and the fixed viabolat.png keep working from any listing folder.

config.json -- every key optional, every default is the constant in the source:

    clip_seconds      4.0    seconds per photo, before crossfade overlap
    xfade_seconds     0.5    crossfade length
    max_total_seconds 90.0   hard ceiling on finished runtime -- a set that
                             already fits is untouched, never padded up to it
    brand_persistent  true   false = show the lower third only between the times below
    brand_in          0.8    only read when brand_persistent is false
    brand_out         6.5    ditto; must be greater than brand_in
    lower_third       "lower_third.png"
    logo              "logo.png"
    music             "music.mp3"
    watermark         "viabolat.png"

    address           ""     the three lines of the lower third, and the body of
    agent_name        ""     the card. Any of them may be blank; blanks are
    agent_phone       ""     dropped and the rest close up.
    brokerage         ""     card only, and only when there is no logo
    output_prefix     ""     what goes in front of the output filenames. Blank
                             derives it from agent_name; blank both leaves the
                             bare tour_/sample_ names a pre-existing folder has
    card              "none" none | intro | outro | both
    card_seconds      5.0    length of the card clip
    card_style        "auto" auto | logo | type -- auto picks logo when one
                             resolves, type-only when none does
    card_theme        "auto" auto | dark | light -- auto measures the logo's
                             contrast against both grounds and takes the higher
    accent            "#C8A24A"  rule, phone line and lower-third bar
    font              "Liberation Sans"  any installed family name
    scrim             "black@0.55"       the panel behind the lower third

Photo order is NOT a config key and never will be -- it lives in the filename
prefix and nowhere else. Changing clip_seconds or xfade_seconds invalidates
work_silent.mp4, so those changes need a full build, not --finish-only. So does
renaming photos to reorder them: --finish-only reuses the earlier stitch and
would reship the old order, which is why that path warns.

A photo set too large to fit max_total_seconds is trimmed, not halted:
photo_quality.select_photos() scores every photo for sharpness and keeps only
the sharpest ones that fit, restored to their original order, and prints what
it dropped and why before anything encodes. This runs between the resolution
gate and build_clips(), so a build that already fits needs no config and sees
no change. See _rules/excess-photos-are-trimmed-by-quality-never-halted.md.

The card is the intro and/or outro plate: logo (or brokerage type when there is
no logo) over address, agent and phone, drawn by ffmpeg from the same config.json.
It is branding, so it must not reach the MLS cut -- which is why a build with a
card stitches TWICE. work_silent.mp4 holds the photos alone and feeds the
unbranded cuts; work_branded.mp4 holds [intro] + photos + [outro] and feeds the
branded cuts and the draft. With no card configured the second stitch is skipped
and both read the same file, so a no-card build is byte-identical to one from
before cards existed. Wherever a card is on screen the lower third and the logo
are held off: the card already says those lines, at full size, in the middle of
the frame. The proofing watermark is NOT held off -- an unwatermarked outro card
is exactly the frame an unapproved sample would be screenshot from.

tour.py is the only interface over all of the above: it picks the listing, imports
and numbers the photos, reports what is missing before anything encodes, asks the
short question set, and runs this script for each of the three rungs. It also
keeps per-brand defaults in agents/<brand>/brand.json, which THIS script never
reads -- tour.py resolves them into each listing's config.json, so config.json
stays the single record of what produced a delivered video.

Outputs -- six cuts, two families. Each name is prefixed with the agent's own
name (from agent_name, or output_prefix), because six listings all producing a
file called tour_branded.mp4 collide the moment they leave out/. The slug matches
the one that named the listing folder -- apostrophes drop rather than separate, so
Sean O'Brien signs sean_obrien_tour_branded.mp4, not sean_o_brien_...:

    DELIVERY (clean, what the client gets on sign-off)
    out/<agent>_tour_branded.mp4      music + branding
    out/<agent>_tour_unbranded.mp4    music, no branding  (MLS/IDX safe)
    out/<agent>_tour_vertical.mp4     portrait, blur-padded for Reels/TikTok
                                      (blur band off the unbranded cut, centre
                                       off the branded one -- see vertical())

    SAMPLE (same edit + centered proofing watermark, what the client reviews)
    out/<agent>_sample_branded.mp4
    out/<agent>_sample_unbranded.mp4
    out/<agent>_sample_vertical.mp4

    DRAFT (--draft only, never a deliverable)
    draft.mp4                         listing root, NOT out/

--samples-only and --delivery-only build one family instead of both. A bare run
still builds all six, exactly as it always has -- the staging is tour.py's, and a
CLI run in an older folder is unchanged. The two flags are opposites and passing
both exits 2, since "build neither family" is not a request.

The point is cost. The tour_ trio is the paid deliverable and is only sent after
the client signs off, so on a cold-outreach pipeline building it up front spends
half of a six-minute encode, and its share of ~200 MB, on a listing that may never
reply. Run 1 writes the three watermarked sample_ cuts the client reviews; run 2,
after sign-off, writes the three tour_ deliverables. Both families come off the
SAME stitch, so run 2 is a --finish-only pass of about a minute rather than six --
which is why .last_build.json's rung key names the intermediate lineage
("draft" / "delivery") and not the cut family. Which run a listing is on is
derived by tour.py from what is already in out/; nothing here records it, and no
marker file is invented to hold it.

A build made from photos that miss the resolution gate -- only reachable with
--allow-lowres -- is named exactly like any other build. The shortfall is reported
at preflight and again at the end of the run, with the count, the worst file and
its upscale factor, so the resolution is stated where it can be read rather than
carried in the filename.

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

import photo_quality

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
# [cfg] hard ceiling on finished runtime -- a cap, never a target. A dump with
# more photos than fit gets trimmed by photo_quality.select_photos(); one that
# fits already needs no change and never gets padded up to it.
MAX_TOTAL_SECONDS = float(_cfg.get("max_total_seconds", 90.0))
FPS = 30
ZOOM_MAX = 1.12        # 12% push. Above ~1.20 it starts to look cheap.
MUSIC_VOLUME = 0.55
MUSIC_XFADE = 2.0      # crossfade length when a short track has to loop
MUSIC_LOOP_MAX = 40    # backstop on the loop below; a real track needs < 10
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

# ---- scripted branding ------------------------------------------------------
# reason: lower_third.png used to be a per-listing Canva export -- the one part of
# the workflow that could not be automated, and the one place two listings could
# get swapped. These fields let the script draw the same information itself. A
# lower_third.png that DOES exist still wins, so a hand-authored plate stays an
# option; the text is the routine, the PNG is the exception.
AGENT_NAME = _cfg.get("agent_name", "")      # [cfg]
AGENT_PHONE = _cfg.get("agent_phone", "")    # [cfg]
ADDRESS = _cfg.get("address", "")            # [cfg]
BROKERAGE = _cfg.get("brokerage", "")        # [cfg]


def _slug(text):
    """Lowercase, underscore-joined, filename-safe. "" when nothing survives.

    reason: apostrophes are dropped rather than turned into separators, matching
    scraper/photos.slugify -- the naming authority that already produced
    the agents/<brand>/ folder this listing sits in. The straight
    non-alphanumeric rule turned "Gibson Sotheby's International Realty" into
    gibson_sotheby_s_..., so an agent whose name carries an apostrophe signed his
    files sean_o_brien_ while his folder read sean_obrien -- two spellings of one
    name, which is the drift the single naming authority exists to prevent.

    Deliberately NOT the scraper's function, and deliberately not imported from
    it. Two differences, both wanted: that one falls back to a default
    ("listing") because a folder cannot be called "", while this one must return
    "" so a config with no agent_name leaves the bare tour_/sample_ names a
    pre-existing CLI folder already has. And make_tour runs with cwd set to a
    listing folder and nothing but ffmpeg on the path -- importing from scraper/
    would make the build depend on the scrape, which it otherwise never does.
    Same apostrophe rule, restated; if you change one, change both.
    """
    text = str(text).replace("'", "").replace("\u2019", "")
    return "_".join("".join(c.lower() if c.isalnum() else " "
                            for c in text).split())


# reason: six listings all producing a file called tour_branded.mp4 collide the
# moment the files leave out/ -- a downloads folder, an email thread, a client's
# Drive. The agent's own name is the one field that is always filled in and always
# the right answer, so it rides in front of the output name. output_prefix
# overrides it for the one case tour.py has to handle: a listing whose agent_name
# is still blank, where the brand folder is a better fallback than no prefix at
# all. Both blank leaves the bare names a pre-existing folder already has.
OUTPUT_PREFIX = _slug(_cfg.get("output_prefix") or AGENT_NAME)    # [cfg]

# reason: default "none", not "outro". A bare CLI run in a folder that predates
# cards must produce exactly the video it always did. tour.py writes "outro" into
# config.json for new listings, which is where the preference belongs.
CARD = str(_cfg.get("card", "none")).lower()          # [cfg] none|intro|outro|both
CARD_SECONDS = float(_cfg.get("card_seconds", 5.0))   # [cfg]
CARD_STYLE = str(_cfg.get("card_style", "auto")).lower()  # [cfg] auto|logo|type
CARD_THEME = str(_cfg.get("card_theme", "auto")).lower()  # [cfg] auto|dark|light
# reason: one accent, used by both plates. On a light card the default darkens,
# because #C8A24A on off-white is barely a phone number; an accent set by hand is
# taken at face value on either ground.
ACCENT = _cfg.get("accent", "#C8A24A")       # [cfg]
LIGHT_ACCENT = ACCENT if "accent" in _cfg else "#8A6D1F"
# (background, type, accent) per theme. The lower third is always dark-on-scrim.
# reason: the light ground is pure white, not a designer off-white. Brokerage
# logos routinely ship with an opaque near-white plate baked behind the art, and
# on #F4F2ED that plate showed as a faint rectangle around the mark.
CARD_THEMES = {"dark": ("#101216", "#FFFFFF", ACCENT),
               "light": ("#FFFFFF", "#16181C", LIGHT_ACCENT)}
LT_FG = "#FFFFFF"
# reason: a family name, resolved through fontconfig, not a path -- no font file
# ships with this repo and a hardcoded /usr/share path breaks on the next machine.
FONT = _cfg.get("font", "Liberation Sans")   # [cfg]
SCRIM = _cfg.get("scrim", "black@0.55")      # [cfg] lower third box behind type
# reason: Zillow and most CDNs serve .webp now; globbing only jpg/png made a full
# folder of photos look empty. Module level so tour.py shares one list.
PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".heic"}
SAMPLE_WM_FRAC = 0.45            # fraction of the frame it may occupy
SAMPLE_WM_OPACITY = 0.35         # 0-1. Readable, still see-through.

# reason: a draft answers "is the edit right?", never "is the picture good?", so it
# is pinned to the cheap preset and a fast encoder regardless of what the delivery
# build will use. Measured on 8 photos: delivery 5m50s, draft ~45s.
DRAFT = "--draft" in sys.argv

# Which of the two output families this run writes. Both default to on, so a bare
# run still builds all six exactly as it always has -- tour.py is what stages them.
# reason: the tour_ trio is the paid deliverable and is only ever sent after the
# client signs off, so building it up front spends half a six-minute encode on a
# listing that may never reply. The families are independent at the output stage
# (vertical() reads only its own family's two landscape cuts), so either trio can
# be built alone off the same stitch. Which run a listing is on is derived from
# what is already in out/ -- see tour.py's stage() -- never recorded in a file.
SAMPLES_ONLY = "--samples-only" in sys.argv
DELIVERY_ONLY = "--delivery-only" in sys.argv
if SAMPLES_ONLY and DELIVERY_ONLY:
    print("--samples-only and --delivery-only are opposites; passing both asks "
          "for\nnothing. Drop one, or pass neither to build all six.",
          file=sys.stderr)
    sys.exit(2)

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
# reason: the draft lineage is named apart so it can never feed a delivery build,
# but nothing on the delivery side ever cleared it. tour.py always passes
# --keep-work or --finish-only, so every listing it ever drafted kept
# work_draft.mp4 + clips_draft/ forever. Named as constants so a DELIVERY run can
# clear them: keep_work is about the intermediates of the rung being run, and says
# nothing about the other rung's.
DRAFT_SILENT_WORK = "work_draft.mp4"
DRAFT_CLIPS_DIR = "clips_draft"
SILENT_WORK = DRAFT_SILENT_WORK if DRAFT else "work_silent.mp4"
# reason: an intro/outro card is branding, and work_silent.mp4 feeds ALL six cuts
# including the MLS-safe tour_unbranded.mp4. Baking a card into that one stitch
# would put the agent's name on the MLS cut. So the branded family gets its own
# stitch. A build with no card skips it entirely and both families read
# work_silent.mp4, exactly as they always have.
BRANDED_WORK = "work_branded.mp4"
DRAFT_OUT = "draft.mp4"          # listing root, NOT out/ -- out/ holds real cuts only
CLIPS_DIR = DRAFT_CLIPS_DIR if DRAFT else "clips"
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
                                        # (see gate_min(), the same rule for any
                                        #  preset this run is not building)
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

# Scripted plates are drawn on a nominal 1920x1080 canvas whichever preset is
# active, then resampled by the same full-frame path a Canva export takes.
# reason: sizing the canvas to OUT_W would make a 720p plate 1280 wide, which
# finish()'s `bw >= 0.9 * 1920` full-frame test reads as a small strip -- the
# plate would be inset by MARGIN and rendered at a third of its size.
PLATE_W, PLATE_H = 1920, 1080
PLATE_MARGIN = 70                       # matches MARGIN at 1080p
CARD_LOGO_W, CARD_LOGO_H = 760, 300     # fit box for a logo on the card

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


def stitch(clips, out=None, durs=None):
    """Chain xfade transitions. offset_i = sum(durs[:i]) - i * XFADE.

    reason: this used to read `offset = i * (CLIP_SECONDS - XFADE_SECONDS)`,
    which is only right while every clip is the same length. A 5s card in a 4s
    chain would have slid every transition after it by a second, and nothing
    would have failed -- ffmpeg builds a perfectly valid graph from wrong
    offsets, so the only symptom is a video that cuts in the wrong places. Same
    silent-failure shape as the shuffled photo order.

    durs are the lengths asked of the encoder, not probed back off disk: an
    encoder rounds 4.0s to whole frames, and probing would drift the offsets off
    the values every delivered build to date was cut with.
    """
    out = SILENT_WORK if out is None else out
    durs = [CLIP_SECONDS] * len(clips) if durs is None else durs
    if len(clips) == 1:
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", clips[0],
             "-c", "copy", out])
        return out
    inputs, filt, prev = [], [], "0:v"
    for c in clips:
        inputs += ["-i", c]
    offset = 0.0
    for i in range(1, len(clips)):
        offset += durs[i - 1] - XFADE_SECONDS
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


def gate_min(out_w, out_h=None):
    """Minimum long-edge pixels a photo needs to feed this preset.

    reason: MIN_PHOTO_W is fixed to the preset THIS run selected, but tour.py asks
    the question about presets it is not running. One derivation, both callers, so
    the number the wizard quotes can never drift from the number the gate applies.
    """
    return int(out_w * ZOOM_MAX)


def gate_failures(photos, out_w=None, out_h=None):
    """[(path, "WxH", upscale_factor)] for photos too small to fill the frame.

    reason: separated from check_resolution so tour.py can ask the same question --
    "which photos block which preset?" -- without printing or exiting, and answer it
    in the preflight instead of after a five-minute render. One implementation of
    the rule, two callers.
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
    """Report photos too small to fill the frame. Returns the offending list.

    reason: 384x288 sources were upscaled 5x to 1080p, which no crf/preset setting
    can fix. Fail at second zero instead of after a 5-minute render. The return
    value carries the offenders so the end-of-build reminder can restate the
    resolution -- the count, the worst file, its upscale factor -- rather than
    encoding the verdict in the output filenames.
    """
    bad = gate_failures(photos)
    if not bad:
        return []
    worst = max(bad, key=lambda r: r[2])
    print(f"\n{len(bad)} of {len(photos)} photos are below {MIN_PHOTO_W}px on the "
          f"long edge, which is what {OUT_W}x{OUT_H} needs:")
    for path, dims, scale in bad:
        print(f"  {os.path.basename(path):<32} {dims:>10}  upscaled {scale:.1f}x")
    print(f"  worst: {os.path.basename(worst[0])} at {worst[1]}, "
          f"upscaled {worst[2]:.1f}x")
    if not allow_lowres:
        # reason: only suggest the smaller preset when it is actually a way out.
        # At 720p already, "try --720p" is noise on a message whose whole job is
        # to be actionable.
        step_down = ("" if OUT_W <= 1280 else
                     f"build --720p (needs {gate_min(1280)}px) if that clears "
                     f"them, or ")
        sys.exit(f"\nThese will look soft at {OUT_W}x{OUT_H}. Re-export at "
                 f"{MIN_PHOTO_W}px+ on the long edge -- 3000px+ if you can get "
                 f"the photographer's originals -- {step_down}rerun with "
                 f"--allow-lowres to build anyway.")
    print(f"  --allow-lowres set: building anyway at {OUT_W}x{OUT_H}. The cuts "
          f"are named\n  like any other build; the shortfall is restated when "
          f"the build finishes.\n")
    return bad


def max_photos_for(seconds):
    """Largest photo count whose stitched runtime stays at or under `seconds`,
    given this module's own CLIP_SECONDS/XFADE_SECONDS/CARD/CARD_SECONDS.

    reason: mirrors tour.py's runtime(n, cfg) arithmetic exactly, duplicated
    rather than imported -- tour.py is the module that imports make_tour, not
    the other way around, so make_tour cannot reach tour.runtime().
    tests/test_photo_quality.py holds the two formulas in agreement.
    """
    cards = (CARD in ("intro", "both")) + (CARD in ("outro", "both"))
    n = 0
    while True:
        clips = [CLIP_SECONDS] * (n + 1) + [CARD_SECONDS] * cards
        total = sum(clips) - (len(clips) - 1) * XFADE_SECONDS
        if total > seconds:
            return n
        n += 1


def select_photos(photos, max_seconds=None):
    """Trim `photos` to fit max_seconds (default MAX_TOTAL_SECONDS): keep the
    sharpest, restored to their original order. A set that already fits comes
    back unchanged -- this only ever removes photos, never pads a short list.

    reason: a DELIBERATE, narrow exception to floorplan.py's flag-only
    philosophy -- a floor-plan candidate halts for a human because dropping a
    real room photo by mistake is a silent-failure risk; trimming excess
    photos was explicitly requested to run unattended, so it reports loudly
    instead of halting. See
    _rules/excess-photos-are-trimmed-by-quality-never-halted.md.
    """
    cap_seconds = MAX_TOTAL_SECONDS if max_seconds is None else max_seconds
    cap = max_photos_for(cap_seconds)
    if len(photos) <= cap:
        return photos, []
    kept, dropped = photo_quality.select(photos, cap)
    print(f"\n{len(dropped)} of {len(photos)} photos trimmed to stay at or "
          f"under {cap_seconds:g}s ({cap} kept, by sharpness):")
    for path, score in dropped:
        print(f"  {os.path.basename(path):<32} sharpness {score:.1f}")
    return kept, dropped


def out_path(name):
    """out/<agent>_<name>.mp4 -- delivery naming, in one place.

    reason: the tour_/sample_ token is the boundary that stops a watermarked proof
    being sent as a deliverable, so it stays in the name whatever prefixes it.
    Nothing else is encoded in the filename: the resolution verdict is reported to
    the console at preflight and at the end of the build instead.
    """
    prefix = f"{OUTPUT_PREFIX}_" if OUTPUT_PREFIX else ""
    return f"out/{prefix}{name}.mp4"


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
    # reason: each pass replaces the track with itself crossfaded onto itself, so
    # length becomes length*2 - d. That has a fixed point at d: with d pinned to
    # MUSIC_XFADE, a body of exactly 2.0s stays 2.0s forever and anything shorter
    # goes negative, so `while length < need` never exits and the build HANGS --
    # no error, no output, nothing to read. music_span() floors body at 1.0s, so
    # any track under ~2s of actual music reaches it. Scale the seam to the body
    # instead. For any real track (body >= 2*MUSIC_XFADE = 4s) this is MUSIC_XFADE
    # exactly and the output is byte-identical to before.
    d = min(MUSIC_XFADE, body / 2.0)
    if d < MUSIC_XFADE:
        print(f"  WARNING: only {body:.1f}s of music after trimming silence. "
              f"Seam crossfade reduced to {d:.1f}s so the loop can converge; "
              f"a track this short will sound obviously looped.")

    length, i = body, 1
    while length < need + 1.0:
        # reason: belt and braces on the arithmetic above. If the step ever stops
        # growing, stop rather than spin -- a hang gives the operator nothing to
        # act on, and this runs after the clips are already rendered.
        if i > MUSIC_LOOP_MAX:
            sys.exit(f"Gave up looping music after {MUSIC_LOOP_MAX} passes "
                     f"({length:.1f}s of {need:.1f}s needed). Supply a longer "
                     f"track, or build with --no-music.")
        nxt = f"work_music_{i}.m4a"
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", cur, "-i", cur,
             "-filter_complex", f"[0:a][1:a]acrossfade=d={d}[a]",
             "-map", "[a]", "-c:a", "aac", "-b:a", "192k", nxt])
        length = length * 2 - d
        print(f"  looped music -> {length:.1f}s "
              f"({d}s crossfade at the seam)")
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


def image_ok(path):
    """True only if path is a real, decodable image with non-zero dimensions.

    reason: the same hole music_ok() was written to close, one asset type over.
    os.path.exists() passes on a 0-byte or truncated PNG; dimensions() then
    returns (0, 0); and every fit box is min(BOX_W / aw, BOX_H / ah), which
    raises ZeroDivisionError. That lands in finish(), i.e. after every clip has
    already been rendered -- minutes of work thrown away by a file the run could
    have rejected at the start.
    """
    if not path or not os.path.exists(path) or os.path.getsize(path) == 0:
        return False
    return all(dimensions(path))


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


# Brightness of the two card grounds, for the contrast measurement below.
THEME_LUMA = {"dark": 18, "light": 255}


def art_contrast(path, samples=64):
    """{theme: mean contrast of the logo art against that card ground}, or None.

    reason: a card picks its own background, so a logo that disappears into it is
    a silent failure -- corcoran.png is near-black artwork drawn for white
    stationery and rendered as a hole in the dark card. Measure the art against
    both candidate grounds and use the one it separates from, the same way
    alpha_bbox() measures the art instead of trusting the canvas.

    Crops to the alpha bbox first: a wordmark filling 8% of its canvas averages
    to alpha 2/255 across the whole file, which rounds the answer to noise. Then
    samples with flags=neighbor, NOT the default area average -- a two-tone mark
    like a dark wordmark with white detail averages to a mid grey that contrasts
    with nothing, and the question here is about the real pixels, not their mean.
    """
    trim, _ = trim_filter(path)
    n = samples * samples

    def plane(vf):
        r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", vf,
                            "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                           capture_output=True)
        return r.stdout[:n]

    size = f"scale={samples}:{samples}:flags=neighbor"
    alpha = plane(f"{trim}alphaextract,{size}")
    if len(alpha) < n:
        # no alpha channel: every pixel is ink, and grey is its own luminance
        grey = plane(f"{trim}format=gray,{size}")
        ink = [(g, 255) for g in grey] if len(grey) == n else []
    else:
        # premultiplied grey divided by alpha recovers each pixel's own luminance
        grey = plane(f"{trim}format=rgba,premultiply=inplace=1,format=gray,{size}")
        if len(grey) < n:
            return None
        ink = [(g * 255.0 / a, a) for g, a in zip(grey, alpha) if a > 8]
    if not ink:
        return None
    weight = sum(w for _, w in ink)
    return {t: round(sum(w * abs(l - b) for l, w in ink) / weight)
            for t, b in THEME_LUMA.items()}


def card_theme(logo):
    """(background, type, accent) for the card.

    Puts the logo on whichever ground it separates from. card_theme in
    config.json forces one.
    """
    if CARD_THEME in CARD_THEMES:
        return CARD_THEMES[CARD_THEME]
    score = art_contrast(logo) if (logo and os.path.exists(logo)) else None
    if score is None:
        return CARD_THEMES["dark"]       # type-only card: dark reads better
    # reason: light unless dark wins clearly. A two-tone mark -- dark wordmark,
    # white detail -- scores the same against both grounds, and brokerage art is
    # overwhelmingly drawn for white stationery, so the tie goes to light.
    theme = "dark" if score["dark"] > score["light"] * 1.15 else "light"
    print(f"    card: logo contrast {score['light']} on light vs "
          f"{score['dark']} on dark -- using the {theme} card")
    return CARD_THEMES[theme]


# ---- scripted plates --------------------------------------------------------
# reason: every text value is written to a file and passed as textfile=, never
# inlined as text=. ffmpeg's filtergraph parser splits on ':' and ',' and does not
# honour the shell's '\'' idiom for a literal apostrophe -- an address like
# "5 Beacon St, Unit 2: O'Brien" silently swallowed the rest of the filter and
# rendered the option list into the frame. A file has no escaping rules at all.
TEXT_DIR = "work_text"
_text_seq = [0]
_font_cache = {}


def font_file(weight="regular"):
    """Concrete font file for FONT at a weight, via fontconfig, or None.

    reason: drawtext's font= takes a family and always renders it regular --
    "Liberation Sans Bold" does not resolve (fontconfig matches DejaVu instead)
    and the family:style pattern cannot survive the filter arg parser, which
    splits on the colon. Resolving to a file here is the only way to get bold,
    and it keeps the config a portable family name rather than a machine path.
    """
    if weight in _font_cache:
        return _font_cache[weight]
    face = None
    try:
        r = subprocess.run(["fc-match", "-f", "%{file}", f"{FONT}:{weight}"],
                           capture_output=True, text=True, check=True)
        if r.stdout.strip() and os.path.exists(r.stdout.strip()):
            face = r.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        pass                     # no fc-match: fall back to font= at one weight
    _font_cache[weight] = face
    return face


def _drawtext(text, size, color, x, y, weight="regular", pad=None):
    """One drawtext filter, its copy handed over in a file."""
    os.makedirs(TEXT_DIR, exist_ok=True)
    path = f"{TEXT_DIR}/{_text_seq[0]:03d}.txt"
    _text_seq[0] += 1
    with open(path, "w") as f:
        f.write(str(text))
    face = font_file(weight)
    src = f"fontfile='{face}'" if face else f"font='{FONT}'"
    # reason: expansion=none stops drawtext reading % and {} in an address as
    # strftime and expression syntax.
    filt = (f"drawtext={src}:textfile='{path}':fontsize={size}:fontcolor={color}"
            f":x={x}:y={y}:expansion=none")
    if pad is not None:
        filt += f":box=1:boxcolor={SCRIM}:boxborderw={pad}"
    return filt


def _clear_text():
    for f in glob.glob(f"{TEXT_DIR}/*.txt"):
        os.remove(f)
    if os.path.isdir(TEXT_DIR) and not os.listdir(TEXT_DIR):
        os.rmdir(TEXT_DIR)


def _line_h(size):
    return round(size * 1.24)


def _t(x):
    """Seconds for a filter argument -- short, and never in exponent notation."""
    return f"{float(x):.3f}".rstrip("0").rstrip(".") or "0"


def render_lower_third(out):
    """Draw the lower third from config text. Returns the path, or None.

    reason: this is the one asset that changed for every listing, so it was the
    one asset that had to be re-exported from Canva for every listing -- and the
    one place two listings could get crossed. Drawing it from the same
    config.json that drives the build removes both. A lower_third.png that
    exists still wins in main(): the hand-authored plate stays available for a
    listing that earns it.

    Drawn on a 1920x1080 canvas whatever the preset, so finish() takes its
    full-frame branch and resamples it exactly as it does a Canva export.
    """
    rows = [(ADDRESS, 58, LT_FG, "bold"),
            (AGENT_NAME, 38, LT_FG, "regular"),
            (AGENT_PHONE, 34, ACCENT, "bold")]
    rows = [r for r in rows if str(r[0]).strip()]
    if not rows:
        return None
    padx, pady, gap, bar = 26, 18, 10, 8
    heights = [_line_h(size) for _, size, _, _ in rows]
    total = sum(heights) + gap * (len(rows) - 1)
    top = PLATE_H - PLATE_MARGIN - pady - total
    text_x = PLATE_MARGIN + bar + padx

    text = []
    y = top
    for (line, size, color, weight), h in zip(rows, heights):
        text.append(_drawtext(line, size, color, text_x, y, weight))
        y += h + gap

    def plate(chain, path):
        run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
             "-i", f"color=c=black@0.0:s={PLATE_W}x{PLATE_H}:d=1,format=rgba",
             "-filter_complex", ",".join(chain), "-frames:v", "1",
             "-update", "1", path])

    # reason: drawtext's own box= draws one rectangle per line, so three lines of
    # different length came out as three ragged plates. One scrim behind the
    # whole block needs the block's true width, which only the font knows -- so
    # render the text alone first and measure it with the same alpha_bbox() the
    # logo fit box uses. One extra ~0.2s plate render, exact either way.
    probe = "work_lt_probe.png"
    plate(text, probe)
    box = alpha_bbox(probe)
    os.remove(probe)
    if box:
        bx, by, bw_, bh_ = box
        px, py = PLATE_MARGIN, max(0, by - pady)
        pw, ph = bx + bw_ + padx - px, bh_ + 2 * pady
    else:                       # nothing measurable: fall back to the nominal box
        px, py, pw, ph = PLATE_MARGIN, top - pady, 900, total + 2 * pady

    # reason: replace=1 or neither the scrim nor the bar is visible. drawbox
    # blends its colour into the destination but leaves the destination's alpha
    # alone, and this canvas starts fully transparent -- the bar came out the
    # right colour at alpha 0.
    parts = [f"drawbox=x={px}:y={py}:w={pw}:h={ph}:color={SCRIM}:t=fill:replace=1",
             f"drawbox=x={px}:y={py}:w={bar}:h={ph}:color={ACCENT}:t=fill:replace=1"]
    plate(parts + text, out)
    _clear_text()
    return out


def card_layout(logo):
    """"logo" or "type" -- which card design this listing gets.

    reason: not every agent has a logo. A logo-centred card with no logo is a
    hole in the middle of the frame, so the absence picks a different design
    rather than degrading the same one. card_style forces either.
    """
    if CARD_STYLE in ("logo", "type"):
        return CARD_STYLE
    return "logo" if (logo and os.path.exists(logo)) else "type"


def render_card(out, logo=None):
    """Draw the intro/outro card. Returns the path, or None if there is nothing
    to say on it.

    One design serves both ends of the tour -- the card that opens it and the
    card that closes it carry the same information, and two designs would be two
    things to keep in step.
    """
    layout = card_layout(logo)
    use_logo = layout == "logo" and image_ok(logo)
    if layout == "logo" and logo and os.path.exists(logo) and not use_logo:
        print(f"    WARNING: {logo} is unreadable or has no dimensions -- "
              f"card falls back to the type layout.")
    bg, fg, accent = card_theme(logo if use_logo else None)

    rule_w, rule_h, gap = 140, 5, 46
    blocks, note = [], ""      # blocks: (kind, height, payload)
    if use_logo:
        trim, (aw, ah) = trim_filter(logo)
        fit = min(CARD_LOGO_W / aw, CARD_LOGO_H / ah)
        blocks.append(("logo", round(ah * fit), (trim, round(aw * fit))))
        note = (f"    card: logo layout, art {aw}x{ah} -> "
                f"{round(aw * fit)}x{round(ah * fit)}")
    else:
        if str(BROKERAGE).strip():
            blocks.append(("text", _line_h(44), (BROKERAGE, 44, accent, "bold")))
        note = ("    card: type-only layout"
                f"{' (no logo found)' if layout == 'type' else ''}")

    body = [(ADDRESS, 76 if not use_logo else 62, fg, "bold"),
            (AGENT_NAME, 44, fg, "regular"),
            (AGENT_PHONE, 38, accent, "bold")]
    body = [b for b in body if str(b[0]).strip()]
    # reason: held until here. Announcing the layout and then announcing there is
    # nothing to put on it reads like two different outcomes for one card.
    if not blocks and not body:
        return None
    print(note)
    if blocks and body:
        blocks.append(("rule", rule_h, None))
    for b in body:
        blocks.append(("text", _line_h(b[1]), b))

    total = sum(h for _, h, _ in blocks) + gap * (len(blocks) - 1)
    y = round((PLATE_H - total) / 2)

    inputs = ["-f", "lavfi",
              "-i", f"color=c={bg}:s={PLATE_W}x{PLATE_H}:d=1"]
    pre, parts, logo_y, logo_w = [], [], None, None
    for kind, h, payload in blocks:
        if kind == "logo":
            logo_y, logo_w = y, payload[1]
            pre.append(f"[1:v]{payload[0]}scale=w={CARD_LOGO_W}:h={CARD_LOGO_H}:"
                       f"force_original_aspect_ratio=decrease[lg];")
            inputs += ["-i", logo]
        elif kind == "rule":
            parts.append(f"drawbox=x={(PLATE_W - rule_w) // 2}:y={y}:"
                         f"w={rule_w}:h={rule_h}:color={accent}:t=fill:replace=1")
        else:
            text, size, color, weight = payload
            parts.append(_drawtext(text, size, color, "(w-text_w)/2", y, weight))
        y += h + gap

    chain = ",".join(parts) if parts else "null"
    if logo_y is None:
        vf = f"[0:v]{chain}[v]"
    else:
        vf = (f"{''.join(pre)}[0:v][lg]overlay=x=(W-w)/2:y={logo_y}[bl];"
              f"[bl]{chain}[v]")
    run(["ffmpeg", "-y", "-loglevel", "error"] + inputs +
        ["-filter_complex", vf, "-map", "[v]", "-frames:v", "1", "-update", "1",
         out])
    _clear_text()
    return out


def card_clip(png, seconds, out):
    """Encode a card plate to a clip that xfades into the photo chain.

    Same codec, crf, preset, fps and frame size as build_clips() -- xfade needs
    matching formats, and a card encoded differently from the clips beside it
    would force a re-encode of the whole chain.
    """
    run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", png,
         "-t", str(seconds),
         "-filter_complex", f"scale={OUT_W}:{OUT_H},setsar=1,format=yuv420p",
         "-c:v", "libx264", "-crf", str(CRF), "-preset", X264_PRESET,
         "-r", str(FPS), out])
    return out


def build_cards(logo):
    """(intro_clip_or_None, outro_clip_or_None) for the configured card mode."""
    if CARD not in ("intro", "outro", "both"):
        return None, None
    os.makedirs(CLIPS_DIR, exist_ok=True)
    png = f"{CLIPS_DIR}/card.png"
    if not render_card(png, logo):
        print("    card: no agent_name, agent_phone, address or brokerage in "
              f"{CONFIG_FILE} -- nothing to put on it, skipping.")
        return None, None
    clip = card_clip(png, CARD_SECONDS, f"{CLIPS_DIR}/card.mp4")
    intro = clip if CARD in ("intro", "both") else None
    outro = clip if CARD in ("outro", "both") else None
    return intro, outro


def require_watermark(watermark):
    """Refuse the build unless the proofing watermark will actually render.

    reason: this is the only thing separating a sample_ cut from a deliverable,
    so unlike the logo and the lower third it is NOT degraded to a warning. It
    covers a MISSING file as well as an unreadable one -- the old
    `bool(watermark and os.path.exists(...))` skipped an absent watermark in
    silence and wrote an unmarked proof, which publish.py then uploaded on the
    strength of its filename.

    Called from preflight as well as from finish(), because knowing at second
    one and refusing at minute five is this repo's own stated failure shape --
    it is what the resolution gate used to do. finish() keeps its check: it is
    the last gate before the pixels, and a caller that reaches it with a broken
    watermark must still not get a cut.
    """
    if not os.path.exists(watermark):
        sys.exit(f"REFUSING TO BUILD: {watermark} does not exist.\nThe proofing "
                 f"watermark is the boundary between a sample and a deliverable; "
                 f"a cut\nwithout it is not a sample. Point 'watermark' in "
                 f"config.json at a valid image --\nthe shared one is "
                 f"global_assets/logos/viabolat.png.\n"
                 f"A --delivery-only build needs no watermark.")
    if not image_ok(watermark):
        sys.exit(f"REFUSING TO BUILD: {watermark} is unreadable or has no "
                 f"dimensions.\nThe proofing watermark is the boundary between a "
                 f"sample and a deliverable; a cut without it is not a sample.\n"
                 f"Replace the file, or point 'watermark' in config.json at a "
                 f"valid image.")


def finish(silent, music, brand, out, branded=True, logo=None, watermark=None,
           cards=(0.0, 0.0)):
    dur = duration(silent)
    # reason: the card already carries the address, the agent and the phone, at
    # full size in the middle of the frame. Leaving the lower third and the
    # top-left logo running over it prints the same three lines twice and the
    # same mark twice. Branding covers the photos; the card covers itself. When
    # no card is configured both bounds collapse to the whole cut and nothing is
    # gated, which is what keeps a no-card build identical to before.
    intro_s, outro_s = cards
    has_card = intro_s > 0 or outro_s > 0
    body_in, body_out = intro_s, dur - outro_s

    def window(persistent):
        """(start, end) for a branding layer, or None for the whole cut."""
        if persistent:
            return (body_in, body_out) if has_card else None
        if not has_card:
            return (BRAND_IN, BRAND_OUT)
        return (body_in + BRAND_IN, min(body_in + BRAND_OUT, body_out))

    # reason: a brand_out past the end of the photos is not an ffmpeg error -- the
    # overlay just stays up to the last frame. Say so rather than let the operator
    # believe a window was applied that never closed.
    if not BRAND_PERSISTENT and body_in + BRAND_OUT > body_out:
        print(f"    WARNING: brand_out {BRAND_OUT}s is past the {body_out:.1f}s mark -- "
              f"the lower third will stay up to {'the card' if has_card else 'the end'}.")
    # reason: branding is cosmetic, so an unreadable lower third or logo drops out
    # with a warning rather than killing a build that is already minutes deep.
    use_brand = bool(branded and image_ok(brand))
    use_logo = bool(branded and image_ok(logo))
    for label, path, used in (("lower third", brand, use_brand),
                              ("logo", logo, use_logo)):
        if branded and path and os.path.exists(path) and not used:
            print(f"    WARNING: {path} is unreadable or has no dimensions -- "
                  f"{label} omitted from this cut.")
    # reason: NOT gated on `branded`. The proofing watermark is the whole reason a
    # sample cut exists, so it must survive onto the unbranded sample too.
    # reason: the watermark is NOT cosmetic and is deliberately not treated like
    # the two above. It is the only thing separating a sample_ cut from a
    # deliverable, so silently dropping it writes an unmarked proof -- the exact
    # file _rules/never-cross-the-sample-tour-boundary.md forbids sending.
    # A broken watermark stops the build.
    # reason: a MISSING watermark used to fall through to use_wm=False and write
    # an unmarked sample_ cut in silence -- publish.py then uploads it on the
    # filename alone. A watermark that is absent is a watermark that will not
    # render, which is the same refusal as one that will not decode. This fires
    # only when a caller asked for a watermark, so --delivery-only, which asks
    # for none, is unaffected.
    if watermark:
        require_watermark(watermark)
    use_wm = bool(watermark)

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
        layers.append(("bp", pos, window(BRAND_PERSISTENT)))
        idx += 1

    if use_logo:
        trim, (aw, ah) = trim_filter(logo)
        fit = min(LOGO_W / aw, LOGO_H / ah)
        print(f"    logo art {aw}x{ah} -> renders "
              f"{round(aw * fit)}x{round(ah * fit)} top-left")
        pre.append(f"[{idx}:v]{trim}scale=w={LOGO_W}:h={LOGO_H}:"
                   f"force_original_aspect_ratio=decrease[lg];")
        layers.append(("lg", f"x={MARGIN}:y={MARGIN}", window(LOGO_PERSISTENT)))
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
        # cannot be cropped or covered away -- and over the card, with no window
        # of any kind, because an unwatermarked outro card is exactly the frame
        # an unapproved sample would be screenshot from.
        layers.append(("wm", "x=(W-w)/2:y=(H-h)/2", None))
        idx += 1

    # reason: overlay is binary, so N layers need N-1 intermediate labels chained
    # in order. The last one flows straight into the fades with no label.
    v = "".join(pre) + "[0:v]"
    for i, (label, pos, win) in enumerate(layers):
        v += f"[{label}]overlay={pos}"
        if win:
            v += f":enable='between(t,{_t(win[0])},{_t(win[1])})'"
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


def vertical(bg_src, fg_src, out):
    """Portrait cut: blurred backdrop behind the letterboxed 16:9 frame.

    The backdrop and the centered frame come from *different* cuts on purpose.
    reason: the backdrop is the source scaled up ~1.8x and centre-cropped, so
    anything the source draws near the bottom edge lands in the bottom band at
    nearly twice its size. Taking both layers from the branded cut therefore
    reproduced the lower third in the band, blurred but large enough to read the
    street address off. The band now comes from the unbranded sibling, which has
    nothing to reproduce, while the centre still comes from the branded one --
    this is the social cut, so it should carry the lower third and logo. Taking
    both layers from the unbranded cut would also kill the ghost, by deleting the
    branding, which is not the same fix.
    """
    fg_dur, bg_dur = duration(fg_src), duration(bg_src)
    # reason: with an intro/outro card the branded cut is longer than the
    # unbranded one it takes its band from, and overlay ends when its shorter
    # input does -- the portrait cut would stop dead at the card. Hold the band's
    # last frame across the difference instead. That frame is already faded to
    # black by finish(), so the card plays against black bands, which is what it
    # wants anyway. Zero difference means no filter and no change to the command.
    pad = ""
    if fg_dur - bg_dur > 0.05:
        pad = f"tpad=stop_mode=clone:stop_duration={fg_dur - bg_dur:.3f},"
    vf = (f"[0:v]scale={VERT_W}:{VERT_H}:force_original_aspect_ratio=increase,"
          f"crop={VERT_W}:{VERT_H},{pad}gblur=sigma={BLUR_SIGMA},"
          f"eq=brightness=-0.12[bgb];"
          f"[1:v]scale={VERT_W}:-2[fgs];"
          f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2[v]")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", bg_src, "-i", fg_src,
         "-filter_complex", vf, "-map", "[v]", "-map", "1:a",
         "-c:v", "libx264", "-crf", str(VERTICAL_CRF), "-preset", X264_PRESET,
         "-pix_fmt", "yuv420p", "-c:a", "copy",
         # reason: pin to the branded source, so a padded band cannot run long.
         "-t", f"{fg_dur:.3f}", "-movflags", "+faststart", out])


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
            # reason: force_original_aspect_ratio rewrites SAR to preserve the
            # display aspect, so a mixed-aspect folder (1024x683 beside
            # 1024x768) reaches concat with 1:1 on some cells and 2048:2049 on
            # others, and concat refuses to configure. The clip path already
            # pins setsar=1 for the same reason; this one did not.
            f"[{i}:v]scale={CELL_W}:{CELL_H}:force_original_aspect_ratio=increase,"
            f"crop={CELL_W}:{CELL_H},setsar=1,"
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
    each other's intermediates mid-encode. The lock lives here rather than in
    tour.py because tour.py builds by running this script -- a CLI run would not see
    a lock tour.py held, and a lock tour.py held would shut this process out of the
    folder it was launched to build. O_EXCL because
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


def draft_lineage():
    """The draft rung's intermediates, whatever rung is currently running.

    reason: named apart from the delivery ones so a draft-quality stitch can
    never feed a delivery build. That separation only holds if something
    eventually clears them -- see cleanup().
    """
    stale = [DRAFT_SILENT_WORK] if os.path.exists(DRAFT_SILENT_WORK) else []
    return stale + sorted(glob.glob(f"{DRAFT_CLIPS_DIR}/*.mp4") +
                          glob.glob(f"{DRAFT_CLIPS_DIR}/*.png"))


def cleanup(keep_work=False):
    """Delete regenerable build artifacts. Only ever called after a successful
    run -- run() raises on any ffmpeg failure, so a broken build keeps its
    intermediates for inspection.
    """
    junk = glob.glob("work_music_*.m4a")          # always regenerated
    junk += glob.glob(f"{TEXT_DIR}/*.txt")        # scripted plate copy
    # reason: redrawn from config.json on every run in well under a second, and
    # a stale one would be a plate for the previous listing's address.
    junk += [f for f in ("work_lower_third.png", "work_lt_probe.png")
             if os.path.exists(f)]
    if not keep_work:
        junk += glob.glob(f"{CLIPS_DIR}/*.mp4")
        junk += glob.glob(f"{CLIPS_DIR}/*.png")   # card plate
        # reason: a draft writes SILENT_WORK only -- work_branded.mp4 belongs to
        # the delivery rung, and a bare --draft used to delete it out from under a
        # kept delivery stitch, leaving half a lineage behind. Each rung clears
        # its own.
        works = (SILENT_WORK,) if DRAFT else (SILENT_WORK, BRANDED_WORK)
        junk += [w for w in works if os.path.exists(w)]
    # reason: a delivery build supersedes any draft of the same listing, so it
    # clears the draft lineage REGARDLESS of keep_work -- --keep-work and
    # --finish-only are about reusing this rung's stitch next run, and a delivery
    # run never reuses work_draft.mp4. Nothing did this before, so tour.py (which
    # always passes one of those flags) left ~35MB of draft intermediates in every
    # listing it drafted. draft.mp4 itself is NOT touched: it is the review cut the
    # operator asked for, not an intermediate.
    stale = [] if DRAFT else draft_lineage()
    for p in junk + stale:
        os.remove(p)
    dirs = [CLIPS_DIR, TEXT_DIR] + ([] if DRAFT else [DRAFT_CLIPS_DIR])
    for d in dirs:
        if os.path.isdir(d) and not os.listdir(d):
            os.rmdir(d)
    if junk:
        mb = "" if keep_work else " (rerun with --keep-work to keep them)"
        print(f"Cleaned up {len(junk)} intermediate file(s){mb}")
    if stale:
        print(f"  cleared {len(stale)} superseded draft intermediate(s) "
              f"({DRAFT_SILENT_WORK} + {DRAFT_CLIPS_DIR}/); {DRAFT_OUT} kept")
    if keep_work:
        also = f" + {BRANDED_WORK}" if os.path.exists(BRANDED_WORK) else ""
        print(f"  kept {SILENT_WORK}{also} + {CLIPS_DIR}/ for --finish-only")


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
    # reason: the extension filter alone matched a *directory* called
    # photos/01_front.jpg, which then went to ffmpeg as an input and failed deep
    # in the stitch. os.path.isfile keeps the order list to things that can
    # actually be decoded.
    photos = sorted(p for p in glob.glob("photos/*")
                    if os.path.splitext(p)[1].lower() in PHOTO_EXTS
                    and os.path.isfile(p))
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
    shortfall = check_resolution(photos,
                                 allow_lowres="--allow-lowres" in sys.argv)

    no_music = "--no-music" in sys.argv
    music = None if no_music else MUSIC
    if music and not music_ok(music):
        sys.exit(f"{MUSIC} is missing, empty, or has no audio stream. "
                 "Drop in a track you are licensed to use, or rerun with "
                 "--no-music to build silent versions.")

    # reason: the watermark is a hard refusal, so it is checked HERE -- before
    # the lock, the clips and the stitch -- and not only at the moment a sample
    # cut is composited. Discovering it at minute five, after the encode has been
    # paid for, is exactly what the resolution gate was fixed for. Only the runs
    # that actually apply one are gated: --delivery-only needs no watermark, a
    # draft does carry it.
    if DRAFT or not DELIVERY_ONLY:
        require_watermark(SAMPLE_WATERMARK)

    acquire_lock()
    if not DRAFT:
        os.makedirs("out", exist_ok=True)

    # reason: a lower_third.png that exists still wins. Scripting the plate is
    # the routine because it is the asset that changed per listing; a plate
    # someone actually designed for this listing is the exception, and the
    # exception should not need a flag to be honoured.
    brand_plate = LOWER_THIRD
    if not os.path.exists(brand_plate):
        drawn = render_lower_third("work_lower_third.png")
        if drawn:
            print(f"  lower third: drawn from {CONFIG_FILE} "
                  f"({'/'.join(x for x in (ADDRESS, AGENT_NAME, AGENT_PHONE) if x)})")
            brand_plate = drawn

    silent = SILENT_WORK
    branded_silent = silent
    spans = (0.0, 0.0)      # (intro, outro) seconds inside the branded stitch
    reused = "--finish-only" in sys.argv and os.path.exists(silent)
    if reused:
        print(f"Reusing {silent} ({duration(silent):.1f}s) - skipping clips.")
        # reason: the order printed above describes photos/ as it stands now, but
        # work_silent.mp4 was stitched by an earlier run. Renaming photos to fix the
        # order and then rebuilding with --finish-only silently reships the old order.
        print("    WARNING: --finish-only reuses that earlier stitch. If photos/ has "
              "changed since, the order above is NOT what renders -- drop the flag.")
        # reason: the branded stitch is the one carrying the card. Without it a
        # --finish-only pass would quietly drop the card from every branded cut,
        # so rebuild it from the kept clips, and fall back to a full build when
        # even those are gone rather than shipping a tour with no card in it.
        if not DRAFT and CARD != "none":
            if os.path.exists(BRANDED_WORK):
                print(f"Reusing {BRANDED_WORK} ({duration(BRANDED_WORK):.1f}s).")
                branded_silent = BRANDED_WORK
                spans = (CARD_SECONDS * (CARD in ("intro", "both")),
                         CARD_SECONDS * (CARD in ("outro", "both")))
            elif glob.glob(f"{CLIPS_DIR}/[0-9]*.mp4"):
                print(f"--finish-only: no {BRANDED_WORK}, restitching it "
                      "from the kept clips.")
                intro, outro = build_cards(LOGO)
                kept = sorted(glob.glob(f"{CLIPS_DIR}/[0-9]*.mp4"))
                branded_silent = stitch(
                    [c for c in (intro, *kept, outro) if c],
                    out=BRANDED_WORK,
                    durs=[CARD_SECONDS] * bool(intro) +
                         [CLIP_SECONDS] * len(kept) +
                         [CARD_SECONDS] * bool(outro))
                spans = (CARD_SECONDS * bool(intro), CARD_SECONDS * bool(outro))
            else:
                print(f"--finish-only: no {BRANDED_WORK} and no clips to restitch "
                      "it from. Building everything.")
                reused = False
    if not reused:
        # reason: --finish-only with no work_silent.mp4 (a previous default build
        # cleaned it up) must fall back to a full build, not crash in finish().
        if "--finish-only" in sys.argv:
            print(f"--finish-only: no {silent} to reuse, building from photos.")
        build_photos, _dropped = select_photos(photos)
        print(f"Building {len(build_photos)} clips...")
        clips = build_clips(build_photos)

        intro, outro = build_cards(LOGO)
        spans = (CARD_SECONDS * bool(intro), CARD_SECONDS * bool(outro))
        print("Stitching with crossfades...")
        if DRAFT:
            # reason: a draft builds one branded cut, so its single stitch is the
            # branded one -- and it is already named apart (work_draft.mp4), so a
            # card baked into it can never reach a delivery build.
            silent = branded_silent = stitch(
                [c for c in (intro, *clips, outro) if c],
                durs=[CARD_SECONDS] * bool(intro) + [CLIP_SECONDS] * len(clips) +
                     [CARD_SECONDS] * bool(outro))
        else:
            silent = stitch(clips)
            branded_silent = silent
            if intro or outro:
                print("Stitching the branded cut with its card...")
                branded_silent = stitch(
                    [c for c in (intro, *clips, outro) if c],
                    out=BRANDED_WORK,
                    durs=[CARD_SECONDS] * bool(intro) + [CLIP_SECONDS] * len(clips) +
                         [CARD_SECONDS] * bool(outro))

    print("Adding music and branding..." if music else "Adding branding (silent)...")
    if music:
        # reason: with a card the branded cut outruns the unbranded one, and
        # finish() pins each cut to its own length -- so the track has to cover
        # the longer of the two or the branded cut ends in silence.
        music = prepare_music(music, max(duration(silent),
                                         duration(branded_silent)))
    # reason: every overlay is silently optional, which made a typo'd filename look
    # like a working build with no branding. Say what is actually applied.
    for name, path in (("lower third", brand_plate), ("logo", LOGO)):
        print(f"  {name}: {path if os.path.exists(path) else 'not found - skipped'}")
    # reason: branding is cosmetic and says "skipped"; the watermark is not, and
    # a missing one now refuses the build rather than quietly writing an unmarked
    # sample. Say which of the two this is before minutes are spent stitching.
    print(f"  sample watermark: {SAMPLE_WATERMARK}"
          f"{'' if os.path.exists(SAMPLE_WATERMARK) else ' - MISSING, sample cuts will refuse'}")

    # reason: one cut, and it is the watermarked branded one -- that single file
    # shows the running order, the pacing, the lower third, the logo and the music
    # fit all at once, which is everything a draft is for. Encoding the other five
    # to answer those questions is the waste this flag exists to stop.
    if DRAFT:
        print(f"  {DRAFT_OUT} (720p draft, not a deliverable)...")
        finish(branded_silent, music, brand_plate, DRAFT_OUT,
               branded=True, logo=LOGO, watermark=SAMPLE_WATERMARK, cards=spans)
        # reason: measure before cleanup(). The runtime line used to be arithmetic
        # over CLIP_SECONDS; reading it off the stitch instead is correct with a
        # card in the chain, but the stitch is one of the files cleanup() deletes.
        runtime = duration(branded_silent)
        cleanup(keep_work=any(f in sys.argv
                              for f in ("--keep-work", "--finish-only")))
        print(f"\nDone. Runtime {runtime:.1f}s")
        print(f"  {DRAFT_OUT}  ({os.path.getsize(DRAFT_OUT)/1e6:.1f} MB)")
        print("  DRAFT -- 720p at a fast preset, for review on this machine only.")
        print("  Nothing here is a deliverable. Rebuild without --draft to ship.")
        return

    # reason: branded cuts read branded_silent, which carries the card; the
    # unbranded cuts read the photos-only stitch. That split is what keeps an
    # agent's name and phone number off the MLS/IDX file. With no card the two
    # are the same object and nothing extra was encoded.
    cuts = {n: out_path(n) for n in
            ("tour_branded", "tour_unbranded", "tour_vertical",
             "sample_branded", "sample_unbranded", "sample_vertical")}

    if SAMPLES_ONLY:
        print("Building the sample_ cuts only -- the client's proofing copy. The "
              "tour_\ndeliverables are a second run, after sign-off.")
    elif DELIVERY_ONLY:
        print("Building the tour_ cuts only -- the signed-off deliverables. The "
              "sample_\ncuts already in out/ are left where they are.")

    # reason: every call site below stays exactly where it was and is only
    # nested. tests/test_card_isolation.py walks main() and asserts FOUR finish()
    # calls with a cuts[...] target and TWO vertical() calls -- that is the guard
    # keeping the card off the MLS cut, and it reads the wiring, not the run.
    if not SAMPLES_ONLY:
        print(f"  {os.path.basename(cuts['tour_branded'])}...")
        finish(branded_silent, music, brand_plate,
               cuts["tour_branded"], branded=True, logo=LOGO, cards=spans)
        print(f"  {os.path.basename(cuts['tour_unbranded'])}...")
        finish(silent, music, None,
               cuts["tour_unbranded"], branded=False, logo=None)

    # reason: sample cuts are the client proofing copy -- identical edit, plus a
    # centered watermark so an unapproved tour cannot be used as-is. The tour_
    # files are the delivery once they sign off.
    if not DELIVERY_ONLY:
        print(f"  {os.path.basename(cuts['sample_branded'])}...")
        finish(branded_silent, music, brand_plate, cuts["sample_branded"],
               branded=True, logo=LOGO, watermark=SAMPLE_WATERMARK, cards=spans)
        print(f"  {os.path.basename(cuts['sample_unbranded'])}...")
        finish(silent, music, None, cuts["sample_unbranded"],
               branded=False, logo=None, watermark=SAMPLE_WATERMARK)

    print("Building vertical cuts...")
    if not SAMPLES_ONLY:
        vertical(cuts["tour_unbranded"], cuts["tour_branded"], cuts["tour_vertical"])
    if not DELIVERY_ONLY:
        vertical(cuts["sample_unbranded"], cuts["sample_branded"],
                 cuts["sample_vertical"])

    # reason: measure before cleanup() deletes the stitches these read from.
    runtime, plain = duration(branded_silent), duration(silent)

    # reason: --finish-only means the user is iterating on music/branding, so the
    # clips are still needed next run. Deleting them would force a full rebuild.
    cleanup(keep_work=any(f in sys.argv for f in ("--keep-work", "--finish-only")))

    extra = "" if abs(runtime - plain) < 0.05 else f" ({plain:.1f}s unbranded)"
    print(f"\nDone. Runtime {runtime:.1f}s{extra}")
    for f in sorted(glob.glob("out/*.mp4")):
        print(f"  {f}  ({os.path.getsize(f)/1e6:.1f} MB)")
    if shortfall:
        worst = max(shortfall, key=lambda r: r[2])
        print(f"\n  BELOW PAR. {len(shortfall)} of {len(photos)} photos are under "
              f"{MIN_PHOTO_W}px, so every cut\n  above is a {OUT_W}x{OUT_H} "
              f"upscale -- worst {os.path.basename(worst[0])} at {worst[1]}, "
              f"upscaled {worst[2]:.1f}x.\n  Watchable, not sharp. Rebuild from "
              f"the photographer's originals before this\n  goes to the MLS. "
              f"Nothing in the filenames records this -- see IDEA.md 4.")


if __name__ == "__main__":
    main()
