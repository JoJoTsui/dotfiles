"""Proxy writes stay in the selected home before installers or source apply."""
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]


class ProxyIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-proxy-isolation-", dir="/tmp")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "selected"
        self.outside = self.root / "outside"
        self.original = self.root / "original"
        self.guards = self.root / "guards"
        for directory in (self.home, self.outside, self.original, self.guards):
            directory.mkdir()
        self.marker = self.outside / "keep"
        self.marker.write_text("unchanged\n")
        self.marker.chmod(0o640)
        guard = self.guards / "chezmoi"
        guard.write_text("#!/bin/sh\nexit 97\n")
        guard.chmod(0o755)
        self.env = {"HOME": str(self.original), "PATH": "/usr/bin:/bin",
                    "DOTFILES_CHEZMOI_BIN": str(guard),
                    "MIHOMO_SUBSCRIPTION_URL": "https://synthetic.invalid/private-subscription",
                    "DEPLOY_PROXY_PORTS": "1"}

    def deploy(self, *arguments):
        return subprocess.run(
            ["/bin/bash", str(SOURCE / "bootstrap.sh"), "--source", str(SOURCE),
             "--home", str(self.home), "--platform", "macos", "--role", "workstation",
             "--apply-only", *arguments], cwd=SOURCE, env=self.env,
            capture_output=True, text=True, timeout=30)

    def assert_public_rejects(self, relative, *, directory):
        destination = self.home / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.symlink_to(self.outside if directory else self.marker,
                               target_is_directory=directory)
        try:
            before = self.marker.stat()
            result = self.deploy()
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("symlink", result.stderr)
            self.assertEqual(sorted(path.name for path in self.outside.iterdir()), ["keep"])
            self.assertEqual(self.marker.read_text(), "unchanged\n")
            self.assertEqual(self.marker.stat().st_mode, before.st_mode)
            self.assertEqual(list(self.original.iterdir()), [])
            self.assertFalse((self.home / ".config").exists(), "preflight must precede state preparation")
        finally:
            destination.unlink()

    def test_public_boundary_rejects_proxy_directory_escapes_before_any_write(self):
        for relative in (
                ".local/share/mihomo", ".local/share/mihomo/bin",
                ".local/share/mihomo/profiles", ".local/share/mihomo/deployment",
                ".local/share/mihomo/deployment/profiles", ".local/share/mihomo/run",
                ".cache/dotfiles", ".cache/dotfiles/mihomo", ".cache/dotfiles/proxy-scripts",
                ".local/share/dotfiles/proxy", ".local/share/dotfiles/proxy/scripts"):
            with self.subTest(path=relative):
                self.assert_public_rejects(relative, directory=True)

    def test_public_boundary_rejects_proxy_file_and_partial_escapes_before_any_write(self):
        for relative in (
                ".local/share/mihomo/subscription-url", ".local/share/mihomo/bin/mihomo",
                ".local/share/mihomo/bin/mihomo.part", ".local/share/mihomo/profiles/config.yaml",
                ".local/share/mihomo/profiles/deployment-config.yaml",
                ".local/share/mihomo/deployment/profiles/config.yaml",
                ".local/share/mihomo/deployment/subscription-url", ".local/share/mihomo/run/deployment.log",
                ".local/share/mihomo/cache.db",
                ".cache/dotfiles/mihomo/mihomo-1.19.29-linux-arm64.gz",
                ".cache/dotfiles/mihomo/mihomo-1.19.29-linux-arm64.gz.part",
                ".cache/dotfiles/proxy-scripts/refresh-profile.sh",
                ".local/share/dotfiles/proxy/scripts/refresh-profile.sh"):
            with self.subTest(path=relative):
                self.assert_public_rejects(relative, directory=False)

    def test_public_boundary_rejects_dangling_and_internal_proxy_symlinks(self):
        for target in (self.outside / "missing", self.home / "ordinary"):
            with self.subTest(target=str(target)):
                secret = self.home / ".local/share/mihomo/subscription-url"
                secret.parent.mkdir(parents=True, exist_ok=True)
                secret.symlink_to(target)
                result = self.deploy()
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("symlink", result.stderr)
                self.assertFalse(target.exists())
                secret.unlink()

    def run_proxy(self, body, **overrides):
        environment = dict(self.env, HOME=str(self.home), **overrides)
        script = ("set -euo pipefail\n"
                  "fail() { printf '%s\\n' \"$*\" >&2; exit 1; }\n"
                  f"DEPLOY_SOURCE={shlex.quote(str(SOURCE))}\n"
                  f"DEPLOY_HOME={shlex.quote(str(self.home))}\n"
                  f"source {shlex.quote(str(SOURCE / 'deployment/payload.sh'))}\n"
                  f"source {shlex.quote(str(SOURCE / 'deployment/proxy.sh'))}\n" + body)
        return subprocess.run(["/bin/bash", "-c", script], cwd=SOURCE, env=environment,
                              capture_output=True, text=True, timeout=30)

    def test_safe_proxy_preflight_does_not_create_state(self):
        result = self.run_proxy("validate_proxy_destinations\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_refresh_binds_helper_writes_and_secret_to_the_selected_home(self):
        root = self.home / ".local/share/mihomo"
        (root / "profiles").mkdir(parents=True)
        (root / "subscription-url").write_text("https://synthetic.invalid/subscription\n")
        scripts = self.home / ".local/share/dotfiles/proxy/scripts"
        scripts.mkdir(parents=True)
        refresh = scripts / "refresh-profile.sh"
        refresh.write_text("#!/bin/sh\n"
                           "test \"$SUBSCRIPTION_URL_FILE\" = \"$INSTALL_ROOT/subscription-url\" || exit 92\n"
                           "printf 'selected\\n' > \"$PROFILE_PATH\"\n")
        refresh.chmod(0o755)
        result = self.run_proxy("refresh_proxy_profile\n", PROFILE_PATH=str(self.marker),
                                SUBSCRIPTION_URL_FILE=str(self.marker))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((root / "profiles/config.yaml").read_text(), "selected\n")
        self.assertEqual(self.marker.read_text(), "unchanged\n")

    def test_deployment_profile_binds_helper_output_to_the_selected_home(self):
        root = self.home / ".local/share/mihomo"
        (root / "profiles").mkdir(parents=True)
        subscription = root / "subscription-url"
        subscription.write_text("https://synthetic.invalid/subscription\n")
        scripts = self.home / ".local/share/dotfiles/proxy/scripts"
        scripts.mkdir(parents=True)
        refresh = scripts / "refresh-profile.sh"
        refresh.write_text("#!/bin/sh\n"
                           f"test \"$SUBSCRIPTION_URL_FILE\" = {shlex.quote(str(subscription))} || exit 92\n"
                           "printf 'mixed-port: 7890\\n' > \"$PROFILE_PATH\"\n")
        refresh.chmod(0o755)
        for name in ("restrict-proxy-groups.py", "apply-us-routing-policy.py"):
            policy = scripts / name
            policy.write_text("#!/bin/sh\nexit 0\n")
            policy.chmod(0o755)
        result = self.run_proxy(
            "DEPLOY_PROXY_PORT=7895\nDEPLOY_PROXY_CONTROLLER_PORT=9091\ndeploy_proxy_profile\n",
            PROFILE_PATH=str(self.marker), SUBSCRIPTION_URL_FILE=str(self.marker))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((root / "deployment/profiles/config.yaml").is_file())
        self.assertIn("mixed-port: 7895", (root / "profiles/deployment-config.yaml").read_text())
        self.assertEqual(self.marker.read_text(), "unchanged\n")


if __name__ == "__main__":
    unittest.main()
