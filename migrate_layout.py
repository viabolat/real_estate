#!/usr/bin/env python3
"""Move a listing folder still in the pre-agent-level layout into <agent>/.

The old layout put config.json and photos/ directly under
agents/<brand>/<listing>/. The current one puts them under
agents/<brand>/<listing>/<agent>/, and every walker in tour.py and status.py
assumes it. A folder left behind is not merely skipped -- tour.py's
agent_dirs() used to return "photos" as the agent slug, so --auto built
agents/<brand>/<listing>/photos/, status.py filed the listing as unverifiable
for having no config.json, and needs_attention/ symlinked a raw photos/
directory. See _rules/an-agent-folder-is-one-that-holds-a-config.md.

The destination is never typed here. It is re-derived from scraper/leads.csv
through status.py's scraped_names(), keyed on agent_phone the same way the
drift audit is -- one naming authority, per
_rules/the-scrape-names-the-folders.md. A listing folder with no lead row
behind it is refused, not guessed at.

    python3 migrate_layout.py          # plan only, writes nothing
    python3 migrate_layout.py --yes    # do it

Everything is moved with os.rename: bytes are relocated, never rewritten and
never dropped. The one exception is a listing whose <agent>/ already exists
holding a byte-identical copy of the same photos -- a half-finished migration
that ran once already. That legacy copy is deleted rather than merged, because
merging two identical trees can only produce the one that is already there.
"""
import argparse
import filecmp
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
AGENTS = os.path.join(ROOT, "agents")
ASSETS = os.path.join(ROOT, "global_assets")
sys.path.insert(0, ROOT)
import status  # noqa: E402  -- the naming authority, not a second copy of it


def _rewrite_json(path, data):
    """Replace a JSON file wholesale, via temp file + os.replace.

    reason: fill_gaps._patch_json() merges keys and cannot remove one, and
    config normalisation below has to DROP a key (an empty "music", a logo
    whose file is gone) so the brand default is inherited instead of shadowed
    by a dead value. Same crash-safe shape, different operation.
    """
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def is_legacy(listing_dir):
    """config.json sitting BESIDE photos/ -- the old layout, agent level absent."""
    return (os.path.isfile(os.path.join(listing_dir, "config.json"))
            and os.path.isdir(os.path.join(listing_dir, "photos")))


def identical_photos(a, b):
    """Do two photos/ directories hold the same filenames and the same bytes?"""
    if not (os.path.isdir(a) and os.path.isdir(b)):
        return False
    na, nb = sorted(os.listdir(a)), sorted(os.listdir(b))
    if not na or na != nb:
        return False
    match, mismatch, errors = filecmp.cmpfiles(a, b, na, shallow=False)
    return not mismatch and not errors


def plan(agents_dir=AGENTS, truth=None):
    """[(kind, brand, listing, slug, detail)] -- nothing is written here.

    kind is "move", "duplicate" (an identical copy already migrated),
    "conflict" (<agent>/ exists but differs) or "refuse" (no lead row).
    """
    truth = status.scraped_names() if truth is None else truth
    out = []
    for brand in sorted(os.listdir(agents_dir)):
        brand_dir = os.path.join(agents_dir, brand)
        if not os.path.isdir(brand_dir):
            continue
        for listing in sorted(os.listdir(brand_dir)):
            listing_dir = os.path.join(brand_dir, listing)
            if not os.path.isdir(listing_dir) or not is_legacy(listing_dir):
                continue
            slug = status.legacy_target(listing_dir, truth)
            if not slug:
                out.append(("refuse", brand, listing, None,
                            "no leads.csv row -- the scrape cannot name it"))
                continue
            dest = os.path.join(listing_dir, slug)
            if os.path.isdir(dest):
                if identical_photos(os.path.join(listing_dir, "photos"),
                                    os.path.join(dest, "photos")):
                    out.append(("duplicate", brand, listing, slug,
                                "byte-identical copy already at " + slug + "/"))
                else:
                    out.append(("conflict", brand, listing, slug,
                                slug + "/ exists and its photos differ"))
                continue
            out.append(("move", brand, listing, slug,
                        f"{len(os.listdir(os.path.join(listing_dir, 'photos')))} photos"))
    return out


# reason: everything a build or a scrape writes at the agent level. out/ and
# clips/ ride along so a listing that was already built keeps its cuts and its
# reusable stitch -- a migration must not cost anyone a re-encode.
MOVABLE = ("photos", "clips", "clips_draft", "out", "work_text", "config.json",
           ".last_build.json", "draft.mp4", "work_silent.mp4",
           "work_branded.mp4", "work_draft.mp4", "contact_sheet.png",
           "outreach_draft.txt")


def normalise_config(cfg_path, root=ROOT):
    """Drop the keys the old scaffold left that the current one does not write.

    reason: save_config() strips empty values before writing (tour.py), so a
    current config.json never carries "music": "" -- an old one does, and it
    SHADOWS the brand default instead of inheriting it. Same for a logo whose
    file went missing in the machine-to-machine transfer: a dead path resolves
    to nothing, and dropping it lets the brand's real mark through.
    """
    cfg = status._json(cfg_path)
    dropped = []
    for key in ("logo", "music", "lower_third", "watermark"):
        val = (cfg.get(key) or "").strip() if isinstance(cfg.get(key), str) else cfg.get(key)
        if key not in cfg:
            continue
        if not val:
            del cfg[key]
            dropped.append(f"{key} (empty)")
        elif not os.path.exists(os.path.join(root, val)):
            del cfg[key]
            dropped.append(f"{key} (file missing: {val})")
    if dropped:
        _rewrite_json(cfg_path, cfg)
    return dropped


def normalise_brand(brand_dir, root=ROOT):
    """Rewrite a bare asset filename in brand.json as a repo-relative path.

    reason: find_gaps.logo_status() resolves the logo with
    os.path.exists(os.path.join(repo_root, logo)), so brand.json holding
    "tcc.png" instead of "global_assets/logos/tcc.png" reads as no logo at all
    -- and the brand was then reported as an acronym near_miss against the very
    file it already pointed at. A phantom gap, not a missing mark.
    """
    path = os.path.join(brand_dir, "brand.json")
    if not os.path.isfile(path):
        return []
    data = status._json(path)
    fixed = []
    for key, sub in (("logo", "logos"), ("music", "music"),
                     ("lower_third", "logos"), ("watermark", "logos")):
        val = (data.get(key) or "").strip()
        if not val or os.sep in val or "/" in val:
            continue
        rel = os.path.join("global_assets", sub, val)
        if os.path.isfile(os.path.join(root, rel)):
            data[key] = rel
            fixed.append(f"{key}: {val} -> {rel}")
    if fixed:
        _rewrite_json(path, data)
    return fixed


def apply_one(kind, brand, listing, slug, agents_dir=AGENTS, root=ROOT, say=print):
    listing_dir = os.path.join(agents_dir, brand, listing)
    if kind == "duplicate":
        for name in MOVABLE:
            p = os.path.join(listing_dir, name)
            if os.path.isdir(p):
                shutil.rmtree(p)
            elif os.path.isfile(p):
                os.remove(p)
        say(f"  removed the duplicate legacy copy under {brand}/{listing}")
        return True
    if kind != "move":
        return False
    dest = os.path.join(listing_dir, slug)
    os.makedirs(dest)
    moved = []
    for name in MOVABLE:
        src = os.path.join(listing_dir, name)
        if os.path.exists(src):
            os.rename(src, os.path.join(dest, name))
            moved.append(name)
    say(f"  {brand}/{listing}/ -> {slug}/  ({', '.join(moved)})")
    dropped = normalise_config(os.path.join(dest, "config.json"), root=root)
    for d in dropped:
        say(f"      dropped {d}")
    return True


def main():
    ap = argparse.ArgumentParser(
        description="Move pre-agent-level listing folders into <agent>/. "
                    "Plans only unless --yes.")
    ap.add_argument("--yes", action="store_true", help="actually move things")
    args = ap.parse_args()

    actions = plan()
    if not actions:
        print("Every listing folder is already at agents/<brand>/<listing>/<agent>/.")
    else:
        print(f"{len(actions)} listing folder(s) in the legacy layout:\n")
        for kind, brand, listing, slug, detail in actions:
            arrow = f" -> {slug}/" if slug else ""
            print(f"  [{kind}] {brand}/{listing}{arrow}\n           {detail}")

    brands = sorted(d for d in os.listdir(AGENTS)
                    if os.path.isdir(os.path.join(AGENTS, d)))
    if args.yes:
        print()
        done = 0
        for kind, brand, listing, slug, _detail in actions:
            done += bool(apply_one(kind, brand, listing, slug))
        for brand in brands:
            for fixed in normalise_brand(os.path.join(AGENTS, brand)):
                print(f"  {brand}/brand.json  {fixed}")
        blocked = [a for a in actions if a[0] in ("refuse", "conflict")]
        print(f"\n{done} migrated, {len(blocked)} left alone.")
        for kind, brand, listing, _slug, detail in blocked:
            print(f"  {brand}/{listing} -- {detail}")
    else:
        print("\nPlan only. Nothing was written. Re-run with --yes to apply.")
        for brand in brands:
            path = os.path.join(AGENTS, brand, "brand.json")
            if not os.path.isfile(path):
                continue
            data = status._json(path)
            for key, sub in (("logo", "logos"), ("music", "music")):
                val = (data.get(key) or "").strip()
                if val and "/" not in val and os.path.isfile(
                        os.path.join(ROOT, "global_assets", sub, val)):
                    print(f"  would also fix {brand}/brand.json {key}: "
                          f"{val} -> global_assets/{sub}/{val}")


if __name__ == "__main__":
    main()
