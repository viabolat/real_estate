# WALKTHROUGH.md — Start to Finish

Do these in order. Steps 1–3 are done once. Steps 4–11 repeat for every listing.

This is the short version. `STEPS.md` Part 1 is the same ground with the reasoning,
the variations and the failure modes; it is the authority when the two disagree.

---

## One-time setup

**Step 1.** Arm the PII gate:

```bash
git config core.hooksPath hooks
```

**Step 2.** Create `.env` from `.env.example` and fill in `SUPABASE_URL` and
`SUPABASE_SERVICE_KEY`.

**Step 3.** Deploy the preview rewrite:

```bash
npx vercel --prod
```

---

## Per listing

**Step 4.** Open the Zillow listing page, select all, copy, and paste it into a new
file in `scraper/dumps/`. One listing per file.

> Already have a folder of photos that never came from a scrape? Drop it in as
> `agents/<brand>/<listing>/<agent>/photos/` and skip to **Step 8** — `tour.py`
> will offer it and ask for the address, agent and phone itself. The roll-up marks
> it *unverifiable* and nothing renames it: the scrape is the only thing that names
> folders, and it cannot name a listing it has no row for.

**Step 5.** Start the tool:

```bash
python3 tour.py
```

**Step 6.** Choose **2. Import new dumps**. Wait for it to finish.

**Step 7.** Open `agents/<brand>/brand.json` and fill in `logo` and `music`.

**Step 8.** Run `python3 tour.py` again and choose **1. Build a tour**.

**Step 9.** Pick the brand, then the listing, then the agent. Answer the questions
it asks.

**Step 10.** Work through the three rungs, confirming each one:

1. Contact sheet — check the photo order.
2. Draft — watch `draft.mp4`.
3. Build — take the default, **Sample cuts**. The three watermarked `sample_`
   cuts land in `out/`. The `tour_` deliverables are run 2, after sign-off — this
   is a cold email, and building them now spends half a six-minute encode on a
   client who may never reply.

**Step 11.** At the publish prompt, answer **yes**. Review the file list and the
URLs, and confirm.

**Step 12.** Open `agents/<brand>/<listing>/<agent>/outreach_draft.txt`, read it,
and paste it into your mail client. The link is already in it. Send.

`python3 status.py` now reads `sample published -- awaiting sign-off` for this
listing. If the client never replies, nothing further is spent on it.

---

## After sign-off

**Step 13.** Run `python3 tour.py` again and pick the same listing. Rung 3 now
asks whether the client has signed off; answer **yes** and it builds the three
`tour_` deliverables — about a minute, not six, because it reuses the stitch run 1
left behind. The `sample_` cuts stay where they are.

**Step 14.** Send the client `out/<agent>_tour_branded.mp4`,
`out/<agent>_tour_unbranded.mp4` and `out/<agent>_tour_vertical.mp4` by hand.
Never a `sample_` file.

---

## Before pushing code

**Step 15.** Run the checks:

```bash
python3 check_pii.py
python3 -m unittest discover -s tests -t .
```

**Step 16.** Commit and push.

---

## Command reference

Everything above, plus the commands you'll reach for outside the happy path.
`STEPS.md` has the full reasoning and every flag; this is just the lookup table.

| Command | Does |
|---|---|
| `python3 tour.py` | Home screen: the roll-up, then build / import / brand settings / sweep. |
| `python3 tour.py --auto` | Every pending dump and unbuilt listing, hands-off, back to back. |
| `python3 tour.py --auto <brand>/<listing>` | Just one listing — also how you resume after a halt. |
| `python3 tour.py --auto <brand>/<listing> --ignore-floorplan-check` | Force past a floor-plan false positive, once. |
| `python3 tour.py --auto <brand>/<listing> --ignore-missing-logo-check` | Force the type-only card through — brokerage genuinely has no mark. |
| `python3 tour.py --auto <brand>/<listing> --ignore-missing-phone-check` | Force through with no phone shown — number is genuinely unavailable. |
| `python3 tour.py --build` | Jump straight to Build a tour, skipping the home screen. |
| `python3 tour.py --sweep-published-samples` | Dry run: what published `sample_` cuts it would clear from `out/`. |
| `python3 tour.py --sweep-published-samples --yes` | Actually clears them. |
| `python3 status.py` | One line per listing: photo count, smallest photo, next action. |
| `python3 status.py --long` | Same, plus what each listing inherits from its brand. |
| `python3 scraper/run.py` | Import every `*.txt` in `scraper/dumps/`. |
| `python3 scraper/run.py one.txt` | Import just that one dump. |
| `python3 scraper/find_gaps.py` | Report missing brand logos / blank `agent_email`s. Reports only — never fetches or writes. |
| `python3 scraper/find_gaps.py --json` | Same data, machine-readable — what a live Claude + Chrome session consumes. |
| `python3 scraper/find_gaps.py --open` | Open up to 5 search tabs for the gaps found; `--open-all` lifts the cap. |
| `python3 publish.py --dry-run` | What would go public and the exact URLs, without uploading. |
| `python3 publish.py` | The same, then asks, then uploads. |
| `python3 check_pii.py` | No lead, phone or email is about to be committed. Exit 0, or do not push. |
| `python3 -m unittest discover -s tests -t .` | The full guard suite, ~0.6s, no ffmpeg. |
