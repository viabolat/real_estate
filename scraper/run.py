#!/usr/bin/env python3
"""
run.py

Convenience wrapper: runs lead.py then photos.py against the
same dump, one command instead of two. Just calls each script as its own
subprocess -- no shared code, no coupling, each one still works fine run on
its own.

Point it at a single dump, or at a folder of them:

    python3 run.py paste.txt          # one listing
    python3 run.py dumps/             # every *.txt in the folder
    python3 run.py                    # same, defaults to scraper/dumps/

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

A dump that fails does not stop the batch. The run reports which ones failed
and exits non-zero, so a batch that half-worked cannot look like a clean one.

For the --full / --out-dir flags, run lead.py / photos.py
directly instead.
"""

import argparse
import os
import subprocess
import sys


def dumps_in(path):
    """The dump files to process, in a stable order."""
    if os.path.isfile(path):
        return [path]
    if not os.path.isdir(path):
        return None
    return sorted(os.path.join(path, n) for n in os.listdir(path)
                  if n.lower().endswith(".txt") and not n.startswith("."))


def run_one(dump, lead_script, photos_script):
    """Both scripts against one dump. True if both exited clean."""
    lead = subprocess.run([sys.executable, lead_script, dump])
    print()
    photos = subprocess.run([sys.executable, photos_script, dump])
    return lead.returncode == 0 and photos.returncode == 0


def main():
    parser = argparse.ArgumentParser(
        description="Run lead.py and photos.py on one dump or a folder of them.")
    parser.add_argument("path", nargs="?",
                        help="A dump file, or a folder of *.txt dumps "
                             "(default: the dumps/ folder beside this script)")
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
        print(f"No *.txt dumps in {path}")
        print("Paste one Zillow page dump per file into that folder, then run this again.")
        sys.exit(1)

    single = len(dumps) == 1
    if not single:
        print(f"{len(dumps)} dump(s) in {path}\n")

    failed = []
    for i, dump in enumerate(dumps, start=1):
        if not single:
            label = f"[{i}/{len(dumps)}] {os.path.basename(dump)}"
            print(f"\n{'=' * len(label)}\n{label}\n{'=' * len(label)}")
        print("=== lead.py ===", flush=True)
        try:
            ok = run_one(dump, lead_script, photos_script)
        except OSError as e:
            # reason: one unreadable or malformed dump must not throw away the
            # rest of the batch. Twenty pasted listings is twenty chances to
            # have saved one as a directory or a zero-byte file.
            print(f"  FAILED to run against {dump}: {e}")
            ok = False
        if not ok:
            failed.append(os.path.basename(dump))

    if not single:
        done = len(dumps) - len(failed)
        print(f"\n{'-' * 60}")
        print(f"{done} of {len(dumps)} dump(s) processed cleanly")
        if failed:
            print(f"failed: {', '.join(failed)}")
        print("Run `python3 status.py` from the project root for the roll-up.")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
