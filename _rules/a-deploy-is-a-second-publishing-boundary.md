---
name: a-deploy-is-a-second-publishing-boundary
area: pii
type: non-negotiable
guarded_by: []
source: CLAUDE.md@717ce32 L344-355
---

# A deploy is a second publishing boundary, and `.vercelignore` is its only gate

`check_pii.py` enumerates what *git* would publish; it has no view of what the
Vercel CLI uploads. And when a `.vercelignore` exists it takes precedence over
`.gitignore`, so adding one turned off the implicit protection that had been keeping
`.env`, `scraper/leads.csv` and the raw dumps out of a deploy — gitignored is not
deploy-ignored. `.env`, `.env.*`, `scraper/`, `outreach/`, `agents.txt` and
`property_email.txt` are listed there explicitly. Anything new holding a key or a
lead is added to **both** files, or it ships to a third party on the next `npx
vercel --prod`. Vercel hosts no video: the deployment is a rewrite rule and nothing
else, which is why `out/`, `agents/`, `clips/` and `*.mp4` are excluded too.
