"""The auxiliary Claude model aliases render only in the gateway merge.

These exercise the public `deploy_client_settings` seam against the working
tree, the same entry point bootstrap and the Magpie step call, in a synthetic
home. They render settings and read the resulting file; they never send a
model request or contact a gateway.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]

HAIKU = "ANTHROPIC_DEFAULT_HAIKU_MODEL"
SMALL_FAST = "ANTHROPIC_SMALL_FAST_MODEL"
AUXILIARY = frozenset((HAIKU, SMALL_FAST))
AUXILIARY_ROUTE = "auto/gpt-6.1-terra"
CONDUCTOR = "group/conductor"
# Aliases this slice deliberately leaves alone: the three tier aliases keep the
# conductor group and the permission classifier keeps the Terra route, which is
# the gateway's own cross-provider family rather than one provider's model.
UNCHANGED = {
    "ANTHROPIC_DEFAULT_FABLE_MODEL": CONDUCTOR,
    "ANTHROPIC_DEFAULT_OPUS_MODEL": CONDUCTOR,
    "ANTHROPIC_DEFAULT_SONNET_MODEL": CONDUCTOR,
    "CLAUDE_CODE_AUTO_MODE_MODEL": AUXILIARY_ROUTE,
}


class AuxiliaryModelRouteTests(unittest.TestCase):
    def setUp(self):
        self.chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        temporary = tempfile.TemporaryDirectory(prefix="dotfiles-magpie-auxiliary-models-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.state = self.home / ".local/state"
        self.settings = self.home / ".claude/settings.json"
        # Drop host deployment and credential variables so none can leak into
        # the synthetic home or change the render.
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("DOTFILES_", "XDG_", "PIXI_", "BUN_", "CARGO_", "RUSTUP_", "UV_",
                                           "NPM_", "ATUIN_", "KIMI_", "PI_", "OPENCODE_", "CODEX_", "CLAUDE_"))
                    and key not in ("GLM_API_TOKEN", "KIMI_API_KEY", "GLM_BASE_URL", "HTTP_PROXY_URL",
                                    "NODE_OPTIONS", "ENV", "BASH_ENV", "ANTHROPIC_AUTH_TOKEN", "CONTEXT7_TOKEN")}

    def write_chezmoi_config(self):
        config = self.home / ".config/chezmoi/chezmoi.toml"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('[data]\n    platform = "macos"\n    role = "workstation"\n'
                          '    arch = "aarch64"\n    kimiApiKey = "REPLACE_ME"\n', encoding="utf-8")
        (self.home / ".cache/tmp").mkdir(parents=True, exist_ok=True)

    def merge(self, *, gateway=True):
        """Run the Claude client-settings merge in a synthetic home."""
        if not self.chezmoi:
            self.skipTest("client settings merge requires chezmoi")
        self.write_chezmoi_config()
        script = self.root / ("gateway-merge.sh" if gateway else "ordinary-merge.sh")
        script.write_text("\n".join([
            "export HOME=" + repr(str(self.home)),
            "export DEPLOY_SOURCE=" + repr(str(SOURCE)),
            "export DEPLOY_HOME=$HOME",
            "export DEPLOY_CHEZMOI=" + repr(str(self.chezmoi)),
            "export XDG_CONFIG_HOME=" + repr(str(self.home / ".config")),
            "export XDG_STATE_HOME=" + repr(str(self.state)),
            "export TMPDIR=" + repr(str(self.home / ".cache/tmp")),
            "fail() { printf 'dotfiles: %s\\n' \"$*\" >&2; exit 1; }",
            'source "$DEPLOY_SOURCE/deployment/payload.sh"',
            'source "$DEPLOY_SOURCE/deployment/client-settings.sh"',
            "deploy_client_settings 0 %s claude-settings" % (1 if gateway else 0),
        ]) + "\n", encoding="utf-8")
        environ = dict(self.env, HOME=str(self.home), PATH="/usr/bin:/bin",
                       XDG_CONFIG_HOME=str(self.home / ".config"),
                       XDG_STATE_HOME=str(self.state))
        return subprocess.run(["/bin/bash", str(script)], env=environ,
                              capture_output=True, text=True, timeout=120)

    def live_env(self):
        return json.loads(self.settings.read_text(encoding="utf-8"))["env"]

    def assert_merged(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_gateway_merge_routes_both_auxiliary_aliases_to_terra(self):
        self.assert_merged(self.merge())
        env = self.live_env()
        for key in sorted(AUXILIARY):
            with self.subTest(key=key):
                self.assertEqual(env[key], AUXILIARY_ROUTE)
        self.assertEqual(env["ANTHROPIC_BASE_URL"], "http://127.0.0.1:3425")
        self.assertEqual(env["ANTHROPIC_AUTH_TOKEN"], "magpie")

    def test_other_managed_model_aliases_keep_their_routes(self):
        self.assert_merged(self.merge())
        env = self.live_env()
        for key, value in UNCHANGED.items():
            with self.subTest(key=key):
                self.assertEqual(env[key], value)
        for key in AUXILIARY:
            self.assertNotEqual(env[key], CONDUCTOR)

    def test_device_values_survive_the_gateway_merge(self):
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.settings.write_text(json.dumps({
            "model": "opus",
            "devicePreference": {"enabled": False},
            "env": {"DEVICE_KEEP": "synthetic-retain", "ANTHROPIC_MODEL": "device/model"},
        }), encoding="utf-8")
        self.assert_merged(self.merge())
        settings = json.loads(self.settings.read_text(encoding="utf-8"))
        self.assertEqual(settings["env"]["DEVICE_KEEP"], "synthetic-retain")
        self.assertEqual(settings["env"]["ANTHROPIC_MODEL"], "device/model")
        self.assertIs(settings["devicePreference"]["enabled"], False)
        self.assertEqual(settings["env"][HAIKU], AUXILIARY_ROUTE)
        self.assertEqual(settings["env"][SMALL_FAST], AUXILIARY_ROUTE)

    def test_repeated_gateway_merges_are_idempotent(self):
        self.assert_merged(self.merge())
        first = self.settings.read_bytes()
        self.assert_merged(self.merge())
        self.assertEqual(self.settings.read_bytes(), first)

    def test_ordinary_merge_does_not_render_the_auxiliary_aliases(self):
        self.assert_merged(self.merge(gateway=False))
        env = self.live_env()
        for key in AUXILIARY:
            self.assertNotIn(key, env)
        self.assertNotIn("ANTHROPIC_BASE_URL", env)


if __name__ == "__main__":
    unittest.main()
