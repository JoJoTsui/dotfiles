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
        self.pins = deployment / "agents/catalog.tsv"
        self.pins.parent.mkdir()
        self.original_pins = (SOURCE / "deployment/agents/catalog.tsv").read_text()
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
            "if args[0] == 'propose-agents':\n"
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
            "    (root / 'deployment/agents/catalog.tsv').write_text('refreshed pins\\n')\n"
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
        refresh = self.recorded_actions()[1]
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
        refresh = self.recorded_actions()[1]
        self.assertEqual(refresh[refresh.index("--bun") + 1], str(self.selected_bun))
        self.assertFalse(self.pixi_log.exists())
        self.assert_reinstalled()

    def test_empty_proposal_never_acquires_a_lock_runtime(self):
        self.selected_bun.unlink()
        self.pixi.unlink()
        result = self.update(EMPTY_PROPOSAL="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.recorded_actions()), 1)
        self.assertFalse(self.pixi_log.exists())
        self.assertEqual(self.pins.read_text(), self.original_pins)
        self.assert_reinstalled()

    def test_native_only_proposal_refreshes_without_acquiring_bun(self):
        self.pixi.unlink()
        result = self.update("qoder", NATIVE_PROPOSAL="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.recorded_actions()), 2)
        refresh = self.recorded_actions()[1]
        self.assertEqual(refresh[refresh.index("--bun") + 1], str(self.selected_bun))
        self.assertFalse(self.pixi_log.exists())
        self.assertEqual(self.pins.read_text(), "refreshed pins\n")
        self.assert_reinstalled("qoder")

    def test_missing_managed_pixi_fails_before_refresh_or_pin_changes(self):
        self.pixi.unlink()
        result = self.update()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("managed Pixi", result.stderr)
        self.assertIn(self.pin, result.stderr)
        self.assertEqual(len(self.recorded_actions()), 1)
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
                self.assertTrue(all(action[0] == "propose-agents" for action in self.recorded_actions()))


if __name__ == "__main__":
    unittest.main()
