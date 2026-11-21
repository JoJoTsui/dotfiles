"""The benchmark records comparable samples through public bootstrap."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from pins import agent_pins, common_pin


SOURCE = Path(__file__).resolve().parents[1]


class DeploymentBaselineTests(unittest.TestCase):
    def test_toolchain_assisted_benchmark_captures_repeatable_workloads(self):
        chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        if not chezmoi:
            self.skipTest("benchmark fixture requires Chezmoi")
        with tempfile.TemporaryDirectory(prefix="dotfiles-benchmark-test-") as temporary:
            root = Path(temporary).resolve()
            bun = root / "bun"
            pins = agent_pins()
            bun.write_text(
                f"#!{sys.executable}\n"
                "import sys\nfrom pathlib import Path\n"
                "if sys.argv[1:] == ['--version']:\n"
                f"    print({common_pin('bun')!r}); raise SystemExit\n"
                "if '--cwd' in sys.argv:\n"
                "    project = Path(sys.argv[sys.argv.index('--cwd') + 1])\n"
                f"    versions = {{'pi': {pins['pi']['version']!r}, 'codegraph': {pins['codegraph']['version']!r}}}\n"
                "    launcher = project / 'node_modules/.bin' / project.name\n"
                "    launcher.parent.mkdir(parents=True, exist_ok=True)\n"
                "    launcher.write_text('#!/bin/sh\\necho ' + versions[project.name] + '\\n')\n"
                "    launcher.chmod(0o755)\n"
            )
            bun.chmod(0o755)
            node = root / "node"
            node.write_text(f"#!/bin/sh\necho v{common_pin('nodejs')}\n")
            node.chmod(0o755)
            report = root / "report"
            execution = "native-macos" if sys.platform == "darwin" else "native-linux"
            result = subprocess.run(
                [sys.executable, str(SOURCE / "tests/deployment_baseline.py"),
                 "--execution", execution, "--samples", "1", "--report", str(report),
                 "--chezmoi", chezmoi, "--bun", str(bun), "--node", str(node)],
                cwd=SOURCE, capture_output=True, text=True, timeout=120,
            )
            baseline = report / "baseline.json"
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr +
                             (baseline.read_text() if baseline.exists() else ""))
            data = json.loads(baseline.read_text())
            self.assertEqual(data["scope"], "toolchain-assisted agents-only")
            self.assertEqual(set(data["workloads"]), {"fresh", "reapply", "single-agent"})
            for workload in data["workloads"].values():
                sample, = workload
                self.assertEqual(sample["status"], "passed")
                self.assertGreater(sample["time_to_usable_seconds"], 0)
                self.assertEqual(sample["diagnostics"]["exit_code"], 0)
                self.assertEqual(sample["started_steps"], [
                    "install-managers", "apply-source", "apply-source.skills",
                    "apply-source.agent-payload", "apply-source.skills-prune",
                    "apply-source.client-settings", "apply-source.macos-discovery", "install-agents",
                ])
                self.assertIn("observed_retry_lines", sample["traffic_observations"])
            self.assertGreater(data["workloads"]["fresh"][0]["owned_mutations"]["added"], 0)
            self.assertEqual(data["workloads"]["reapply"][0]["owned_mutations"]["added"], 0)


if __name__ == "__main__":
    unittest.main()
