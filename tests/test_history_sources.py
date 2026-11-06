"""Default history discovery without reading real histories or running Atuin."""
from contextlib import redirect_stdout
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("history_sources", SOURCE / "dot_local/lib/dotfiles/history.py")
HISTORY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HISTORY)


@unittest.skipUnless(os.name == "posix", "Darwin/Linux discovery; Windows retains its native adapter")
class HistorySourceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dotfiles-history-sources-")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name) / "device"
        self.canonical = self.home / ".config/nushell"
        self.native = self.home / "Library/Application Support/nushell"
        self.canonical.mkdir(parents=True)
        self.native.mkdir(parents=True)
        self.environment = patch.dict(os.environ, HOME=str(self.home), XDG_CONFIG_HOME=str(self.home / ".config"))
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def listing(self, platform):
        output = io.StringIO()
        with patch.object(HISTORY.sys, "platform", platform), redirect_stdout(output):
            HISTORY.import_history(None, None, None)
        return output.getvalue()

    def test_macos_lists_both_existing_nu_locations_without_opening_them(self):
        for directory in (self.canonical, self.native):
            for filename in ("history.txt", "history.sqlite3"):
                (directory / filename).write_bytes(b"synthetic history must not be opened\n")
        with patch.object(Path, "open", side_effect=AssertionError("listing opened a history")):
            output = self.listing("darwin")
        for directory in (self.canonical, self.native):
            for kind, filename in (("nu", "history.txt"), ("nu-db", "history.sqlite3")):
                self.assertIn(f"{kind}: available ({directory / filename})", output)
        self.assertIn("Nothing imported", output)

    def test_macos_ambiguous_nu_defaults_require_file_before_running_atuin(self):
        for kind, filename in (("nu", "history.txt"), ("nu-db", "history.sqlite3")):
            with self.subTest(format=kind):
                for directory in (self.canonical, self.native):
                    (directory / filename).write_bytes(b"synthetic ambiguous source\n")
                with patch.object(HISTORY.sys, "platform", "darwin"), \
                        patch.object(HISTORY, "configured_path", return_value=self.home / "data"), \
                        patch.object(HISTORY, "run_atuin", return_value="atuin unverified") as run:
                    with self.assertRaisesRegex(HISTORY.HistoryError, "multiple.*select --file PATH"):
                        HISTORY.import_history(None, kind, None)
                    run.assert_not_called()
                self.assertFalse((self.home / "data/dotfiles-imports" / f"{kind}.json").exists())
                self.assertFalse((self.home / "data/dotfiles-imports" / f"{kind}.lock").exists())
                for directory in (self.canonical, self.native):
                    self.assertEqual((directory / filename).read_bytes(), b"synthetic ambiguous source\n")

    def test_macos_overlapping_config_roots_list_each_candidate_once(self):
        with patch.dict(os.environ, XDG_CONFIG_HOME=str(self.native.parent)):
            output = self.listing("darwin")
        for filename in ("history.txt", "history.sqlite3"):
            self.assertEqual(output.count(str(self.native / filename)), 1)

    def test_linux_keeps_only_configured_xdg_nu_defaults(self):
        custom_config = self.home / "custom-config"
        with patch.dict(os.environ, XDG_CONFIG_HOME=str(custom_config)):
            output = self.listing("linux")
        self.assertIn(str(custom_config / "nushell/history.txt"), output)
        self.assertIn(str(custom_config / "nushell/history.sqlite3"), output)
        self.assertNotIn(str(self.canonical), output)
        self.assertNotIn(str(self.native), output)


if __name__ == "__main__":
    unittest.main()
