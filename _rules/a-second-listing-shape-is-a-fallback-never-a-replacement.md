---
name: a-second-listing-shape-is-a-fallback-never-a-replacement
area: photos
type: non-negotiable
guarded_by:
  - tests/test_photo_extraction.py
source: scraper/photos.py
---

# A second listing shape is read as a fallback, never as a replacement

Zillow serves two listing shapes and they do not carry the same photo URLs. A
regular listing (GraphQL `ForSalePriorityQuery`) has both
`-uncropped_scaled_within_<w>_<h>.jpg` and `-cc_ft_<w>.jpg`. A **Showcase**
listing (`ViewShowcasePriorityQuery`) has no uncropped variant at all — only
`cc_ft`, `sc_` and `sr_`. `PHOTO_PATTERN` matched uncropped alone, so every
Showcase listing returned zero URLs, downloaded nothing, and was set aside as a
failed dump while its payload held every photo.

`extract_photo_urls()` runs the uncropped pass first and unchanged, then appends
`cc_ft` **only for hashes that pass never saw**. The two are never merged into
one regex ranked by width: both families exist at width 1536 on a regular
listing, so a widest-wins tie would silently hand back cropped variants in place
of the uncropped originals across the whole existing photo library. Measured on
the nine dumps this was built from, the cc_ft hash set is exactly equal to the
uncropped set on every regular listing and in the same first-appearance order —
so the fallback appends nothing there, and a regular listing's output is
byte-identical to what it was before Showcase support existed. That equality is
what the test pins.

The pattern is **not** widened to `sc_`/`sr_` as insurance against the next
variant. Those over-collect by 8–15 images per Showcase listing — they include
images that are not gallery photos, and a too-broad match ships junk in a
client's gallery while still passing a count check. Narrow match plus a loud
failure is the shape.

The same split renames attribution, and it is read the same way. A regular
listing carries `brokerName`; a Showcase listing carries `brokerageName` and no
`brokerName` at all, so `target_for()` slugged four listings to
`agents/unknown_brokerage/<address>/unassigned_agent` while the payload plainly
said `Coldwell Banker Realty - Newton`. One such tree was written to disk, with
zero photos in it. `lead.broker_name()` reads `brokerName` and falls back to
`brokerageName`, and it is **one** reader for all three callers -- the
`leads.csv` row, `target_for()`'s folder name and the `config.json` brokerage --
because the scrape is the single naming authority
(`the-scrape-names-the-folders`) and three copies of that lookup is three
chances for the CSV and the folder to disagree. The two keys are disjoint across
every dump measured, so a regular listing never reaches the fallback and its
broker slug, which is a folder name, cannot move.

`agentName` has no such second key: on a Showcase payload
`listingAgentAttributionContact` is null and no personal name appears anywhere,
so `UNASSIGNED_AGENT` there is correct and is not a gap to close.

The loud failure is `photo_count_verdict()`. `main()` used to print
`WARNING: photoCount says 33 but found 0 photo URLs` and carry on; that line had
been firing on roughly 40% of dumps for as long as Showcase listings existed and
nobody acted on it, because the run still reported success and still scaffolded
the folder. Finding **zero** URLs in a dump that claims photos is a fact about
the scraper, not about the listing — the regexes no longer describe what Zillow
serves — so it exits 4 before `os.makedirs()` and before `scaffold()`, leaving
nothing behind. Exit 4 and not 2: `run.py` treats everything outside `(0, 3)` as
a failed dump and keeps going either way, but 2 already means "not a listing
dump" and the two must stay tellable apart by hand. Any other disagreement,
fewer **or more** than `photoCount`, stays the warning it has always been.
