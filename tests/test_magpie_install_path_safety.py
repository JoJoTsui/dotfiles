"""Native Magpie installation must preserve device-owned destination links and files."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1]
COMMAND = SOURCE / "dot_local/bin/executable_dotfiles-magpie"
ENGINE = SOURCE / "deployment/magpie.sh"
PIN_CLI = b"#!/bin/sh\nprintf 'magpie 0.1.4404\\n'\n"


class MagpieInstallPathSafetyTests(unittest.TestCase):
    def test_install_preserves_a_symlinked_destination_directory(self):
        with tempfile.TemporaryDirectory(prefix="dotfiles-magpie-install-path-") as temporary:
            home = Path(temporary)
            tools = home / "tools"
            tools.mkdir()
            device = home / "device"
            (device / "bin").mkdir(parents=True)
            sentinel = device / "bin/magpie"
            sentinel.write_text("device-owned sentinel\n", encoding="utf-8")
            destination_parent = home / ".local/share/dotfiles"
            destination_parent.mkdir(parents=True)
            (destination_parent / "magpie").symlink_to(device, target_is_directory=True)

            payload = b"fixture release bytes\n"
            fixture = home / "release"
            fixture.write_bytes(payload)
            catalog = home / "releases.tsv"
            catalog.write_text(
                "magpie|0.1.4404|linux-amd64|https://example.invalid/magpie|"
                + hashlib.sha256(payload).hexdigest() + "\n", encoding="utf-8"
            )
            curl = tools / "curl"
            curl.write_text(
                '#!/bin/sh\nwhile [ "$1" != "-o" ]; do shift; done\n'
                'cp "$FIXTURE_RELEASE" "$2"\n', encoding="utf-8"
            )
            curl.chmod(0o755)
            environment = {
                "HOME": str(home), "PATH": f"{tools}:/usr/bin:/bin",
                "DEPLOY_PLATFORM": "linux", "DEPLOY_ARCH": "x86_64",
                "MAGPIE_RELEASE_CATALOG": str(catalog),
                "DOTFILES_MAGPIE_ENGINE": str(ENGINE),
                "FIXTURE_RELEASE": str(fixture),
            }
            result = subprocess.run(
                ["/bin/bash", str(COMMAND), "install"], env=environment,
                capture_output=True, text=True, timeout=15, check=False
            )
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "device-owned sentinel\n")
            self.assertTrue((destination_parent / "magpie").is_symlink())

    def run_install(self, setup):
        """Run install in a synthetic home that lives until the test ends."""
        temporary = tempfile.TemporaryDirectory(prefix="dotfiles-magpie-install-path-")
        self.addCleanup(temporary.cleanup)
        home = Path(temporary.name)
        tools = home / "tools"
        tools.mkdir()
        # The fixture is a pinned-version CLI so a fresh install is accepted
        # even when the downloader's bytes are version-checked before use.
        payload = PIN_CLI
        fixture = home / "release"
        fixture.write_bytes(payload)
        catalog = home / "releases.tsv"
        catalog.write_text(
            "magpie|0.1.4404|linux-amd64|https://example.invalid/magpie|"
            + hashlib.sha256(payload).hexdigest() + "\n", encoding="utf-8"
        )
        curl = tools / "curl"
        curl.write_text(
            '#!/bin/sh\nwhile [ "$1" != "-o" ]; do shift; done\n'
            'cp "$FIXTURE_RELEASE" "$2"\n', encoding="utf-8"
        )
        curl.chmod(0o755)
        environment = {
            "HOME": str(home), "PATH": f"{tools}:/usr/bin:/bin",
            "DEPLOY_PLATFORM": "linux", "DEPLOY_ARCH": "x86_64",
            "MAGPIE_RELEASE_CATALOG": str(catalog),
            "DOTFILES_MAGPIE_ENGINE": str(ENGINE),
            "FIXTURE_RELEASE": str(fixture),
        }
        setup(home)
        result = subprocess.run(
            ["/bin/bash", str(COMMAND), "install"], env=environment,
            capture_output=True, text=True, timeout=15, check=False
        )
        return result, home

    def test_install_rejects_a_dangling_destination_leaf_symlink(self):
        def setup(home):
            leaf = home / ".local/share/dotfiles/magpie/bin/magpie"
            leaf.parent.mkdir(parents=True)
            leaf.symlink_to(home / "absent-cli")

        result, home = self.run_install(setup)
        leaf = home / ".local/share/dotfiles/magpie/bin/magpie"
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(leaf.is_symlink())
        self.assertFalse((home / "absent-cli").exists())

    def test_install_preserves_an_unrecognized_existing_regular_file(self):
        # Ownership of an existing regular file cannot be established from its
        # bytes, so the installer preserves it instead of replacing it.
        def setup(home):
            leaf = home / ".local/share/dotfiles/magpie/bin/magpie"
            leaf.parent.mkdir(parents=True)
            leaf.write_text("device-owned cli\n", encoding="utf-8")
            leaf.chmod(0o755)

        result, home = self.run_install(setup)
        leaf = home / ".local/share/dotfiles/magpie/bin/magpie"
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(leaf.is_symlink())
        self.assertEqual(leaf.read_bytes(), b"device-owned cli\n")

    def test_install_preserves_an_existing_directory_at_the_binary_path(self):
        # A directory cannot be the pinned CLI bytes. The installer must refuse
        # it without executing, downloading over, or removing it, so a
        # device-owned directory and its contents survive the attempt.
        def setup(home):
            leaf = home / ".local/share/dotfiles/magpie/bin/magpie"
            leaf.mkdir(parents=True)
            (leaf / "device-owned").write_text("keep me\n", encoding="utf-8")

        result, home = self.run_install(setup)
        leaf = home / ".local/share/dotfiles/magpie/bin/magpie"
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(leaf.is_dir())
        self.assertFalse(leaf.is_symlink())
        self.assertEqual((leaf / "device-owned").read_text(encoding="utf-8"), "keep me\n")

    def test_install_creates_a_fresh_destination(self):
        result, home = self.run_install(lambda home: None)
        leaf = home / ".local/share/dotfiles/magpie/bin/magpie"
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(leaf.is_symlink())
        self.assertEqual(leaf.read_bytes(), PIN_CLI)


if __name__ == "__main__":
    unittest.main()
