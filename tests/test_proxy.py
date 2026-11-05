"""Proxy catalog and provisioning checks without network access."""
import hashlib
import gzip
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]


class ProxyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-proxy-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "device"
        self.chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        self.skills = self.root / "skills"
        shutil.copytree(SOURCE / "tests/fixtures/skill-library", self.skills)
        self.env = {"HOME": str(self.root / "original"), "PATH": "/usr/bin:/bin",
                    "DOTFILES_CHEZMOI_BIN": self.chezmoi or "",
                    "DOTFILES_SKILLS_DIR": str(self.skills)}

    def deploy(self, *arguments):
        if not self.chezmoi:
            self.skipTest("actual apply requires chezmoi")
        return subprocess.run(["/bin/bash", str(SOURCE / "bootstrap.sh"),
                               "--source", str(SOURCE), "--home", str(self.home),
                               "--platform", "linux", "--role", "workstation",
                               *arguments],
                              cwd=SOURCE, env=self.env, capture_output=True,
                              text=True, timeout=120)

    def test_catalog_pins_one_https_digest_per_target(self):
        rows = [line.split("|") for line in
                (SOURCE / "deployment/proxy/mihomo.tsv").read_text().splitlines()
                if line and not line.startswith("#")]
        self.assertEqual({row[2] for row in rows},
                         {"linux-amd64", "linux-arm64", "darwin-amd64", "darwin-arm64"})
        for name, version, target, url, digest in rows:
            self.assertEqual(name, "mihomo")
            self.assertTrue(url.startswith("https://"))
            self.assertIn(f"v{version}", url)
            self.assertIn(target.split("-")[0], url)
            self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_apply_installs_wrappers_scripts_secret_and_unit(self):
        result = self.deploy("--apply-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        scripts = self.home / ".local/share/dotfiles/proxy/scripts"
        for name in ("refresh-profile.sh", "run-mihomo.sh", "run-mihomo-supervised.sh",
                     "configure-mihomo.py", "apply-us-routing-policy.py",
                     "restrict-proxy-groups.py"):
            path = scripts / name
            self.assertTrue(path.is_file(), name)
            self.assertTrue(path.stat().st_mode & 0o111, name)
        startup = self.home / ".local/share/dotfiles/proxy/config/startup.env"
        self.assertIn("MIHOMO_MODE=rule", startup.read_text())
        secret = self.home / ".local/share/mihomo/subscription-url"
        self.assertEqual(secret.read_text().strip(), "REPLACE_ME")
        self.assertEqual(secret.stat().st_mode & 0o777, 0o600)
        for name in ("with-proxy", "direct"):
            wrapper = self.home / f".local/bin/{name}"
            self.assertTrue(wrapper.is_file(), name)
            self.assertTrue(wrapper.stat().st_mode & 0o111, name)
        unit = self.home / ".config/systemd/user/mihomo.service"
        self.assertIn("run-mihomo-supervised.sh", unit.read_text())

    def test_plan_reports_proxy_only_when_requested(self):
        if not self.chezmoi:
            self.skipTest("plan requires chezmoi")
        plain = self.deploy("--plan")
        self.assertEqual(plain.returncode, 0, plain.stderr)
        self.assertFalse(__import__("json").loads(plain.stdout)["proxy"])
        selected = self.deploy("--plan", "--proxy")
        self.assertEqual(selected.returncode, 0, selected.stderr)
        plan = __import__("json").loads(selected.stdout)
        self.assertTrue(plan["proxy"])
        self.assertIn("install-proxy", plan["actions"])

    def test_binary_install_verifies_the_pin_and_replaces_stale_binary(self):
        source = self.root / "source"
        catalog = source / "deployment/proxy/mihomo.tsv"
        catalog.parent.mkdir(parents=True)
        payload = gzip.compress(b"#!/bin/sh\necho 'Mihomo Meta v1.19.29'\n")
        asset = self.root / "mihomo.gz"
        asset.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        catalog.write_text(f"mihomo|1.19.29|linux-amd64|https://fixture.invalid/mihomo.gz|{digest}\n")
        script = self.root / "run.sh"
        script.write_text(
            "set -e\n"
            f"DEPLOY_SOURCE='{source}'\n"
            "DEPLOY_PLATFORM=wsl\n"
            f"HOME='{self.root}/home'\n"
            f"export XDG_CACHE_HOME='{self.root}/cache'\n"
            f"mkdir -p \"$HOME\"\n"
            "fail() { echo \"$*\" >&2; exit 1; }\n"
            "uname() { printf x86_64; }\n"
            f"curl() {{ cp '{asset}' \"$9\"; }}\n"
            f"source '{SOURCE}/deployment/proxy.sh'\n"
            "install_proxy_binary\n"
            "test -x \"$HOME/.local/share/mihomo/bin/mihomo\"\n",
            encoding="utf-8")
        result = subprocess.run(["/bin/bash", str(script)], env=dict(os.environ),
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("v1.19.29", result.stdout)
        binary = self.root / "home/.local/share/mihomo/bin/mihomo"
        self.assertTrue(binary.stat().st_mode & 0o111)

        # A digest mismatch must fail on a fresh install.
        binary.unlink()
        catalog.write_text(f"mihomo|1.19.29|linux-amd64|https://fixture.invalid/mihomo.gz|{'0' * 64}\n")
        result = subprocess.run(["/bin/bash", str(script)], env=dict(os.environ),
                                capture_output=True, text=True, timeout=60)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("digest mismatch", result.stderr)


    def run_proxy_script(self, body, env=None):
        script = self.root / "proxy.sh"
        script.write_text(
            "set -e\n"
            f"DEPLOY_SOURCE='{SOURCE}'\n"
            f"export HOME='{self.home}'\n"
            "fail() { echo \"$*\" >&2; exit 1; }\n"
            f"source '{SOURCE}/deployment/proxy.sh'\n"
            + body,
            encoding="utf-8")
        environment = dict(os.environ, **(env or {}))
        return subprocess.run(["/bin/bash", str(script)], env=environment,
                              capture_output=True, text=True, timeout=120)

    def test_the_policy_covers_every_deployment_step(self):
        policy = (SOURCE / "deployment/proxy-policy.tsv").read_text(encoding="utf-8")
        names = set()
        for line in policy.splitlines():
            if not line or line.startswith("#"):
                continue
            names.add(line.split("|")[0])
        steps = set()
        for line in (SOURCE / "bootstrap.sh").read_text(encoding="utf-8").splitlines():
            if "run_step " in line:
                steps.add(line.split("run_step ", 1)[1].split()[0])
        self.assertTrue(steps)
        self.assertEqual(steps - names, set())

    def test_a_section_needs_the_proxy_only_when_the_policy_says_so(self):
        result = self.run_proxy_script(
            'for step in install-managers apply-source.skills install-agents install-common '
            'apply-source prepare-shell; do\n'
            '  if deploy_step_uses_proxy "$step"; then printf "%s yes\\n" "$step"; '
            'else printf "%s no\\n" "$step"; fi\n'
            'done')
        self.assertEqual(result.returncode, 0, result.stderr)
        rules = dict(line.split() for line in result.stdout.splitlines() if line.split())
        self.assertEqual(rules["install-managers"], "yes")
        self.assertEqual(rules["apply-source.skills"], "yes")
        self.assertEqual(rules["install-agents"], "yes")
        self.assertEqual(rules["install-common"], "no")
        self.assertEqual(rules["apply-source"], "no")
        self.assertEqual(rules["prepare-shell"], "no")

    def test_the_deployment_proxy_takes_a_free_port_when_one_is_busy(self):
        import socket
        busy = socket.socket()
        busy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        busy.bind(("127.0.0.1", 0))
        busy.listen(1)
        port = busy.getsockname()[1]
        try:
            result = self.run_proxy_script(
                f'DEPLOY_PROXY_PORTS="{port} {port + 1}"\n'
                'deploy_proxy_choose_port')
        finally:
            busy.close()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(port + 1))

    def test_a_running_proxy_client_is_detected(self):
        result = self.run_proxy_script('deploy_proxy_client_running || printf "none\n"')
        self.assertEqual(result.returncode, 0, result.stderr)


    def write_proxy_fixture(self):
        """A home with the scripts and the profile the deployment builds."""
        scripts = self.home / ".local/share/dotfiles/proxy/scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        root = self.home / ".local/share/mihomo"
        (root / "profiles").mkdir(parents=True, exist_ok=True)
        (root / "profiles/fixture.yaml").write_text(
            "mixed-port: 7890\nport: 7891\nsocks-port: 7892\n"
            "external-controller: 127.0.0.1:9090\nsecret: \"topsecret\"\n"
            "proxies:\n  - name: \"US-1\"\n    server: us.example.invalid\n"
            "proxy-groups:\n  - name: GLOBAL\n    type: select\n    proxies: [\"US-1\"]\n"
            "rules:\n  - MATCH,GLOBAL\n",
            encoding="utf-8")
        (root / "subscription-url").write_text("https://example.invalid/subscription", encoding="utf-8")
        refresh = scripts / "refresh-profile.sh"
        refresh.write_text(
            "#!/bin/sh\nmkdir -p \"$INSTALL_ROOT/profiles\"\n"
            "cp \"$HOME/.local/share/mihomo/profiles/fixture.yaml\" \"$INSTALL_ROOT/profiles/config.yaml\"\n",
            encoding="utf-8")
        refresh.chmod(0o755)
        for name in ("restrict-proxy-groups.py", "apply-us-routing-policy.py"):
            policy = scripts / name
            policy.write_text(
                "#!/usr/bin/env python3\nimport sys\n"
                "profile = sys.argv[-1]\n"
                "open(profile, 'a').write('# policy applied\\n')\n",
                encoding="utf-8")
            policy.chmod(0o755)
        return scripts

    def test_the_deployment_profile_owns_its_ports_and_controller(self):
        self.write_proxy_fixture()
        result = self.run_proxy_script(
            'DEPLOY_PROXY_PORT=7895\nDEPLOY_PROXY_CONTROLLER_PORT=9091\n'
            'deploy_proxy_profile')
        self.assertEqual(result.returncode, 0, result.stderr)
        profile = self.home / ".local/share/mihomo/profiles/deployment-config.yaml"
        self.assertTrue(profile.is_file())
        text = profile.read_text(encoding="utf-8")
        self.assertIn("mixed-port: 7895", text)
        self.assertIn("port: 0", text)
        self.assertIn("socks-port: 0", text)
        self.assertIn("external-controller: 127.0.0.1:9091", text)
        self.assertIn('secret: ""', text)
        self.assertNotIn("topsecret", text)

    def test_the_deployment_profile_leaves_the_service_profile_alone(self):
        self.write_proxy_fixture()
        result = self.run_proxy_script(
            'DEPLOY_PROXY_PORT=7895\nDEPLOY_PROXY_CONTROLLER_PORT=9091\n'
            'deploy_proxy_profile')
        self.assertEqual(result.returncode, 0, result.stderr)
        service = self.home / ".local/share/mihomo/profiles/config.yaml"
        self.assertFalse(service.exists())

    def test_the_deployment_profile_needs_the_us_policy_scripts(self):
        self.write_proxy_fixture()
        (self.home / ".local/share/dotfiles/proxy/scripts/restrict-proxy-groups.py").unlink()
        result = self.run_proxy_script(
            'DEPLOY_PROXY_PORT=7895\nDEPLOY_PROXY_CONTROLLER_PORT=9091\n'
            'deploy_proxy_profile')
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
