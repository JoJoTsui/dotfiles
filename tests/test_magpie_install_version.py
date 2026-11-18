"""The native Magpie installer verifies existing bytes before trusting them."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1]
COMMAND = SOURCE / "dot_local/bin/executable_dotfiles-magpie"
ENGINE = SOURCE / "deployment/magpie.sh"
PIN_VERSION = "0.1.4404"


def cli_script(reported_version, exit_status=0):
    """A fake CLI that reports a version and records every invocation.

    With the default exit_status the script ends on the successful printf,
    matching its original bytes. A non-zero exit_status appends an explicit
    ``exit`` so the version command fails while still printing the pin.
    """
    script = (
        "#!/bin/sh\n"
        "printf '%s' ran > \"$MAGPIE_CLI_EXECUTED\"\n"
        "printf '" + reported_version + "\\n'\n"
    )
    if exit_status:
        script += "exit " + str(exit_status) + "\n"
    return script.encode("utf-8")


class MagpieInstallVersionTests(unittest.TestCase):
    def run_install(self, reported_version, digest=None, exit_status=0):
        """Run `dotfiles-magpie install` against an existing CLI in a fresh home.

        Returns the result, the CLI bytes after the run, whether the CLI was
        executed, and whether a download was attempted.
        """
        with tempfile.TemporaryDirectory(prefix="dotfiles-magpie-version-") as temporary:
            home = Path(temporary)
            tools = home / "tools"
            tools.mkdir()
            executed = home / "cli-executed"
            downloaded = home / "download-attempted"

            content = cli_script(reported_version, exit_status)
            cli = home / "existing-magpie"
            cli.write_bytes(content)
            cli.chmod(0o755)

            # A fake HTTPS downloader records any attempt, then fails so a test
            # can tell that the installer fell through to the network path.
            curl = tools / "curl"
            curl.write_text(
                '#!/bin/sh\nprintf downloaded > "$MAGPIE_DOWNLOAD_ATTEMPTED"\nexit 1\n',
                encoding="utf-8")
            curl.chmod(0o755)

            if digest is None:
                digest = hashlib.sha256(content).hexdigest()
            catalog = home / "releases.tsv"
            catalog.write_text(
                "magpie|" + PIN_VERSION + "|linux-amd64|https://example.invalid/asset|"
                + digest + "\n", encoding="utf-8")

            environment = {
                "HOME": str(home), "PATH": f"{tools}:/usr/bin:/bin",
                "DEPLOY_PLATFORM": "linux", "DEPLOY_ARCH": "x86_64",
                "MAGPIE_CLI_BIN": str(cli), "MAGPIE_RELEASE_CATALOG": str(catalog),
                "DOTFILES_MAGPIE_ENGINE": str(ENGINE),
                "MAGPIE_CLI_EXECUTED": str(executed),
                "MAGPIE_DOWNLOAD_ATTEMPTED": str(downloaded),
            }
            result = subprocess.run(["/bin/bash", str(COMMAND), "install"], env=environment,
                                    capture_output=True, text=True, timeout=15, check=False)
            return result, cli.read_bytes(), executed.exists(), downloaded.exists()

    def test_the_pinned_version_is_accepted_when_bytes_match_the_pin(self):
        reported = "magpie " + PIN_VERSION
        result, content, executed, downloaded = self.run_install(reported)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("the CLI " + PIN_VERSION + " is installed", result.stdout)
        self.assertEqual(content, cli_script(reported))
        self.assertFalse(downloaded, "a verified pinned CLI must not be downloaded again")

    def test_a_mismatched_digest_cli_is_neither_executed_nor_overwritten(self):
        # The file reports the pinned version, but its bytes are not the pinned
        # bytes. The version string alone must not make it trusted or reusable.
        reported = "magpie " + PIN_VERSION
        result, content, executed, downloaded = self.run_install(reported, digest="0" * 64)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(executed, "unverified bytes were executed for their version")
        self.assertEqual(content, cli_script(reported), "the existing CLI was overwritten")
        self.assertFalse(downloaded)

    def test_a_longer_version_does_not_satisfy_the_pin_after_bytes_are_verified(self):
        # The bytes match the pin, so a wrong version is a version mismatch, not
        # a reason to fall through to a download the way the old installer did.
        reported = "magpie " + PIN_VERSION + "0"
        result, content, executed, downloaded = self.run_install(reported)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(downloaded, "a verified but wrong-version CLI must not trigger a download")
        self.assertEqual(content, cli_script(reported))

    def test_a_prerelease_version_does_not_satisfy_the_pin_after_bytes_are_verified(self):
        reported = "magpie " + PIN_VERSION + "-rc1"
        result, content, executed, downloaded = self.run_install(reported)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(downloaded, "a verified but wrong-version CLI must not trigger a download")
        self.assertEqual(content, cli_script(reported))

    def run_fresh_install(self, reported_version, exit_status=0):
        """Install a fresh payload at the public seam with a fake downloader.

        The fake curl copies a fake CLI script into the download target, so no
        real Magpie binary is fetched or executed. TMPDIR is test-owned, which
        lets the test assert the installer removed only its private download.
        """
        with tempfile.TemporaryDirectory(prefix="dotfiles-magpie-fresh-") as temporary:
            home = Path(temporary)
            tools = home / "tools"
            tools.mkdir()
            tmpdir = home / "tmp"
            tmpdir.mkdir()
            executed = home / "cli-executed"

            payload = cli_script("magpie " + reported_version, exit_status)
            fixture = home / "release"
            fixture.write_bytes(payload)

            catalog = home / "releases.tsv"
            catalog.write_text(
                "magpie|" + PIN_VERSION + "|linux-amd64|https://example.invalid/asset|"
                + hashlib.sha256(payload).hexdigest() + "\n", encoding="utf-8")

            curl = tools / "curl"
            curl.write_text(
                '#!/bin/sh\nwhile [ "$1" != "-o" ]; do shift; done\n'
                'cp "$FIXTURE_RELEASE" "$2"\n', encoding="utf-8")
            curl.chmod(0o755)

            environment = {
                "HOME": str(home), "PATH": f"{tools}:/usr/bin:/bin",
                "DEPLOY_PLATFORM": "linux", "DEPLOY_ARCH": "x86_64",
                "MAGPIE_RELEASE_CATALOG": str(catalog),
                "DOTFILES_MAGPIE_ENGINE": str(ENGINE),
                "FIXTURE_RELEASE": str(fixture),
                "MAGPIE_CLI_EXECUTED": str(executed),
                "TMPDIR": str(tmpdir),
            }
            result = subprocess.run(
                ["/bin/bash", str(COMMAND), "install"], env=environment,
                capture_output=True, text=True, timeout=15, check=False)
            cli = home / ".local/share/dotfiles/magpie/bin/magpie"
            # Capture the destination state before the temporary home is gone.
            placed = cli.exists()
            content = cli.read_bytes() if placed else None
            return result, placed, content, payload, executed.exists(), list(tmpdir.iterdir())

    def test_a_fresh_payload_with_a_wrong_version_is_rejected(self):
        # The downloaded bytes match the catalog digest, but --version reports
        # a different release. Matching the digest is not proof of the version:
        # the payload must be rejected without placing the destination.
        result, placed, content, payload, executed, leftover = self.run_fresh_install(
            PIN_VERSION + "0")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(placed, "a wrong-version payload was placed")
        self.assertIsNone(content, "a wrong-version payload was placed")
        self.assertEqual(leftover, [], "the installer left its private download behind")
        self.assertTrue(executed, "the verified payload should have been version-checked")

    def test_a_fresh_payload_with_the_pinned_version_installs(self):
        result, placed, content, payload, executed, leftover = self.run_fresh_install(
            PIN_VERSION)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(placed, "the verified payload was not placed")
        self.assertEqual(content, payload)
        self.assertEqual(leftover, [], "the installer left its private download behind")

    def test_a_fresh_payload_whose_version_command_fails_is_rejected(self):
        # The payload prints the pin but --version exits non-zero. A failing
        # version command is not a usable CLI, even with matching output, so it
        # must not be placed and its private download must be cleaned.
        result, placed, content, payload, executed, leftover = self.run_fresh_install(
            PIN_VERSION, exit_status=1)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(placed, "a payload with a failing --version was placed")
        self.assertIsNone(content, "a payload with a failing --version was placed")
        self.assertEqual(leftover, [], "the installer left its private download behind")

    def test_a_cached_cli_that_reports_the_pin_but_exits_nonzero_is_rejected(self):
        # Existing bytes match the digest and print the pin, but the --version
        # process exits non-zero. Matching stdout alone must not be enough to
        # reuse a cached CLI, and no download should be attempted.
        reported = "magpie " + PIN_VERSION
        result, content, executed, downloaded = self.run_install(reported, exit_status=1)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(downloaded, "a failing cached CLI must not trigger a download")
        self.assertEqual(content, cli_script(reported, exit_status=1))
        self.assertTrue(executed, "the cached CLI should have been version-checked")


if __name__ == "__main__":
    unittest.main()
