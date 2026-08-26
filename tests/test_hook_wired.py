"""The PII gate runs itself, and an unwired gate does not read as a passing one.

Guards CLAUDE.md: "No lead, phone number or email address is ever committed" and
"A gate that cannot run must fail closed."

reason: check_pii.py never has an interesting answer, which is exactly why an
operator stops typing it. hooks/pre-push makes it automatic. But hooks/ is
committed while core.hooksPath is per-clone config, so a fresh clone ships the
file with the gate OFF -- present and silent, which is this project's own stated
failure shape: "nothing to scan and nothing found read identically and mean
opposite things." These tests guard the hook's content; tour.py's home screen
guards the wiring at runtime, because a test cannot check the operator's clone.
"""
import os
import re
import stat
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers

HOOK = os.path.join(helpers.REPO, "hooks", "pre-push")


class TestHookWired(unittest.TestCase):

    def setUp(self):
        self.assertTrue(os.path.isfile(HOOK), "hooks/pre-push is missing.")
        with open(HOOK) as f:
            self.text = f.read()
        # Everything outside a comment -- a bypass in prose is documentation.
        self.code = "\n".join(l for l in self.text.splitlines()
                              if not l.lstrip().startswith("#"))

    def test_is_executable(self):
        mode = os.stat(HOOK).st_mode
        self.assertTrue(mode & stat.S_IXUSR,
                        "hooks/pre-push is not executable, so git skips it "
                        "silently -- the gate would be present and off.")

    def test_has_a_shebang(self):
        self.assertTrue(self.text.startswith("#!"),
                        "hooks/pre-push needs a shebang to run at all.")

    def test_runs_check_pii(self):
        self.assertIn("check_pii.py", self.code,
                      "hooks/pre-push does not invoke check_pii.py.")

    def test_no_bypass(self):
        """The hook must not defuse itself. --no-verify is git's escape hatch."""
        for pattern, why in (
                # reason: scoped to an actual git invocation. A bare
                # "--no-verify" also matches the hook telling an operator what
                # git's own escape hatch is called, which is documentation, not
                # a bypass -- and the first version of this test failed on
                # exactly that.
                (r"git\b[^\n]*--no-verify",
                 "a hook that passes --no-verify to git"),
                (r"\|\|\s*true", "|| true swallows the gate's exit code"),
                (r"\|\|\s*exit\s+0", "|| exit 0 swallows the gate's exit code"),
                (r"exit\s+0\s*$", "an unconditional exit 0 at the end"),
                (r"^\s*#!/bin/sh\s+-e?x?\s*$", "")):
            if not why:
                continue
            self.assertIsNone(
                re.search(pattern, self.code, re.M),
                f"hooks/pre-push contains a bypass: {why}. The gate has to be "
                "the only thing between a lead and the remote.")

    def test_fails_closed_without_python(self):
        """No interpreter is 'cannot scan', which must not print as 'clean'."""
        self.assertIn("command -v python3", self.code)
        self.assertRegex(self.code, r"exit\s+1",
                         "a missing python3 must exit non-zero, not warn.")

    def test_tour_checks_the_wiring_at_runtime(self):
        """A committed hook proves nothing about the clone that has it."""
        with open(os.path.join(helpers.REPO, "tour.py")) as f:
            tour = f.read()
        self.assertIn("core.hooksPath", tour,
                      "tour.py must detect an unwired hook and say so -- the "
                      "file being committed does not mean it is enabled here.")


if __name__ == "__main__":
    unittest.main()
