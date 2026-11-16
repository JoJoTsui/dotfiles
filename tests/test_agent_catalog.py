"""The per-agent provider catalog is the only source of agent installation data."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
CATALOG = "deployment/agents/providers.tsv"
PLATFORMS = ("linux", "macos", "wsl")
POWERSHELL = os.environ.get("DOTFILES_TEST_POWERSHELL") or shutil.which("pwsh") or shutil.which("powershell")


class ProviderCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-agent-catalog-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "device"
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("DOTFILES_", "XDG_", "BUN_", "PIXI_", "UV_", "NPM_", "ATUIN_",
                                           "CARGO_", "RUSTUP_", "KIMI_", "PI_", "OPENCODE_", "CODEX_", "CLAUDE_"))
                    and key not in ("GLM_API_TOKEN", "KIMI_API_KEY", "GLM_BASE_URL", "HTTP_PROXY_URL",
                                    "NODE_OPTIONS", "ENV", "BASH_ENV", "ANTHROPIC_AUTH_TOKEN", "CONTEXT7_TOKEN")}
        self.env.update(HOME=str(self.root / "original"), PATH="/usr/bin:/bin")

    def plan(self, platform, source=SOURCE, *arguments, home=None):
        return subprocess.run(["/bin/bash", str(Path(source) / "bootstrap.sh"),
                               "--home", str(home or self.home), "--platform", platform, "--plan", *arguments],
                              cwd=source, env=self.env, capture_output=True, text=True, timeout=60)

    def catalog_records(self, source=SOURCE):
        records = []
        for line in (Path(source) / CATALOG).read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            records.append(line.split("|"))
        return records

    def source_copy(self, name="source"):
        """A writable source tree whose agent catalog the test can break."""
        source = self.root / name.replace("/", "-")
        if source.exists():
            shutil.rmtree(source)
        source.mkdir()
        shutil.copy2(SOURCE / "bootstrap.sh", source / "bootstrap.sh")
        shutil.copy2(SOURCE / ".chezmoi.toml.tmpl", source / ".chezmoi.toml.tmpl")
        shutil.copytree(SOURCE / "deployment", source / "deployment")
        return source

    def write_catalog(self, source, records):
        path = Path(source) / CATALOG
        header = [line for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("#")]
        body = ["|".join(record) for record in records]
        path.write_text("\n".join(header + body) + "\n", encoding="utf-8")

    def test_one_catalog_backs_both_bootstrap_adapters(self):
        self.assertTrue((SOURCE / CATALOG).is_file())
        self.assertFalse((SOURCE / "deployment/agents/catalog.tsv").exists())
        self.assertFalse((SOURCE / "deployment/agents/native.tsv").exists())
        for adapter in ("bootstrap.ps1", "deployment/agents.sh"):
            text = (SOURCE / adapter).read_text(encoding="utf-8")
            with self.subTest(adapter=adapter):
                self.assertIn(CATALOG, text)
                self.assertNotIn("deployment/agents/catalog.tsv", text)
                self.assertNotIn("deployment/agents/native.tsv", text)
        # The native Windows adapter resolves its records through the shared
        # reader instead of naming a catalog of its own.
        windows = (SOURCE / "deployment/windows.ps1").read_text(encoding="utf-8")
        self.assertIn("Get-AgentCatalog", windows)
        self.assertNotIn("deployment/agents/catalog.tsv", windows)
        self.assertNotIn("deployment/agents/native.tsv", windows)

    def test_plan_names_provider_version_commands_and_herdr_kind_for_every_platform(self):
        expected = {record[0]: record for record in self.catalog_records()}
        for platform in PLATFORMS:
            with self.subTest(platform=platform):
                result = self.plan(platform)
                self.assertEqual(result.returncode, 0, result.stderr)
                plan = json.loads(result.stdout)
                packages = {entry["name"]: entry for entry in plan["agentPackages"]}
                self.assertEqual(set(packages), set(plan["agents"]) | {"codegraph"})
                for name, entry in packages.items():
                    record = expected[name]
                    with self.subTest(agent=name):
                        self.assertIn(entry["provider"], ("bun", "native", "homebrew"))
                        self.assertEqual(entry["policy"], record[4])
                        self.assertEqual(entry["commands"], record[5].split(","))
                        self.assertEqual(entry["herdr"], None if record[9] == "-" else record[9])
                        self.assertEqual(entry["version"], record[3])
                        self.assertEqual(entry["manager"], "bun" if record[1] == "bun" else "native")
                self.assertFalse(self.home.exists())

    def test_the_codex_provider_follows_the_platform_chain(self):
        for platform, provider in (("linux", "bun"), ("wsl", "bun"), ("macos", "homebrew")):
            with self.subTest(platform=platform):
                result = self.plan(platform)
                self.assertEqual(result.returncode, 0, result.stderr)
                packages = {entry["name"]: entry for entry in json.loads(result.stdout)["agentPackages"]}
                self.assertEqual(packages["codex"]["provider"], provider)
                self.assertEqual(packages["codex"]["herdr"], "codex")
                # The deployment-owned project stays the pinned fallback.
                self.assertEqual(packages["codex"]["manager"], "bun")
                self.assertEqual(packages["codex"]["package"], "@openai/codex")

    def test_a_catalog_record_drives_the_plan_without_a_named_branch(self):
        source = self.source_copy()
        records = self.catalog_records(source)
        records.append(["widget", "bun", "@example/widget", "1.2.3", "exact", "widget", "all", "1",
                        "selectable", "-", "22.0.0", "-", "deployment/agents/widget/bun.lock", "-"])
        self.write_catalog(source, records)
        lock = source / "deployment/agents/widget/bun.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("{}\n", encoding="utf-8")
        result = self.plan("linux", source=source)
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertIn("widget", plan["agents"])
        packages = {entry["name"]: entry for entry in plan["agentPackages"]}
        self.assertEqual(packages["widget"]["provider"], "bun")
        self.assertEqual(packages["widget"]["version"], "1.2.3")
        self.assertEqual(packages["widget"]["commands"], ["widget"])
        self.assertIn("widget", plan["tools"])

    def test_invalid_catalog_records_fail_before_any_state_is_created(self):
        cases = {
            "duplicate agent provider row": (
                lambda records: records + [records[0]],
                "duplicate agent provider catalog record", "linux"),
            "unknown provider": (
                lambda records: records + [["widget", "brew", "-", "1.0.0", "exact", "widget", "all", "1",
                                            "selectable", "-", "-", "-", "-", "-"]],
                "unknown provider", "linux"),
            "unsupported platform": (
                lambda records: [record[:6] + ["plan9"] + record[7:] for record in records],
                "unsupported platform", "linux"),
            "missing lock": (
                lambda records: [record[:12] + ["deployment/agents/gone/bun.lock"] + record[13:]
                                 for record in records if record[0] == "kimi"],
                "missing supported Bun lock", "linux"),
            "unknown Herdr kind": (
                lambda records: [record[:9] + ["kodex"] + record[10:] for record in records
                                 if record[0] == "codex" and record[1] == "bun"],
                "unknown Herdr kind", "linux"),
            "no viable provider": (
                lambda records: [record[:6] + ["windows"] + record[7:] for record in records
                                 if record[0] == "qoder"],
                "has no provider that can serve", "linux"),
            "shared provider order": (
                lambda records: [record[:7] + ["1"] + record[8:] for record in records
                                 if record[0] == "codex"],
                "share the order", "macos"),
            "wrong field count": (
                lambda records: [record[:-1] for record in records],
                "expected 14 fields", "linux"),
        }
        for label, (mutate, message, platform) in cases.items():
            with self.subTest(case=label):
                source = self.source_copy("source-" + label.replace(" ", "-"))
                self.write_catalog(source, mutate(self.catalog_records(source)))
                home = self.root / ("home-" + label.replace(" ", "-"))
                result = self.plan(platform, source=source, home=home)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
                self.assertFalse(home.exists())

    def test_a_catalog_record_without_its_herdr_kind_is_rejected(self):
        source = self.source_copy()
        records = self.catalog_records(source)
        records.append(["widget", "bun", "@example/widget", "1.2.3", "exact", "widget", "all", "1",
                        "selectable", "widgetd", "22.0.0", "-", "deployment/agents/widget/bun.lock", "-"])
        self.write_catalog(source, records)
        lock = source / "deployment/agents/widget/bun.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("{}\n", encoding="utf-8")
        result = self.plan("linux", source=source)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown Herdr kind", result.stderr)
        self.assertFalse(self.home.exists())


@unittest.skipUnless(POWERSHELL, "set DOTFILES_TEST_POWERSHELL for the public Windows boundary")
class WindowsProviderCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-agent-catalog-win-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "device"
        self.env = os.environ.copy()
        for name in tuple(self.env):
            if name.startswith(("DOTFILES_", "XDG_", "PIXI_", "BUN_", "CARGO_", "RUSTUP_", "ATUIN_", "UV_")):
                self.env.pop(name)

    def test_the_windows_plan_names_provider_version_commands_and_herdr_kind(self):
        result = subprocess.run([POWERSHELL, "-NoLogo", "-NoProfile", "-NonInteractive", "-File",
                                 str(SOURCE / "bootstrap.ps1"), "-TargetHome", str(self.home), "-Plan"],
                                cwd=SOURCE, env=self.env, capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        packages = {entry["name"]: entry for entry in plan["agentPackages"]}
        self.assertEqual(set(packages), set(plan["agents"]) | {"codegraph"})
        for name, entry in packages.items():
            with self.subTest(agent=name):
                self.assertIn(entry["provider"], ("bun", "native", "homebrew"))
                self.assertEqual(entry["policy"], "exact")
                self.assertTrue(entry["commands"])
                self.assertEqual(entry["manager"], "bun" if entry["package"] else "native")
        self.assertEqual(packages["codex"]["provider"], "bun")
        self.assertEqual(packages["codex"]["herdr"], "codex")
        self.assertEqual(packages["minimax"]["herdr"], None)
        self.assertEqual(packages["qoder"]["herdr"], "qodercli")
        self.assertFalse(self.home.exists())


if __name__ == "__main__":
    unittest.main()
