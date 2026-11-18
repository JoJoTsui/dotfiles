"""Public bootstrap must not run the Magpie gateway against a synthetic home.

The gateway status probe talks to a shared loopback port, so a full default
bootstrap into a synthetic or foreign home could reach the real account's
gateway. These checks exercise the public entry point only: no installer runs,
no real home is read or written, and no network command is reachable.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1]
BOOTSTRAP = SOURCE / "bootstrap.sh"


class MagpieBootstrapIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-magpie-bootstrap-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "device"
        self.original = self.root / "original"
        self.original.mkdir()
        self.tools = self.root / "tools"
        self.tools.mkdir()
        self.env = os.environ.copy()
        for name in tuple(self.env):
            if name.startswith(("DOTFILES_", "XDG_", "PIXI_", "BUN_", "CARGO_", "RUSTUP_",
                                "ATUIN_", "UV_", "PIP_", "NPM_", "MAGPIE_", "OPENCODE_",
                                "CODEX_", "CLAUDE_", "KIMI_", "PI_", "QODER_", "MINIMAX_")) or name in (
                "GLM_API_TOKEN", "KIMI_API_KEY", "GLM_BASE_URL", "HTTP_PROXY_URL",
                "ANTHROPIC_AUTH_TOKEN", "CONTEXT7_TOKEN", "NODE_OPTIONS", "ENV", "BASH_ENV",
            ):
                self.env.pop(name)
        self.env["HOME"] = str(self.original)
        # Guard the network/account boundary: any accidental gateway probe or
        # installer call fails loudly instead of reaching the real device.
        self.env["PATH"] = f"{self.tools}:/usr/bin:/bin"
        for name in ("curl", "magpie", "sudo", "chsh"):
            command = self.tools / name
            command.write_text('#!/bin/sh\nprintf "forbidden command: %s\\n" "$0" >&2\nexit 91\n')
            command.chmod(0o755)

    def bootstrap(self, *arguments, env=None):
        command = ["/bin/bash", str(BOOTSTRAP), "--source", str(SOURCE),
                   "--home", str(self.home), *arguments]
        return subprocess.run(command, cwd=SOURCE, env=env or self.env,
                              capture_output=True, text=True, timeout=60)

    def plan(self, *arguments, env=None):
        result = self.bootstrap("--plan", *arguments, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def link_home_state_root(self):
        """Make bootstrap fail after the guard, without creating state or running adapters."""
        if self.home.is_symlink():
            self.home.unlink()
        elif self.home.exists():
            shutil.rmtree(self.home)
        self.home.mkdir()
        sentinel = self.root / "sentinel"
        sentinel.mkdir(exist_ok=True)
        (self.home / ".local").symlink_to(sentinel, target_is_directory=True)

    def assert_past_guard_but_stopped(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("target state root is a symlink", result.stderr)
        self.assertNotIn("--no-magpie", result.stderr)
        self.assertNotIn("forbidden command", result.stderr)

    def test_full_deployment_selecting_magpie_fails_before_target_creation(self):
        # No --platform override: the target is rejected on the detected native
        # platform because it is not the current account's home.
        result = self.bootstrap()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertTrue(result.stderr.startswith("dotfiles:"), result.stderr)
        self.assertIn("simulated or foreign home", result.stderr)
        self.assertIn("--no-magpie", result.stderr)
        self.assertNotIn("forbidden command", result.stderr)
        self.assertFalse(self.home.exists())
        self.assertEqual(list(self.original.iterdir()), [])

    def test_guard_does_not_trust_inherited_home(self):
        # Even when inherited HOME equals --home, the native account resolver
        # decides; a synthetic target is still refused.
        result = self.bootstrap(env=dict(self.env, HOME=str(self.home)))
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("--no-magpie", result.stderr)
        self.assertFalse(self.home.exists())

    def test_plan_still_reports_default_magpie_for_a_synthetic_home(self):
        plan = self.plan()
        self.assertIs(plan["magpie"], True)
        self.assertIn("magpie-apply", plan["actions"])
        self.assertIs(self.plan("--no-magpie")["magpie"], False)
        self.assertFalse(self.home.exists())
        self.assertEqual(list(self.original.iterdir()), [])

    def test_restricted_modes_skip_the_guard_on_a_synthetic_home(self):
        for mode in ("--apply-only", "--agents-only"):
            with self.subTest(mode=mode):
                self.link_home_state_root()
                self.assert_past_guard_but_stopped(self.bootstrap(mode))

    def test_explicit_no_magpie_keeps_the_synthetic_home_available(self):
        cases = ((("--no-magpie",), {}), ((), {"DOTFILES_MAGPIE": "false"}))
        for arguments, environment in cases:
            with self.subTest(arguments=arguments, environment=environment):
                self.link_home_state_root()
                env = dict(self.env, **environment)
                self.assert_past_guard_but_stopped(self.bootstrap(*arguments, env=env))


if __name__ == "__main__":
    unittest.main()
