# WALKTHROUGH.md — Start to Finish

Do these in order. Steps 1–3 are done once. Steps 4–11 repeat for every listing.

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

**Step 5.** Start the tool:

```bash
python3 tour.py
```

**Step 6.** Choose **2. Import new dumps**. Wait for it to finish.

**Step 7.** Open `agents/<brand>/brand.json` and fill in `logo` and `music`.

**Step 8.** Run `python3 tour.py` again and choose **1. Build a tour**.

**Step 9.** Pick the brand, then the listing. Answer the questions it asks.

**Step 10.** Work through the three rungs, confirming each one:

1. Contact sheet — check the photo order.
2. Draft — watch `draft.mp4`.
3. Delivery — the six cuts land in `out/`.

**Step 11.** At the publish prompt, answer **yes**. Review the file list and the
URLs, and confirm.

**Step 12.** Open `outreach/drafts/<brand>__<listing>.txt`, read it, and paste it
into your mail client. The link is already in it. Send.

---

## After sign-off

**Step 13.** Send the client `out/<agent>_tour_branded.mp4`,
`out/<agent>_tour_unbranded.mp4` and `out/<agent>_tour_vertical.mp4` by hand.

---

## Before pushing code

**Step 14.** Run the checks:

```bash
python3 check_pii.py
python3 -m unittest discover -s tests -t .
```

**Step 15.** Commit and push.
