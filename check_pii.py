#!/usr/bin/env python3
"""
check_pii.py

Refuses to let a lead, an agent's phone number, or an email address reach the
remote. Run it before every push.

    python3 check_pii.py          # exit 0 = safe to push
    python3 check_pii.py --staged # only what is staged right now

reason: this repo is private, and a private repo is an access-control boundary,
not a redaction one. It gets shared with a collaborator, cloned to a second
machine, or made public years later, and nothing re-reviews the history at that
moment. .gitignore is the first line and it is fragile in a specific way -- git
only treats "#" as a comment at the start of a line, so a pattern written as
"scraper/paste.txt  # raw dump" silently matches nothing. That exact mistake
left leads.html and paste.txt unignored in this repo for a few minutes. A
pattern that fails is invisible; a check that exits non-zero is not.

What it looks at: every file git would actually publish -- tracked files, plus
staged ones, plus untracked files that are NOT ignored. An ignored file is not
scanned, because not shipping it is the whole point.

What it looks for:
  1. Anything phone-shaped or email-shaped.
  2. Every real agent name, phone and email currently in scraper/leads.csv.
     The lead list is the ground truth for what must not escape, so it is the
     dictionary the scan is run against -- not a guess at what a name looks like.

It fails CLOSED. Without git, outside a repository, or when git enumerates no
publishable files at all, it exits 2 rather than printing a clean result -- because
"nothing to scan" and "nothing found" read identically in the output and mean
opposite things.

Findings are printed MASKED. A check that prints the phone number it found in
full has moved the leak into the terminal, the scrollback, and any CI log.
"""

import argparse
import csv
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
LEADS = os.path.join(ROOT, "scraper", "leads.csv")

PHONE = re.compile(r'\b\d{3}[-.\s)]\s?\d{3}[-.\s]\d{4}\b')
EMAIL = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')

# Text that legitimately looks like an email but is documentation, not a lead.
ALLOW = re.compile(r'@example\.|@2x|noreply@|your@|name@|@[A-Za-z]+\.(?:png|jpg|mp4|py|md)\b')

# Binary and asset extensions -- nothing to read, and huge.
SKIP_EXT = (".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mp3", ".ico", ".pdf",
            ".zip", ".gz", ".ttf", ".otf", ".woff", ".woff2")


def git(*args):
    out = subprocess.run(["git", "-C", ROOT, *args],
                         capture_output=True, text=True)
    return [l for l in out.stdout.splitlines() if l.strip()]


def require_git():
    """Exit non-zero unless git is installed AND ROOT is a working repository.

    reason: git() swallows a failed subprocess and returns []. With git missing,
    or with the tree copied somewhere without its .git, published_files() then
    returned nothing and the scan reported "Scanned 0 publishable file(s) / Safe
    to push" and exited 0 -- over a directory that may hold the entire lead list.
    That is this file's own stated failure mode, one level up: "A pattern that
    fails is invisible; a check that exits non-zero is not." A gate whose tooling
    is absent must fail closed, because "nothing to scan" and "nothing found" are
    indistinguishable in the output but opposite in meaning.
    """
    try:
        out = subprocess.run(["git", "-C", ROOT, "rev-parse", "--git-dir"],
                             capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"REFUSING TO PASS: cannot run git ({e}).")
        print("This check can only see what git would publish. Without git it "
              "sees nothing, and nothing looks identical to clean.")
        sys.exit(2)
    if out.returncode != 0:
        print(f"REFUSING TO PASS: {ROOT} is not a git repository.")
        print("This check enumerates files via git. Outside a repository it "
              "scans nothing, which would print as clean.")
        sys.exit(2)


def published_files(staged_only=False):
    """Every path git would publish. Ignored files are excluded by git itself."""
    if staged_only:
        names = git("diff", "--cached", "--name-only")
    else:
        names = git("ls-files") + git("ls-files", "--others", "--exclude-standard")
    seen, out = set(), []
    for n in names:
        if n in seen or n.lower().endswith(SKIP_EXT):
            continue
        seen.add(n)
        p = os.path.join(ROOT, n)
        if os.path.isfile(p):
            out.append(n)
    return out


def mask(s):
    """Enough to find it, not enough to leak it."""
    s = s.strip()
    if len(s) <= 4:
        return "*" * len(s)
    return f"{s[:2]}{'*' * (len(s) - 4)}{s[-2:]}"


def lead_values():
    """Real names, phones and emails from leads.csv -- the dictionary to scan for."""
    if not os.path.isfile(LEADS):
        return [], True
    vals = set()
    with open(LEADS, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            for k in ("agent_name", "agent_email", "agent_phone", "contact_name"):
                v = (r.get(k) or "").strip()
                # reason: a 1-2 word fragment like "The" or a blank would match
                # every file in the repo. Only take values specific enough to be
                # a real identifier.
                if len(v) >= 6:
                    vals.add(v)
                    if k in ("agent_name", "contact_name"):
                        vals.add(v.lower().replace(" ", "_").replace(".", "").replace("/", "_"))
    return sorted(vals), False


def main():
    ap = argparse.ArgumentParser(description="Refuse to push leads or PII.")
    ap.add_argument("--staged", action="store_true",
                    help="only scan what is staged right now")
    args = ap.parse_args()

    require_git()
    files = published_files(args.staged)
    names, no_leads = lead_values()

    hits = []
    for rel in files:
        try:
            with open(os.path.join(ROOT, rel), encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except OSError:
            continue
        for i, line in enumerate(lines, start=1):
            for m in PHONE.finditer(line):
                hits.append((rel, i, "phone-shaped", mask(m.group())))
            for m in EMAIL.finditer(line):
                if not ALLOW.search(m.group()):
                    hits.append((rel, i, "email-shaped", mask(m.group())))
            for n in names:
                if n in line:
                    hits.append((rel, i, "value from leads.csv", mask(n)))

    scope = "staged" if args.staged else "publishable"
    print(f"Scanned {len(files)} {scope} file(s) against "
          f"{len(names)} value(s) from leads.csv.")
    if no_leads:
        print("  NOTE: scraper/leads.csv not found -- pattern checks ran, but "
              "there was no lead list to check names against.")

    if not files and not args.staged:
        print("REFUSING TO PASS: git listed no publishable files at all.")
        print("A repository with nothing in it is not a clean scan, it is a "
              "scan that did not happen.")
        sys.exit(2)

    if not hits:
        print("No leads or PII found. Safe to push.")
        return

    print(f"\n{len(hits)} finding(s) -- masked on purpose, open the file to see it:\n")
    for rel, line, kind, shown in hits:
        print(f"  {rel}:{line}  {kind}: {shown}")
    print("\nRemove these or add the file to .gitignore, then run again.")
    sys.exit(1)


if __name__ == "__main__":
    main()
