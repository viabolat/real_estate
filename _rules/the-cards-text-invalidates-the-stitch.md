---
name: the-cards-text-invalidates-the-stitch
area: card
type: non-negotiable
guarded_by:
  - tests/test_auto_flow.py
source: PROGRESS.md@this-change — "how do i rerun a single listing i had the wrong number for contact", 2026-09-02
---

# The card's text invalidates the branded stitch

`render_card()` draws four values from `config.json` — `address`, `agent_name`,
`agent_phone` and `brokerage` — and `build_cards()` bakes that PNG into a clip that
`stitch()` welds into **`work_branded.mp4`**. From that moment the text is pixels.

`--finish-only` reuses `work_branded.mp4` whole (`make_tour.py`, the `reused` branch).
The lower third does not work that way: `render_lower_third()` runs unconditionally on
every pass, before the reuse check, and `work_lower_third.png` is cleanup junk. So the
two surfaces that carry the agent's phone number are redrawn on **different schedules**.

The failure that follows is specific and silent. Correct a wrong `agent_phone`,
rerun, and `rebuild_reason()` — which compared `card` and `card_seconds` but not the
values printed on the card — returns `None`. The build takes the fast path and ships
**one cut showing the corrected number in the lower third and the wrong one on the
outro card.** No error, no warning, nothing in the log. The digits are the whole
deliverable; a listing agent's phone number is what the video exists to hand to a
buyer.

## The rule

`tour.py`'s `CARD_TEXT_KEYS` is the invalidation set, and it must stay equal to what
`render_card()` draws. A change to any of them returns `"the card's text changed"`
from `rebuild_reason()`, which forces `--keep-work` in place of `--finish-only`.

Add a fifth line to the card and the key goes in that tuple in the *same pass* —
`test_the_card_keys_are_exactly_what_render_card_draws` reads `make_tour.py`'s source
and fails otherwise.

The check is gated on `card != "none"`. With no card there is nothing burned in, and
the lower third is redrawn anyway, so the fast path stays correct.

## Why not just always rebuild

A full build re-encodes every photo — ~40 clips on the larger listings. `--finish-only`
exists because that cost is real and the intermediates are kept on purpose
([a-build-deletes-its-own-intermediates](a-build-deletes-its-own-intermediates.md)).
The answer is a correct invalidation set, not the removal of the fast path.

Note the middle branch in `make_tour.py`: with `work_branded.mp4` gone but `clips/`
intact, `--finish-only` restitches the branded cut and calls `build_cards()` again —
a correct rebuild without re-encoding the photos. Deleting `work_branded.mp4` by hand
is therefore also a valid fix; `rebuild_reason()` just makes it automatic.
