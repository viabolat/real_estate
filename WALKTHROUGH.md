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
