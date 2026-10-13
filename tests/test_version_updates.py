"""Local tests for the proposal-driven version refresh transaction."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deployment.update_versions import (
    VersionError,
    agent_rows,
    check,
    common_versions,
    node_satisfies,
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
        self.assertEqual(counts["agents"], 6)
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
        changed = refresh(self.root, self.proposal({"common": {"uv": "99.1.0"}}), Path("unused"))
        self.assertIn(Path("deployment/common-tools.tsv"), changed)
        self.assertEqual(common_versions(self.root)["uv"], "99.1.0")
        self.assertNotEqual(original, common_versions(self.root)["uv"])
        self.assertEqual(check(self.root)["commonPins"], check(SOURCE)["commonPins"])
        self.assertEqual(refresh(self.root, self.proposal({"common": {"uv": "99.1.0"}}), Path("unused")), [])

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
        self.assertEqual(check(self.root)["agents"], 6)

    def test_windows_manager_refresh_keeps_exception_and_bootstrap_pins_in_sync(self):
        proposal = self.proposal({
            "managers": {"pixi": "0.82.0"},
            "windowsAssets": {"pixi": {
                "version": "0.82.0", "url": "https://example.invalid/pixi-0.82.0.zip",
                "sha256": "a" * 64,
            }},
        })
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
