"""Skills-only Caveman deployment: no gateway ownership or lifecycle actions."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from fixtures.skills import write_skill_library

SOURCE = Path(__file__).resolve().parents[1]


class CavemanRetirementTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-caveman-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        if not self.chezmoi:
            self.skipTest("actual source apply requires chezmoi")
        self.skills = write_skill_library(self.root / "skills-fixture")
        caveman = self.skills / "caveman"
        caveman.mkdir()
        (caveman / "SKILL.md").write_text(
            "---\nname: caveman\ndescription: standalone voice fixture\n---\nUse concise prose.\n")

    def deploy(self, home, platform):
        return subprocess.run(
            ["/bin/bash", str(SOURCE / "bootstrap.sh"), "--source", str(SOURCE),
             "--home", str(home), "--platform", platform, "--role", "workstation",
             "--apply-only"],
            cwd=SOURCE,
            env={"HOME": str(self.root / "original"), "PATH": "/usr/bin:/bin",
                 "DOTFILES_CHEZMOI_BIN": self.chezmoi,
                 "DOTFILES_SKILLS_DIR": str(self.skills)},
            capture_output=True, text=True, timeout=180,
        )

    def test_fresh_apply_does_not_create_gateway_configuration(self):
        for platform in ("linux", "macos"):
            with self.subTest(platform=platform):
                home = self.root / platform
                result = self.deploy(home, platform)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse((home / ".caveman").exists())
                baseline = home / ".local/state/dotfiles/client-settings/caveman-config.json"
                self.assertFalse(baseline.exists())
                self.assertTrue((home / ".agents/skills/caveman/SKILL.md").is_file())

    def test_reapply_preserves_gateway_files_and_never_executes_its_binaries(self):
        for platform in ("linux", "macos"):
            with self.subTest(platform=platform):
                home = self.root / platform
                gateway = home / ".caveman"
                (gateway / "run").mkdir(parents=True)
                (gateway / "bin").mkdir()
                config = gateway / "caveman.yaml"
                # A different provider URL forces the old owned merge to change it.
                config.write_text("# device-owned formatting\ncompat:\n  minimax-cn:\n    base_url: https://device.invalid/anthropic\n")
                state = gateway / "run/8787.json"
                # A stale run file used to be enough to revive a stopped gateway.
                state.write_text(json.dumps({"pid": 99999999, "listen": "127.0.0.1:8787",
                                             "mode": "compress"}))
                os.utime(state, (1000000000, 1000000000))
                os.utime(config, (1000000010, 1000000010))
                baseline = home / ".local/state/dotfiles/client-settings/caveman-config.json"
                baseline.parent.mkdir(parents=True)
                baseline.write_text('{"compat":{"minimax-cn":{"base_url":"https://device.invalid/anthropic"}}}\n')
                cli = home / ".pixi/envs/nodejs/bin/caveman"
                cli.parent.mkdir(parents=True)
                marker = home / "gateway-invoked"
                for binary in (gateway / "bin/caveman-proxy", cli):
                    binary.write_text('#!/bin/sh\nprintf invoked > "$HOME/gateway-invoked"\nexit 1\n')
                    binary.chmod(0o755)
                paths = (config, state, baseline, gateway / "bin/caveman-proxy", cli)
                before = {path: (path.read_bytes(), path.stat().st_mtime_ns,
                                 path.stat().st_mode) for path in paths}
                for _ in range(2):
                    result = self.deploy(home, platform)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertFalse(marker.exists())
                    for path, expected in before.items():
                        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns,
                                          path.stat().st_mode), expected, str(path))
                self.assertTrue((home / ".agents/skills/caveman/SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
