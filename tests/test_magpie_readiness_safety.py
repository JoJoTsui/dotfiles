"""A gateway must report readiness before clients can rely on it."""
from pathlib import Path
import subprocess
import tempfile
import unittest

if __package__:
    from .fixtures.magpie_engine import install_engine_shim
else:
    from fixtures.magpie_engine import install_engine_shim

SOURCE = Path(__file__).resolve().parents[1]
COMMAND = SOURCE / "dot_local/bin/executable_dotfiles-magpie"
ENGINE = SOURCE / "deployment/magpie.sh"
CATALOG = SOURCE / "deployment/magpie"


class MagpieReadinessSafetyTests(unittest.TestCase):
    def run_start(self, status_body):
        """Run `dotfiles-magpie start` against a fake CLI status response."""
        with tempfile.TemporaryDirectory(prefix="dotfiles-magpie-readiness-") as temporary:
            home = Path(temporary)
            # The command's guard resolves the platform and the account home
            # natively; a fake CLI under a synthetic HOME needs the test shim.
            shim = install_engine_shim(home, name="magpie-engine-shim.sh")
            status = home / "status.json"
            status.write_text(status_body, encoding="utf-8")
            cli = home / "magpie-fake"
            cli.write_text("#!/bin/sh\ncase \"$1\" in\n"
                           "  status) cat \"$MAGPIE_FAKE_STATUS\" ;;\n"
                           "  serve) exit 1 ;;\n"
                           "esac\n", encoding="utf-8")
            cli.chmod(0o755)
            environment = {"HOME": str(home), "PATH": "/usr/bin:/bin",
                           "DEPLOY_PLATFORM": "linux", "MAGPIE_CLI_BIN": str(cli),
                           "MAGPIE_FAKE_STATUS": str(status),
                           "MAGPIE_START_ATTEMPTS": "1", "DOTFILES_MAGPIE_ENGINE": str(shim)}
            return subprocess.run(["/bin/bash", str(COMMAND), "start"], env=environment,
                                  capture_output=True, text=True, timeout=10, check=False)

    def run_public_command(self, command, status_body):
        """Run a public Magpie command against a fake CLI status response."""
        with tempfile.TemporaryDirectory(prefix="dotfiles-magpie-readiness-") as temporary:
            home = Path(temporary)
            # The command's guard resolves the platform and the account home
            # natively; a fake CLI under a synthetic HOME needs the test shim.
            shim = install_engine_shim(home, name="magpie-engine-shim.sh")
            status = home / "status.json"
            status.write_text(status_body, encoding="utf-8")
            cli = home / "magpie-fake"
            cli.write_text("#!/bin/sh\ncase \"$1\" in\n"
                           "  status) cat \"$MAGPIE_FAKE_STATUS\" ;;\n"
                           "  *) exit 0 ;;\n"
                           "esac\n", encoding="utf-8")
            cli.chmod(0o755)
            environment = {"HOME": str(home), "PATH": "/usr/bin:/bin",
                           "DEPLOY_PLATFORM": "linux", "MAGPIE_CLI_BIN": str(cli),
                           "MAGPIE_FAKE_STATUS": str(status),
                           "MAGPIE_CATALOG_DIR": str(CATALOG),
                           "DOTFILES_MAGPIE_ENGINE": str(shim)}
            return subprocess.run(["/bin/bash", str(COMMAND), command], env=environment,
                                  capture_output=True, text=True, timeout=30, check=False)

    def assert_not_ready(self, status_body):
        result = self.run_start(status_body)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("gateway already answers", result.stdout)

    def test_start_rejects_a_status_response_without_running_true(self):
        self.assert_not_ready("{}\n")

    def test_start_rejects_running_false(self):
        self.assert_not_ready('{"running": false}\n')

    def test_start_rejects_malformed_status(self):
        self.assert_not_ready("not json\n")

    def test_start_rejects_non_boolean_running(self):
        self.assert_not_ready('{"running": "true"}\n')
        self.assert_not_ready('{"running": 1}\n')

    def test_start_accepts_running_true(self):
        result = self.run_start('{"running": true, "gateway": "http://127.0.0.1:3425"}\n')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("gateway already answers", result.stdout)

    def test_status_rejects_running_false_with_exit_zero(self):
        result = self.run_public_command(
            "status", '{"running": false, "gateway": "http://127.0.0.1:3425"}\n')
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("gateway|http://127.0.0.1:3425|does not answer", result.stdout)
        self.assertNotIn("gateway|http://127.0.0.1:3425|answers", result.stdout)
        self.assertIn("missing: gateway", result.stderr)

    def test_status_accepts_running_true(self):
        result = self.run_public_command(
            "status", '{"running": true, "gateway": "http://127.0.0.1:3425"}\n')
        self.assertIn("gateway|http://127.0.0.1:3425|answers", result.stdout)
        self.assertNotIn("missing: gateway", result.stderr)

    def test_test_rejects_running_false_with_exit_zero(self):
        result = self.run_public_command(
            "test", '{"running": false, "gateway": "http://127.0.0.1:3425"}\n')
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("the Magpie gateway does not answer on", result.stderr)
        self.assertNotIn("role|model|state|detail", result.stdout)


if __name__ == "__main__":
    unittest.main()
