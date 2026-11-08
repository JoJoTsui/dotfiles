"""Checks for the host bring-up command with stub daemons; no host changes."""
import os
import json
import shutil
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
SCRIPT = SOURCE / "dot_local/bin/executable_dotfiles-host-up"


class HostUpTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-host-up-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bin = self.root / "bin"
        self.home = self.root / "home"
        self.live = self.root / "live"
        self.repo = self.root / "repo"
        for directory in (self.bin, self.home, self.live, self.repo):
            directory.mkdir()
        config = self.home / ".config/herdr/config.toml"
        config.parent.mkdir(parents=True)
        config.write_text("[session]\nresume_agents_on_restore = true\n")
        self.write_stub("curl", """#!/bin/sh
for argument in "$@"; do
    case "$argument" in
        *9090*) echo 200; exit 0 ;;
        *8787*) echo 404; exit 0 ;;
    esac
done
echo 000
""")
        self.write_stub("with-proxy", "#!/bin/sh\nexec \"$@\"\n")
        for name in ("caveman", "codex", "link-home", "mihomo"):
            self.write_stub(name, "#!/bin/sh\nexit 0\n")
        self.herdr_state = self.root / "herdr-running"
        self.herdr_state.touch()
        self.herdr_log = self.root / "herdr.log"
        self.write_stub("herdr", """#!/bin/sh
printf '%s\\n' "$*" >> "$HERDR_LOG"
if [ "$1 $2" = "api snapshot" ]; then
    [ -f "$HERDR_STATE" ] && exit 0
    exit 1
fi
if [ "$1" = server ]; then
    touch "$HERDR_STATE"
    exit 0
fi
exit 0
""")
        self.write_stub("health", """#!/bin/sh
printf 'health %s\\n' "$*" >> "$HERDR_LOG"
exit ${HEALTH_EXIT:-0}
""")

    def write_stub(self, name, text):
        path = self.bin / name
        path.write_text(text, encoding="utf-8")
        path.chmod(0o755)

    def environment(self):
        return {
            "HOME": str(self.home),
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "DOTFILES_SOURCE": str(self.repo),
            "DOTFILES_LIVE_ROOT": str(self.live),
            "DOTFILES_WITH_PROXY": str(self.bin / "with-proxy"),
            "DOTFILES_CAVEMAN_BIN": str(self.bin / "caveman"),
            "DOTFILES_CODEX_BIN": str(self.bin / "codex"),
            "DOTFILES_HERDR_BIN": str(self.bin / "herdr"),
            "DOTFILES_CURL": str(self.bin / "curl"),
            "DOTFILES_AGENT_HEALTH": str(self.bin / "health"),
            "DOTFILES_LINK_HOME": str(self.bin / "link-home"),
            "DOTFILES_MIHOMO_SUPERVISOR": str(self.bin / "mihomo"),
            "HERDR_STATE": str(self.herdr_state),
            "HERDR_LOG": str(self.herdr_log),
        }

    def run_host_up(self, *arguments):
        return subprocess.run(
            ["/bin/bash", str(SCRIPT), *arguments],
            env=self.environment(),
            cwd=SOURCE,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_status_is_read_only_and_healthy_with_stubs(self):
        result = self.run_host_up("status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ok   links", result.stdout)
        self.assertIn("ok   mihomo", result.stdout)
        self.assertIn("host stack ready", result.stdout)

    def test_up_with_already_running_daemons_is_idempotent(self):
        result = self.run_host_up("up")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("host stack ready", result.stdout)
        self.assertFalse((self.home / ".caveman/run").exists())

    def test_restore_does_not_restart_a_running_herdr(self):
        result = self.run_host_up("up", "--restore")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("restore happens on the next server start", result.stderr)
        self.assertNotIn("server", self.herdr_log.read_text().splitlines())

    def test_restore_starts_herdr_when_absent_and_up_does_not(self):
        plain = self.run_host_up("up")
        self.assertEqual(plain.returncode, 0, plain.stderr)
        self.assertNotIn("server", self.herdr_log.read_text().splitlines())
        self.herdr_state.unlink()
        restored = self.run_host_up("up", "--restore")
        self.assertEqual(restored.returncode, 0, restored.stderr)
        self.assertIn("server", self.herdr_log.read_text().splitlines())
        events = self.herdr_log.read_text().splitlines()
        self.assertLess(events.index("health --before-restore"), events.index("server"))
        self.assertEqual(events[-1], "health ")

    def test_failed_preflight_never_starts_herdr(self):
        self.herdr_state.unlink()
        self.write_stub("health", "#!/bin/sh\nexit 1\n")
        result = self.run_host_up("up", "--restore")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("restore withheld", result.stderr)
        self.assertFalse(self.herdr_state.exists())
        self.assertFalse(self.herdr_log.exists())

    def test_missing_health_never_starts_herdr(self):
        self.herdr_state.unlink()
        (self.bin / "health").unlink()
        result = self.run_host_up("up", "--restore")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("health preflight is missing", result.stderr)
        self.assertFalse(self.herdr_state.exists())

    def test_failed_links_stop_before_other_dependencies(self):
        self.herdr_state.unlink()
        self.write_stub("link-home", "#!/bin/sh\nexit 1\n")
        self.write_stub("curl", "#!/bin/sh\necho unexpected >&2\nexit 1\n")
        result = self.run_host_up("up", "--restore")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stopped at ensure_links", result.stderr)
        self.assertNotIn("unexpected", result.stderr)
        self.assertFalse(self.herdr_state.exists())

    def test_restore_requires_enabled_config_before_starting_herdr(self):
        self.herdr_state.unlink()
        (self.home / ".config/herdr/config.toml").unlink()
        result = self.run_host_up("up", "--restore")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("restore is not enabled", result.stderr)
        self.assertFalse(self.herdr_state.exists())

    def test_real_health_allows_cold_restore_but_keeps_dependency_checks(self):
        self.herdr_state.unlink()
        self.write_stub("health", f'#!/bin/sh\nexec /bin/bash "{SOURCE}/dot_local/bin/executable_dotfiles-agent-health" "$@"\n')
        self.write_stub("codegraph", "#!/bin/sh\necho codegraph-test\n")
        self.write_stub("graphify", "#!/bin/sh\nexit 0\n")
        self.write_stub("curl", """#!/bin/sh
for argument in "$@"; do
    case "$argument" in
        *9090*) echo 200; exit 0 ;;
        *8787*) echo 404; exit 0 ;;
        *cloudflare*) echo loc=US; exit 0 ;;
    esac
done
exit 1
""")
        run = self.home / ".caveman/run/8787.json"
        run.parent.mkdir(parents=True)
        run.write_text('{"pid":' + str(os.getpid()) + '}')
        result = self.run_host_up("up", "--restore")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Herdr check deferred", result.stdout)
        self.assertTrue(self.herdr_state.exists())

        self.herdr_state.unlink()
        self.herdr_log.unlink()
        run.unlink()
        failed = self.run_host_up("up", "--restore")
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("caveman run file", failed.stderr)
        self.assertFalse(self.herdr_state.exists())
        self.assertFalse(self.herdr_log.exists())

    def test_cold_restore_removes_duplicate_session_but_keeps_explicit_resume(self):
        self.herdr_state.unlink()
        session = {"source": "herdr:codex", "agent": "codex", "kind": "id", "value": "conversation"}
        panes = {"1": {"cwd": "/shell", "agent_session": session},
                 "2": {"cwd": "/project", "agent_session": session,
                       "agent_resume": {"argv": ["codex-herdr", "resume", "conversation"]}}}
        path = self.home / ".config/herdr/session.json"
        original = json.dumps({"workspaces": [{"tabs": [{"panes": panes}]}]})
        path.write_text(original)
        result = self.run_host_up("up", "--restore")
        self.assertEqual(result.returncode, 0, result.stderr)
        saved = json.loads(path.read_text())["workspaces"][0]["tabs"][0]["panes"]
        self.assertEqual(saved["1"], {"cwd": "/shell"})
        self.assertEqual(saved["2"], panes["2"])
        self.assertEqual(next(path.parent.glob("session.json.pre-restore.*.bak")).read_text(), original)

    def test_remote_preparation_normalizes_snapshot_without_starting_herdr(self):
        self.herdr_state.unlink()
        session = {"source": "herdr:codex", "agent": "codex", "kind": "id", "value": "conversation"}
        path = self.home / ".config/herdr/session.json"
        path.write_text(json.dumps({"workspaces": [{"tabs": [{"panes": {
            "1": {"agent_session": session}, "2": {"agent_session": session}}}]}]}))
        result = self.run_host_up("up")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.herdr_state.exists())
        self.assertNotIn("server", self.herdr_log.read_text().splitlines())
        self.assertIn("remote client", result.stdout)
        panes = json.loads(path.read_text())["workspaces"][0]["tabs"][0]["panes"]
        self.assertNotIn("agent_session", panes["2"])

    def test_cold_remote_preparation_starts_dependencies_in_order_and_leaves_herdr_down(self):
        self.herdr_state.unlink()
        events = self.root / "startup-order"
        self.write_stub("curl", f'''#!/bin/sh
for argument in "$@"; do
    case "$argument" in
        *9090*) [ -f "{self.root}/mihomo-ready" ] && echo 200 || echo 000; exit 0 ;;
        *8787*) [ -f "{self.root}/caveman-ready" ] && echo 404 || echo 000; exit 0 ;;
    esac
done
''')
        self.write_stub("mihomo", f'''#!/bin/sh
echo mihomo >> "{events}"
touch "{self.root}/mihomo-ready"
''')
        self.write_stub("caveman", f'''#!/bin/sh
[ -f "{self.root}/mihomo-ready" ] || exit 1
echo caveman >> "{events}"
touch "{self.root}/caveman-ready"
''')
        self.write_stub("codex", f'''#!/bin/sh
case "$*" in
    "app-server daemon version") [ -f "{self.root}/codex-ready" ] ;;
    "app-server daemon start")
        [ -f "{self.root}/caveman-ready" ] || exit 1
        echo codex >> "{events}"
        touch "{self.root}/codex-ready" ;;
    *) exit 1 ;;
esac
''')
        self.write_stub("health", f'''#!/bin/sh
[ -f "{self.root}/codex-ready" ] || exit 1
echo health >> "{events}"
''')
        result = self.run_host_up("up")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events.read_text().splitlines(), ["mihomo", "caveman", "codex", "health"])
        self.assertFalse(self.herdr_state.exists())
        self.assertNotIn("server", self.herdr_log.read_text().splitlines())

    def test_link_repair_does_not_recurse_into_service_preparation(self):
        marker = self.root / "linked"
        self.write_stub("link-home", f'''#!/bin/sh
if [ "$1" = --check ]; then [ -f "{marker}" ]; exit $?; fi
[ "$1" = --links-only ] || exit 9
touch "{marker}"
''')
        result = self.run_host_up("up")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(marker.exists())

    def test_failed_integration_policy_stops_before_agent_startup(self):
        self.herdr_state.unlink()
        adapter = self.repo / "deployment/legacy/agent-integrations.sh"
        adapter.parent.mkdir(parents=True)
        adapter.write_text("#!/bin/sh\nexit 1\n")
        result = self.run_host_up("up")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stopped at ensure_agent_integrations", result.stderr)
        self.assertFalse(self.herdr_state.exists())
        self.assertFalse(self.herdr_log.exists())

    def test_invalid_saved_session_withholds_restore(self):
        self.herdr_state.unlink()
        path = self.home / ".config/herdr/session.json"
        path.write_text("invalid JSON")
        result = self.run_host_up("up", "--restore")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("saved Herdr session validation", result.stderr)
        self.assertFalse(self.herdr_state.exists())
        self.assertEqual(path.read_text(), "invalid JSON")

    def test_failing_health_fails_the_command(self):
        environment = self.environment()
        environment["HEALTH_EXIT"] = "1"
        result = subprocess.run(
            ["/bin/bash", str(SCRIPT), "up"], env=environment, cwd=SOURCE,
            capture_output=True, text=True, timeout=60)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("health preflight", result.stderr)
        self.assertNotIn("host stack ready", result.stdout)

    def test_missing_legacy_link_home_is_not_a_failure(self):
        environment = self.environment()
        environment["DOTFILES_LINK_HOME"] = str(self.root / "missing-link-home")
        result = subprocess.run(
            ["/bin/bash", str(SCRIPT), "status"], env=environment, cwd=SOURCE,
            capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("links (not a legacy home)", result.stdout)

    def test_installed_legacy_helper_discovers_persistent_repo(self):
        installed = self.live / ".local/bin/dotfiles-host-up"
        installed.parent.mkdir(parents=True)
        shutil.copy2(SCRIPT, installed)
        linker = self.live / "dotfiles/deployment/legacy/link-home.sh"
        linker.parent.mkdir(parents=True)
        linker.write_text("#!/bin/sh\nexit 0\n")
        environment = self.environment()
        for name in ("DOTFILES_SOURCE", "DOTFILES_LIVE_ROOT", "DOTFILES_LINK_HOME"):
            environment.pop(name)
        result = subprocess.run(["/bin/bash", str(installed), "status"],
                                env=environment, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("not a legacy home", result.stdout)
        self.assertIn("ok   links\n", result.stdout)

    def test_help_and_syntax(self):
        result = self.run_host_up("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage: dotfiles-host-up", result.stdout)
        syntax = subprocess.run(["/bin/bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)


if __name__ == "__main__":
    unittest.main()
