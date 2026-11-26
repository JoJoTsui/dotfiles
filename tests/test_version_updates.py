"""Local tests for the proposal-driven version refresh transaction."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from deployment.update_versions import (
    MANAGER_DIGEST_SOURCES,
    NativeBaselineUnavailable,
    VersionError,
    agent_rows,
    agent_version_overrides,
    check,
    common_versions,
    main,
    manager_digest_rows,
    native_agent_rows,
    node_satisfies,
    propose_agents,
    refresh,
)

SOURCE = Path(__file__).resolve().parents[1]


class VersionUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-version-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        shutil.copytree(SOURCE / "deployment", self.root / "deployment",
                        ignore=shutil.ignore_patterns("agent-payload"))

    def proposal(self, value):
        path = Path(self.temporary.name) / "proposal.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_current_version_sources_are_consistent(self):
        counts = check(SOURCE)
        self.assertEqual(counts["agents"], 9)
        self.assertEqual(counts["nativeAgents"], 1)
        self.assertGreater(counts["commonPins"], 20)
        self.assertGreater(counts["bundlePins"], 50)
        self.assertEqual(counts["windowsAssets"], 8)

    def test_node_engine_ranges_cover_supported_npm_forms_and_reject_unknown_syntax(self):
        self.assertTrue(node_satisfies("24.21.0", ">=20.19.0 <25"))
        self.assertTrue(node_satisfies("24.21.0", "^18 || ^20 || >=22.0.0"))
        self.assertTrue(node_satisfies("24.21.0", "24.x"))
        self.assertFalse(node_satisfies("24.21.0", "^20.0.0"))
        with self.assertRaises(VersionError):
            node_satisfies("24.21.0", "20.0.0 - 22.0.0")

    def test_common_refresh_is_reviewable_and_idempotent(self):
        original = common_versions(self.root)["uv"]
        assets = self.root / "deployment/windows-assets.json"
        before = assets.read_bytes()
        changed = refresh(self.root, self.proposal({"common": {"uv": "99.1.0"}}), Path("unused"))
        self.assertIn(Path("deployment/common-tools.tsv"), changed)
        # A proposal without Windows assets must not rewrite that catalog.
        self.assertNotIn(Path("deployment/windows-assets.json"), changed)
        self.assertEqual(assets.read_bytes(), before)
        self.assertEqual(common_versions(self.root)["uv"], "99.1.0")
        self.assertNotEqual(original, common_versions(self.root)["uv"])
        self.assertEqual(check(self.root)["commonPins"], check(SOURCE)["commonPins"])
        self.assertEqual(refresh(self.root, self.proposal({"common": {"uv": "99.1.0"}}), Path("unused")), [])

    def test_atuin_refresh_changes_catalogs_without_an_importer_source(self):
        self.assertFalse((self.root / "dot_local/lib/dotfiles/history.py").exists())
        candidate = self.proposal({
            "common": {"atuin": "99.1.0"},
            "windowsAssets": {"atuin": {
                "version": "99.1.0", "url": "https://example.invalid/atuin-99.1.0.zip",
                "sha256": "a" * 64,
            }},
        })
        changed = refresh(self.root, candidate, Path("unused"))
        self.assertEqual(set(changed), {Path("deployment/common-tools.tsv"),
                                        Path("deployment/windows-assets.json")})
        self.assertEqual(common_versions(self.root)["atuin"], "99.1.0")
        self.assertEqual(refresh(self.root, candidate, Path("unused")), [])

    def test_profile_renders_catalog_atuin_pin_for_every_platform(self):
        chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        if not chezmoi:
            self.skipTest("profile rendering requires chezmoi")
        catalog = self.root / "deployment/common-tools.tsv"
        original = common_versions(self.root)["atuin"]
        catalog.write_text(catalog.read_text().replace(f"atuin=={original}", "atuin==99.1.0"))
        config = self.root / "chezmoi.toml"
        config.write_text("")
        template = (SOURCE / "dot_config/dotfiles/profile.json.tmpl").read_text()
        importer = SOURCE / "dot_local/lib/dotfiles/history.py"
        before = importer.read_bytes()
        for platform in ("linux", "macos", "windows"):
            with self.subTest(platform=platform):
                result = subprocess.run([
                    chezmoi, "--source", str(self.root), "--destination", str(self.root / "home"),
                    "--config", str(config), "--cache", str(self.root / "cache"),
                    "--persistent-state", str(self.root / "state.boltdb"),
                    "--override-data", json.dumps({"platform": platform, "role": "workstation",
                                                     "arch": "aarch64", "bundles": []}),
                    "execute-template", template,
                ], env={"HOME": str(self.root / "original"), "PATH": os.defpath},
                    capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["atuinVersion"], "99.1.0")
        self.assertEqual(importer.read_bytes(), before)

    def test_agent_refresh_updates_catalog_manifest_and_lock_using_isolated_bun(self):
        name = "pi"
        current = common_versions(self.root)["bun"]
        package = agent_rows(self.root)[name]["package"]
        fake_bun = Path(self.temporary.name) / "bun"
        fake_bun.write_text(
            "#!" + sys.executable + "\n"
            "import json, pathlib, re, sys\n"
            "if sys.argv[1] == '--version': print(" + repr(current) + "); raise SystemExit(0)\n"
            "project = pathlib.Path(sys.argv[sys.argv.index('--cwd') + 1])\n"
            "manifest = json.loads((project / 'package.json').read_text())\n"
            "path = project / 'bun.lock'\n"
            "lock = json.loads(re.sub(r',(?=\\s*[}\\]])', '', path.read_text()))\n"
            "package, version = next(iter(manifest['dependencies'].items()))\n"
            "lock['workspaces']['']['dependencies'] = manifest['dependencies']\n"
            "lock['packages'][package][0] = f'{package}@{version}'\n"
            "path.write_text(json.dumps(lock) + '\\n')\n"
        , encoding="utf-8")
        fake_bun.chmod(0o755)
        with patch("deployment.update_versions.npm_metadata", return_value={
            "version": "99.1.0", "engines": {"node": ">=20.0.0"}
        }) as metadata:
            candidate = self.proposal({"agents": {name: "99.1.0"}})
            changed = refresh(self.root, candidate, fake_bun)
            self.assertEqual(refresh(self.root, candidate, fake_bun), [])
        self.assertEqual(metadata.call_count, 2)
        metadata.assert_called_with(package, "99.1.0")
        self.assertIn(Path(f"deployment/agents/{name}/package.json"), changed)
        self.assertIn(Path(f"deployment/agents/{name}/bun.lock"), changed)
        self.assertEqual(agent_rows(self.root)[name]["version"], "99.1.0")
        self.assertEqual(check(self.root)["agents"], 9)

    def test_an_agent_pin_moves_the_deployment_owned_record_and_keeps_the_floor(self):
        # The frozen Bun project carries the agent's pin and moves with it.
        # The macOS Homebrew record carries a floor: Homebrew owns the
        # installed version, so the deployment keeps accepting it.
        name = "codex"
        current = common_versions(self.root)["bun"]
        fake_bun = Path(self.temporary.name) / "bun"
        fake_bun.write_text(
            "#!" + sys.executable + "\n"
            "import json, pathlib, re, sys\n"
            "if sys.argv[1] == '--version': print(" + repr(current) + "); raise SystemExit(0)\n"
            "project = pathlib.Path(sys.argv[sys.argv.index('--cwd') + 1])\n"
            "manifest = json.loads((project / 'package.json').read_text())\n"
            "path = project / 'bun.lock'\n"
            "lock = json.loads(re.sub(r',(?=\\s*[}\\]])', '', path.read_text()))\n"
            "package, version = next(iter(manifest['dependencies'].items()))\n"
            "lock['workspaces']['']['dependencies'] = manifest['dependencies']\n"
            "lock['packages'][package][0] = f'{package}@{version}'\n"
            "path.write_text(json.dumps(lock) + '\\n')\n"
        , encoding="utf-8")
        fake_bun.chmod(0o755)
        with patch("deployment.update_versions.npm_metadata", return_value={
            "version": "99.1.0", "engines": {"node": ">=16.0.0"}
        }):
            candidate = self.proposal({"agents": {name: "99.1.0"}})
            changed = refresh(self.root, candidate, fake_bun)
        self.assertIn(Path("deployment/agents/providers.tsv"), changed)
        records = [line.split("|") for line in
                   (self.root / "deployment/agents/providers.tsv").read_text(encoding="utf-8").splitlines()
                   if line and not line.startswith("#")]
        owned = [record for record in records if record[0] == name and record[5] == "exact"]
        floor = [record for record in records if record[0] == name and record[5] == "floor"]
        self.assertEqual([record[4] for record in owned], ["99.1.0"])
        self.assertEqual([record[4] for record in floor], ["0.169.0"])
        self.assertEqual(len([record for record in records if record[0] == name]), 2)
        self.assertEqual(check(self.root)["agents"], 9)

    def test_native_agent_refresh_rewrites_only_the_pin_and_validates_the_release(self):
        name = "qoder"
        manifest = native_agent_rows(self.root)[name]["manifest"]
        with patch("deployment.update_versions.native_metadata", return_value={"latest": "99.1.0"}) as metadata:
            candidate = self.proposal({"agents": {name: "99.1.0"}})
            changed = refresh(self.root, candidate, Path("unused"))
            self.assertEqual(refresh(self.root, candidate, Path("unused")), [])
        self.assertIn(Path("deployment/agents/providers.tsv"), changed)
        metadata.assert_called_with(manifest, "99.1.0")
        self.assertEqual(native_agent_rows(self.root)[name]["version"], "99.1.0")
        self.assertFalse((self.root / "deployment/agents/qoder").exists())

    def test_manager_refresh_moves_the_digests_with_the_version(self):
        digests = {target: "a" * 64 for target in MANAGER_DIGEST_SOURCES["chezmoi"]["targets"]}
        with patch("deployment.update_versions.manager_digests", return_value=digests) as published:
            candidate = self.proposal({
                "managers": {"chezmoi": "99.1.0"},
                "windowsAssets": {"chezmoi": {
                    "version": "99.1.0", "url": "https://example.invalid/chezmoi-99.1.0.zip",
                    "sha256": "a" * 64,
                }},
            })
            changed = refresh(self.root, candidate, Path("unused"))
        self.assertIn(Path("deployment/managers.sh"), changed)
        published.assert_called_once_with("chezmoi", "99.1.0")
        rows = manager_digest_rows((self.root / "deployment/managers.sh").read_text(encoding="utf-8"))
        self.assertEqual(set(rows["chezmoi"]), set(digests))
        for line in rows["chezmoi"].values():
            self.assertIn("a" * 64, line[1])

    def test_a_manager_without_every_target_digest_is_rejected(self):
        managers = self.root / "deployment/managers.sh"
        text = managers.read_text(encoding="utf-8")
        managers.write_text(text.replace(
            "        macos-aarch64) target=aarch64-apple-darwin; digest=", "        macos-aarch64) target=aarch64-apple-darwin; skipped=", 1))
        with self.assertRaisesRegex(VersionError, "digest rows do not cover every supported target"):
            check(self.root)

    def test_propose_agents_reports_only_changed_pins(self):
        def latest(package):
            if package == "@moonshot-ai/kimi-code":
                return "99.0.0"
            return next(item["version"] for item in agent_rows(self.root).values()
                        if item["package"] == package)

        with patch("deployment.update_versions.npm_latest", side_effect=latest), \
                patch("deployment.update_versions.native_latest", return_value="99.0.0"):
            proposal = propose_agents(self.root, "kimi,qoder")
        self.assertEqual(proposal, {"agents": {"kimi": "99.0.0", "qoder": "99.0.0"}})
        with patch("deployment.update_versions.npm_latest", return_value="1.0.0"), \
                patch("deployment.update_versions.native_latest", return_value="1.0.0"):
            self.assertEqual(propose_agents(self.root, "none"), {"agents": {}})

    def test_propose_agents_skips_a_native_release_without_the_baseline_build(self):
        def latest(package):
            if package == "@moonshot-ai/kimi-code":
                return "99.0.0"
            return next(item["version"] for item in agent_rows(self.root).values()
                        if item["package"] == package)

        errors = StringIO()
        with patch("deployment.update_versions.npm_latest", side_effect=latest), \
                patch("deployment.update_versions.native_latest",
                      side_effect=NativeBaselineUnavailable("99.0.0")), \
                redirect_stderr(errors):
            proposal = propose_agents(self.root, "kimi,qoder")

        self.assertEqual(proposal, {"agents": {"kimi": "99.0.0"}})
        self.assertIn("qoder 99.0.0 dropped the linux amd64-baseline build", errors.getvalue())
        self.assertIn("keeping the repository pin", errors.getvalue())

    def test_propose_agents_skips_device_owned_versions(self):
        with patch("deployment.update_versions.npm_latest", return_value="99.0.0"), \
                patch("deployment.update_versions.native_latest", return_value="99.0.0") as native:
            proposal = propose_agents(self.root, "kimi,qoder", {"qoder": "1.1.97"})
        self.assertEqual(proposal, {"agents": {"kimi": "99.0.0"}})
        native.assert_not_called()

    def test_agent_version_overrides_reads_the_device_manifest(self):
        path = Path(self.temporary.name) / "versions.tsv"
        path.write_text(
            "# device versions\n"
            "agent|qoder|1.1.97\n"
            "tool|ruff|0.14.0\n"
            "cli|gh|2.80.0\n",
            encoding="utf-8",
        )
        self.assertEqual(agent_version_overrides(path), {"qoder": "1.1.97"})
        path.write_text("agent|qoder|1.1.97\nagent|qoder|1.1.98\n", encoding="utf-8")
        with self.assertRaisesRegex(VersionError, "duplicate agent version override"):
            agent_version_overrides(path)

    def test_propose_cli_reports_updates_current_and_device_owned_agents(self):
        output = StringIO()
        proposal_path = Path(self.temporary.name) / "proposal.json"
        override_path = Path(self.temporary.name) / "versions.tsv"
        with patch("deployment.update_versions.agent_version_overrides", return_value={"qoder": "1.1.97"}), \
                patch("deployment.update_versions.propose_agents", return_value={"agents": {"kimi": "99.0.0"}}), \
                redirect_stdout(output):
            status = main([
                "propose-agents", "--root", str(self.root), "--selection", "kimi,pi,qoder",
                "--overrides", str(override_path), "--output", str(proposal_path),
            ])
        self.assertEqual(status, 0)
        report = output.getvalue()
        current_kimi = agent_rows(self.root)["kimi"]["version"]
        current_pi = agent_rows(self.root)["pi"]["version"]
        self.assertIn("resolved 1 repository agent update(s):", report)
        self.assertIn(f"kimi {current_kimi} -> 99.0.0", report)
        self.assertIn(f"already up-to-date: pi {current_pi}", report)
        self.assertIn("no repository update: qoder 1.1.97 (device-owned)", report)
        self.assertNotIn("dropped the linux", report)

    def test_propose_cli_does_not_infer_device_overrides_without_an_explicit_path(self):
        output = StringIO()
        proposal_path = Path(self.temporary.name) / "proposal.json"
        with patch("deployment.update_versions.agent_version_overrides") as overrides, \
                patch("deployment.update_versions.propose_agents", return_value={"agents": {}}) as propose, \
                redirect_stdout(output):
            status = main([
                "propose-agents", "--root", str(self.root), "--selection", "none",
                "--output", str(proposal_path),
            ])
        self.assertEqual(status, 0)
        overrides.assert_not_called()
        propose.assert_called_once_with(self.root.resolve(), "none", {})

    def test_homebrew_cli_reports_changed_current_and_uninstalled_packages(self):
        output = StringIO()
        report = {
            "upgraded": ["opencode (opencode-v2) 2.3.1 -> 2.3.2"],
            "current": ["pi (pi-coding-agent) 1.6.0"],
            "notInstalled": ["claude (claude-code)"],
        }
        with patch("deployment.update_versions.shutil.which", return_value="/opt/homebrew/bin/brew"), \
                patch("deployment.update_versions.homebrew_upgrade", return_value=report), \
                redirect_stdout(output):
            status = main([
                "upgrade-homebrew", "--root", str(self.root),
                "--selection", "opencode,pi,claude", "--brew", "brew",
            ])
        self.assertEqual(status, 0)
        text = output.getvalue()
        self.assertIn("upgraded 1 Homebrew-managed client(s):", text)
        self.assertIn("opencode (opencode-v2) 2.3.1 -> 2.3.2", text)
        self.assertIn("already up-to-date 1 Homebrew-managed client(s):", text)
        self.assertIn("pi (pi-coding-agent) 1.6.0", text)
        self.assertIn("no Homebrew update (package not installed):", text)
        self.assertIn("claude (claude-code)", text)

    def test_windows_manager_refresh_keeps_exception_and_bootstrap_pins_in_sync(self):
        proposal = self.proposal({
            "managers": {"pixi": "0.82.0"},
            "windowsAssets": {"pixi": {
                "version": "0.82.0", "url": "https://example.invalid/pixi-0.82.0.zip",
                "sha256": "a" * 64,
            }},
        })
        digests = {target: "b" * 64 for target in MANAGER_DIGEST_SOURCES["pixi"]["targets"]}
        with patch("deployment.update_versions.manager_digests", return_value=digests):
            changed = refresh(self.root, proposal, Path("unused"))
        self.assertIn(Path("deployment/common.sh"), changed)
        self.assertIn(Path("deployment/windows-assets.json"), changed)
        self.assertIn("PIXI_VERSION=0.82.0", (self.root / "deployment/common.sh").read_text())
        assets = json.loads((self.root / "deployment/windows-assets.json").read_text())
        pixi = next(asset for asset in assets if asset["name"] == "pixi")
        self.assertEqual(pixi["version"], "0.82.0")
        self.assertEqual(check(self.root)["windowsAssets"], 8)

    def test_invalid_candidate_does_not_change_source_files(self):
        original = (self.root / "deployment/common-tools.tsv").read_bytes()
        with self.assertRaisesRegex(VersionError, "unknown common package"):
            refresh(self.root, self.proposal({"common": {"not-a-tool": "1.2.3"}}), Path("unused"))
        self.assertEqual((self.root / "deployment/common-tools.tsv").read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
