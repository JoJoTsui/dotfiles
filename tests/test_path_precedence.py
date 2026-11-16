"""The managed PATH order follows the platform.

macOS resolves the managed launcher directory before the Bun directory, so a
launcher for an adopted Homebrew agent wins in an interactive shell. Linux,
WSL, and native Windows keep the Bun directory first, because Bun is the
agent provider there. Both shell adapters render the same model, and the
rendered files are the evidence.
"""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import tomllib
import unittest

SOURCE = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "posix", "shell execution; native Windows has its own adapter")
class PathPrecedenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-path-order-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        if not self.chezmoi:
            self.skipTest("rendering the shared settings requires chezmoi")

    def deploy(self, platform):
        """Render the shared settings of one platform into a disposable home."""
        home = self.root / platform
        arguments = ["bash", str(SOURCE / "bootstrap.sh"), "--source", str(SOURCE),
                     "--home", str(home), "--platform", platform, "--role", "workstation",
                     "--apply-only"]
        if platform == "windows":
            # The Windows matrix has no ARM build.
            arguments += ["--arch", "x86_64"]
        result = subprocess.run(arguments, cwd=SOURCE, capture_output=True, text=True, timeout=120,
                                env={"HOME": str(home), "PATH": "/usr/bin:/bin", "TERM": "xterm-256color",
                                     "DOTFILES_SKILLS_DIR": str(SOURCE / "tests/fixtures/skill-library"),
                                     "DOTFILES_CHEZMOI_BIN": self.chezmoi})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return home

    def posix_path(self, home):
        """The PATH a POSIX shell resolves after sourcing the rendered settings."""
        result = subprocess.run(["/bin/sh", "-c", '. "$HOME/.env_core"; printf "%s\\n" "$PATH"'],
                                env={"HOME": str(home), "PATH": "/usr/bin:/bin"}, cwd=home,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip().split(":")

    def nu_path(self, home):
        """The PATH the Nu adapter resolves."""
        nu = shutil.which("nu")
        if not nu:
            self.skipTest("the Nu adapter needs a Nushell binary")
        result = subprocess.run([nu, "--config", str(home / ".config/nushell/config.nu"),
                                 "--env-config", str(home / ".config/nushell/env.nu"),
                                 "-c", "print ($env.PATH | to json --raw)"],
                                env={"HOME": str(home), "PATH": "/usr/bin:/bin"}, cwd=home,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def write_command(self, path, output):
        """A fake command the device provides."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\nprintf '%s\\n' " + shlex.quote(output) + "\n")
        path.chmod(0o755)

    def assert_precedes(self, entries, first, second):
        """The first managed directory wins over the second one."""
        self.assertIn(first, entries)
        self.assertIn(second, entries)
        self.assertLess(entries.index(first), entries.index(second))

    def test_macos_resolves_the_managed_launcher_directory_before_the_bun_directory(self):
        home = self.deploy("macos")
        launcher = str(home / ".local/bin")
        bun = str(home / ".bun/bin")
        self.assert_precedes(self.posix_path(home), launcher, bun)
        self.assert_precedes(self.nu_path(home), launcher, bun)

    def test_the_other_platforms_keep_the_bun_directory_first(self):
        for platform in ("linux", "wsl", "windows"):
            with self.subTest(platform=platform):
                home = self.deploy(platform)
                launcher = str(home / ".local/bin")
                bun = str(home / ".bun/bin")
                self.assert_precedes(self.posix_path(home), bun, launcher)
                self.assert_precedes(self.nu_path(home), bun, launcher)

    def test_the_managed_directories_own_the_front_of_the_path(self):
        for platform in ("macos", "linux"):
            with self.subTest(platform=platform):
                home = self.deploy(platform)
                for entries in (self.posix_path(home), self.nu_path(home)):
                    self.assertLess(entries.index(str(home / ".bun/bin")), entries.index("/usr/bin"))
                    self.assertLess(entries.index(str(home / ".local/bin")), entries.index("/usr/bin"))

    def test_every_platform_orders_the_same_managed_directories(self):
        """The model declares the directories once and orders them per platform."""
        with (SOURCE / ".chezmoidata.toml").open("rb") as handle:
            shared = tomllib.load(handle)["sharedShell"]
        entries = shared["pathEntries"]
        orders = {"linux": shared["pathOrder"], "macos": shared["macosPathOrder"],
                  "windows": shared["windowsPathOrder"]}
        for platform, order in orders.items():
            with self.subTest(platform=platform):
                for name in order:
                    self.assertIn(name, entries)
        # macOS changes which directory comes first, not the set of them.
        self.assertEqual(sorted(orders["macos"]), sorted(orders["linux"]))
        # Every declared directory is ordered by at least one platform.
        ordered = {name for order in orders.values() for name in order}
        self.assertEqual(ordered, set(entries))

    def test_a_macos_shell_resolves_an_adopted_agent_to_the_homebrew_copy(self):
        home = self.deploy("macos")
        # The device's Homebrew provides the command. The managed launcher
        # points at that executable, while the Bun directory keeps an older
        # copy of the same command.
        self.write_command(home / "device/kimi", "homebrew 2.6.2")
        self.write_command(home / ".bun/bin/kimi", "bun 2.4.1")
        launcher = home / ".local/bin/kimi"
        launcher.parent.mkdir(parents=True, exist_ok=True)
        launcher.write_text('#!/bin/sh\nexec "$HOME/device/kimi" "$@"\n')
        launcher.chmod(0o755)
        result = subprocess.run(["/bin/sh", "-c", '. "$HOME/.env_core"; kimi --version'],
                                env={"HOME": str(home), "PATH": "/usr/bin:/bin"}, cwd=home,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "homebrew 2.6.2")

    def test_a_linux_shell_resolves_an_agent_to_the_bun_copy(self):
        home = self.deploy("linux")
        self.write_command(home / ".local/bin/kimi", "homebrew 2.6.2")
        self.write_command(home / ".bun/bin/kimi", "bun 2.4.1")
        result = subprocess.run(["/bin/sh", "-c", '. "$HOME/.env_core"; kimi --version'],
                                env={"HOME": str(home), "PATH": "/usr/bin:/bin"}, cwd=home,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "bun 2.4.1")


if __name__ == "__main__":
    unittest.main()
