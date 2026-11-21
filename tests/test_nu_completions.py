"""Pinned completion preparation with synthetic archives and real Nu parsing.

The preparation module and the public preparation command are exercised
separately: the module seam covers the publication lifecycle, and the command
seam runs the real Nushell and Python against a disposable home.
"""
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
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

    def assert_loader_starts(self, loader):
        """The loader must still start Nu with a complete generation."""
        result = subprocess.run([NU, "--no-config-file", "-c",
                                 "source " + json.dumps(str(loader))
                                 + '; scope commands | where name == "git" | length'],
                                env=dict(os.environ), check=False, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "1")

    def published_generations(self):
        modules = self.home / ".local/share/nushell/completions/nu-scripts"
        return sorted(entry for entry in modules.iterdir()
                      if self.module.PUBLISHED_DIRECTORY.fullmatch(entry.name))

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

    def test_superseded_module_directories_are_pruned_and_foreign_entries_preserved(self):
        self.install("git")
        self.assertEqual(self.prepare(), 1)
        modules = self.home / ".local/share/nushell/completions/nu-scripts"
        published = [path for path in modules.iterdir() if path.name.startswith(self.revision)]
        self.assertEqual(len(published), 1)
        superseded = modules / ("b" * 40 + "-" + "c" * 16)
        (superseded / "custom-completions/git").mkdir(parents=True)
        (superseded / "custom-completions/git/git-completions.nu").write_text("# earlier bytes\n")
        device = modules / "device-created"
        device.mkdir()
        (device / "keep.nu").write_text("# device skill\n")
        linked = modules / ("d" * 40 + "-" + "e" * 16)
        linked.symlink_to(device, target_is_directory=True)
        self.assertEqual(self.prepare(), 1)
        self.assertFalse(superseded.exists())
        self.assertEqual((device / "keep.nu").read_text(), "# device skill\n")
        self.assertTrue(linked.is_symlink())
        self.assertTrue(published[0].is_dir())
        self.assertIn(published[0].name, self.loader.read_text())

    def test_every_managed_loader_imports_the_published_generation(self):
        """The canonical loader and a native copy both import the new generation."""
        self.install("git")
        native = self.home / "Library/Application Support/nushell/vendor/autoload/nu-scripts.nu"
        self.assertEqual(self.prepare(loaders=[native]), 1)
        first = self.loader.read_text()
        self.assertIn("git-completions.nu", first)
        self.assertEqual(native.read_text(), first)
        # A changed selection publishes a second generation.
        self.install("just")
        self.write_desired(common=("git",), bundles=("just",))
        self.assertEqual(self.prepare(loaders=[native]), 2)
        second = self.loader.read_text()
        self.assertNotEqual(second, first)
        self.assertEqual(native.read_text(), second)
        self.assertEqual(len(self.published_generations()), 1)
        self.assert_loader_starts(self.loader)
        self.assert_loader_starts(native)

    def test_a_refused_loader_switch_leaves_every_loader_usable(self):
        """A loader the filesystem refuses keeps the generation it imports."""
        self.install("git")
        native = self.home / "Library/Application Support/nushell/vendor/autoload/nu-scripts.nu"
        self.assertEqual(self.prepare(loaders=[native]), 1)
        first = self.loader.read_text()
        # A changed selection publishes a second generation.
        self.install("just")
        self.write_desired(common=("git",), bundles=("just",))
        real_replace = os.replace
        def refuse(source, destination, *arguments, **keywords):
            if Path(destination) == native:
                raise PermissionError("simulated refusal")
            return real_replace(source, destination, *arguments, **keywords)
        with mock.patch.object(self.module.os, "replace", side_effect=refuse):
            with self.assertRaisesRegex(self.module.CompletionError, "loader switch failed"):
                self.prepare(loaders=[native])
        # The loader that switched imports the new generation.
        self.assertNotEqual(self.loader.read_text(), first)
        # The refused loader keeps the generation it imports, so both start Nu.
        self.assertEqual(native.read_text(), first)
        self.assert_loader_starts(self.loader)
        self.assert_loader_starts(native)

    def test_a_publication_to_another_loader_keeps_the_live_loader_usable(self):
        """The preparation publishes into a staging autoload directory.

        The live loader must keep importing a complete generation, so a
        publication that does not reach it cannot retire the generation it
        uses.
        """
        self.install("git")
        self.assertEqual(self.prepare(), 1)
        self.assert_loader_starts(self.loader)
        # A changed selection publishes a second generation.
        self.install("just")
        self.write_desired(common=("git",), bundles=("just",))
        stage = self.autoload / ".prepare-stage"
        stage.mkdir()
        self.assertEqual(self.prepare(loaders=[stage / "nu-scripts.nu"]), 2)
        self.assert_loader_starts(self.loader)
        self.assertEqual(len(self.published_generations()), 1)

    def test_a_windows_style_import_keeps_the_generation_it_names(self):
        """An escaped Windows import keeps the generation it names.

        A loader stores every import as a JSON string, so a Windows path
        spells every separator twice and the raw path is not part of the
        loader. Only a decoded reference finds the generation, and this check
        runs on every platform.
        """
        modules = self.home / ".local/share/nushell/completions/nu-scripts"
        generation = modules / (self.revision + "-" + "d" * 16)
        (generation / "custom-completions/git").mkdir(parents=True)
        windows_module = ("C:\\Users\\device\\.local\\share\\nushell\\completions\\nu-scripts\\"
                          + generation.name + "\\custom-completions\\git\\git-completions.nu")
        loader = self.root / "windows-loader.nu"
        text = ("# Managed pinned Nu completions; prepared after tool installation.\n"
                "use " + json.dumps(windows_module) + " *\n")
        loader.write_text(text, encoding="utf-8")
        self.assertNotIn(str(generation), text)
        imported = self.module.imported_generations([loader], modules)
        self.assertEqual(imported, {generation})
        self.module.retire_published(modules, imported)
        self.assertTrue(generation.is_dir())
        # A loader that names another generation leaves this one retirable.
        other = self.root / "other-loader.nu"
        other.write_text("use " + json.dumps(
            "C:\\Users\\device\\.local\\share\\nushell\\completions\\nu-scripts\\"
            + "f" * 40 + "-" + "0" * 16 + "\\custom-completions\\git\\git-completions.nu") + " *\n",
            encoding="utf-8")
        imported = self.module.imported_generations([other], modules)
        self.assertEqual(imported, set())
        self.module.retire_published(modules, imported)
        self.assertFalse(generation.exists())

    def test_a_quoted_home_name_keeps_the_generation_it_names(self):
        """A home path with a quote keeps the generation it names.

        The loader stores the import as a JSON string, so the quote in the
        path appears escaped and the raw path is not part of the loader.
        """
        home = self.root / 'device "quoted"'
        modules = home / ".local/share/nushell/completions/nu-scripts"
        generation = modules / (self.revision + "-" + "e" * 16)
        (generation / "custom-completions/git").mkdir(parents=True)
        loader = self.root / "quoted-loader.nu"
        text = self.module.loader_text(
            generation, [{"command": "git", "path": "custom-completions/git/git-completions.nu"}])
        loader.write_text(text, encoding="utf-8")
        self.assertNotIn(str(generation), text)
        imported = self.module.imported_generations([loader], modules)
        self.assertEqual(imported, {generation})
        self.module.retire_published(modules, imported)
        self.assertTrue(generation.is_dir())

    def test_an_empty_selection_prunes_every_published_directory(self):
        modules = self.home / ".local/share/nushell/completions/nu-scripts"
        published = modules / (self.revision + "-" + "c" * 16)
        published.mkdir(parents=True)
        device = modules / "device-created"
        device.mkdir()
        with mock.patch.object(self.module.urllib.request, "urlopen", side_effect=AssertionError("network forbidden")):
            self.assertEqual(self.prepare(), 0)
        self.assertFalse(published.exists())
        self.assertTrue(device.is_dir())
        self.assertEqual(self.loader.read_text().count("use "), 0)

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

    def test_transient_download_open_failure_retries_successfully(self):
        self.install("git")
        os.environ.pop("DOTFILES_NU_SCRIPTS_ARCHIVE")
        content = self.module_bytes[self.modules[0]["path"]]
        with (mock.patch.object(self.module.urllib.request, "urlopen",
                                side_effect=[OSError("transient TLS failure"), io.BytesIO(content)]) as download,
              mock.patch.object(self.module.time, "sleep") as sleep):
            self.assertEqual(self.prepare(), 1)
        self.assertEqual(download.call_count, 2)
        sleep.assert_called_once_with(3)
        cache = self.home / ".cache/dotfiles/nu-scripts"
        self.assertEqual([path.name for path in cache.iterdir()], [self.modules[0]["sha256"] + ".nu"])
        self.assertEqual(next(cache.iterdir()).read_bytes(), content)
        self.assertIn("git-completions.nu", self.loader.read_text())

    def test_interrupted_download_retries_with_truncated_temporary_file(self):
        class InterruptedResponse(io.BytesIO):
            def read(self, size=-1):
                if self.tell():
                    raise OSError("interrupted download")
                return super().read(size)

        self.install("git")
        os.environ.pop("DOTFILES_NU_SCRIPTS_ARCHIVE")
        content = self.module_bytes[self.modules[0]["path"]]
        partial = InterruptedResponse(content + b"discard these trailing bytes")
        with (mock.patch.object(self.module.urllib.request, "urlopen",
                                side_effect=[partial, io.BytesIO(content)]) as download,
              mock.patch.object(self.module.time, "sleep") as sleep):
            self.assertEqual(self.prepare(), 1)
        self.assertEqual(download.call_count, 2)
        sleep.assert_called_once_with(3)
        cache = self.home / ".cache/dotfiles/nu-scripts"
        self.assertEqual([path.name for path in cache.iterdir()], [self.modules[0]["sha256"] + ".nu"])
        self.assertEqual(next(cache.iterdir()).read_bytes(), content)

    def test_exhausted_download_retries_clean_cache_and_preserve_working_resources(self):
        self.install("git")
        self.prepare()
        before_loader = self.loader.read_bytes()
        before_modules = {path: path.read_bytes() for path in self.home.rglob("*-completions.nu")}
        os.environ.pop("DOTFILES_NU_SCRIPTS_ARCHIVE")
        with (mock.patch.object(self.module.urllib.request, "urlopen",
                                side_effect=OSError("persistent TLS failure")) as download,
              mock.patch.object(self.module.time, "sleep") as sleep,
              self.assertRaisesRegex(OSError, "persistent TLS failure")):
            self.prepare()
        self.assertEqual(download.call_count, 3)
        self.assertEqual(sleep.call_args_list, [mock.call(3), mock.call(3)])
        self.assertEqual(self.loader.read_bytes(), before_loader)
        self.assertEqual({path: path.read_bytes() for path in self.home.rglob("*-completions.nu")}, before_modules)
        self.assertEqual(list((self.home / ".cache/dotfiles/nu-scripts").iterdir()), [])
        self.assertFalse(list(self.autoload.glob(".nu-scripts-*")))

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
            self.prepare(loaders=[self.home / ".." / "outside"])
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


@unittest.skipUnless(NU and tomllib, "requires Nushell and Python 3.11+")
class ShellPreparationPublicationTests(unittest.TestCase):
    """The public preparation command publishes the pinned loader.

    The command runs in a disposable home with the real Nu and Python. Every
    other managed command is a stub that emits a parseable Nu resource, so the
    check observes the publication the command performs and not the tools it
    calls.
    """

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dotfiles-nu-publication-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / "device"
        self.bin = self.home / ".pixi/bin"
        self.bin.mkdir(parents=True)
        self.config = self.home / ".config/dotfiles"
        self.config.mkdir(parents=True)
        self.autoload = self.home / ".local/share/nushell/vendor/autoload"
        self.loader = self.autoload / "nu-scripts.nu"
        self.generations = self.home / ".local/share/nushell/completions/nu-scripts"
        # A native discovery copy exists, so the command publishes to it.
        self.native_autoload = self.home / "Library/Application Support/nushell/vendor/autoload"
        self.native_autoload.mkdir(parents=True)
        # The user autoload directory is the second path a launch without an
        # XDG override reads.
        self.native_user_autoload = self.home / "Library/Application Support/nushell/autoload"
        self.native_user_autoload.mkdir(parents=True)
        self.revision = "b" * 40
        self.modules = [{"command": "git", "path": "custom-completions/git/git-completions.nu"}]
        self.archive = self.root / "upstream.tgz"
        self.environment = {
            "HOME": str(self.home),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "TERM": "xterm-256color",
            "DOTFILES_NU_SCRIPTS_ARCHIVE": str(self.archive),
        }
        self.install_tools()
        self.install_configuration()
        self.write_archive()
        self.write_desired(("git",), ())

    def link(self, name, target):
        path = self.bin / name
        path.symlink_to(target)
        return path

    def stub(self, name, body=""):
        path = self.bin / name
        script = "#!/bin/sh\nexit 0\n" if not body else "#!/bin/sh\nprintf '%s\\n' '" + body + "'\n"
        path.write_text(script)
        path.chmod(0o755)
        return path

    def install_tools(self):
        self.link("nu", NU)
        self.link("python", sys.executable)
        self.stub("starship", "let starship_stub = 1")
        self.stub("pixi", "let pixi_stub = 1")
        self.stub("fzf", "let fzf_stub = 1")
        self.stub("wt", "let wt_stub = 1")
        self.stub("zoxide")
        self.stub("git")
        self.stub("just", 'export extern "just" [--help(-h)]')

    def install_configuration(self):
        library = self.home / ".local/lib/dotfiles"
        library.mkdir(parents=True)
        shutil.copy2(SOURCE / "dot_local/lib/dotfiles/completions.py", library / "completions.py")
        commands = self.home / ".local/bin"
        commands.mkdir(parents=True)
        prepare = commands / "dotfiles-shell-prepare"
        shutil.copy2(SOURCE / "dot_local/bin/executable_dotfiles-shell-prepare", prepare)
        prepare.chmod(0o755)
        nushell = self.home / ".config/nushell"
        nushell.mkdir(parents=True)
        (nushell / "config.nu").write_text("# managed configuration\n")
        (nushell / "env.nu").write_text("# managed environment\n")
        (self.home / ".env_core").write_text(
            'export XDG_CONFIG_HOME="$HOME/.config"\n'
            'export XDG_DATA_HOME="$HOME/.local/share"\n'
            'export XDG_CACHE_HOME="$HOME/.cache"\n'
            'export XDG_STATE_HOME="$HOME/.local/state"\n'
            'export PIXI_HOME="$HOME/.pixi"\n'
            'export DOTFILES_COMMON_BIN="$PIXI_HOME/bin"\n'
            'export DOTFILES_PLATFORM=macos\n')

    def write_archive(self):
        with tarfile.open(self.archive, "w:gz") as handle:
            for module in self.modules:
                content = ('export extern "' + module["command"] + '" [--help(-h)]\n').encode()
                module["sha256"] = hashlib.sha256(content).hexdigest()
                member = tarfile.TarInfo("nu_scripts-" + self.revision + "/" + module["path"])
                member.size = len(content)
                handle.addfile(member, io.BytesIO(content))
        catalog = {
            "version": 1, "revision": self.revision,
            "url": "https://codeload.github.com/nushell/nu_scripts/tar.gz/" + self.revision,
            "sha256": hashlib.sha256(self.archive.read_bytes()).hexdigest(),
            "modules": self.modules,
        }
        (self.config / "nu-completions.json").write_text(json.dumps(catalog))

    def write_desired(self, common=(), bundles=()):
        for filename, names in (("pixi-global.toml", common), ("pixi-bundles.toml", bundles)):
            contents = "version = 1\n[envs]\n"
            for name in names:
                contents += '[envs."' + name + '"]\nexposed = { "' + name + '" = "' + name + '" }\n'
            (self.config / filename).write_text(contents)

    def prepare(self):
        return subprocess.run([str(self.home / ".local/bin/dotfiles-shell-prepare")],
                              env=self.environment, capture_output=True, text=True, timeout=180)

    def loader_commands(self, loader):
        result = subprocess.run([str(self.bin / "nu"), "--no-config-file", "-c",
                                 "source " + json.dumps(str(loader))
                                 + '; scope commands | where name in ["git" "just"] | get name | to json --raw'],
                                env=self.environment, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        return set(json.loads(result.stdout))

    def native_directory(self, variable, override):
        """The directory a launch without an XDG override resolves."""
        environment = {key: value for key, value in self.environment.items() if key != override}
        result = subprocess.run([str(self.bin / "nu"), "-c", "print $" + variable],
                                env=environment, capture_output=True, text=True, timeout=60)
        if result.returncode:
            return None
        return Path(result.stdout.strip())

    def native_loader(self):
        """The loader a launch without an XDG override reads, when it differs."""
        data = self.native_directory("nu.data-dir", "XDG_DATA_HOME")
        if data is None:
            return None
        loader = data / "vendor/autoload/nu-scripts.nu"
        return None if loader == self.loader else loader

    def native_user_loader(self):
        """The loader a launch without a config override reads, when it differs."""
        config = self.native_directory("nu.default-config-dir", "XDG_CONFIG_HOME")
        if config is None or not (config / "autoload").is_dir():
            return None
        loader = config / "autoload/nu-scripts.nu"
        return None if loader == self.loader else loader

    def published_generations(self):
        return sorted(entry.name for entry in self.generations.iterdir())

    def test_the_preparation_publishes_to_every_active_loader(self):
        result = self.prepare()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.loader.is_file())
        self.assertEqual(self.loader_commands(self.loader), {"git"})
        for loader in (self.native_loader(), self.native_user_loader()):
            if loader is None:
                continue
            self.assertTrue(loader.is_file(), str(loader))
            self.assertEqual(loader.read_bytes(), self.loader.read_bytes())
            self.assertEqual(self.loader_commands(loader), {"git"})

    def test_a_failed_second_publication_leaves_the_loader_usable(self):
        first = self.prepare()
        self.assertEqual(first.returncode, 0, first.stderr)
        before = self.loader.read_bytes()
        self.assertEqual(len(self.published_generations()), 1)
        # A publication that cannot verify its pinned bytes fails and leaves
        # the working loader and its generation alone.
        self.archive.write_bytes(b"checksum mismatch")
        failed = self.prepare()
        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual(self.loader.read_bytes(), before)
        self.assertEqual(self.loader_commands(self.loader), {"git"})
        self.assertEqual(len(self.published_generations()), 1)
        # The retry publishes the next generation and retires the previous one.
        self.write_archive()
        self.write_desired(("git",), ("just",))
        retry = self.prepare()
        self.assertEqual(retry.returncode, 0, retry.stderr)
        self.assertEqual(self.loader_commands(self.loader), {"git", "just"})
        self.assertEqual(len(self.published_generations()), 1)
        self.assertNotEqual(self.loader.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
