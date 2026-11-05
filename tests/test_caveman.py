"""Caveman gateway mounts for coding agents, applied through public deployment."""
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from fixtures.skills import write_skill_library

SOURCE = Path(__file__).resolve().parents[1]
CLIENT_SETTINGS = SOURCE / "deployment" / "client-settings"
MANAGED_CONFIG = CLIENT_SETTINGS / "caveman.yaml"
TARGET = ".caveman/caveman.yaml"


def managed_mounts(text):
    """Read the `compat:` mounts of a gateway configuration."""
    mounts = {}
    provider = None
    inside = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not raw[0].isspace():
            inside = line == "compat:"
            provider = None
            continue
        if not inside:
            continue
        key, _, value = line.partition(":")
        if not value.strip():
            provider = key.strip()
            mounts.setdefault(provider, "")
        elif provider is not None:
            mounts[provider] = value.strip()
    return mounts


class CavemanMountTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-caveman-")
        self.addCleanup(self.temporary.cleanup)
        # Resolve the temporary root: macOS puts it behind the /var ->
        # /private/var symlink, and the managed state is written under the
        # canonical home the scripts see.
        self.root = Path(self.temporary.name).resolve()
        self.home = self.root / "device"
        self.chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        if not self.chezmoi:
            self.skipTest("actual config apply requires chezmoi")
        self.skills = write_skill_library(self.root / "skills-fixture")
        self.env = {"HOME": str(self.root / "original"), "PATH": "/usr/bin:/bin",
                    "DOTFILES_CHEZMOI_BIN": self.chezmoi,
                    "DOTFILES_SKILLS_DIR": str(self.skills)}

    def deploy(self, *arguments):
        import subprocess
        return subprocess.run(["/bin/bash", str(SOURCE / "bootstrap.sh"),
                                "--source", str(SOURCE), "--home", str(self.home),
                                "--platform", os.environ.get("DOTFILES_TEST_PLATFORM", "linux"),
                                "--role", os.environ.get("DOTFILES_TEST_ROLE", "workstation"),
                                "--apply-only", *arguments],
                              cwd=SOURCE, env=self.env, capture_output=True,
                              text=True, timeout=600)

    def gateway_config(self):
        return self.home / ".caveman" / "caveman.yaml"

    def test_managed_mount_matches_the_pi_provider_catalog(self):
        mounts = managed_mounts(MANAGED_CONFIG.read_text())
        self.assertIn("minimax-cn", mounts)
        catalog = json.loads((CLIENT_SETTINGS / "pi-models-store.json").read_text())
        self.assertIn("minimax-cn", catalog)
        catalog_urls = {model["baseUrl"] for model in catalog["minimax-cn"]["models"]}
        self.assertEqual(catalog_urls, {mounts["minimax-cn"]})

    def test_catalog_declares_the_gateway_target(self):
        rows = (CLIENT_SETTINGS / "targets.tsv").read_text().splitlines()
        self.assertIn(f"yaml|caveman.yaml|{TARGET}|caveman-config", rows)
        policies = json.loads((CLIENT_SETTINGS / "policies.json").read_text())
        self.assertIn("caveman-config", policies)
        self.assertIn(["compat", "minimax-cn", "base_url"], policies["caveman-config"])

    def test_apply_enforces_the_mount_and_preserves_device_configuration(self):
        config = self.gateway_config()
        config.parent.mkdir(parents=True)
        config.write_text(
            "providers:\n"
            "  anthropic:\n"
            "    base_url: https://api.anthropic.com\n"
            "compat:\n"
            "  device-mount:\n"
            "    base_url: https://device.invalid/anthropic\n"
            "  minimax-cn:\n"
            "    base_url: https://stale.invalid/anthropic\n")
        result = self.deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        mounts = managed_mounts(config.read_text())
        self.assertEqual(mounts["minimax-cn"],
                         managed_mounts(MANAGED_CONFIG.read_text())["minimax-cn"])
        self.assertEqual(mounts["device-mount"], "https://device.invalid/anthropic")
        self.assertIn("providers:", config.read_text())

    def test_apply_leaves_an_unchanged_gateway_configuration_untouched(self):
        first = self.deploy()
        self.assertEqual(first.returncode, 0, first.stderr)
        config = self.gateway_config()
        self.assertTrue(config.is_file())
        before = config.stat().st_mtime_ns
        time.sleep(1.1)
        second = self.deploy()
        self.assertEqual(second.returncode, 0, second.returncode and second.stderr)
        self.assertEqual(before, config.stat().st_mtime_ns)

    def test_first_apply_preserves_correct_device_yaml_and_running_gateway(self):
        config = self.gateway_config()
        config.parent.mkdir(parents=True)
        managed_url = managed_mounts(MANAGED_CONFIG.read_text())["minimax-cn"]
        original = (
            "# Keep this device comment and ordering.\n"
            "mode: 'compress'\n"
            "compat:\n"
            f"  minimax-cn: {{base_url: '{managed_url}'}}\n"
            "  device-mount:\n"
            "    base_url: https://device.invalid/anthropic\n").encode()
        config.write_bytes(original)
        # Distinct whole seconds also exercise Bash 3.2's -nt comparison.
        stamp = time.time() - 20
        os.utime(config, (stamp, stamp))
        before = config.stat().st_mtime_ns

        gateway = config.parent
        (gateway / "run").mkdir()
        (gateway / "bin").mkdir()
        standby = subprocess.Popen(["/bin/sleep", "300"])
        self.addCleanup(standby.wait, timeout=5)
        self.addCleanup(standby.terminate)
        state = gateway / "run" / "8787.json"
        state.write_text(json.dumps({
            "pid": standby.pid, "listen": "127.0.0.1:8787", "mode": "compress",
            "compat_upstreams": {"minimax-cn": managed_url},
        }))
        os.utime(state, (stamp + 10, stamp + 10))
        binary = gateway / "bin" / "caveman-proxy"
        binary.write_text(
            "#!/bin/sh\n"
            "printf restarted > \"$HOME/proxy-restarted\"\n"
            f"printf '%s' '{json.dumps({'compat_upstreams': {'minimax-cn': managed_url}})}'"
            " > \"$HOME/.caveman/run/8787.json\"\n")
        binary.chmod(0o755)

        result = self.deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(config.read_bytes(), original)
        self.assertEqual(config.stat().st_mtime_ns, before)
        self.assertFalse((self.home / "proxy-restarted").exists())
        self.assertIsNone(standby.poll())
        baseline = self.home / ".local/state/dotfiles/client-settings/caveman-config.json"
        self.assertEqual(json.loads(baseline.read_text())["compat"]["minimax-cn"]["base_url"],
                         managed_url)


class CavemanRestartTests(unittest.TestCase):
    """The gateway restart repeats the settings of the instance it replaces."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-caveman-restart-")
        self.addCleanup(self.temporary.cleanup)
        # Resolve the temporary root: macOS puts it behind the /var ->
        # /private/var symlink, and the managed state is written under the
        # canonical home the scripts see.
        self.root = Path(self.temporary.name).resolve()
        self.home = self.root / "device"
        self.home.mkdir()
        self.gateway = self.home / ".caveman"
        (self.gateway / "run").mkdir(parents=True)
        (self.gateway / "bin").mkdir()
        self.state = self.gateway / "run" / "8787.json"
        self.config = self.gateway / "caveman.yaml"
        self.config.write_text("compat:\n  minimax-cn:\n    base_url: https://api.minimaxi.com/anthropic\n")

    def write_state(self, pid):
        self.state.write_text(json.dumps({
            "schema": "caveman.proxy.run.v1", "pid": pid, "port": 8787,
            "listen": "127.0.0.1:8787", "mode": "compress", "owner": "wrap",
            "instance_token": "token", "started_at": "2026-01-01T00:00:00Z",
            "recovery_via_mcp": True, "compat_upstreams": {},
        }))

    def fake_proxy(self):
        binary = self.gateway / "bin" / "caveman-proxy"
        binary.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$CAVEMAN_MODE|$CAVEMAN_LISTEN|$CAVEMAN_RECOVERY|$CAVEMAN_PROXY_OWNER\""
            " > \"$HOME/proxy-env\"\n"
            "mkdir -p \"$HOME/.caveman/run\"\n"
            "printf '%s' '{\"mode\":\"compress\",\"recovery_via_mcp\":true,"
            "\"compat_upstreams\":{\"minimax-cn\":\"https://api.minimaxi.com/anthropic\"}}'"
            " > \"$HOME/.caveman/run/8787.json\"\n")
        binary.chmod(0o755)
        return binary

    def run_adapter(self, **environment):
        script = (
            'source "$DEPLOY_SOURCE/deployment/caveman.sh"\n'
            'refresh_caveman_proxy\n')
        child_env = {"HOME": str(self.home), "PATH": "/usr/bin:/bin",
                     "DEPLOY_SOURCE": str(SOURCE)}
        child_env.update(environment)
        return subprocess.run(["/bin/bash", "-c", script],
                              cwd=SOURCE, env=child_env,
                              capture_output=True, text=True, timeout=120)

    def standby_gateway(self):
        standby = subprocess.Popen(["/bin/sleep", "300"])
        self.addCleanup(self.stop_standby, standby)
        return standby

    def stop_standby(self, standby):
        standby.terminate()
        try:
            standby.wait(timeout=5)
        except subprocess.TimeoutExpired:
            standby.kill()

    def test_restart_repeats_the_published_settings_and_publishes_the_mount(self):
        standby = self.standby_gateway()
        self.write_state(standby.pid)
        time.sleep(0.05)
        # The config must be strictly newer than the run state. Bash 3.2
        # compares whole seconds, so the difference has to be visible there.
        self.newer_config()
        binary = self.fake_proxy()
        stub = self.root / "caveman"
        stub.write_text("#!/bin/sh\nexit 0\n")
        stub.chmod(0o755)
        result = self.run_adapter(CAVEMAN_PROXY_BIN=str(binary),
                                   CAVEMAN_CLI=str(stub))
        self.assertEqual(result.returncode, 0, result.stderr)
        recorded = (self.home / "proxy-env").read_text().strip()
        self.assertEqual(recorded, "compress|127.0.0.1:8787|mcp|start")
        self.assertIn("minimax-cn", self.state.read_text())

    def test_unchanged_configuration_leaves_the_gateway_alone(self):
        standby = self.standby_gateway()
        self.write_state(standby.pid)
        binary = self.fake_proxy()
        stub = self.root / "caveman"
        stub.write_text("#!/bin/sh\nexit 0\n")
        stub.chmod(0o755)
        result = self.run_adapter(CAVEMAN_PROXY_BIN=str(binary),
                                   CAVEMAN_CLI=str(stub))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.home / "proxy-env").exists())
        self.assertEqual(standby.poll(), None)

    def newer_config(self):
        """Make the configuration strictly newer than the run state.

        Bash 3.2 compares whole seconds, so the difference has to be visible
        there.
        """
        stamp = time.time() + 2
        os.utime(self.config, (stamp, stamp))

    def managed_proxy(self):
        """A with-proxy stub that records that it wrapped the gateway."""
        stub = self.home / ".local" / "bin" / "with-proxy"
        stub.parent.mkdir(parents=True, exist_ok=True)
        stub.write_text("#!/bin/sh\n"
                        "printf 'wrapped' > \"$HOME/proxy-wrapped\"\n"
                        "exec \"$@\"\n")
        stub.chmod(0o755)
        return stub

    def test_macos_starts_the_gateway_without_the_managed_proxy(self):
        standby = self.standby_gateway()
        self.write_state(standby.pid)
        self.newer_config()
        binary = self.fake_proxy()
        self.managed_proxy()
        result = self.run_adapter(DEPLOY_PLATFORM="macos",
                                   CAVEMAN_PROXY_BIN=str(binary))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.home / "proxy-env").exists())
        self.assertFalse((self.home / "proxy-wrapped").exists())

    def test_linux_starts_the_gateway_through_the_managed_proxy(self):
        standby = self.standby_gateway()
        self.write_state(standby.pid)
        self.newer_config()
        binary = self.fake_proxy()
        self.managed_proxy()
        result = self.run_adapter(DEPLOY_PLATFORM="linux",
                                   CAVEMAN_PROXY_BIN=str(binary))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.home / "proxy-wrapped").exists())


if __name__ == "__main__":
    unittest.main()
