"""Public-cache seeding safety, using only synthetic temporary file trees."""
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

import native_macos as gate


@unittest.skipUnless(os.name == "posix", "native macOS cache validation requires POSIX file APIs")
class NativeMacOSCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cache-seed-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.cache = self.root / "public-cache"
        self.cache.mkdir()
        self.home = self.root / "fresh-home"

    def write(self, relative, content=b"public package bytes"):
        path = self.cache / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_only_allowed_public_trees_are_copied_with_independent_writes(self):
        for subtree in gate.PUBLIC_CACHE_PATHS:
            self.write(subtree + "/payload")
        for excluded in ("pixi/cached-envs-v0", "pixi/envs", "pixi/bin",
                         ".pixi/envs", ".bun/managed", "auth.json"):
            self.write(excluded + "/must-not-copy", b"unrelated device state")
        original = self.cache / "pixi/pkgs/payload"
        original.chmod(0o755)
        summary = gate.seed_package_cache(self.cache, self.home)
        target = self.home / ".cache/pixi/pkgs/payload"
        self.assertEqual(summary["paths"], list(gate.PUBLIC_CACHE_PATHS))
        self.assertEqual(summary["regular_files"], 5)
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o755)
        self.assertNotEqual(original.stat().st_ino, target.stat().st_ino)
        target.write_bytes(b"independent destination write")
        self.assertEqual(original.read_bytes(), b"public package bytes")
        for excluded in ("pixi/cached-envs-v0", "pixi/envs", "pixi/bin",
                         ".pixi/envs", ".bun/managed", "auth.json"):
            self.assertFalse((self.home / ".cache" / excluded).exists())
        self.assertFalse((self.home / ".pixi").exists())
        self.assertFalse((self.home / ".bun").exists())

    def test_relative_pixi_links_and_absolute_internal_bun_aliases_are_local(self):
        package = self.write("pixi/pkgs/package/lib/data")
        (package.parent / "relative").symlink_to("data")
        payload = self.write("bun/install/pkg@1.0.0@@@1/index.js")
        alias = self.cache / "bun/install/pkg/1.0.0@@@1"
        alias.parent.mkdir()
        alias.symlink_to(payload.parent)
        summary = gate.seed_package_cache(self.cache, self.home)
        pixi_link = self.home / ".cache/pixi/pkgs/package/lib/relative"
        bun_link = self.home / ".cache/bun/install/pkg/1.0.0@@@1"
        self.assertEqual(os.readlink(pixi_link), "data")
        self.assertFalse(os.path.isabs(os.readlink(bun_link)))
        self.assertTrue(bun_link.resolve().is_relative_to(self.home))
        self.assertEqual((bun_link / "index.js").read_bytes(), payload.read_bytes())
        self.assertEqual(summary["symlinks"], 2)

    def test_external_file_or_directory_links_are_rejected_before_any_write(self):
        for name, directory in (("outside-file", False), ("outside-directory", True)):
            with self.subTest(name=name):
                external = self.root / name
                if directory:
                    external.mkdir()
                else:
                    external.write_bytes(b"never read this private data")
                link = self.cache / "bun/install/link"
                link.parent.mkdir(parents=True, exist_ok=True)
                link.symlink_to(external, target_is_directory=directory)
                with self.assertRaisesRegex(RuntimeError, "escapes"):
                    gate.seed_package_cache(self.cache, self.home)
                self.assertFalse(self.home.exists())
                link.unlink()

    def test_stale_absolute_bun_alias_is_rejected(self):
        self.write("bun/install/pkg@1.0.0@@@1/index.js")
        (self.cache / "bun/install/stale").symlink_to(self.root / "deleted-cache/pkg")
        with self.assertRaises((RuntimeError, OSError)):
            gate.seed_package_cache(self.cache, self.home)
        self.assertFalse(self.home.exists())

    def test_cache_root_and_subtree_symlinks_are_rejected(self):
        self.write("pixi/pkgs/package")
        alias = self.root / "cache-alias"
        alias.symlink_to(self.cache, target_is_directory=True)
        with self.assertRaises(RuntimeError):
            gate.seed_package_cache(alias, self.home)
        (self.cache / "bun").symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(RuntimeError):
            gate.seed_package_cache(self.cache, self.home)
        self.assertFalse(self.home.exists())

    def test_overlap_existing_home_and_symlinked_destination_ancestors_rejected(self):
        self.write("pixi/pkgs/package")
        with self.assertRaisesRegex(RuntimeError, "overlap"):
            gate.seed_package_cache(self.cache, self.cache / "fixture")
        self.home.mkdir()
        with self.assertRaisesRegex(RuntimeError, "fresh"):
            gate.seed_package_cache(self.cache, self.home)
        alias = self.root / "destination-alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "fresh"):
            gate.seed_package_cache(self.cache, alias / "fixture")
        self.assertFalse((self.root / "fixture").exists())

    def test_special_file_rejected_without_opening_it(self):
        self.write("pixi/pkgs/package")
        os.mkfifo(self.cache / "pixi/pkgs/pipe")
        with self.assertRaisesRegex(RuntimeError, "special file"):
            gate.seed_package_cache(self.cache, self.home)
        self.assertFalse(self.home.exists())

    def test_changed_source_parent_cannot_redirect_file_reads(self):
        self.write("bun/install/package/payload")
        external = self.root / "unrelated-private-directory"
        external.mkdir()
        (external / "payload").write_bytes(b"private data")
        original_open = gate._open_cache_file
        def change_parent(root_fd, relative):
            package = self.cache / "bun/install/package"
            package.rename(package.with_name("held-package"))
            package.symlink_to(external, target_is_directory=True)
            return original_open(root_fd, relative)
        with mock.patch.object(gate, "_open_cache_file", side_effect=change_parent):
            with self.assertRaises(OSError):
                gate.seed_package_cache(self.cache, self.home)
        self.assertFalse((self.home / ".cache/bun/install/package/payload").exists())


if __name__ == "__main__":
    unittest.main()
