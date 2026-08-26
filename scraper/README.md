# Zillow lead + photo extraction

Two standalone scripts that both read the same input (`paste.txt`) and pull
different things out of it. Neither needs a browser, login, or API key —
Zillow's listing page already embeds all of this data in the page itself
(a `__NEXT_DATA__` JSON blob), it just comes through with the quotes
backslash-escaped when you copy/paste the page as text. Both scripts parse
around that escaping.

## Workflow

1. Open a Zillow listing page, select all, copy, and paste the full page
   text into `paste.txt` (overwriting whatever was there before).
2. Run `run.py paste.txt` to record the listing/agent info *and*
   save its photos in one command. The photos land in
   `agents/<broker_name>/<address>/photos/`, ready for `make_tour.py`.
3. Repeat from step 1 for the next listing.

**One listing per run.** `paste.txt` should hold exactly one dump at a
time — the extraction is regex-based and only looks for the *first* match
of each field, so pasting two listings into the same file would silently
mix data from both (e.g. listing #1's address with photos from both
listings). Overwrite `paste.txt` fully before each run.

## `run.py`

Convenience wrapper — runs `lead.py` then `photos.py` against
the same dump as two subprocesses. No shared code, no coupling; it's just a
shortcut for the two commands so you don't have to run them separately.

Takes one dump, or a whole folder of them:

```
python3 run.py                 # every *.txt in dumps/  (the default)
python3 run.py dumps/          # same thing, said explicitly
python3 run.py paste.txt       # just the one
```

- **One listing per file, always.** The parsers are first-match regexes over
  the whole text, so two dumps concatenated into one file read the first
  listing's agent name and phone onto the second listing's photos — a wrong
  phone number on a finished video, with nothing raised. Separate files make
  that impossible rather than merely discouraged.
- **Re-running a folder is safe and cheap.** Duplicate lead rows are skipped,
  photos already on disk are skipped, and neither `brand.json` nor
  `config.json` is ever overwritten. So there is no "processed" folder to move
  dumps into and no state to drift out of sync with the folder — leave them
  where they are and run it again.
- **One bad dump does not stop the batch.** Failures are named in a summary at
  the end and the run exits non-zero, so a batch that half-worked cannot look
  like a clean one.
- `dumps/` is **gitignored** — raw dumps carry the agent's name, phone, email
  and the property address. Only `dumps/.gitkeep` is tracked.
- For the roll-up across every listing afterwards, run `python3 status.py` from
  the project root.

Needs the `--full` or `--out-dir` flags? Run `lead.py` /
`photos.py` directly instead — the wrapper doesn't expose them.

## `lead.py`

Extracts the property summary and listing agent contact info.

```
python3 lead.py paste.txt
python3 lead.py paste.txt --full     # also writes beautified.txt
```

- Prints a report to the terminal: address/price/beds/baths/status, then
  **Agent name / Phone / Brokerage / MLS ID / Email**, then who actually
  receives the lead if the "Contact Agent" button is clicked (this can
  differ from the listing agent when a paid Premier Agent ad intercepts
  it).
- Appends one row to `leads.csv` (creates it with a header if missing) —
  unless it's a duplicate of a row already there, in which case it's
  skipped and printed as such. A row counts as a duplicate only when
  **both** the `zpid` (Zillow's property ID) and the listing agent's phone
  number match an existing row. Address text isn't used for this (too
  fragile — formatting varies), and `zpid` alone isn't either: the same
  property can get relisted later under a different agent/brokerage, and
  that's a genuinely new lead worth keeping, not a duplicate.
- Regenerates `leads.html` from the full contents of `leads.csv` every run
  — always reflects every listing recorded so far, not just the latest one.
- `--full` additionally writes `beautified.txt`: the raw dump with a
  newline inserted before every recognized field, for manually eyeballing
  a listing's full data when something looks off.
- **Refuses a dump with no `zpid`** and writes nothing. An empty file, a
  half-copied paste or the wrong browser tab parses into a row of blanks,
  and because duplicate detection needs a `zpid` it cannot recognise that
  row as a duplicate either — so every rerun appends another. It used to
  exit 0, which meant a batch run reported it as processed cleanly while
  poisoning `leads.csv`. `photos.py` refuses the same dump for the
  same reason: with no photo URLs and no address it would create
  `agents/unknown_brokerage/listing/` complete with a `brand.json`, a
  folder the naming authority can never match.

## Nothing in here gets committed

`leads.csv`, `leads.html`, `paste.txt`, `beautified.txt`, `dumps/` and
`photos/` are all gitignored by repo-level rules — every one of them holds an
agent's name, phone number, email, or all three. Run `python3 check_pii.py`
from the project root before pushing; it scans everything git would publish
against the real values in `leads.csv` and exits non-zero on a hit.

Note that `leads.csv` therefore does **not** travel with a clone, and it is the
naming authority for `agents/<broker>/<address>`. See `PROGRESS.md` §1.

## `photos.py`

Downloads every photo for the listing at full resolution.

```
python3 photos.py paste.txt
python3 photos.py paste.txt --out-dir some/other/folder
```

- Reads the dump's `photoCount` field and every `uncropped_scaled_within_*`
  photo URL, dedupes by photo hash (keeping the largest resolution variant
  found), and downloads them in gallery order.
- Saves to `agents/<broker_name>/<address>/photos/01.jpg`, `02.jpg`, ... by
  default — a sibling of `scraper/`, not a subfolder of it. Both folder names
  are slugified from the same dump fields `lead.py` writes to the
  `broker_name` and `address` columns, so the folder and the CSV row always
  agree. That is exactly the working directory `make_tour.py` expects, so a
  scrape drops in ready to build with no moving or renaming.
- Apostrophes are dropped rather than turned into separators, so
  `Gibson Sotheby's International Realty` slugs to
  `gibson_sothebys_international_realty`. A missing brokerage falls back to
  `unknown_brokerage`. `make_tour._slug`, which names the output files inside
  that folder, applies the same apostrophe rule — it has to, or one agent's name
  gets two spellings. It is a separate function because `make_tour.py` runs from
  a listing folder with no `scraper/` on the path, and it returns `""` rather
  than a fallback so a blank `agent_name` leaves the bare `tour_`/`sample_`
  names. `tests/test_naming.py` fails if the two drift apart.
- **The scrape is the naming authority.** Do not rename a listing folder by
  hand, and do not add an alias table mapping a scraped brokerage onto a
  shorter name you prefer — that is a second authority, and the two drift.
  `../status.py` re-checks every folder against `leads.csv` on each run,
  matching on agent phone (address formatting varies between the config and
  the CSV; a phone number does not) and printing the `mv` for any that has
  drifted. The accepted cost: *Coldwell Banker Realty - Boston* and
  *- Waltham* are two brand folders with two logos to set.
- Scaffolds the listing so it is buildable with no typing:
  - `agents/<broker>/brand.json` — created once per brokerage, with `logo`
    and `music` **blank** for you to fill in. Holds only what is genuinely
    brokerage-wide (pacing, card, brokerage name). It deliberately does
    **not** hold `agent_name`/`agent_phone`: `leads.csv` already has two
    agents under *Coldwell Banker Realty - Boston* and two under *Gibson
    Sotheby's*, and folders are slugged from `broker_name`, so a
    brand-level agent would print one agent's phone number on another
    agent's video.
  - `agents/<broker>/<address>/config.json` — the address, agent name,
    agent phone and brokerage straight from the dump, plus the brand's
    values inherited at creation, plus the correct `watermark` path.
    The `address` written here is the **display** line the card and lower
    third print — `streetAddress`, city, state and zip composed from the
    dump, e.g. `2 Commonwealth Ave, Boston, MA 02116`. The bare
    `streetAddress` names the folder (it has to match the CSV's `address`
    column); on a card it reads like an unfinished draft.
  - Neither file is ever overwritten. Re-running says `already exists,
    left alone`.
- Pins `watermark` to `global_assets/logos/viabolat.png`. The built-in
  default resolves against the listing folder then beside `make_tour.py`,
  neither of which is where this repo keeps it — and when it fails to
  resolve the build prints one line and silently drops the mark, shipping
  an **unwatermarked** `sample_` cut.
- Reports the real resolution of what it just downloaded, against
  `make_tour.py`'s own gates. The variant in a photo URL is a ceiling, not
  a promise: `uncropped_scaled_within_1536_1152` returns the original
  untouched when the original is smaller, and one listing here came back at
  346px from a URL advertising 1536. Better to learn that now than 20
  minutes into a build.
- Prints a `WARNING` if the number of photo URLs found doesn't match the
  dump's own `photoCount` (signals a possibly truncated paste).
- Re-running on the same listing is safe/idempotent — files that already
  exist on disk aren't re-downloaded.

## Files & folders

| Path | What it is |
|---|---|
| `paste.txt` | Input — the raw text dump of one Zillow listing page. Overwrite before each run. |
| `run.py` | Wrapper — runs `lead.py` then `photos.py` in one command. |
| `lead.py` | Extracts property + agent info from `paste.txt`. |
| `photos.py` | Downloads all listing photos from `paste.txt`. |
| `leads.csv` | Output — one row per listing ever processed by `lead.py`. Canonical data store. |
| `leads.html` | Output — `leads.csv` rendered as a browser-viewable table. Regenerated every run; open it directly in a browser. |
| `../agents/<broker>/<address>/photos/` | Output — numbered full-resolution `.jpg`s in gallery order, written into the build tree rather than under `scraper/`. |
| `../agents/<broker>/brand.json` | Output — per-brokerage stub, created once. `logo` and `music` blank for you to fill in. Never overwritten. |
| `../agents/<broker>/<address>/config.json` | Output — per-listing build settings from the dump. Never overwritten. |
| `beautified.txt` | Output (only with `--full`) — the last dump, reformatted for manual reading. |
| `MISC/` | Everything unrelated to this workflow (video-package pitch notes, client email templates, background music for video editing). Kept for reference, not read by either script. |
