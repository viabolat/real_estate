#!/usr/bin/env python3
"""Rebuild the rule table inside _rules/CONTEXT.md from the rule files' frontmatter.

reason: a hand-curated index drifts the moment a rule is added and nothing detects
it -- the same failure shape as a photo-order sidecar. The prose in CONTEXT.md is
hand-written; only the table between the RULE-TABLE markers is generated. Stdlib
only, like everything else here.

    python3 _rules/reindex.py          # rewrite the table
    python3 _rules/reindex.py --check  # exit 1 if the table is stale
"""
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "CONTEXT.md")
START = "<!-- RULE-TABLE:start -->"
END = "<!-- RULE-TABLE:end -->"

# The areas, in the order a build actually moves through them.
AREAS = ["interface", "photos", "scrape", "naming", "build", "card",
         "delivery", "publishing", "outreach", "pii", "docs"]


def frontmatter(path):
    """Parse the flat subset of YAML these files use: scalars and one list."""
    out, key = {}, None
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    if lines[0].strip() != "---":
        raise SystemExit(f"{path}: no frontmatter")
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("  - "):
            out.setdefault(key, []).append(line[4:].strip())
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        out[key] = [] if val == "[]" else (val if val else [])
    return out


def title(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("# "):
                return line[2:].strip()
    raise SystemExit(f"{path}: no heading")


def table():
    rows = []
    for path in sorted(glob.glob(os.path.join(HERE, "*.md"))):
        if os.path.basename(path) == "CONTEXT.md":
            continue
        fm = frontmatter(path)
        rows.append((fm.get("area", "?"), fm["name"], title(path),
                     fm.get("guarded_by") or []))

    unknown = sorted({r[0] for r in rows} - set(AREAS))
    if unknown:
        raise SystemExit(f"unknown area(s): {unknown} -- add them to AREAS")

    out = [START, "", f"{len(rows)} rules.", "",
           "| Area | Rule | Guarded by |", "|---|---|---|"]
    for area in AREAS:
        for _, name, head, tests in sorted(r for r in rows if r[0] == area):
            guard = "<br>".join(f"`{t}`" for t in tests) if tests else "*prose only*"
            out.append(f"| {area} | [{head}]({name}.md) | {guard} |")
    out += ["", f"Unguarded rules: "
            f"{sum(1 for r in rows if not r[3])} of {len(rows)}.", "", END]
    return "\n".join(out)


def main():
    with open(INDEX, encoding="utf-8") as f:
        doc = f.read()
    a, b = doc.index(START), doc.index(END) + len(END)
    new = doc[:a] + table() + doc[b:]
    if "--check" in sys.argv:
        if new != doc:
            print("_rules/CONTEXT.md is stale -- run python3 _rules/reindex.py")
            return 1
        print("_rules/CONTEXT.md is current")
        return 0
    with open(INDEX, "w", encoding="utf-8") as f:
        f.write(new)
    print(f"rebuilt the rule table in {INDEX}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
