"""PTY-driver regressions independent of installed shells or real history."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

import test_history_behavior as history_behavior


@unittest.skipUnless(os.name == "posix", "the history terminal driver requires a POSIX PTY")
class HistoryTerminalTests(unittest.TestCase):
    def test_services_a_cursor_query_after_the_initial_drain_window(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-history-terminal-") as temporary:
            root = Path(temporary)
            child = root / "delayed-cursor-query.py"
            child.write_text(
                "import os, select, sys, time, tty\n"
                "tty.setraw(0)\n"
                # With no test commands, the helper's startup/exit drains end
                # after 1 second. Send a real line-editor cursor query later.
                "time.sleep(1.3)\n"
                "os.write(1, b'\\x1b[6n')\n"
                "received = bytearray()\n"
                "deadline = time.monotonic() + 15\n"
                "while time.monotonic() < deadline:\n"
                "    ready, _, _ = select.select([0], [], [], 0.1)\n"
                "    if ready:\n"
                "        received.extend(os.read(0, 4096))\n"
                "        if b'\\x1b[1;1R' in received:\n"
                "            os.write(1, b'cursor-response-received\\n')\n"
                "            sys.exit(0)\n"
                "sys.exit(2)\n")
            # Call the actual helper without its installation/configuration
            # setUp: this child has no Atuin, tool prefix or account state.
            driver = history_behavior.HistoryBehaviorTests()
            driver.home = root
            driver.env = {"HOME": str(root), "PATH": "/usr/bin:/bin", "TERM": "xterm-256color"}
            output = driver.terminal("controlled-child", [],
                                     arguments=[sys.executable, str(child)])
            self.assertIn("cursor-response-received", output)


if __name__ == "__main__":
    unittest.main()
