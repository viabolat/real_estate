#!/usr/bin/env python3
"""
run.py

Convenience wrapper: runs lead.py then photos.py against the
same dump, one command instead of two. Just calls each script as its own
subprocess -- no shared parsing state, no coupling beyond one imported
predicate (is_dump, below), each one still works fine run on its own.

Point it at a single dump, or at a folder of them:

    python3 run.py paste.txt          # one listing
    python3 run.py dumps/             # every *.txt and *.json in the folder
    python3 run.py                    # same, defaults to scraper/dumps/

A dump is a .txt or a .json file. Both are read as raw text and handed to the
same regexes -- the __NEXT_DATA__ blob saved on its own is the same bytes the
full page dump carries inside it -- so the extension decides only what is picked
up, never how it is parsed. photos.is_dump() is the one predicate for that, so
this and tour.py's pending-dump count can never disagree about a file.

One dump per file, always. The parsers use a first-match regex over the whole
text, so two dumps concatenated into one file would read the first listing's
agent name and phone onto the second listing's photos -- a wrong phone number
on a finished video, with nothing raised. Separate files make that impossible
rather than merely discouraged.

Re-running a folder is safe and cheap: lead.py skips a lead row that
already exists (same zpid and listing agent phone), photos.py skips
photos already on disk and never overwrites a brand.json or config.json. So
there is no "processed" folder to move dumps into, and no state to get out of
sync with the folder -- leave them where they are and run it again.

A dump that is a duplicate of one already scraped -- same company, address and
agent -- is reported loudly and separately from a clean run, so a batch of
re-pasted dumps cannot read as fresh work; it is not a failure and does not
affect the exit code.

A dump that fails does not stop the batch. The run reports which ones failed
and exits non-zero, so a batch that half-worked cannot look like a clean one.

For the --full / --out-dir flags, run lead.py / photos.py
directly instead.
"""

import argparse
import os
import subprocess
import sys

# reason: the "what counts as a dump" answer is shared with tour.py through
# photos.py, the same way target_for() shares the folder-naming answer. The one
# import into an otherwise subprocess-only wrapper buys a predicate that cannot
# drift; the parsing itself is still two subprocesses and no shared state.
from photos import is_dump


def dumps_in(path):
    """The dump files to process, in a stable order."""
    if os.path.isfile(path):
        return [path]
    if not os.path.isdir(path):
        return None
    return sorted(os.path.join(path, n) for n in os.listdir(path)
                  if is_dump(n))


def run_one(dump, lead_script, photos_script):
    """Both scripts against one dump. "new" | "duplicate" | "failed".

    reason: each script now exits 3 for "already have this, did nothing" --
    distinct from 0 (proceeded) and 2 (not a listing dump, a real failure) --
    so a re-scraped dump can be reported as a no-op instead of looking like
    fresh work in the batch summary. Either script calling it a duplicate is
    enough to call the pair one: whichever side found nothing new to do is
    exactly the resources-wasted signal this exists to surface.
    """
    lead = subprocess.run([sys.executable, lead_script, dump])
    print()
    photos = subprocess.run([sys.executable, photos_script, dump])
    codes = (lead.returncode, photos.returncode)
    if any(c not in (0, 3) for c in codes):
        return "failed"
    if 3 in codes:
        return "duplicate"
    return "new"


def main():
    parser = argparse.ArgumentParser(
        description="Run lead.py and photos.py on one dump or a folder of them.")
    parser.add_argument("path", nargs="?",
                        help="A dump file, or a folder of *.txt / *.json "
                             "dumps (default: the dumps/ folder beside this "
                             "script)")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    lead_script = os.path.join(script_dir, "lead.py")
    photos_script = os.path.join(script_dir, "photos.py")
    default_dumps = os.path.join(script_dir, "dumps")

    path = args.path or default_dumps
    dumps = dumps_in(path)

    if dumps is None:
        print(f"Not a file or folder: {path}")
        sys.exit(1)
    if not dumps:
        print(f"No *.txt or *.json dumps in {path}")
        print("Paste one Zillow page dump per file into that folder, then run this again.")
        sys.exit(1)

    single = len(dumps) == 1
    if not single:
        print(f"{len(dumps)} dump(s) in {path}\n")

    new, duplicate, failed = [], [], []
    for i, dump in enumerate(dumps, start=1):
        if not single:
            label = f"[{i}/{len(dumps)}] {os.path.basename(dump)}"
            print(f"\n{'=' * len(label)}\n{label}\n{'=' * len(label)}")
        print("=== lead.py ===", flush=True)
        try:
            result = run_one(dump, lead_script, photos_script)
        except OSError as e:
            # reason: one unreadable or malformed dump must not throw away the
            # rest of the batch. Twenty pasted listings is twenty chances to
            # have saved one as a directory or a zero-byte file.
            print(f"  FAILED to run against {dump}: {e}")
            result = "failed"
        {"new": new, "duplicate": duplicate, "failed": failed}[result].append(
            os.path.basename(dump))

    if not single:
        print(f"\n{'-' * 60}")
        print(f"{len(new)} new, {len(duplicate)} duplicate, {len(failed)} failed "
              f"-- {len(dumps)} dump(s) total")
        if duplicate:
            print(f"duplicate (nothing downloaded/appended): {', '.join(duplicate)}")
        if failed:
            print(f"failed: {', '.join(failed)}")
        print("Run `python3 status.py` from the project root for the roll-up.")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
