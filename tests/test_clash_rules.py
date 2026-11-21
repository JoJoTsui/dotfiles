"""The desktop Clash Verge fallback rule.

The artifact under test is the profile's Script enhancement, which Clash Verge
evaluates as JavaScript, so the regression itself is a Node test
(clash/tests/script-enhancement.test.mjs). This wrapper runs it from the
Python suite so the repository's standard check covers the desktop routing
policy as well.
"""
from pathlib import Path
import os
import shutil
import subprocess
import unittest

SOURCE = Path(__file__).resolve().parents[1]
SCRIPT = SOURCE / "clash" / "script-enhancement.js"
REGRESSION = SOURCE / "clash" / "tests" / "script-enhancement.test.mjs"


def node_binary():
    """The Node runtime the regression needs, if the device has one."""
    return os.environ.get("DOTFILES_TEST_NODE") or shutil.which("node")


class ClashFallbackTest(unittest.TestCase):
    """The owned catch-all is the single final rule of the effective rules."""

    def test_the_script_enhancement_is_owned_by_the_repository(self):
        self.assertTrue(SCRIPT.is_file(), f"missing {SCRIPT.relative_to(SOURCE)}")
        self.assertTrue(
            REGRESSION.is_file(), f"missing {REGRESSION.relative_to(SOURCE)}"
        )

    def test_the_node_regression_passes(self):
        node = node_binary()
        if not node:
            self.skipTest("node runs the Clash Verge script regression")

        result = subprocess.run(
            [node, "--test", str(REGRESSION)],
            capture_output=True,
            text=True,
            cwd=SOURCE,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
