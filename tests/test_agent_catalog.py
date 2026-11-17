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

    def test_the_dsh_agents_are_pinned_bun_projects_without_a_herdr_kind(self):
        records = {record[0]: record for record in self.catalog_records()}
        for name, package, version, commands, minimum in (
                ("dsh", "@deepseek-ai/dsh", "0.2.2-rc.1", "dsh", "24.9.0"),
                ("dsh-tui", "@deepseek-harness-tui/dsh-tui", "0.20.1", "dsh-tui,dst", "22.19.0")):
            with self.subTest(agent=name):
                record = records[name]
                self.assertEqual(record[1], "bun")
                self.assertEqual(record[2], package)
                self.assertEqual(record[4], version)
                self.assertEqual(record[5], "exact")
                self.assertEqual(record[6], commands)
                self.assertEqual(record[7], "all")
                self.assertEqual(record[9], "selectable")
                self.assertEqual(record[10], "-")
                self.assertEqual(record[11], minimum)
                self.assertTrue((SOURCE / record[13]).is_file())
                self.assertTrue((SOURCE / f"deployment/agents/{name}/package.json").is_file())

    def test_plan_names_provider_version_commands_and_herdr_kind_for_every_platform(self):
        # macOS resolves Homebrew first; the other platforms use the
        # deployment-owned provider alone.
        providers = {
            "macos": {"kimi": "homebrew", "pi": "homebrew", "opencode": "homebrew",
                      "claude": "homebrew", "codex": "homebrew", "minimax": "bun",
                      "codegraph": "bun", "qoder": "native", "dsh": "bun", "dsh-tui": "bun"},
            "linux": {"kimi": "bun", "pi": "bun", "opencode": "bun", "claude": "bun",
                      "codex": "bun", "minimax": "bun", "codegraph": "bun", "qoder": "native",
                      "dsh": "bun", "dsh-tui": "bun"},
        }
        providers["wsl"] = providers["linux"]
        for platform in PLATFORMS:
            with self.subTest(platform=platform):
                result = self.plan(platform)
                self.assertEqual(result.returncode, 0, result.stderr)
                plan = json.loads(result.stdout)
                packages = {entry["name"]: entry for entry in plan["agentPackages"]}
                self.assertEqual(set(packages), set(plan["agents"]) | {"codegraph"})
                for name, entry in packages.items():
                    provider = providers[platform][name]
                    record = next(item for item in self.catalog_records()
                                  if item[0] == name and item[1] == provider)
                    owned = next(item for item in self.catalog_records()
                                 if item[0] == name and item[1] in ("bun", "native"))
                    with self.subTest(agent=name):
                        self.assertEqual(entry["provider"], provider)
                        self.assertEqual(entry["policy"], record[5])
                        self.assertEqual(entry["commands"], record[6].split(","))
                        self.assertEqual(entry["herdr"], None if record[10] == "-" else record[10])
                        self.assertEqual(entry["version"], record[4])
                        # The entry describes the provider the plan selects.
                        self.assertEqual(entry["manager"], provider)
                        if provider == "homebrew":
                            self.assertEqual(entry["package"], record[2])
                            self.assertEqual(entry["packageKind"], record[3])
                            self.assertNotIn("minimumNode", entry)
                            self.assertNotIn("lock", entry)
                            # The deployment-owned fallback keeps its own field.
                            fallback = entry["fallback"]
                            self.assertEqual(fallback["provider"], owned[1])
                            self.assertEqual(fallback["package"], owned[2])
                            self.assertEqual(fallback["lock"], owned[13])
                        elif provider == "bun":
                            self.assertEqual(entry["package"], record[2])
                            self.assertEqual(entry["minimumNode"], record[11])
                            self.assertEqual(entry["lock"], record[13])
                            self.assertNotIn("fallback", entry)
                        else:
                            self.assertEqual(entry["package"], None)
                            self.assertEqual(entry["manifest"], record[13])
                            self.assertNotIn("fallback", entry)
                self.assertFalse(self.home.exists())

    def test_a_homebrew_plan_entry_names_the_homebrew_package_and_kind(self):
        result = self.plan("macos")
        self.assertEqual(result.returncode, 0, result.stderr)
        packages = {entry["name"]: entry for entry in json.loads(result.stdout)["agentPackages"]}
        for name, kind in (("kimi", "formula"), ("codex", "cask")):
            with self.subTest(agent=name):
                entry = packages[name]
                homebrew = next(item for item in self.catalog_records()
                                if item[0] == name and item[1] == "homebrew")
                owned = next(item for item in self.catalog_records()
                             if item[0] == name and item[1] in ("bun", "native"))
                self.assertEqual(entry["provider"], "homebrew")
                self.assertEqual(entry["manager"], "homebrew")
                self.assertEqual(entry["package"], homebrew[2])
                self.assertEqual(entry["packageKind"], kind)
                # A Homebrew entry never carries the deployment-owned project.
                self.assertNotEqual(entry["manager"], "bun")
                self.assertNotIn("lock", entry)
                self.assertNotIn("minimumNode", entry)
                selected = {key: value for key, value in entry.items() if key != "fallback"}
                self.assertNotIn("bun.lock", json.dumps(selected))
                # The deployment-owned fallback is explicit and separate.
                fallback = entry["fallback"]
                self.assertEqual(fallback["provider"], "bun")
                self.assertEqual(fallback["manager"], "bun")
                self.assertEqual(fallback["package"], owned[2])
                self.assertEqual(fallback["lock"], owned[13])
                self.assertEqual(fallback["minimumNode"], owned[11])
        # Every Homebrew entry of the plan stays free of a deployment lock.
        for name, entry in packages.items():
            if entry["provider"] != "homebrew":
                continue
            with self.subTest(agent=name):
                self.assertNotIn("lock", entry)
                self.assertIn("fallback", entry)

    def test_the_catalog_declares_the_homebrew_package_of_every_agent_homebrew_ships(self):
        expected = {
            "kimi": ("formula", "kimi-code", "2.4.1"),
            "pi": ("formula", "pi-coding-agent", "1.5.2"),
            "opencode": ("formula", "opencode-v2", "2.2.5"),
            "claude": ("cask", "claude-code", "2.1.325"),
            "codex": ("cask", "codex", "0.166.0"),
        }
        records = [record for record in self.catalog_records() if record[1] == "homebrew"]
        self.assertEqual({record[0] for record in records}, set(expected))
        for record in records:
            kind, package, floor = expected[record[0]]
            with self.subTest(agent=record[0]):
                self.assertEqual(record[3], kind)
                self.assertEqual(record[2], package)
                self.assertEqual(record[4], floor)
                # An installer-owned provider carries a floor, not an exact pin.
                self.assertEqual(record[5], "floor")
                self.assertEqual(record[7], "macos")
                self.assertEqual(record[8], "1")
        # The clients Homebrew does not ship stay with the deployment-owned
        # provider alone.
        for name in ("minimax", "codegraph", "qoder", "dsh", "dsh-tui"):
            with self.subTest(agent=name):
                self.assertNotIn(name, expected)

    def test_a_homebrew_record_needs_a_package_kind_and_a_floor(self):
        cases = {
            "missing package kind": (
                lambda records: [record[:3] + ["-"] + record[4:] for record in records
                                 if record[1] == "homebrew"],
                "unknown Homebrew package kind"),
            "unknown package kind": (
                lambda records: [record[:3] + ["tarball"] + record[4:] for record in records
                                 if record[1] == "homebrew"],
                "unknown Homebrew package kind"),
            "exact policy": (
                lambda records: [record[:5] + ["exact"] + record[6:] for record in records
                                 if record[1] == "homebrew"],
                "installer-owned provider carries a floor"),
            "missing package": (
                lambda records: [record[:2] + [""] + record[3:] for record in records
                                 if record[1] == "homebrew"],
                "missing Homebrew package"),
        }
        for label, (mutate, message) in cases.items():
            with self.subTest(case=label):
                source = self.source_copy("source-" + label.replace(" ", "-"))
                self.write_catalog(source, mutate(self.catalog_records(source)))
                home = self.root / ("home-" + label.replace(" ", "-"))
                result = self.plan("macos", source=source, home=home)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
                self.assertFalse(home.exists())

    def test_a_deployment_owned_record_carries_no_package_kind(self):
        source = self.source_copy()
        records = self.catalog_records(source)
        records = [record[:3] + ["npm"] + record[4:] for record in records if record[1] == "bun"]
        self.write_catalog(source, records)
        home = self.root / "home-kind"
        result = self.plan("linux", source=source, home=home)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("a Bun record has no package kind", result.stderr)
        self.assertFalse(home.exists())

    def test_the_codex_provider_follows_the_platform_chain(self):
        for platform, provider in (("linux", "bun"), ("wsl", "bun"), ("macos", "homebrew")):
            with self.subTest(platform=platform):
                result = self.plan(platform)
                self.assertEqual(result.returncode, 0, result.stderr)
                packages = {entry["name"]: entry for entry in json.loads(result.stdout)["agentPackages"]}
                entry = packages["codex"]
                self.assertEqual(entry["provider"], provider)
                self.assertEqual(entry["herdr"], "codex")
                if provider == "homebrew":
                    # The Homebrew package is named; the deployment-owned
                    # project stays the fallback in its own field.
                    self.assertEqual(entry["manager"], "homebrew")
                    self.assertEqual(entry["package"], "codex")
                    self.assertEqual(entry["packageKind"], "cask")
                    self.assertNotIn("lock", entry)
                    self.assertEqual(entry["fallback"]["package"], "@openai/codex")
                    self.assertEqual(entry["fallback"]["lock"], "deployment/agents/codex/bun.lock")
                else:
                    self.assertEqual(entry["manager"], "bun")
                    self.assertEqual(entry["package"], "@openai/codex")
                    self.assertEqual(entry["lock"], "deployment/agents/codex/bun.lock")
                    self.assertNotIn("fallback", entry)

    def test_a_catalog_record_drives_the_plan_without_a_named_branch(self):
        source = self.source_copy()
        records = self.catalog_records(source)
        records.append(["widget", "bun", "@example/widget", "-", "1.2.3", "exact", "widget", "all", "1",
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
                lambda records: records + [["widget", "brew", "-", "-", "1.0.0", "exact", "widget", "all", "1",
                                            "selectable", "-", "-", "-", "-", "-"]],
                "unknown provider", "linux"),
            "unsupported platform": (
                lambda records: [record[:7] + ["plan9"] + record[8:] for record in records],
                "unsupported platform", "linux"),
            "missing lock": (
                lambda records: [record[:13] + ["deployment/agents/gone/bun.lock"] + record[14:]
                                 for record in records if record[0] == "kimi"],
                "missing supported Bun lock", "linux"),
            "unknown Herdr kind": (
                lambda records: [record[:10] + ["kodex"] + record[11:] for record in records
                                 if record[0] == "codex" and record[1] == "bun"],
                "unknown Herdr kind", "linux"),
            "no viable provider": (
                lambda records: [record[:7] + ["windows"] + record[8:] for record in records
                                 if record[0] == "qoder"],
                "has no provider that can serve", "linux"),
            "shared provider order": (
                lambda records: [record[:8] + ["1"] + record[9:] for record in records
                                 if record[0] == "codex"],
                "share the order", "macos"),
            "wrong field count": (
                lambda records: [record[:-1] for record in records],
                "expected 15 fields", "linux"),
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
        records.append(["widget", "bun", "@example/widget", "-", "1.2.3", "exact", "widget", "all", "1",
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
                # The Windows plan resolves a deployment-owned provider, so
                # the entry names it and carries no separate fallback.
                self.assertEqual(entry["manager"], entry["provider"])
                self.assertNotIn("fallback", entry)
        self.assertEqual(packages["codex"]["provider"], "bun")
        self.assertEqual(packages["codex"]["herdr"], "codex")
        self.assertEqual(packages["minimax"]["herdr"], None)
        self.assertEqual(packages["qoder"]["herdr"], "qodercli")
        self.assertEqual(packages["dsh"]["herdr"], None)
        self.assertEqual(packages["dsh-tui"]["herdr"], None)
        self.assertFalse(self.home.exists())


if __name__ == "__main__":
    unittest.main()
