"""Pinned completion preparation with synthetic archives and real Nu parsing."""
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1]
NU = os.environ.get("DOTFILES_TEST_NU") or shutil.which("nu")
try:
    import tomllib
except ImportError:
    tomllib = None


@unittest.skipUnless(NU and tomllib, "requires Nushell and Python 3.11+")
class NuCompletionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dotfiles-nu-completions-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / "device with spaces"
        self.config = self.home / ".config/dotfiles"
        self.config.mkdir(parents=True)
        self.pixi = self.home / ".pixi"
        (self.pixi / "bin").mkdir(parents=True)
        self.autoload = self.home / ".local/share/nushell/vendor/autoload"
        self.loader = self.autoload / "nu-scripts.nu"
        self.archive = self.root / "upstream.tgz"
        self.revision = "a" * 40
        self.modules = [
            {"command": command, "path": f"custom-completions/{command}/{command}-completions.nu"}
            for command in ("git", "bat")]
        self.catalog_path = self.config / "nu-completions.json"
        self.environment = {
            "HOME": str(self.home), "PATH": "/usr/bin:/bin", "TERM": "xterm-256color",
            "USERPROFILE": str(self.home), "APPDATA": str(self.home / "AppData/Roaming"),
            "LOCALAPPDATA": str(self.home / "AppData/Local"),
            "DOTFILES_NU_SCRIPTS_ARCHIVE": str(self.archive),
        }
        for name in ("SYSTEMROOT", "SystemRoot", "WINDIR"):
            if name in os.environ:
                self.environment[name] = os.environ[name]
        self.patch = mock.patch.dict(os.environ, self.environment, clear=True)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        specification = importlib.util.spec_from_file_location("completion_fixture", SOURCE / "dot_local/lib/dotfiles/completions.py")
        self.module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(self.module)
        real_run = self.module.subprocess.run
        self.native_calls = []
        self.native_results = {}
        def native_or_real(arguments, **options):
            executable = Path(arguments[0])
            command = executable.stem
            if executable.parent == self.pixi / "bin" and command in self.module.NATIVE_GENERATORS:
                self.native_calls.append(arguments)
                default = (0, f'module generated_{command} {{ export extern "{command}" [--help(-h)] }}\nuse generated_{command} *\n', '')
                status, output, error = self.native_results.get(command, default)
                return subprocess.CompletedProcess(arguments, status, output, error)
            return real_run(arguments, **options)
        self.native_patch = mock.patch.object(self.module.subprocess, "run", side_effect=native_or_real)
        self.native_patch.start()
        self.addCleanup(self.native_patch.stop)
        self.write_archive()
        self.write_desired(common=("git",), bundles=("just",))

    def write_archive(self, *, broken=False, extra=None):
        self.module_bytes = {}
        with tarfile.open(self.archive, "w:gz") as handle:
            for module in self.modules:
                content = (f'export extern "{module["command"]}" [--help(-h)]\n').encode()
                if broken and module["command"] == "git":
                    content = b"export def broken [\n"
                module["sha256"] = hashlib.sha256(content).hexdigest()
                self.module_bytes[module["path"]] = content
                member = tarfile.TarInfo("nu_scripts-" + self.revision + "/" + module["path"])
                member.size = len(content)
                handle.addfile(member, io.BytesIO(content))
            if extra:
                member = tarfile.TarInfo(extra)
                member.size = 0
                handle.addfile(member, io.BytesIO())
        self.catalog = {
            "version": 1, "revision": self.revision,
            "url": "https://codeload.github.com/nushell/nu_scripts/tar.gz/" + self.revision,
            "sha256": hashlib.sha256(self.archive.read_bytes()).hexdigest(),
            "modules": self.modules,
        }
        self.catalog_path.write_text(json.dumps(self.catalog), encoding="utf-8")

    def write_desired(self, *, common=(), bundles=()):
        for filename, names in (("pixi-global.toml", common), ("pixi-bundles.toml", bundles)):
            contents = "version = 1\n[envs]\n"
            for name in names:
                contents += f'[envs."{name}"]\nexposed = {{ "{name}" = "{name}" }}\n'
            (self.config / filename).write_text(contents)

    def install(self, name, *, executable=True):
        path = self.pixi / "bin" / name
        path.write_text("synthetic managed binary\n")
        path.chmod(0o755 if executable else 0o644)

    def prepare(self, **arguments):
        return self.module.prepare(self.catalog_path, Path(NU), **arguments)

    def test_only_declared_and_installed_managed_commands_are_loaded(self):
        self.install("git")
        self.install("bat")  # Installed but not selected by either manifest.
        host = self.root / "host-bin"
        host.mkdir()
        (host / "just").write_text("#!/bin/sh\nexit 0\n")
        (host / "just").chmod(0o755)
        os.environ["PATH"] = str(host) + os.pathsep + os.environ["PATH"]
        self.assertEqual(self.prepare(), 1)
        text = self.loader.read_text()
        self.assertIn("git-completions.nu", text)
        self.assertNotIn("bat-completions.nu", text)
        self.assertNotIn("just-completions.nu", text)
        paths = [p.relative_to(self.home).as_posix() for p in self.home.rglob("*-completions.nu")]
        self.assertEqual(len(paths), 1)
        result = subprocess.run([NU, "--no-config-file", "-c", "source " + json.dumps(str(self.loader)) + '; scope commands | where name == "git" | length'],
                                env=dict(os.environ), check=False, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "1")

    def test_zero_matches_needs_no_archive_and_clears_stale_imports(self):
        self.autoload.mkdir(parents=True)
        self.loader.write_text("# old managed imports\n")
        self.archive.unlink()
        with mock.patch.object(self.module.urllib.request, "urlopen", side_effect=AssertionError("network forbidden")):
            self.assertEqual(self.prepare(), 0)
        self.assertNotIn("old managed", self.loader.read_text())
        self.assertFalse((self.home / ".cache").exists())

    def test_verified_cache_reapplication_is_offline_and_deterministic(self):
        self.install("git")
        self.install("just")
        os.environ.pop("DOTFILES_NU_SCRIPTS_ARCHIVE")
        prefix = "https://raw.githubusercontent.com/nushell/nu_scripts/" + self.revision + "/"
        def response(url, **_arguments):
            self.assertTrue(url.startswith(prefix), url)
            return io.BytesIO(self.module_bytes[url.removeprefix(prefix)])
        with mock.patch.object(self.module.urllib.request, "urlopen", side_effect=response) as download:
            self.assertEqual(self.prepare(), 2)
            requested = {call.args[0] for call in download.call_args_list}
            self.assertEqual(requested, {prefix + module["path"] for module in self.modules if module["command"] == "git"})
            self.assertEqual(download.call_count, 1)
        before = self.loader.read_bytes()
        with mock.patch.object(self.module.urllib.request, "urlopen", side_effect=AssertionError("network forbidden")):
            self.assertEqual(self.prepare(), 2)
        self.assertEqual(self.loader.read_bytes(), before)

    def test_native_generators_use_managed_binaries_without_community_downloads(self):
        self.write_desired(common=("uv",), bundles=("just",))
        self.install("uv")
        self.install("just")
        self.archive.unlink()
        with mock.patch.object(self.module.urllib.request, "urlopen", side_effect=AssertionError("network forbidden")):
            self.assertEqual(self.prepare(), 2)
        self.assertEqual(self.native_calls, [
            [str(self.pixi / "bin/uv"), "generate-shell-completion", "nushell"],
            [str(self.pixi / "bin/just"), "--completions", "nushell"],
        ])
        loader = self.loader.read_text()
        self.assertIn('source "', loader)
        self.assertNotIn('use "', loader)
        self.assertFalse((self.home / ".cache").exists())
        result = subprocess.run([NU, "--no-config-file", "-c", "source " + json.dumps(str(self.loader))
                                 + '; scope commands | where name in [uv just] | get name | to json'],
                                check=False, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(json.loads(result.stdout)), {"uv", "just"})

    def test_native_generator_failure_or_invalid_output_preserves_working_loader(self):
        self.install("git")
        self.install("just")
        self.prepare()
        before = self.loader.read_bytes()
        before_modules = {path: path.read_bytes() for path in self.home.rglob("*-completions.nu")}
        self.native_results["just"] = (7, "", "generator failure")
        with self.assertRaisesRegex(self.module.CompletionError, "native completion generator failed"):
            self.prepare()
        self.assertEqual(self.loader.read_bytes(), before)
        self.native_results["just"] = (0, "export def broken [\n", "")
        with self.assertRaisesRegex(self.module.CompletionError, "failed validation"):
            self.prepare()
        self.assertEqual(self.loader.read_bytes(), before)
        self.assertEqual({path: path.read_bytes() for path in self.home.rglob("*-completions.nu")}, before_modules)

    def test_raw_module_checksum_mismatch_preserves_working_loader(self):
        self.install("git")
        self.prepare()
        before = self.loader.read_bytes()
        os.environ.pop("DOTFILES_NU_SCRIPTS_ARCHIVE")
        with (mock.patch.object(self.module.urllib.request, "urlopen", return_value=io.BytesIO(b"unexpected bytes")),
              self.assertRaisesRegex(self.module.CompletionError, "module checksum mismatch")):
            self.prepare()
        self.assertEqual(self.loader.read_bytes(), before)
        self.assertFalse(list((self.home / ".cache/dotfiles/nu-scripts").glob("*.nu")))

    def test_offline_archive_modules_still_require_individual_checksums(self):
        self.install("git")
        self.catalog["modules"][0]["sha256"] = "0" * 64
        self.catalog_path.write_text(json.dumps(self.catalog))
        with self.assertRaisesRegex(self.module.CompletionError, "module checksum mismatch"):
            self.prepare()
        self.assertFalse(self.loader.exists())

    def test_bad_archive_or_nu_syntax_preserves_working_loader_and_modules(self):
        self.install("git")
        self.prepare()
        before_loader = self.loader.read_bytes()
        before_modules = {path: path.read_bytes() for path in self.home.rglob("*-completions.nu")}
        self.archive.write_bytes(b"checksum mismatch")
        with self.assertRaisesRegex(self.module.CompletionError, "checksum"):
            self.prepare()
        self.assertEqual(self.loader.read_bytes(), before_loader)
        self.write_archive(broken=True)
        with self.assertRaisesRegex(self.module.CompletionError, "failed validation"):
            self.prepare()
        self.assertEqual(self.loader.read_bytes(), before_loader)
        self.assertEqual({path: path.read_bytes() for path in self.home.rglob("*-completions.nu")}, before_modules)
        self.assertFalse(list(self.autoload.glob(".nu-scripts-*")))

    def test_unsafe_archive_members_and_catalog_paths_are_rejected(self):
        self.install("git")
        self.write_archive(extra="nu_scripts-" + self.revision + "/../../escape.nu")
        with self.assertRaisesRegex(self.module.CompletionError, "unsafe"):
            self.prepare()
        self.assertFalse(self.loader.exists())
        for path in ("../outside.nu", "C:outside.nu", "custom-completions\\outside.nu"):
            with self.subTest(path=path):
                self.catalog["modules"][0]["path"] = path
                self.catalog_path.write_text(json.dumps(self.catalog))
                with self.assertRaisesRegex(self.module.CompletionError, "relative"):
                    self.prepare()

    def test_destination_traversal_and_symlinks_are_rejected_without_external_writes(self):
        outside = self.root / "outside"
        outside.mkdir()
        with self.assertRaisesRegex(self.module.CompletionError, "parent traversal"):
            self.prepare(autoload=self.home / ".." / "outside")
        self.assertFalse(list(outside.iterdir()))
        self.autoload.parent.mkdir(parents=True)
        try:
            self.autoload.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("symlink creation prohibited by this host")
        with self.assertRaisesRegex(self.module.CompletionError, "symlink"):
            self.prepare()
        self.assertFalse(list(outside.iterdir()))

    def test_command_matching_requires_executable_unix_files_and_accepts_windows_wrappers(self):
        self.install("git", executable=False)
        with mock.patch.object(self.module, "WINDOWS", False):
            self.assertEqual(self.prepare(), 0)
        self.install("git.exe", executable=False)
        with mock.patch.object(self.module, "WINDOWS", True):
            self.assertEqual(self.prepare(), 1)

    def test_desired_manifest_symlinks_preserve_loader_and_foreign_content(self):
        self.install("git")
        self.prepare()
        before = self.loader.read_bytes()
        for name in ("pixi-global.toml", "pixi-bundles.toml"):
            with self.subTest(manifest=name):
                manifest = self.config / name
                content = manifest.read_bytes()
                foreign = self.root / ("foreign-" + name)
                foreign.write_bytes(content)
                manifest.unlink()
                try:
                    manifest.symlink_to(foreign)
                except OSError:
                    manifest.write_bytes(content)
                    self.skipTest("symlink creation prohibited by this host")
                with self.assertRaisesRegex(self.module.CompletionError, "symlink"):
                    self.prepare()
                self.assertEqual(self.loader.read_bytes(), before)
                self.assertEqual(foreign.read_bytes(), content)
                manifest.unlink()
                manifest.write_bytes(content)


if __name__ == "__main__":
    unittest.main()
