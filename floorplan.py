"""floorplan.py -- best-effort detection of a floor plan or site map among a
listing's photos.

PROGRESS.md 4.2: "Detect likely floor plans ... print them as candidates, and
never reorder or delete." This module holds to that by construction, not just
by convention -- the only file operation anywhere in it is an ffmpeg subprocess
whose output is captured to an in-memory bytes object; no function here is ever
handed a path to write, rename or remove.

A floor plan or site map is overwhelmingly a white/paper background with thin,
mostly-neutral linework -- unlike even a bright, white-walled room, which still
carries chroma from wood tones, fixtures and reflections. So a photo is flagged
only when it clears a high fraction of near-white pixels AND a high fraction of
low-chroma pixels; either alone trips on a genuinely bright, plain room. Same
technique make_tour.py already uses for alpha_bbox()/art_contrast(): pipe
ffmpeg's decoded pixels to a subprocess and score them in pure Python. Nothing
beyond stdlib + ffmpeg.
"""
import os
import subprocess

GRID = 32               # downsample every photo to GRID x GRID before scoring
NEAR_WHITE = 235         # a channel this high or above counts as "white"
LOW_CHROMA = 18          # max-min channel spread this low or below counts as neutral
WHITE_FRACTION = 0.55    # fraction of pixels that must be near-white to flag
CHROMA_FRACTION = 0.85   # fraction of pixels that must be low-chroma to flag


def extract_rgb(path, grid=GRID):
    """Raw RGB24 bytes of `path`, downsampled to grid x grid, or b"" if ffmpeg
    could not decode it. Only ever captures stdout -- no output path is ever
    passed to ffmpeg, so this cannot write, rename or delete anything.
    """
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-vf",
         f"scale={grid}:{grid}:flags=neighbor", "-f", "rawvideo",
         "-pix_fmt", "rgb24", "-"],
        capture_output=True)
    want = grid * grid * 3
    return p.stdout[:want] if p.returncode == 0 and len(p.stdout) >= want else b""


def score(raw, grid=GRID):
    """(white_fraction, low_chroma_fraction) over raw RGB24 bytes."""
    n = len(raw) // 3
    if n == 0:
        return 0.0, 0.0
    white = chroma = 0
    for i in range(0, n * 3, 3):
        r, g, b = raw[i], raw[i + 1], raw[i + 2]
        if r >= NEAR_WHITE and g >= NEAR_WHITE and b >= NEAR_WHITE:
            white += 1
        if max(r, g, b) - min(r, g, b) <= LOW_CHROMA:
            chroma += 1
    return white / n, chroma / n


def looks_like_floor_plan(raw, grid=GRID):
    """(flagged, (white_fraction, low_chroma_fraction)). Short or empty input
    never flags -- an undecodable photo is skipped, not guessed at.
    """
    if len(raw) < grid * grid * 3:
        return False, (0.0, 0.0)
    white, chroma = score(raw, grid)
    return (white >= WHITE_FRACTION and chroma >= CHROMA_FRACTION), (white, chroma)


def detect(photo_paths, grid=GRID, extract=extract_rgb):
    """[(filename, reason)] for photos that look like a floor plan or site map.

    Never deletes, renames or moves anything. `extract` is injectable so a test
    can score synthetic bytes without invoking ffmpeg.
    """
    flagged = []
    for path in photo_paths:
        raw = extract(path, grid)
        hit, (white, chroma) = looks_like_floor_plan(raw, grid)
        if hit:
            flagged.append((
                os.path.basename(path),
                f"looks like a floor plan or site map "
                f"({white:.0%} near-white, {chroma:.0%} low-chroma)"))
    return flagged
