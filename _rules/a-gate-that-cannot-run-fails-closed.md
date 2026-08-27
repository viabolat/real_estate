---
name: a-gate-that-cannot-run-fails-closed
area: pii
type: non-negotiable
guarded_by:
  - tests/test_guards.py
  - tests/test_hook_wired.py
source: CLAUDE.md@717ce32 L603-610
---

# A gate that cannot run must fail closed

`check_pii.py` enumerates files by shelling out to git, and `git()` swallows a
failed subprocess and returns `[]`. Outside a repository — git not installed, or the
tree copied without its `.git` — it therefore scanned *nothing* and printed `Safe to
push`, exit 0, over a folder that may hold the whole lead list. "Nothing to scan"
and "nothing found" are indistinguishable in the output and opposite in meaning.
`require_git()` and the empty-file-list check both exit 2 rather than let that read
as clean. Do not add a flag that downgrades either to a warning.
