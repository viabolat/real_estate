---
name: the-pii-gate-runs-itself
area: pii
type: non-negotiable
guarded_by:
  - tests/test_hook_wired.py
source: CLAUDE.md@717ce32 L435-449
---

# The PII gate runs itself, and an unwired gate is reported, never assumed

`check_pii.py` never has an interesting answer, which is exactly why an operator
stops running it. `hooks/pre-push` makes it automatic. But `hooks/` is committed
while `core.hooksPath` is **per-clone config**, so a fresh clone ships the file with
the gate *off* — present and silent, which on screen is indistinguishable from the
gate passing. That is this repo's own stated failure shape. So `tour.py`'s home
screen checks `core.hooksPath` and the hook's executable bit and prints the one-line
fix when either is wrong, **and** runs `check_pii.py`'s scan itself regardless: the
hook only fires for pushes through the git CLI, and libgit2-based clients — most IDE
git integrations — do not run git hooks at all. Do not add a bypass to the hook;
`git push --no-verify` is git's own escape hatch and is visible in the command
someone typed, where a bypass baked into the hook would not be.
`tests/test_hook_wired.py` guards both.
