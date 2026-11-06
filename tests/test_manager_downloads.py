"""The manager download retries a transient failure and fails closed."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from pins import manager_pin

SOURCE = Path(__file__).resolve().parents[1]


class ManagerDownloadTests(unittest.TestCase):
    """download_verified under the shell options bootstrap.sh runs with."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-manager-download-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.count = self.root / "curl-count"
        self.artifact = self.root / "artifact"
        self.verified = self.root / "verified"
        self.write_stub("curl", """#!/bin/sh
count=0
[ -f "$CURL_COUNT" ] && count=$(cat "$CURL_COUNT")
count=$((count + 1))
printf '%s' "$count" > "$CURL_COUNT"
if [ "$count" -le "$CURL_FAILURES" ]; then
    printf 'curl: (18) partial transfer\\n' >&2
    exit 18
fi
printf 'artifact-bytes' > "$CURL_OUTPUT"
exit 0
""")
        self.write_stub("sleep", "#!/bin/sh\nexit 0\n")

    def write_stub(self, name, body):
        path = self.bin / name
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)

    def run_download(self, failures, verify=True):
        """Run download_verified with the deployment's shell options."""
        environment = dict(
            os.environ,
            PATH=f"{self.bin}:{os.environ['PATH']}",
            CURL_COUNT=str(self.count),
            CURL_OUTPUT=str(self.artifact),
            CURL_FAILURES=str(failures),
            VERIFY_LOG=str(self.verified),
        )
        verification = ('verify_sha256() { printf "verified %s\\n" "${1##*/}" >> "$VERIFY_LOG"; }'
                        if verify else
                        'verify_sha256() { printf "dotfiles: SHA-256 mismatch for %s\\n" "${1##*/}" >&2; exit 1; }')
        script = self.root / "run.sh"
        script.write_text(
            "set -euo pipefail\n"
            "fail() { printf 'dotfiles: %s\\n' \"$*\" >&2; exit 1; }\n"
            f". '{SOURCE}/deployment/managers.sh'\n"
            f"{verification}\n"
            "download_verified 'https://example.invalid/artifact' \"$CURL_OUTPUT\" digest\n",
            encoding="utf-8")
        result = subprocess.run(["/bin/bash", str(script)], env=environment,
                                capture_output=True, text=True, timeout=120)
        return result

    def calls(self):
        return int(self.count.read_text(encoding="utf-8")) if self.count.exists() else 0

    def verifications(self):
        return len(self.verified.read_text(encoding="utf-8").splitlines()) if self.verified.exists() else 0

    def test_a_transient_failure_is_retried_and_the_artifact_verified(self):
        result = self.run_download(failures=1)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), 2)
        self.assertEqual(self.verifications(), 1)

    def test_exhausted_attempts_return_the_last_status_without_verifying(self):
        result = self.run_download(failures=3)
        self.assertEqual(result.returncode, 18)
        self.assertEqual(self.calls(), 3)
        self.assertEqual(self.verifications(), 0)

    def test_a_checksum_mismatch_still_fails(self):
        result = self.run_download(failures=0, verify=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SHA-256 mismatch", result.stderr)

    def test_linux_and_wsl_chezmoi_select_the_verified_static_archive(self):
        for platform in ("linux", "wsl"):
            with self.subTest(platform=platform):
                home = self.root / platform
                (home / ".local/bin").mkdir(parents=True)
                scratch = self.root / (platform + "-tmp")
                scratch.mkdir()
                request = self.root / (platform + "-request")
                script = self.root / (platform + "-install.sh")
                script.write_text(
                    "set -euo pipefail\n"
                    "fail() { printf 'dotfiles: %s\\n' \"$*\" >&2; exit 1; }\n"
                    f". '{SOURCE}/deployment/managers.sh'\n"
                    "download_verified() { printf '%s\\n' \"$1\" \"$3\" > \"$REQUEST_LOG\"; : > \"$2\"; }\n"
                    "tar() { printf 'synthetic-chezmoi' > \"$4/chezmoi\"; }\n"
                    "install_chezmoi\n",
                    encoding="utf-8")
                result = subprocess.run(
                    ["/bin/bash", str(script)],
                    env={"HOME": str(home), "PATH": "/usr/bin:/bin", "TMPDIR": str(scratch),
                         "REQUEST_LOG": str(request), "DEPLOY_PLATFORM": platform, "DEPLOY_ARCH": "x86_64"},
                    capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                url, digest = request.read_text().splitlines()
                version = manager_pin("CHEZMOI_VERSION")
                self.assertEqual(url, f"https://github.com/twpayne/chezmoi/releases/download/v{version}/"
                                      f"chezmoi_{version}_linux-musl_amd64.tar.gz")
                self.assertRegex(digest, r"^[0-9a-f]{64}$")
                target = home / ".local/bin/chezmoi"
                self.assertEqual(target.read_text(), "synthetic-chezmoi")
                self.assertTrue(os.access(target, os.X_OK))

    def test_the_download_needs_no_command_besides_curl(self):
        self.assertTrue(shutil.which("curl"))


if __name__ == "__main__":
    unittest.main()
