---
name: the-dashboard-reads-it-never-writes
area: interface
type: non-negotiable
guarded_by:
  - tests/test_dashboard.py
source: PROGRESS.md@this-change — "a read-only dashboard over the leads and listings, rendered in memory on loopback", 2026-09-02
---

# `dashboard.py` renders derived state and writes nothing — not to disk, not to a CSV, not to the network

The dashboard shows what four other things already know: `status.py`'s roll-up,
`scraper/leads.html`, `needs_attention/`, and the three CSVs under `outreach/`.
It joins them onto one page and plays the sample cut. It invents no state and
records none.

Three failures a new HTTP surface makes newly possible, and how each is refused.

## 1. A viewer that grows a writer

Every mutation stays behind `tour.py`'s prompts. `dashboard.py` contains no
`open(..., "w")` — its only `open()` is `"rb"`, asserted from the AST — no
`shutil`, no `os.remove`, no `save_config()`, no `publish_rung()`.

A "mark contacted" button here would give `outreach/contacted.csv` a second
writer, and
[`the-draft-is-automatic-the-send-is-not`](the-draft-is-automatic-the-send-is-not.md)
already names the exact failure: a send that becomes a flag is a send nobody
decided. A "publish" button would be the second owner of a prompt
[`a-publish-prompt-has-one-owner`](a-publish-prompt-has-one-owner.md) holds to
one. The dashboard's job ends at *showing* that the thing is due; the deciding
happens where it always did.

## 2. A PII artifact on disk

The page carries every agent's name, phone number and email in full. It is
rendered into memory and written to a socket — it is never a file.

That is the `leads.html` lesson made structural. `scraper/leads.html` *is* the
lead list, and it survived unignored for a while because a `#` comment sat on
the same line as its `.gitignore` pattern. An artifact that is never created
cannot be missed by an ignore rule, and `check_pii.py` cannot fail to scan a
file that does not exist.

The bind is `127.0.0.1` and nothing else — the source contains no wildcard host
and no empty-string bind, and both are asserted. `dashboard.py` is also in
`.vercelignore` under
[`a-deploy-is-a-second-publishing-boundary`](a-deploy-is-a-second-publishing-boundary.md):
it holds no PII, so `check_pii.py` would never catch it, and the one host in
this project is exactly where "a file that serves PII" must not land.
`.gitignore` deliberately gains **no** entry — the module is committed source
that produces no artifact, and a pattern for a file that is never written would
be a lie in the ignore file.

## 3. The `sample_`/`tour_` boundary, at a third layer

`resolve_media()` asks `publish.family(name)` and refuses anything that is not
`"sample"` with a **403, before the filesystem is touched at all**. So a `tour_`
request is refused whether or not that cut exists, and the 403-vs-404 difference
never leaks which deliverables are on disk.

This is the third enforcement of the family boundary, after
`publish.publishable()` and `tour.clear_published_cuts()`, and it asks rather
than testing the prefix —
[`only-sample-cuts-publish`](only-sample-cuts-publish.md) makes `family()` the
single owner, and `dashboard.py`'s source contains neither string literal
outside its docstring. A local server is a publishing boundary the moment the
URL is pasted into a chat or the screen is shared, so the refusal sits at the
socket, not at render time.

Paths are confined to `agents/` by `os.path.realpath` against a realpath'd base,
compared with `base + os.sep` — `realpath` catches an encoded `..` *and* a
symlink pointing out of the tree, which `normpath` does not, and the separator
is what stops a sibling `agents_evil/` passing as `agents/`.

## The seven rungs are ordered, never summed

`rung()` returns one integer, testing delivered → follow-up due → contacted →
published → sample built → ready. The order is not cosmetic:
`publish.followup_due()` already *implies* contacted, so rendering the two as
independent filters would put every due listing under both a heading that means
"leave it alone" and one that means "act" — the duplicate-send shape
[`a-follow-up-is-its-own-draft-and-its-own-row`](a-follow-up-is-its-own-draft-and-its-own-row.md)
records. Testing 6 before 5 is what makes the rungs a partition, and
`tests/test_dashboard.py` checks every flag combination.

There is no eighth rung. "Signed off" has no derivable signal, and
[`needs-attention-is-a-view-not-a-move`](needs-attention-is-a-view-not-a-move.md)
forbids inventing one — a `tour_` cut already stands in for
signed-off-and-delivered.
