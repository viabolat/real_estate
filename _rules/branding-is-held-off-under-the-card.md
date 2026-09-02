---
name: branding-is-held-off-under-the-card
area: card
type: non-negotiable
guarded_by:
  - tests/test_finish_window.py
source: CLAUDE.md@717ce32 L260-267
---

# Branding is held off wherever the card is on screen, and the watermark is not

The card already carries the address, the agent and the phone at full size in the
middle of the frame; the lower third and the logo over the top of it print the same
lines twice. `finish()` takes a `cards=(intro, outro)` span and gates the branding
layers to the photo body. The proofing watermark is deliberately exempt — an
unwatermarked outro card is exactly the frame an unapproved sample would be
screenshot from.
