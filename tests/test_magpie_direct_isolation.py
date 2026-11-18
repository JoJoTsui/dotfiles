"""Direct Magpie gateway commands must reject a synthetic or foreign home.

The public command shares the gateway boundary with the bootstrap step: it can
probe the device's loopback port and start, stop, or reconfigure a gateway.
These checks exercise the command only. They run the real source engine against
a synthetic HOME with fake sentinel CLIs/curl, so a command that gets past the
guard is caught touching a sentinel or PID state instead of reaching a real
gateway. No real home, credential, installer, or network endpoint is used.
"""
from pathlib import Path
import platform
import sys
import subprocess
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1]
COMMAND = SOURCE / "dot_local/bin/executable_dotfiles-magpie"
ENGINE = SOURCE / "deployment/magpie.sh"
CATALOG = SOURCE / "deployment/magpie"

# A distinctive marker the command prints when it refuses a direct invocation.
GUARD = "the gateway commands require the real account home on a supported platform"
GUARDED = ("apply", "status", "providers", "test", "start", "stop")

# The engine reads the deployment selector for its own behavior; the guard must
# not trust it, so pin it to a supported value to exercise the engine in red.
NATIVE_SELECTOR = {"Darwin": "macos", "Linux": "linux"}.get(platform.system(), "linux")

FAKE_CLI = """#!/bin/sh
printf '%s\\n' "$*" >> "$MAGPIE_SENTINEL_LOG"
case "$1" in
  status) printf '{"running":true,"gateway":"http://127.0.0.1:3425"}\\n' ;;
  *) printf 'ok\\n' ;;
esac
exit 0
"""

FAKE_CURL = """#!/bin/sh
printf '%s\\n' "$*" >> "$MAGPIE_SENTINEL_LOG"
printf 'not-a-real-payload\\n'
exit 0
"""


class MagpieDirectIsolationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dotfiles-magpie-direct-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / "device"
        self.home.mkdir()
        self.tools = self.root / "tools"
        self.tools.mkdir()
        self.sentinel = self.root / "touched.log"
        self.pid_file = self.home / ".local/state/dotfiles/magpie/gateway/gateway.pid"

        cli = self.tools / "magpie-fake"
        cli.write_text(FAKE_CLI, encoding="utf-8")
        cli.chmod(0o755)
        self.cli = cli

        curl = self.tools / "curl"
        curl.write_text(FAKE_CURL, encoding="utf-8")
        curl.chmod(0o755)

        # A minimal, explicit environment: the fake subprocesses must never
        # inherit unrelated credential variables from the operator's shell.
        self.env = {
            "HOME": str(self.home),
            "PATH": f"{self.tools}:/usr/bin:/bin",
            "TMPDIR": str(self.root),
            "LANG": "C",
            "DEPLOY_PLATFORM": NATIVE_SELECTOR,
            "DOTFILES_MAGPIE_ENGINE": str(ENGINE),
            "MAGPIE_CATALOG_DIR": str(CATALOG),
            "MAGPIE_CLI_BIN": str(cli),
            "MAGPIE_BIN": str(cli),
            "MAGPIE_SENTINEL_LOG": str(self.sentinel),
            "MAGPIE_PYTHON": sys.executable,
            "MAGPIE_RELEASE_CATALOG": str(self.root / "no-release-catalog.tsv"),
        }

    def run_command(self, *arguments):
        return subprocess.run(["/bin/bash", str(COMMAND), *arguments], cwd=SOURCE,
                              env=self.env, capture_output=True, text=True, timeout=30,
                              check=False)

    def test_help_works_without_the_engine_or_a_real_home(self):
        result = self.run_command("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage: dotfiles-magpie", result.stderr)
        self.assertFalse(self.sentinel.exists(), result.stdout + result.stderr)

    def test_guarded_commands_fail_before_sentinels_or_pid_state(self):
        for command in GUARDED:
            with self.subTest(command=command):
                # Each case gets a fresh sentinel so one case cannot mask another.
                self.sentinel.unlink(missing_ok=True)
                if self.pid_file.exists():
                    self.pid_file.unlink()
                result = self.run_command(command)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(GUARD, result.stderr, result.stdout + result.stderr)
                self.assertFalse(self.sentinel.exists(),
                                 "a guarded command invoked a fake CLI/curl: " +
                                 result.stdout + result.stderr)
                self.assertFalse(self.pid_file.exists(),
                                 "a guarded command wrote PID state: " +
                                 result.stdout + result.stderr)

    def test_deployed_engine_preserves_existing_pid_in_a_synthetic_home(self):
        engine = self.home / ".local/share/dotfiles/magpie/engine.sh"
        engine.parent.mkdir(parents=True)
        engine.write_bytes(ENGINE.read_bytes())
        self.pid_file.parent.mkdir(parents=True)
        original = b"123\nforeign-fingerprint\n"
        self.pid_file.write_bytes(original)
        self.env.pop("DOTFILES_MAGPIE_ENGINE")
        for command in GUARDED:
            with self.subTest(command=command):
                result = self.run_command(command)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(GUARD, result.stderr, result.stdout + result.stderr)
                self.assertFalse(self.sentinel.exists(), result.stdout + result.stderr)
                self.assertEqual(self.pid_file.read_bytes(), original)

    def test_a_supported_platform_selector_cannot_bypass_the_guard(self):
        # The guard resolves the platform natively and the home from the account
        # database, so no deployment selector makes a synthetic home acceptable.
        for selector in ("macos", "linux", "wsl"):
            with self.subTest(selector=selector):
                self.sentinel.unlink(missing_ok=True)
                env = dict(self.env, DEPLOY_PLATFORM=selector)
                result = subprocess.run(["/bin/bash", str(COMMAND), "status"], cwd=SOURCE,
                                        env=env, capture_output=True, text=True, timeout=30,
                                        check=False)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(GUARD, result.stderr, result.stdout + result.stderr)
                self.assertFalse(self.sentinel.exists(), result.stdout + result.stderr)

    def test_a_foreign_platform_is_rejected_when_the_account_check_succeeds(self):
        # This shim loads the real engine but makes the real-account-home check
        # succeed, leaving the platform comparison as the only gate. A selector
        # opposite the native OS must still be refused before `start` reaches
        # the fake CLI/curl sentinel.
        self.sentinel.unlink(missing_ok=True)
        shim = self.root / "engine-shim.sh"
        shim.write_text(
            '. "$MAGPIE_REAL_ENGINE"\n'
            'magpie_real_account_home() { return 0; }\n',
            encoding="utf-8",
        )
        opposite = "linux" if platform.system() == "Darwin" else "macos"
        env = dict(self.env,
                   DOTFILES_MAGPIE_ENGINE=str(shim),
                   MAGPIE_REAL_ENGINE=str(ENGINE),
                   DEPLOY_PLATFORM=opposite)
        result = subprocess.run(["/bin/bash", str(COMMAND), "start"], cwd=SOURCE,
                                env=env, capture_output=True, text=True, timeout=30,
                                check=False)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(GUARD, result.stderr, result.stdout + result.stderr)
        self.assertFalse(self.sentinel.exists(),
                         "start reached the gateway with a foreign platform selector: " +
                         result.stdout + result.stderr)

    def test_install_is_not_blocked_by_the_direct_command_guard(self):
        # Install reaches its own release-catalog validation despite the fake
        # home; the new gateway guard must not apply to it. Its real operation is
        # covered by the dedicated fake-install tests.
        self.sentinel.unlink(missing_ok=True)
        env = dict(self.env, DEPLOY_PLATFORM="linux")
        result = subprocess.run(["/bin/bash", str(COMMAND), "install"], cwd=SOURCE,
                                env=env, capture_output=True, text=True, timeout=30,
                                check=False)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn(GUARD, result.stderr, result.stdout + result.stderr)
        self.assertIn("release catalog", result.stderr, result.stdout + result.stderr)
        self.assertFalse(self.sentinel.exists(), result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
