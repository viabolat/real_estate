---
name: a-fetched-logo-names-the-brokerage-or-it-is-not-fetched
area: scrape
type: non-negotiable
guarded_by:
  - tests/test_fill_gaps.py
source: 2026-09-02 serhant fetch
---

# A fetched logo names the brokerage, or it is not fetched

`fill_gaps.py --fetch` is the only lane that reaches the network, and the mark it
writes goes on a client's video under a brokerage's name. A page is full of other
people's marks. `serhant.com` alone carries the **Netflix** wordmark (for the show
the brokerage appears in), two MLS marks and an RLS mark. Every one of them
downloads cleanly, is a genuine PNG, and clears a size gate.

The first version took the first match of a fixed pattern list and wrote it. It
wrote, in order across three attempts:

1. `favicon-16x16.png` — 16×16, because `rel="icon"` led the list. A 16px file
   scaled into `make_tour.py`'s 360×200 box is an upscale smear.
2. The **Netflix** wordmark, 384×120, from `og:image` — a real PNG, a plausible
   size, another company's registered trademark.
3. The Netflix wordmark again, from `<img class="netflix-logo" src=…>`, because
   the `<img>` pattern required the logo-ish attribute to appear *before* `src=`
   in the tag — and serhant's own `<img src=… alt="Logo" class="heading-logo">`
   puts `src` first, so it never matched at all.

No byte check and no dimension check catches any of that. Three gates that all
answer "is this a usable image" and none that answers "is this *their* image".

## What the check has to be

**Ownership, asked directly.** A candidate `<img>` earns its place two ways and no
other:

- **vouched** — an attribute names the brokerage: a distinctive word out of
  `broker_name` appears in `class`, `id`, `alt`, `title` or the `src` URL.
- **generic** — a logo-ish attribute reduces to nothing but positional words. A
  site does not qualify its own identity: it writes `alt="Logo"`,
  `class="heading-logo"`, `class="logo__img dark"`. It qualifies everyone else's
  — `netflix-logo`, `property-card__mls-logo`, `rls_logo_vertical2020`. Strip the
  positional adjectives (`header`, `site`, `nav`, `main`, `dark`, `img`, …); if a
  word survives, that word is the owner and the owner is not this brokerage.

Everything else is skipped with a reason, for a session to handle. `og:image` is
not a candidate at all — a share card is chosen to sell the page, not to identify
the company, and there is no test that separates the two.

Attribute order carries no meaning: parse the tag's attributes into a dict rather
than matching on their sequence.

A mark still has to be a real PNG (`png_size()` reads the IHDR — no image
dependency in this repo) and at least `MIN_LOGO_PX` on its long side. Those gates
stay; they are just not the interesting ones.

`fetch_logo()` falls through every candidate the page offers before giving up, so
one wrong or oversmall answer no longer ends the attempt. The reason reported is
the last failure, not the first.

This is the same refusal `find_gaps.py` already makes with `near_miss`: a
plausible-but-wrong brokerage mark must never be adopted automatically. See
[`fill-gaps-acts-only-on-what-find-gaps-named`](fill-gaps-acts-only-on-what-find-gaps-named.md).
