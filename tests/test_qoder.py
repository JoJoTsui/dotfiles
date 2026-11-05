"""Unix Qoder pin and launcher checks using isolated synthetic releases."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

from pins import native_agent_pins

SOURCE = Path(__file__).resolve().parents[1]


class QoderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dotfiles-qoder-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / "device with spaces"
        self.home.mkdir()
        self.state = self.home / ".qoder"
        self.version = native_agent_pins()["qoder"]["version"]
        self.cli = self.state / "bin/qodercli" / ("qodercli-" + self.version)
        self.entry = self.state / "entry/qoder"
        self.calls = self.root / "version-calls"
        self.network_calls = self.root / "network-calls"
        self.archive = self.root / "release.tgz"
        self.manifest = self.root / "manifest.json"
        self.archive_url = "https://qoder.invalid/synthetic-release.tgz"
        self.environment = {
            "HOME": str(self.home), "PATH": "/usr/bin:/bin", "TMPDIR": str(self.root),
            "QODER_TEST_CALLS": str(self.calls), "QODER_TEST_NETWORK_CALLS": str(self.network_calls),
            "QODER_TEST_ARCHIVE": str(self.archive), "QODER_TEST_MANIFEST": str(self.manifest),
            "QODER_TEST_ARCHIVE_URL": self.archive_url,
        }

    def cli_bytes(self, version):
        return (
            '#!/bin/sh\n'
            'if [ "${1:-}" = --version ]; then\n'
            '    printf "version\\n" >> "$QODER_TEST_CALLS"\n'
            '    count=$(wc -l < "$QODER_TEST_CALLS" | tr -d " ")\n'
            f'    if [ "$count" = "${{QODER_TEST_BAD_CALL:-}}" ]; then echo "{version}0"; '
            f'else echo "{version}"; fi\n'
            'else\n'
            '    printf "pinned:%s\\n" "$*"\n'
            'fi\n'
        ).encode()

    def write_executable(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        path.chmod(0o755)

    def seed_device_state(self):
        self.write_executable(self.entry, b"#!/bin/sh\necho stale-dispatcher\n")
        self.write_executable(self.state / "bin/qodercli/qodercli-0.0.1", b"older release\n")
        for name in ("auth.json", "state/session.json"):
            path = self.state / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic device-owned state\n")
        return {path: path.read_bytes() for path in self.state.rglob("*") if path.is_file()}

    def write_release(self, version):
        content = self.cli_bytes(version)
        with tarfile.open(self.archive, "w:gz") as archive:
            member = tarfile.TarInfo("qodercli")
            member.size = len(content)
            member.mode = 0o755
            archive.addfile(member, io.BytesIO(content))
        checksum = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.environment["QODER_TEST_ARCHIVE_SHA256"] = checksum
        self.manifest.write_text(json.dumps({
            "latest": self.version,
            "releases": [{"os": "darwin", "arch": "arm64", "url": self.archive_url,
                          "sha256": checksum}],
        }))
        return content

    def install(self, **environment):
        script = r'''
set -euo pipefail
DEPLOY_SOURCE=$1
CLI_AGENTS_SET=true
CLI_AGENTS=qoder
DEPLOY_TOOLS=()
DEPLOY_PLATFORM=macos
fail() { printf '%s\n' "$*" >&2; exit 1; }
source "$DEPLOY_SOURCE/deployment/agents.sh"
qoder_platform_key() { printf 'darwin arm64'; }
curl() {
    printf 'manifest\n' >> "$QODER_TEST_NETWORK_CALLS"
    while [ "$#" -gt 0 ]; do
        if [ "$1" = -o ]; then cp "$QODER_TEST_MANIFEST" "$2"; return; fi
        shift
    done
    fail 'missing synthetic manifest destination'
}
download_verified() {
    printf 'archive\n' >> "$QODER_TEST_NETWORK_CALLS"
    [ "$1" = "$QODER_TEST_ARCHIVE_URL" ] || fail 'unexpected archive URL'
    [ "$3" = "$QODER_TEST_ARCHIVE_SHA256" ] || fail 'unexpected archive checksum'
    cp "$QODER_TEST_ARCHIVE" "$2"
}
install_qoder "$2" 'https://qoder.invalid/channels'
'''
        return subprocess.run(
            ["/bin/bash", "-c", script, "qoder-fixture", str(SOURCE), self.version],
            cwd=SOURCE, env=dict(self.environment, **environment), capture_output=True,
            text=True, timeout=30,
        )

    def assert_launchers_use_pin(self):
        for command in ("qoder", "qodercli"):
            launcher = self.home / ".local/bin" / command
            self.assertTrue(launcher.is_file())
            self.assertFalse(launcher.is_symlink())
            self.assertIn(str(self.cli), launcher.read_text())
            diagnostic = subprocess.run([str(launcher), "--version"], env=self.environment,
                                        capture_output=True, text=True, timeout=10)
            self.assertEqual(diagnostic.returncode, 0, diagnostic.stderr)
            self.assertEqual(diagnostic.stdout.strip(), self.version)
            forwarded = subprocess.run([str(launcher), "argument with spaces", "--flag"],
                                       env=self.environment, capture_output=True, text=True, timeout=10)
            self.assertEqual(forwarded.returncode, 0, forwarded.stderr)
            self.assertEqual(forwarded.stdout.strip(), "pinned:argument with spaces --flag")

    def test_existing_pinned_cli_ignores_and_preserves_stale_vendor_dispatcher(self):
        self.write_executable(self.cli, self.cli_bytes(self.version))
        before = self.seed_device_state()
        for _attempt in range(2):
            result = self.install()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assert_launchers_use_pin()
            self.assertEqual(result.stdout.splitlines(), [self.version, self.version])
            self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertFalse(self.network_calls.exists())

    def test_downloaded_pinned_cli_owns_both_launchers_and_preserves_device_state(self):
        before = self.seed_device_state()
        content = self.write_release(self.version)
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [self.version, self.version])
        self.assertEqual(self.network_calls.read_text().splitlines(), ["manifest", "archive"])
        self.assertEqual(self.cli.read_bytes(), content)
        self.assert_launchers_use_pin()
        self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_downloaded_version_containing_pin_is_rejected_before_publication(self):
        self.write_executable(self.cli, self.cli_bytes("0.0.1"))
        before = self.seed_device_state()
        self.write_release(self.version + "0")
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("pinned version " + self.version, result.stderr)
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertFalse((self.home / ".local/bin/qoder").exists())
        self.assertFalse((self.home / ".local/bin/qodercli").exists())

    def test_both_launcher_diagnostics_require_exact_pin(self):
        self.write_executable(self.cli, self.cli_bytes(self.version))
        for bad_call, command in ((2, "qoder"), (3, "qodercli")):
            with self.subTest(command=command):
                self.calls.unlink(missing_ok=True)
                result = self.install(QODER_TEST_BAD_CALL=str(bad_call))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(command + " diagnostic did not report pinned version " + self.version,
                              result.stderr)
        self.assertFalse(self.network_calls.exists())


if __name__ == "__main__":
    unittest.main()
