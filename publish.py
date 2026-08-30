#!/usr/bin/env python3
"""publish.py — puts the watermarked sample cuts, and only those, on the CDN.

    cd agents/<brand>/<listing>
    python3 ../../../publish.py            # table, confirmation, upload
    python3 ../../../publish.py --dry-run  # table and URLs, nothing leaves the machine

The bucket behind /preview/ is PUBLIC. That is safe for exactly one reason: the
only thing this script will ever put in it is a sample_ cut, which carries the
proofing watermark. The obvious implementation -- loop over out/*.mp4 and upload
-- would put <agent>_tour_branded.mp4, the unwatermarked paid deliverable, on a
guessable public URL at build time, before sign-off. That is the boundary the
tour_/sample_ filename split exists to make enforceable, and PROGRESS.md 5.1
settled the same question for outreach: it is a one-word difference in a
filename. So publishable() refuses anything that is not sample_, and there is no
flag that lifts it.

family() is the one place that decides which prefix means what, and publishable()
is written on top of it. status.py and tour.py both ask it rather than testing the
prefix themselves -- tour.py to derive which run a listing is on, status.py to name
the state -- so the sample_/tour_ boundary has a single implementation. A second
one would drift, and the drift would be an unwatermarked deliverable counted as a
proof.

published_listings() reads back the (brand, listing) pairs this script has already
confirmed onto the bucket, so "awaiting sign-off" is derived from the record of
what was published rather than from a marker file. It reads links.csv BY HEADER
NAME: that file has been migrated once already for exactly this kind of reason.

Why this is not in make_tour.py:

  make_tour.py is stdlib + ffmpeg and nothing else, it holds .build.lock for the
  length of a six-minute encode, and it is contractually blind to the
  agents/<brand>/<listing> layout. An upload needs a dependency-shaped API, a
  network failure domain that must not fail a good build, and that exact layout
  to build a collision-free remote path. All three arguments point out of that
  file.

Why urllib and not the supabase library: Storage is a plain REST endpoint, and
this project has no third-party dependencies. That property is worth more than
the forty lines it costs.

Why verification reads the API and not the public URL: public objects are served
through a CDN, so a HEAD issued seconds after an upload can hit an edge node that
has not replicated yet and report a correct upload as failed. The authenticated
object/list endpoint reads the origin and has no such race.

Local files are never deleted. A public bucket must not become the only copy of a
deliverable, and config.json is supposed to still explain what shipped months
later.

The project's Supabase plan caps a single upload at roughly 50MB -- no per-bucket
override, just the platform default -- and a two-minute 720p sample_ cut at
make_tour.py's CRF 18 routinely lands past it. A PUT that comes back 413 gets
retried with a smaller re-encode (UPLOAD_CRF_LADDER), climbing crf until one
clears the cap or the ladder runs out. That re-encode lives in a temp file for
the length of one PUT and nothing else; out/ is never touched, and verification
compares against whatever size actually reached the bucket, not out/'s.

Every confirmed publish also writes one email draft to outreach/drafts/ --
outreach/template.txt filled in with the agent's first name and the address from
the listing's config.json, and the sample_branded link. It quotes the watermarked
cut and never the tour_ file. Nothing is sent, and there is no SMTP credential
anywhere in this repo: PROGRESS.md 5.1 settled that mail leaving the machine is a
separate, deliberate act, never a flag someone trips.

The link written to outreach/links.csv is the LAST field on its line, and the file
is written with \n endings. It used to sit mid-row, so anything that grabbed the
link took the uploaded_at timestamp with it and the URL 404'd.
"""

import argparse
import contextlib
import csv
import datetime
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))

PHOTO_EXT = (".jpg", ".jpeg", ".png")
# Mirrors make_tour.py's 720p gate (1280 * ZOOM_MAX) -- see status.py.
GATE_720P = 1433


def _jpeg_size():
    """Borrow the scraper's pure-stdlib header reader rather than keeping another
    copy of it, or shelling out to ffprobe once per photo. status.py does the
    same. Returns a callable; falls back to a no-op when the scraper is absent,
    since a missing size check must never block a publish that is otherwise fine."""
    try:
        import importlib.util
        path = os.path.join(ROOT, "scraper", "photos.py")
        spec = importlib.util.spec_from_file_location("_photos_publish", path)
        mod = importlib.util.module_from_spec(spec)
        sys.path.insert(0, os.path.dirname(path))
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.path.pop(0)
        return mod.jpeg_size
    except Exception:
        return lambda path: (None, None)


jpeg_size = _jpeg_size()
DOTENV = os.path.join(ROOT, ".env")
LINKS = os.path.join(ROOT, "outreach", "links.csv")
# reason: url is LAST and uploaded_at FIRST. With the link mid-row, anything that
# grabbed it took ",2026-08-26T16:58:12" along and the URL 404'd. Nothing follows
# the last field, so nothing can be swallowed into it.
LINK_COLUMNS = ["uploaded_at", "brand", "listing", "cut", "url"]
TEMPLATE = os.path.join(ROOT, "outreach", "template.txt")
DRAFTS = os.path.join(ROOT, "outreach", "drafts")

BUCKET = "listing-media"
# The live host, plus the rewrite in vercel.json. Absolute on purpose: this string
# is what gets pasted into a cold email and written to outreach/links.csv, and a
# site-relative /preview/... path is not a link once it leaves this machine.
PREVIEW_HOST = "https://real-estate.viabolat.com"
PREVIEW_BASE = f"{PREVIEW_HOST}/preview"
TIMEOUT = 300                      # a 72 MB cut over a slow line
ATTEMPTS = 3
PRIMARY_CUT = "sample_branded"     # the one that gets quoted in an email
# reason: the bucket has no per-bucket file_size_limit override -- confirmed
# against the Storage API's own bucket record -- so a PUT past ~50MB 400s
# with the project's own EntityTooLarge. Discovered 2026-08-30: a two-minute
# 720p sample_ cut at make_tour.py's CRF 18 landed at 77.8MB. Each rung
# re-encodes the same local file smaller; upload() stops climbing at the
# first crf that clears the cap. See
# _rules/an-oversized-upload-compresses-a-review-copy.md.
UPLOAD_CRF_LADDER = (23, 28, 32)

# Values copied out of .env.example and never filled in. See credentials().
PLACEHOLDER = re.compile(
    r"your[-_]project[-_]ref|your[-_]?project|changeme|<[^>]*>", re.I)


# ---- configuration ----------------------------------------------------------

def load_dotenv(path=None):
    """KEY=VALUE lines into os.environ. An already-set variable always wins.

    reason: the stdlib has no .env parser, so a script that documents "put the
    key in .env" and then reads only os.environ exits 2 on a machine where the
    operator did exactly what the docs said. Deliberately tiny -- no export
    keyword, no interpolation, no multi-line values. Anything more is a
    dependency wearing a disguise.
    """
    # reason: resolve DOTENV at call time, not as a default argument. A default
    # binds at import, so mock.patch.object(publish, "DOTENV", ...) could not
    # reach it -- the credentials fail-closed test went on reading the real .env
    # and passed only for as long as that file held the example placeholder. The
    # moment a real URL landed in it the test failed, having quietly tested
    # nothing before that. A gate's own test must not depend on the operator's
    # machine being unconfigured.
    if path is None:
        path = DOTENV
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return False
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)
    return True


def credentials():
    """(base_url, service_key), or exit 2.

    reason: same rule as require_git() in check_pii.py. A publish step that
    silently no-ops reads identically to one that succeeded, and they mean
    opposite things.
    """
    load_dotenv()
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    missing = [n for n, v in (("SUPABASE_URL", url),
                              ("SUPABASE_SERVICE_KEY", key)) if not v]
    # reason: .env.example ships SUPABASE_URL=https://your-project-ref.supabase.co
    # so that the shape is obvious. Copying the file and filling in only the key
    # left that placeholder in place, and a non-empty string passed the check
    # above -- so the run got all the way to uploading 90 MB against a hostname
    # that cannot resolve. A value that is still the example is not configuration.
    placeholder = [n for n, v in (("SUPABASE_URL", url),
                                  ("SUPABASE_SERVICE_KEY", key))
                   if v and (PLACEHOLDER.search(v) or "<" in v or ">" in v)]
    if missing or placeholder:
        names = missing + placeholder
        it = "it" if len(names) == 1 else "them"
        state = "not set" if not placeholder else "not set, or still the example"
        print(f"REFUSING TO PUBLISH: {' and '.join(names)} {state}.")
        if placeholder:
            print("  " + ", ".join(placeholder) + " still reads as the "
                  ".env.example placeholder. Fill in the real value -- the "
                  "project ref\n  is in your Supabase dashboard URL.")
        print(f"Set {it} in the environment, or in {DOTENV} (see .env.example).")
        print("Nothing was uploaded. This exits non-zero rather than doing "
              "nothing quietly, because those two look the same from here.")
        sys.exit(2)
    return url, key


# ---- the gate ---------------------------------------------------------------

def family(name):
    """"sample" | "tour" | None -- which family a cut in out/ belongs to.

    reason: the sample_/tour_ boundary is the one this file exists to hold, and
    it now has a second reader: tour.py derives which run a listing is on from
    what is in out/, and status.py reports it. Both ask here rather than growing
    their own prefix test, because two implementations of this boundary is
    exactly the drift the boundary exists to prevent. publishable() is still the
    gate; this is only the naming half of it, so the two can never disagree.

    The prefix appears twice because output_prefix leads every filename with the
    agent's own name -- sean_obrien_sample_branded.mp4 -- and is blank on a
    listing that never set one.
    """
    if not name.endswith(".mp4"):
        return None
    if name.startswith("tour_") or "_tour_" in name:
        return "tour"
    if name.startswith("sample_") or "_sample_" in name:
        return "sample"
    return None


def publishable(name):
    """(ok, reason). The one rule this file exists to enforce.

    A sample_ cut is watermarked by construction -- make_tour.py hard-refuses a
    build whose watermark will not render -- so the filename is sufficient
    evidence and no frame inspection is needed here. Do not add one.
    """
    if not name.endswith(".mp4"):
        return False, "not an mp4"
    kind = family(name)
    if kind == "tour":
        return False, ("tour_ cuts are the signed-off deliverable and never "
                       "auto-publish")
    if kind == "sample":
        return True, ""
    return False, "not a recognised cut"


def remote_path(listing_dir, filename):
    """agents/<brand>/<listing>/ + x.mp4 -> "<brand>/<listing>/x.mp4".

    reason: the bare filename collides. Two listings by the same agent both
    produce sean_obrien_sample_branded.mp4, and a listing with a blank
    agent_name produces a bare sample_branded.mp4 -- with x-upsert the second
    silently overwrites the first. This is the collision _reference/layout.md
    solved locally with output_prefix, and it has to be solved again at the
    bucket. Refusing a directory that is not under agents/ keeps the layout
    knowledge honest: publish.py may know it, make_tour.py may not.
    """
    full = os.path.abspath(listing_dir)
    parent, listing = os.path.split(full)
    grand, brand = os.path.split(parent)
    if not listing or not brand or os.path.basename(grand) != "agents":
        raise ValueError(
            f"{full} is not agents/<brand>/<listing>. The remote path is "
            "derived from the folder, and the scrape is what names the folder.")
    return f"{brand}/{listing}/{filename}"


def public_url(base, path):
    return f"{base}/storage/v1/object/public/{BUCKET}/{urllib.parse.quote(path)}"


def preview_url(path):
    """The public link for a remote path: PREVIEW_HOST/preview/<brand>/<listing>/<cut>.

    reason: the .mp4 is dropped because vercel.json's rewrite appends it to the
    destination -- keeping it here would resolve to <cut>.mp4.mp4 and 404. The host
    is included because this is the string that reaches a client.
    """
    stem = path[:-4] if path.endswith(".mp4") else path
    return f"{PREVIEW_BASE}/{urllib.parse.quote(stem)}"


# ---- the wire ---------------------------------------------------------------

def _request(url, key, method, body=None, length=None, content_type=None,
             extra=None):
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {key}")
    if content_type:
        req.add_header("Content-Type", content_type)
    if length is not None:
        req.add_header("Content-Length", str(length))
    for k, v in (extra or {}).items():
        req.add_header(k, v)
    return urllib.request.urlopen(req, timeout=TIMEOUT)


def upload(base, key, local_path, path):
    """PUT one file. Returns None on success, an error string on failure."""
    url = f"{base}/storage/v1/object/{BUCKET}/{urllib.parse.quote(path)}"
    size = os.path.getsize(local_path)
    last = ""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            # reason: reopened per attempt -- a retry cannot reuse a file object
            # the failed attempt already read to the end.
            with open(local_path, "rb") as f:
                with _request(url, key, "PUT", body=f, length=size,
                              content_type="video/mp4",
                              extra={"x-upsert": "true"}) as r:
                    if r.status in (200, 201):
                        return None
                    last = f"HTTP {r.status}"
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:200]
            last = f"HTTP {e.code} {detail}"
            if e.code < 500:
                return last          # auth, bucket, path -- retrying cannot help
        except urllib.error.URLError as e:
            last = str(e)
            # reason: a hostname that does not resolve does not resolve three
            # times either. Retrying it burned two extra attempts per file on a
            # typo in SUPABASE_URL and buried the actual cause in noise.
            if isinstance(e.reason, socket.gaierror):
                return (f"{last} -- SUPABASE_URL does not resolve. Check the "
                        "project ref.")
        except OSError as e:
            last = str(e)
        if attempt < ATTEMPTS:
            print(f"    attempt {attempt} failed ({last}), retrying...")
    return last


def _too_large(detail):
    """True if `detail` (an upload() error string) is the bucket's own "the
    object is bigger than the project allows" response -- the one failure
    worth retrying with a smaller file rather than the same bytes again."""
    return "413" in detail and "EntityTooLarge" in detail


@contextlib.contextmanager
def _compressed_copy(local_path, crf):
    """A CRF-`crf` re-encode of local_path, alive only inside this `with`.

    reason: some cuts land past the bucket's upload cap (see
    UPLOAD_CRF_LADDER above). out/ is the master and is never touched --
    this is a second, smaller file that exists purely for the one PUT that
    needs it. Cleanup rides NamedTemporaryFile's own teardown rather than a
    manual delete call here, which is what keeps
    test_nothing_in_publish_deletes_a_local_file meaningful: this file may
    still never remove a DELIVERABLE, and this is not one.
    """
    with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp:
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", local_path,
                 "-c:v", "libx264", "-crf", str(crf), "-preset", "medium",
                 "-c:a", "aac", "-b:a", "128k", tmp.name],
                check=True, capture_output=True, text=True)
        except FileNotFoundError:
            yield None, "ffmpeg is not on PATH"
            return
        except subprocess.CalledProcessError as e:
            detail = (e.stderr or "").strip()[:200]
            yield None, detail or f"ffmpeg exited {e.returncode}"
            return
        yield tmp.name, os.path.getsize(tmp.name)


def list_objects(base, key, prefix):
    """{filename: size} for one listing's folder, read from the origin.

    reason: this is the verification step, and it deliberately does NOT fetch
    the public URL. See the module docstring -- the CDN race turns a correct
    upload into an intermittent failure report.
    """
    url = f"{base}/storage/v1/object/list/{BUCKET}"
    body = json.dumps({"prefix": prefix, "limit": 200, "offset": 0}).encode()
    with _request(url, key, "POST", body=body, length=len(body),
                  content_type="application/json") as r:
        items = json.loads(r.read().decode("utf-8"))
    out = {}
    for it in items:
        meta = it.get("metadata") or {}
        if "size" in meta:                       # a folder entry has no metadata
            out[os.path.basename(it.get("name", ""))] = meta["size"]
    return out


# ---- the record -------------------------------------------------------------

def migrate_links():
    """Rewrite an existing links.csv into the current column order, once.

    reason: the url used to sit mid-row, and csv's default \r\n put a trailing
    carriage return on the last field for anything reading the file by hand. The
    file is gitignored, so it never travels and a one-off fix here would not reach
    any other clone -- the repair belongs in the code that writes it.
    """
    if not os.path.isfile(LINKS):
        return
    with open(LINKS, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows or list(rows[0].keys()) == LINK_COLUMNS:
        return
    with open(LINKS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LINK_COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: (r.get(k) or "").strip() for k in LINK_COLUMNS})


def record_links(rows):
    """Append to outreach/links.csv -- the file PROGRESS.md 5.1's emails.py reads."""
    os.makedirs(os.path.dirname(LINKS), exist_ok=True)
    migrate_links()
    new = not os.path.isfile(LINKS)
    with open(LINKS, "a", newline="", encoding="utf-8") as f:
        # reason: lineterminator="\n" -- csv defaults to \r\n, which glues a \r
        # onto the url now that url is the last field on the line.
        w = csv.DictWriter(f, fieldnames=LINK_COLUMNS, lineterminator="\n")
        if new:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def published_listings():
    """{(brand, listing)} that have had a cut confirmed onto the review bucket.

    reason: status.py needs to tell "sample built, not sent" from "sample sent,
    waiting on the client", and links.csv already records every confirmed
    publish. That makes the answer derivable, so no new marker file is invented
    for it -- the same reason photo order lives in the filename prefix.

    Read by header name, never by column position: the url moved to the end of
    the row once already, and a positional reader would have silently followed
    it. A missing file is an empty set, exactly as a missing leads.csv is.
    """
    if not os.path.isfile(LINKS):
        return set()
    try:
        with open(LINKS, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except OSError:
        return set()
    return {(r["brand"].strip(), r["listing"].strip()) for r in rows
            if (r.get("brand") or "").strip() and (r.get("listing") or "").strip()}


# ---- the draft --------------------------------------------------------------

def draft_text(listing_dir, url):
    """(rendered email, [placeholders still unfilled]) from outreach/template.txt.

    reason: the wording lived in property_email.txt with three <angle bracket>
    blanks filled in by hand on every send, from a CSV whose link was the thing
    that broke. The template is committed -- it holds no lead data, only the
    sender's own name -- so a clone can draft; the values come from the listing's
    config.json, which is already the single record of what produced the build.
    """
    with open(TEMPLATE, encoding="utf-8") as f:
        body = f.read()
    cfg = {}
    try:
        with open(os.path.join(listing_dir, "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        pass
    name = (cfg.get("agent_name") or "").strip()
    fields = {"agent_first": name.split()[0] if name else "",
              "address": (cfg.get("address") or "").strip(),
              "url": url}
    # reason: a blank field leaves its {placeholder} visible instead of rendering
    # "Hi ," -- a gap you can see beats one silently filled with nothing.
    missing = sorted(k for k, v in fields.items() if not v)
    for k, v in fields.items():
        if v:
            body = body.replace("{" + k + "}", v)
    return body, missing


def write_draft(listing_dir, brand, listing, url):
    """Write the draft and return (path, missing). Overwrites: it is derived."""
    text, missing = draft_text(listing_dir, url)
    os.makedirs(DRAFTS, exist_ok=True)
    path = os.path.join(DRAFTS, f"{brand}__{listing}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path, missing


# ---- the run ----------------------------------------------------------------

def human(n):
    return f"{n / 1_000_000:.1f} MB"


def confirm(question, default=False):
    d = "Y/n" if default else "y/N"
    while True:
        try:
            a = input(f"{question} ({d}): ").strip().lower()
        except EOFError:
            raise SystemExit("\nNo input available. Run publish.py in a terminal.")
        if not a:
            return default
        if a in ("y", "yes"):
            return True
        if a in ("n", "no"):
            return False
        print("  Answer y or n.")


def smallest_photo(listing_dir):
    """Longest edge of the smallest photo in photos/, or None if unmeasurable.

    reason: the soft-cut warning used to read a _lowres suffix off the filenames.
    Nothing is encoded in a filename any more, so it is measured here instead --
    from photos/, which is where the gate measures it too. jpeg_size comes from
    the scraper rather than a fourth copy of the header parser, exactly as
    status.py borrows it.
    """
    photo_dir = os.path.join(listing_dir, "photos")
    if not os.path.isdir(photo_dir):
        return None
    edges = []
    for name in sorted(os.listdir(photo_dir)):
        path = os.path.join(photo_dir, name)
        if not os.path.isfile(path) or not name.lower().endswith(PHOTO_EXT):
            continue
        try:
            w, h = jpeg_size(path)
        except Exception:
            continue
        if w and h:
            edges.append(max(w, h))
    return min(edges) if edges else None


def survey(listing_dir):
    """(allowed, refused) over out/. allowed is [(name, size, remote_path)]."""
    out_dir = os.path.join(listing_dir, "out")
    if not os.path.isdir(out_dir):
        return None, None
    allowed, refused = [], []
    for name in sorted(os.listdir(out_dir)):
        p = os.path.join(out_dir, name)
        if not os.path.isfile(p):
            continue
        ok, why = publishable(name)
        if ok:
            allowed.append((name, os.path.getsize(p), remote_path(listing_dir, name)))
        elif name.endswith(".mp4"):
            refused.append((name, why))
    return allowed, refused


def main():
    ap = argparse.ArgumentParser(
        description="Publish this listing's sample_ cuts to Supabase Storage.")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the table and the URLs, upload nothing")
    ap.add_argument("listing", nargs="?", default=".",
                    help="listing folder (default: the working directory)")
    args = ap.parse_args()

    listing_dir = os.path.abspath(args.listing)
    try:
        remote_path(listing_dir, "probe.mp4")
    except ValueError as e:
        print(f"REFUSING TO PUBLISH: {e}")
        sys.exit(2)

    base, key = credentials()
    files, refused = survey(listing_dir)
    if files is None:
        print(f"No out/ in {listing_dir}. Build the delivery first: python3 tour.py")
        sys.exit(1)
    if not files:
        print("Nothing to publish: no sample_ cuts in out/.")
        sys.exit(1)

    print(f"Bucket {BUCKET} at {base} -- PUBLIC. "
          "Only watermarked sample_ cuts go here.\n")
    for name, size, path in files:
        print(f"  {name}  ({human(size)})")
        print(f"    -> {path}")
        print(f"       {preview_url(path)}")
    if refused:
        print("\nHeld back:")
        for name, why in refused:
            print(f"  {name}  --  {why}")

    smallest = smallest_photo(listing_dir)
    if smallest and smallest < GATE_720P:
        print(f"\nBELOW PAR: the smallest photo in this listing is {smallest}px, "
              f"so these cuts\nwere upscaled past what the photos hold. They are "
              f"soft, and nothing in their\nnames says so. A prospect judges the "
              f"quality of your work by this file.\nSee IDEA.md 4.")
        if not args.dry_run and not confirm("Publish soft cuts anyway?", False):
            print("Nothing was uploaded.")
            return

    if args.dry_run:
        # reason: the draft is the point of a publish now, so a dry run has to
        # show it. Rendering it here exercises the template and the config the
        # same way a real run does, without touching the bucket.
        primary = next((p for n, _, p in files if PRIMARY_CUT in n), None)
        if primary:
            text, missing = draft_text(listing_dir, preview_url(primary))
            brand, listing = remote_path(listing_dir, "x.mp4").split("/")[:2]
            print(f"\nThe draft this would write to "
                  f"{os.path.relpath(DRAFTS, ROOT)}/{brand}__{listing}.txt:\n")
            print("\n".join("  " + l for l in text.splitlines()))
            if missing:
                print(f"\n  {len(missing)} placeholder(s) left unfilled "
                      f"({', '.join(missing)}) -- config.json has no value for "
                      f"them.")
        else:
            print(f"\nNo {PRIMARY_CUT} cut here, so no email draft: the outreach "
                  f"link is always\nthe watermarked branded sample.")
        print("\n--dry-run: nothing was uploaded.")
        return
    if not confirm(f"\nUpload these {len(files)} file(s)?", False):
        print("Nothing was uploaded.")
        return

    print()
    failed = []
    actual_size = {}
    compressed = []
    for name, size, path in files:
        local = os.path.join(listing_dir, "out", name)
        print(f"  uploading {name} ({human(size)})...")
        err = upload(base, key, local, path)
        uploaded_size = size
        if err and _too_large(err):
            print(f"    {human(size)} is over the bucket's upload cap -- "
                  "compressing a smaller review copy...")
            last_crf = None
            for crf in UPLOAD_CRF_LADDER:
                last_crf = crf
                with _compressed_copy(local, crf) as (tmp_path, result):
                    if tmp_path is None:
                        err = f"could not compress a smaller copy ({result})"
                        break
                    print(f"    crf {crf} -> {human(result)}, uploading...")
                    err = upload(base, key, tmp_path, path)
                    if not err:
                        uploaded_size = result
                if not err or not _too_large(err):
                    break
            if err and _too_large(err):
                err = (f"still over the bucket's upload cap after "
                       f"compressing down to crf {last_crf}. Shorten "
                       "clip_seconds or the photo count, or raise the "
                       "project's storage upload limit.")
        if err:
            print(f"    FAILED: {err}")
            failed.append(name)
        else:
            actual_size[name] = uploaded_size
            if uploaded_size != size:
                compressed.append(name)

    if len(failed) == len(files):
        # reason: the verification step used to run anyway and report "uploads
        # finished but the listing check could not run", which reads as a
        # verification problem on top of a successful upload. Every upload had
        # failed. Say that, and only that.
        print(f"\nNothing was uploaded -- all {len(files)} file(s) failed above.")
        print("The local cuts in out/ were not touched, and links.csv was not "
              "written.")
        sys.exit(1)

    # ---- verify against the origin, once, for the whole listing ----
    prefix = os.path.dirname(files[0][2])
    try:
        present = list_objects(base, key, prefix)
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"\nUploads finished but the listing check could not run ({e}).")
        print("Treat this as unverified: nothing was written to links.csv.")
        sys.exit(1)

    confirmed, rows = [], []
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    brand, listing = prefix.split("/", 1)
    for name, size, path in files:
        if name in failed:
            continue
        expected = actual_size.get(name, size)
        if present.get(name) != expected:
            print(f"  UNVERIFIED: {name} is {present.get(name, 'absent')} at the "
                  f"origin, expected {expected}")
            failed.append(name)
            continue
        confirmed.append((name, path))
        rows.append({"uploaded_at": stamp, "brand": brand, "listing": listing,
                     "cut": name, "url": preview_url(path)})

    draft, missing = None, []
    if rows:
        record_links(rows)
        # reason: cold outreach quotes the sample_branded cut and nothing else --
        # PROGRESS.md 5.1's hard rule. The tour_ file is the paid deliverable and
        # is a one-word difference in a filename.
        primary = next((p for n, p in confirmed if PRIMARY_CUT in n), None)
        if primary:
            draft, missing = write_draft(listing_dir, brand, listing,
                                         preview_url(primary))

    print(f"\n{len(confirmed)} of {len(files)} confirmed at the origin.")
    for name, path in confirmed:
        mark = "  <- send this one" if PRIMARY_CUT in name else ""
        print(f"  {preview_url(path)}{mark}")
    if compressed:
        print(f"\n{len(compressed)} cut(s) were over the bucket's upload cap, "
              f"so the CDN copy is a smaller re-encode ({', '.join(compressed)})."
              " out/ still holds the original quality.")
    if confirmed:
        print("\nThese are served through a CDN, so a link can 404 for a few "
              "seconds\nbefore the edge catches up. That is not a failed upload.")
        print(f"Recorded in {os.path.relpath(LINKS, ROOT)}.")
    if draft:
        print(f"\nEmail draft: {os.path.relpath(draft, ROOT)}")
        if missing:
            print(f"  {len(missing)} placeholder(s) left unfilled "
                  f"({', '.join(missing)}) -- fill them in or add them to "
                  f"config.json.")
        print("  Nothing is sent. Copy it into your mail client when you are "
              "ready.")
    elif confirmed:
        print(f"\nNo {PRIMARY_CUT} cut was confirmed, so no email draft was "
              f"written.")
    print("\nThe local cuts in out/ were not touched.")

    if failed:
        print(f"\n{len(failed)} file(s) did not make it: {', '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped. A part-sent file may exist; re-running overwrites it.")
