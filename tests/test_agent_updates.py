"""Normal agent maintenance selects an exact Bun only for lock refresh."""
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]


class AgentUpdateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dotfiles-agent-update-", dir="/tmp")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        deployment = self.source / "deployment"
        deployment.mkdir(parents=True)
        shutil.copy2(SOURCE / "deployment/update_versions.py", deployment / "update_versions.py")
        catalog = SOURCE / "deployment/common-tools.tsv"
        shutil.copy2(catalog, deployment / "common-tools.tsv")
        row = next(line for line in catalog.read_text().splitlines() if line.startswith("bun|"))
        self.pin = row.split("|")[1].split("==")[1]
        self.pins = deployment / "agents/providers.tsv"
        self.pins.parent.mkdir()
        self.original_pins = (SOURCE / "deployment/agents/providers.tsv").read_text()
        self.pins.write_text(self.original_pins)
        self.home = self.root / "home"
        self.common = self.home / ".local/bin"
        self.common.mkdir(parents=True)
        self.selected_bun = self.bun(self.common / "bun", "99.0.0")
        self.cached_bun = self.bun(self.root / "runtime/bun", self.pin)
        self.pixi = self.home / ".pixi/bin/pixi"
        self.pixi.parent.mkdir(parents=True)
        self.pixi_log = self.root / "pixi.json"
        self.actions = self.root / "actions.jsonl"
        self.bootstrap_log = self.root / "bootstrap.json"
        self.env = {"HOME": str(self.home), "PATH": "/usr/bin:/bin",
                    "TMPDIR": str(self.root), "DOTFILES_COMMON_BIN": str(self.common)}
        self.write_pixi()
        bootstrap = self.source / "bootstrap.sh"
        bootstrap.write_text("#!/bin/sh\nexec " + shlex.quote(sys.executable) + " -c " +
                             shlex.quote("import json,sys; from pathlib import Path; "
                                         f"Path({str(self.bootstrap_log)!r}).write_text(json.dumps(sys.argv[1:]))") +
                             ' "$@"\n')
        # Keep the real common_versions import while controlling only the two
        # updater CLI operations, so pin lookup exercises the production owner.
        guard = self.root / "update_guard.py"
        guard.write_text(
            "import json, subprocess, sys\nfrom pathlib import Path\n"
            f"sys.path.insert(0, {str(self.source)!r})\n"
            "from deployment.update_versions import agent_rows, common_versions\n"
            "args = sys.argv[1:]\n"
            f"with Path({str(self.actions)!r}).open('a') as log: log.write(json.dumps(args) + '\\n')\n"
            "if args[0] == 'upgrade-homebrew':\n"
            "    pass\n"
            "elif args[0] == 'propose-agents':\n"
            "    import os\n"
            "    name = 'qoder' if os.environ.get('NATIVE_PROPOSAL') else 'pi'\n"
            "    proposal = {'agents': {} if os.environ.get('EMPTY_PROPOSAL') else {name: '99.0.0'}}\n"
            "    Path(args[args.index('--output') + 1]).write_text(json.dumps(proposal))\n"
            "elif args[0] == 'refresh':\n"
            "    bun = Path(args[args.index('--bun') + 1])\n"
            "    root = Path(args[args.index('--root') + 1])\n"
            "    assert bun.is_absolute()\n"
            "    proposal = json.loads(Path(args[args.index('--proposal') + 1]).read_text())\n"
            "    if set(proposal['agents']) & agent_rows(root).keys():\n"
            "        assert subprocess.check_output([str(bun), '--version'], text=True).strip() == common_versions(root)['bun']\n"
            "    (root / 'deployment/agents/providers.tsv').write_text('refreshed pins\\n')\n"
            "else: raise SystemExit(98)\n")
        python = self.root / "python"
        python.write_text(
            "#!" + sys.executable + "\nimport os, sys\n"
            f"if len(sys.argv) > 2 and sys.argv[1] == {str(deployment / 'update_versions.py')!r}:\n"
            f"    os.execv(sys.executable, [sys.executable, {str(guard)!r}, *sys.argv[2:]])\n"
            "os.execv(sys.executable, [sys.executable, *sys.argv[1:]])\n")
        python.chmod(0o755)
        self.env["DOTFILES_PYTHON"] = str(python)
        self.command = self.common / "dotfiles-agents"
        template = (SOURCE / "dot_local/bin/executable_dotfiles-agents.tmpl").read_text()
        self.command.write_text(template.replace("{{ .chezmoi.sourceDir }}", str(self.source)))
        self.assertNotIn("{{", self.command.read_text())
        self.command.chmod(0o755)

    def bun(self, path, version):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\n[ \"$1\" = --version ] || exit 99\nprintf '%s\\n' " +
                        shlex.quote(version) + "\n")
        path.chmod(0o755)
        return path

    def write_pixi(self, *, result=None, status=0):
        self.pixi.write_text(
            "#!" + sys.executable + "\nimport json, sys\nfrom pathlib import Path\n"
            f"Path({str(self.pixi_log)!r}).write_text(json.dumps(sys.argv[1:]))\n"
            f"print({str(result if result is not None else self.cached_bun)!r})\n"
            f"raise SystemExit({status})\n")
        self.pixi.chmod(0o755)

    def update(self, selection="pi", **overrides):
        return subprocess.run(["/bin/bash", str(self.command), "update", selection],
                              cwd=self.root, env=dict(self.env, **overrides),
                              capture_output=True, text=True, timeout=30)

    def recorded_actions(self):
        return [json.loads(line) for line in self.actions.read_text().splitlines()]

    def assert_reinstalled(self, selection="pi"):
        self.assertEqual(json.loads(self.bootstrap_log.read_text()),
                         ["--source", str(self.source), "--agents-only", "--agents", selection])

    def test_newer_device_bun_uses_the_exact_cached_runtime_for_normal_update(self):
        result = self.update()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.pixi_log.read_text()),
                         ["exec", "--spec", f"bun=={self.pin}", "sh", "-c", "command -v bun"])
        self.assertEqual(self.recorded_actions()[0][0], "upgrade-homebrew")
        refresh = self.recorded_actions()[2]
        self.assertEqual(refresh[refresh.index("--bun") + 1], str(self.cached_bun))
        self.assertEqual(self.pins.read_text(), "refreshed pins\n")
        self.assertEqual(subprocess.check_output([str(self.selected_bun), "--version"], text=True).strip(),
                         "99.0.0")
        self.assert_reinstalled()

    def test_exact_selected_bun_refreshes_without_pixi(self):
        self.bun(self.selected_bun, self.pin)
        self.pixi.unlink()
        result = self.update()
        self.assertEqual(result.returncode, 0, result.stderr)
        refresh = self.recorded_actions()[2]
        self.assertEqual(refresh[refresh.index("--bun") + 1], str(self.selected_bun))
        self.assertFalse(self.pixi_log.exists())
        self.assert_reinstalled()

    def test_empty_proposal_never_acquires_a_lock_runtime(self):
        self.selected_bun.unlink()
        self.pixi.unlink()
        result = self.update(EMPTY_PROPOSAL="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.recorded_actions()), 2)
        self.assertFalse(self.pixi_log.exists())
        self.assertEqual(self.pins.read_text(), self.original_pins)
        self.assert_reinstalled()

    def test_native_only_proposal_refreshes_without_acquiring_bun(self):
        self.pixi.unlink()
        result = self.update("qoder", NATIVE_PROPOSAL="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.recorded_actions()), 3)
        refresh = self.recorded_actions()[2]
        self.assertEqual(refresh[refresh.index("--bun") + 1], str(self.selected_bun))
        self.assertFalse(self.pixi_log.exists())
        self.assertEqual(self.pins.read_text(), "refreshed pins\n")
        self.assert_reinstalled("qoder")

    def test_a_native_bump_that_drops_the_baseline_build_is_refused(self):
        # The installer falls back to the baseline Linux build on a host
        # without AVX and AVX2, so a release that drops it cannot be pinned.
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "dotfiles_update_versions", SOURCE / "deployment/update_versions.py")
        updater = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(updater)

        def manifest(version, baseline):
            files = [
                {"os": "darwin", "arch": "arm64",
                 "url": "https://example.invalid/qodercli-darwin-arm64.tar.gz",
                 "sha256": "a" * 64},
                {"os": "linux", "arch": "amd64",
                 "url": "https://example.invalid/qodercli-linux-x64.tar.gz",
                 "sha256": "b" * 64},
            ]
            if baseline:
                files.append({"os": "linux", "arch": "amd64-baseline",
                              "url": "https://example.invalid/qodercli-linux-x64-baseline.tar.gz",
                              "sha256": "c" * 64})
            return {"latest": version, "files": files}

        def fake_fetch(url, label):
            parts = [part for part in url.split("/") if part]
            version = parts[-2] if parts[-1] == "manifest.json" else parts[-1]
            return manifest(version, baseline=version == "1.1.82")

        updater._fetch_json = fake_fetch
        root = self.root / "refresh-root"
        shutil.copytree(SOURCE / "deployment", root / "deployment",
                        ignore=shutil.ignore_patterns("agent-payload", "__pycache__"))
        proposal = self.root / "native-proposal.json"
        proposal.write_text(json.dumps({"agents": {"qoder": "1.1.94"}}))
        with self.assertRaises(Exception) as raised:
            updater.refresh(root, proposal, self.selected_bun)
        self.assertIn("dropped the linux amd64-baseline build", str(raised.exception))

    def test_the_homebrew_upgrade_brings_the_selected_clients_up_to_date(self):
        # Homebrew owns an installed formula or cask. The update upgrades it
        # before the deployment adopts it, so the launcher follows.
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "dotfiles_update_versions", SOURCE / "deployment/update_versions.py")
        updater = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(updater)

        calls = []
        original = subprocess.run

        def fake_run(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="opencode-v2 2.3.2\n", stderr="")

        updater.subprocess.run = fake_run
        try:
            upgraded = updater.homebrew_upgrade(SOURCE, "opencode", "brew")
        finally:
            updater.subprocess.run = original
        self.assertEqual(upgraded, ["opencode (opencode-v2)"])
        self.assertEqual(calls, [["brew", "list", "--versions", "opencode-v2"],
                                  ["brew", "upgrade", "opencode-v2"]])

    def test_a_homebrew_client_that_is_not_installed_is_not_installed(self):
        # The deployment adopts a Homebrew client and never installs one, so
        # the update must not install it either.
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "dotfiles_update_versions", SOURCE / "deployment/update_versions.py")
        updater = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(updater)

        calls = []
        original = subprocess.run

        def fake_run(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="")

        updater.subprocess.run = fake_run
        try:
            upgraded = updater.homebrew_upgrade(SOURCE, "opencode", "brew")
        finally:
            updater.subprocess.run = original
        self.assertEqual(upgraded, [])
        self.assertEqual(calls, [["brew", "list", "--versions", "opencode-v2"]])

    def test_a_failing_homebrew_upgrade_is_reported(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "dotfiles_update_versions", SOURCE / "deployment/update_versions.py")
        updater = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(updater)

        original = subprocess.run

        def fake_run(command, **kwargs):
            if command[:3] == ["brew", "list", "--versions"]:
                return subprocess.CompletedProcess(command, 0, stdout="opencode-v2 2.3.2\n", stderr="")
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="brew refused")

        updater.subprocess.run = fake_run
        try:
            with self.assertRaises(Exception) as raised:
                updater.homebrew_upgrade(SOURCE, "opencode", "brew")
        finally:
            updater.subprocess.run = original
        self.assertIn("cannot upgrade the Homebrew formula opencode-v2", str(raised.exception))

    def test_status_reports_a_shadowed_bun_global_copy(self):
        registry = self.home / ".bun/install/global/node_modules/@earendil-works/pi-coding-agent"
        registry.mkdir(parents=True)
        (registry / "package.json").write_text(json.dumps(
            {"name": "@earendil-works/pi-coding-agent", "version": "9.9.9",
             "bin": {"pi": "dist/bundle/cli.js"}}))
        result = subprocess.run(["/bin/bash", str(self.command), "status", "pi"],
                                cwd=self.root, env=dict(self.env),
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("GLOBAL COPIES", result.stdout)
        self.assertIn("@earendil-works/pi-coding-agent 9.9.9", result.stdout)
        self.assertIn("bins: pi", result.stdout)
        self.assertIn("bun remove -g @earendil-works/pi-coding-agent", result.stdout)

    def test_status_uses_the_device_owned_version(self):
        override = self.home / ".config/dotfiles/versions.tsv"
        override.parent.mkdir(parents=True)
        override.write_text("# device\nagent|pi|8.8.8\n")
        result = subprocess.run(["/bin/bash", str(self.command), "status", "pi"],
                                cwd=self.root, env=dict(self.env),
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("8.8.8", result.stdout)
        self.assertIn("device-owned version", result.stdout)
        self.assertNotIn("mismatch", result.stdout)

    def test_status_does_not_confuse_ledger_intent_and_failed_path_probe(self):
        ledger = self.home / ".local/state/dotfiles/agents.lock.tsv"
        ledger.parent.mkdir(parents=True)
        # Three fields predate the catalog policy column.
        ledger.write_text("pi|bun|1.5.0\n")
        path = self.root / "shadow tools"
        binary = self.bun(path / "pi", "1.5.0")
        binary.write_text(binary.read_text() + "exit 27\n")
        self.bun(self.common / "pi", "1.5.0")
        (self.home / ".env_core").write_text(f'export PATH={shlex.quote(str(self.common))}:"$PATH"\n')
        report = subprocess.run([str(self.command), "status", "pi"], cwd=self.root,
                                env=dict(self.env, PATH=f"{path}:/usr/bin:/bin"),
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(report.returncode, 0, report.stderr)
        self.assertIn("last apply: bun 1.5.0", report.stdout)
        self.assertIn(f"path: {binary}", report.stdout)
        self.assertIn("unverified (probe exited 27)", report.stdout)
        self.assertNotIn("live: installed", report.stdout)

    def test_missing_managed_pixi_fails_before_refresh_or_pin_changes(self):
        self.pixi.unlink()
        result = self.update()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("managed Pixi", result.stderr)
        self.assertIn(self.pin, result.stderr)
        self.assertEqual(len(self.recorded_actions()), 2)
        self.assertEqual(self.pins.read_text(), self.original_pins)
        self.assertFalse(self.bootstrap_log.exists())

    def test_failed_or_invalid_pixi_runtime_leaves_pins_intact(self):
        wrong = self.bun(self.root / "wrong/bun", "99.0.0")
        for name, result_path, status in (
                ("failed exec", self.cached_bun, 29), ("relative path", "relative/bun", 0),
                ("missing executable", self.root / "missing/bun", 0), ("wrong version", wrong, 0)):
            with self.subTest(case=name):
                self.write_pixi(result=result_path, status=status)
                result = self.update()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("lock refresh", result.stderr)
                self.assertEqual(self.pins.read_text(), self.original_pins)
                self.assertFalse(self.bootstrap_log.exists())
                self.assertTrue(all(action[0] in ("propose-agents", "upgrade-homebrew")
                                    for action in self.recorded_actions()))


if __name__ == "__main__":
    unittest.main()
