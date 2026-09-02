"""photo_quality.py -- scores a listing's photos for sharpness/contrast so
make_tour.py can trim an oversized set down to the 90s ceiling by dropping the
weakest photos, never the newest or the last N.

Same shape as floorplan.py: pipe ffmpeg's decoded pixels to a subprocess and
score them in pure Python. The only file operation anywhere in this module is
that ffmpeg subprocess, whose output is captured to an in-memory bytes object
-- no function here is ever handed a path to write, rename or remove.

A blurry, flat, or badly underexposed photo has low edge energy in its luma
channel; a photo with real detail -- furniture edges, window mullions, tile
grout -- has high edge energy regardless of exposure. select() uses that score
only to choose which photos survive; it restores the kept ones to their
original order before returning, so it never disturbs the ordering that lives
in the filename prefix (see _rules/photo-order-lives-in-the-filename-prefix.md).
"""
import os
import subprocess

GRID = 64   # finer than floorplan.py's 32 -- edge energy needs more than a
            # coarse color/chroma read to tell a sharp photo from a soft one


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


def sharpness(raw, grid=GRID):
    """Mean squared luma gradient over raw RGB24 bytes -- higher is sharper.
    Undecodable or short input scores 0.0 rather than raising.
    """
    if len(raw) < grid * grid * 3:
        return 0.0
    luma = [0.299 * raw[i] + 0.587 * raw[i + 1] + 0.114 * raw[i + 2]
            for i in range(0, grid * grid * 3, 3)]
    total = count = 0.0
    for r in range(grid):
        row = r * grid
        for c in range(grid):
            here = luma[row + c]
            if c + 1 < grid:
                d = luma[row + c + 1] - here
                total += d * d
                count += 1
            if r + 1 < grid:
                d = luma[row + grid + c] - here
                total += d * d
                count += 1
    return total / count if count else 0.0


def rank(photo_paths, extract=extract_rgb, grid=GRID):
    """[(path, score)] for photo_paths, highest score (sharpest) first.
    `extract` is injectable so a test can score synthetic bytes without
    invoking ffmpeg.
    """
    scored = [(p, sharpness(extract(p, grid), grid)) for p in photo_paths]
    return sorted(scored, key=lambda ps: ps[1], reverse=True)


def select(photo_paths, keep_n, extract=extract_rgb, grid=GRID):
    """Keep the keep_n sharpest of photo_paths, restored to their ORIGINAL
    relative order. Returns (kept, dropped) -- dropped is [(path, score)],
    weakest first, for the caller to print as a report. keep_n >= len(paths)
    keeps everything and drops nothing.
    """
    if len(photo_paths) <= keep_n:
        return list(photo_paths), []
    ranked = rank(photo_paths, extract, grid)
    keep = {p for p, _ in ranked[:keep_n]}
    kept = [p for p in photo_paths if p in keep]
    dropped = sorted((ps for ps in ranked if ps[0] not in keep),
                      key=lambda ps: ps[1])
    return kept, dropped
