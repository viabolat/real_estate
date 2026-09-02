---
name: the-lower-third-does-not-repeat-the-card
area: card
type: non-negotiable
guarded_by: []
source: CLAUDE.md@717ce32 L268-277
---

# The lower third does not say what the card already says

Both are drawn from the same `address` / `agent_name` / `agent_phone`, so a
persistent lower third plus a card prints the operator's details twice in one video.
`finish()` keeps the two from overlapping *in time*; that rule says nothing about
the redundancy across the whole cut. So `tour.py` defaults `brand_persistent` to
`false` whenever a card exists and no hand-made `lower_third.png` does: the lower
third introduces the property, clears, and the card closes. A `lower_third.png`
someone authored says something the card does not, so it is exempt. The default is
stated out loud and still overridable.
