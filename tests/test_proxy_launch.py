"""The shared proxy launcher: one endpoint decision for every shell.

The POSIX launcher owns the endpoint precedence, the health check, and the
fallback. The Nushell adapter reads the same answer, so a session in either
shell routes the same way. These checks drive the public commands with a local
endpoint and compare what a child actually receives.

The bindings the launcher emits carry fixed variable names and single-line
values, so a value never introduces a variable of its own. The POSIX session
helper reads the same answer and refuses what the launcher refuses.
"""
import os
import shutil
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
LAUNCHER = SOURCE / "dot_local/bin/executable_with-proxy"
DIRECT = SOURCE / "dot_local/bin/executable_direct"
ADAPTER = SOURCE / "dot_config/nushell/proxy.nu"
CONFIG_TEMPLATE = SOURCE / ".chezmoi.toml.tmpl"
ENV_CORE_TEMPLATE = SOURCE / "dot_env_core.tmpl"
NU = os.environ.get("DOTFILES_TEST_NU") or shutil.which("nu")

# The variables the launchers own.
PROXY_VARIABLES = (
    "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
    "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy", "PROXY",
)
# The inherited variables a direct launch clears for its child.
INHERITED_VARIABLES = PROXY_VARIABLES + ("FTP_PROXY", "ftp_proxy")


def proxy_variables(text):
    """The proxy variables in the environment of a child process."""
    found = {}
    for line in text.splitlines():
        name, separator, value = line.partition("=")
        if separator and name in PROXY_VARIABLES:
            found[name] = value
    return found


class LauncherFixture:
    """A disposable home with the managed launchers and a probe stub."""

    def __init__(self, root):
        self.root = root
        self.bin = root / "bin"
        self.bin.mkdir(parents=True, exist_ok=True)
        for name, source in (("with-proxy", LAUNCHER), ("direct", DIRECT)):
            target = self.bin / name
            shutil.copy2(source, target)
            target.chmod(0o755)
        # The probe stub answers for one port and stays silent for the others,
        # so the health check is exercised without a proxy on the host.
        self.nc = self.bin / "nc"
        self.nc.write_text('#!/bin/sh\n[ "$3" = "${LISTENING_PORT:-none}" ]\n')
        self.nc.chmod(0o755)
        self.env = {
            "HOME": str(root / "home"),
            "PATH": f"{self.bin}:/usr/bin:/bin",
        }
        (root / "home").mkdir(parents=True, exist_ok=True)

    def run(self, arguments, environment=None, *, launcher="with-proxy"):
        return subprocess.run(
            [str(self.bin / launcher), *arguments],
            env={**self.env, **(environment or {})},
            capture_output=True, text=True, timeout=30)

    def child_environment(self, arguments=(), environment=None, *, command=("env",),
                          launcher="with-proxy"):
        """The proxy variables a child receives through the launcher."""
        result = self.run([*arguments, *command], environment, launcher=launcher)
        return result, proxy_variables(result.stdout)


class ProxyLauncherTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dotfiles-proxy-launcher-")
        self.addCleanup(temporary.cleanup)
        self.fixture = LauncherFixture(Path(temporary.name))

    def test_the_explicit_endpoint_wins_over_the_probe(self):
        result, variables = self.fixture.child_environment(
            [], {"PROXY_HTTP": "http://proxy.example.invalid:8080",
                "LISTENING_PORT": "7897"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(variables["HTTP_PROXY"], "http://proxy.example.invalid:8080")
        self.assertEqual(variables["http_proxy"], "http://proxy.example.invalid:8080")
        self.assertEqual(variables["PROXY"], "http://proxy.example.invalid:8080")
        self.assertEqual(variables["ALL_PROXY"], "socks5h://proxy.example.invalid:8080")

    def test_the_probe_prefers_the_port_the_device_serves(self):
        for port in ("7897", "7890"):
            with self.subTest(port=port):
                result, variables = self.fixture.child_environment(
                    [], {"LISTENING_PORT": port})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(variables["HTTP_PROXY"], f"http://127.0.0.1:{port}")
                self.assertEqual(variables["ALL_PROXY"], f"socks5h://127.0.0.1:{port}")

    def test_the_ordinary_fallback_answers_when_nothing_is_healthy(self):
        result, variables = self.fixture.child_environment([])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(variables["HTTP_PROXY"], "http://127.0.0.1:7890")
        self.assertEqual(variables["NO_PROXY"], "localhost,127.0.0.1,::1")

    def test_the_supported_overrides_reach_the_child(self):
        result, variables = self.fixture.child_environment(
            [], {"PROXY_HTTP": "http://proxy.example.invalid:8080",
                "PROXY_SOCKS": "socks5h://proxy.example.invalid:1080",
                "PROXY_NO": "localhost,127.0.0.1,::1,example.invalid"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(variables["ALL_PROXY"], "socks5h://proxy.example.invalid:1080")
        self.assertEqual(variables["all_proxy"], "socks5h://proxy.example.invalid:1080")
        self.assertEqual(variables["NO_PROXY"], "localhost,127.0.0.1,::1,example.invalid")
        self.assertEqual(variables["no_proxy"], "localhost,127.0.0.1,::1,example.invalid")

    def test_a_url_with_a_query_survives_the_interface(self):
        endpoint = "http://user:pass@proxy.example.invalid:8080?token=a=b&x=1"
        result, variables = self.fixture.child_environment([], {"PROXY_HTTP": endpoint})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(variables["HTTP_PROXY"], endpoint)
        self.assertEqual(variables["PROXY"], endpoint)
        self.assertEqual(variables["ALL_PROXY"],
                         "socks5h://user:pass@proxy.example.invalid:8080?token=a=b&x=1")

    def test_the_direct_fallback_clears_the_inherited_variables_for_the_child(self):
        inherited = {name: "http://stale.example.invalid:1" for name in INHERITED_VARIABLES}
        result, variables = self.fixture.child_environment(
            ["--if-available"], inherited)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(variables, {})
        self.assertNotIn("stale.example.invalid", result.stdout)

    def test_the_direct_launcher_clears_the_same_variables(self):
        inherited = {name: "http://stale.example.invalid:1" for name in INHERITED_VARIABLES}
        result, variables = self.fixture.child_environment([], inherited, launcher="direct")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(variables, {})

    def test_the_proxied_launch_applies_its_environment_to_the_child_only(self):
        result, variables = self.fixture.child_environment(
            [], {"PROXY_HTTP": "http://proxy.example.invalid:8080"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(variables), set(PROXY_VARIABLES))
        # The launching shell keeps its own environment.
        shell = subprocess.run(
            ["/bin/sh", "-c",
             'with-proxy env > /dev/null; env | grep -c -E "^(HTTP_PROXY|HTTPS_PROXY|http_proxy|'
             'https_proxy|ALL_PROXY|all_proxy|NO_PROXY|no_proxy|PROXY|FTP_PROXY|ftp_proxy)=" '
             "|| true"],
            env=self.fixture.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(shell.stdout.strip(), "0")

    def test_a_line_separator_in_an_override_is_refused(self):
        for override in ("PROXY_HTTP", "PROXY_SOCKS", "PROXY_NO"):
            for separator in ("\n", "\r"):
                with self.subTest(override=override, separator=separator):
                    value = f"http://proxy.example.invalid:8080{separator}INJECTED=1"
                    result = self.fixture.run(["/bin/sh", "-c", "printf child-ran"],
                                              {override: value})
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn("child-ran", result.stdout)
                    self.assertIn("line separator", result.stderr)

    def test_no_extra_name_reaches_the_child(self):
        result = self.fixture.run(["/bin/sh", "-c", "env"],
                                  {"PROXY_HTTP": "http://proxy.example.invalid:8080\nINJECTED=1"})
        self.assertNotIn("INJECTED", result.stdout)

    def test_the_child_environment_holds_only_the_owned_names(self):
        result = self.fixture.run(["/bin/sh", "-c", "env"])
        self.assertEqual(result.returncode, 0, result.stderr)
        names = {line.split("=", 1)[0] for line in result.stdout.splitlines() if "=" in line}
        self.assertEqual({name for name in names if "proxy" in name.lower()},
                         set(PROXY_VARIABLES))

    def test_the_export_output_carries_only_the_owned_names(self):
        result = self.fixture.run(["--print"],
                                  {"PROXY_HTTP": "http://proxy.example.invalid:8080"})
        self.assertEqual(result.returncode, 0, result.stderr)
        names = [line.split("=", 1)[0].removeprefix("export ")
                 for line in result.stdout.splitlines() if line]
        self.assertEqual(names, list(PROXY_VARIABLES))

    def test_the_export_output_carries_no_extra_name(self):
        result = self.fixture.run(["--print"],
                                  {"PROXY_HTTP": "http://proxy.example.invalid:8080\nINJECTED=1"})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertNotIn("INJECTED", result.stdout)

    def test_the_export_output_evaluates_to_the_chosen_value(self):
        endpoint = "http://user:pass@proxy.example.invalid:8080?token=a=b&x=1"
        printed = self.fixture.run(["--print"], {"PROXY_HTTP": endpoint})
        self.assertEqual(printed.returncode, 0, printed.stderr)
        evaluated = subprocess.run(
            ["/bin/sh", "-c", 'eval "$1"; printf "%s\\n" "$HTTP_PROXY"', "sh", printed.stdout],
            env={"PATH": "/usr/bin:/bin"}, capture_output=True, text=True, timeout=30)
        self.assertEqual(evaluated.stdout.strip(), endpoint)

    def test_the_export_output_round_trips_through_a_posix_shell(self):
        """A POSIX shell must read the export lines and keep the value intact."""
        shell = shutil.which("dash") or shutil.which("sh")
        if not shell:
            self.skipTest("no POSIX shell on this host")
        value = "http://proxy.example.invalid:8080/o'k\tvalue"
        printed = self.fixture.run(["--print"], {"PROXY_HTTP": value})
        self.assertEqual(printed.returncode, 0, printed.stderr)
        # A POSIX single-quoted literal, not bash's ANSI-C $'...' quote: a
        # POSIX shell reads the latter as ordinary characters and keeps them.
        self.assertNotIn("$'", printed.stdout)
        self.assertIn("export HTTP_PROXY='", printed.stdout)
        script = self.fixture.root / "exports.sh"
        script.write_text(printed.stdout, encoding="utf-8")
        sourced = subprocess.run(
            [shell, "-c", '. "$1"; printf "%s" "$HTTP_PROXY"', "sh", str(script)],
            env={"PATH": "/usr/bin:/bin"}, capture_output=True, text=True, timeout=30)
        self.assertEqual(sourced.returncode, 0, sourced.stderr)
        self.assertEqual(sourced.stdout, value)

    def test_the_launcher_preserves_the_arguments_and_the_exit_status(self):
        result = self.fixture.run(["/bin/sh", "-c", 'printf "%s|" "$@"', "sh", "one", "two three"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "one|two three|")
        failed = self.fixture.run(["/bin/sh", "-c", "exit 7"])
        self.assertEqual(failed.returncode, 7)

    def test_a_local_endpoint_is_used_for_the_child(self):
        listener = socket.socket()
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        try:
            endpoint = f"http://127.0.0.1:{port}"
            result, variables = self.fixture.child_environment([], {"PROXY_HTTP": endpoint})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(variables["HTTP_PROXY"], endpoint)
            self.assertEqual(variables["ALL_PROXY"], f"socks5h://127.0.0.1:{port}")
        finally:
            listener.close()

    def test_the_health_check_finds_a_listening_endpoint(self):
        listener = socket.socket()
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind(("127.0.0.1", 7897))
        except OSError:
            listener.close()
            self.skipTest("a proxy already serves 7897 on this host")
        listener.listen(1)
        try:
            result = subprocess.run(
                ["/bin/bash", str(LAUNCHER), "--print-url"],
                env={"PATH": "/usr/bin:/bin"}, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "http://127.0.0.1:7897")
        finally:
            listener.close()


class PosixSessionTests(unittest.TestCase):
    """The POSIX session helper reads the shared answer and refuses what it refuses."""

    @classmethod
    def setUpClass(cls):
        cls.chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        if not cls.chezmoi:
            raise unittest.SkipTest("rendering the shared settings requires chezmoi")
        cls.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-proxy-session-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        cls.env_core = cls.render_env_core()

    @classmethod
    def render_env_core(cls):
        """Render the shared POSIX settings once, outside any home."""
        home = cls.root / "render"
        config = cls.root / "chezmoi.toml"
        environment = {"HOME": str(home), "PATH": "/usr/bin:/bin",
                       "DOTFILES_PLATFORM": "linux", "DOTFILES_ROLE": "workstation"}
        common = [cls.chezmoi, "--source", str(SOURCE), "--destination", str(home),
                  "--cache", str(cls.root / "cache")]
        rendered = subprocess.run(
            common + ["--config", str(config), "execute-template", "--init"],
            input=CONFIG_TEMPLATE.read_text(),
            env=environment, capture_output=True, text=True, timeout=120)
        if rendered.returncode != 0:
            raise AssertionError(rendered.stderr)
        config.write_text(rendered.stdout)
        result = subprocess.run(
            common + ["--config", str(config), "execute-template"],
            input=ENV_CORE_TEMPLATE.read_text(),
            env=environment, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise AssertionError(result.stderr)
        return result.stdout

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dotfiles-proxy-session-home-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.fixture = LauncherFixture(self.root)
        (self.root / "home" / ".env_core").write_text(self.env_core)

    def session(self, script, environment=None):
        """Run a script in a session that sourced the rendered settings."""
        return subprocess.run(["/bin/sh", "-c", f'. "$HOME/.env_core"; {script}'],
                              env={**self.fixture.env, **(environment or {})},
                              capture_output=True, text=True, timeout=30)

    def test_the_session_helper_applies_the_shared_decision(self):
        result = self.session('noproxy; printf "%s\\n" "$http_proxy"',
                              {"PROXY_HTTP": "http://proxy.example.invalid:8080"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "http://proxy.example.invalid:8080")

    def test_the_session_helper_refuses_a_rejected_override(self):
        result = self.session(
            'noproxy; status=$?; printf "status=%s injected=[%s]\\n" "$status" "${INJECTED-unset}"',
            {"PROXY_HTTP": "http://proxy.example.invalid:8080\nINJECTED=1"})
        status, injected = result.stdout.split()
        self.assertNotEqual(status, "status=0")
        self.assertEqual(injected, "injected=[unset]")
        self.assertIn("line separator", result.stderr)


@unittest.skipUnless(NU, "requires Nushell")
class NushellProxyLauncherTests(unittest.TestCase):
    """The Nushell adapter must reach the same decision as the POSIX launcher."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dotfiles-proxy-nu-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.fixture = LauncherFixture(self.root)
        self.empty = self.root / "empty.nu"
        self.empty.write_text("", encoding="utf-8")

    def nu(self, script, environment=None):
        return subprocess.run(
            [NU, "--no-config-file", "--env-config", str(self.empty), "-c",
             f'source "{ADAPTER}"; {script}'],
            env={**self.fixture.env, **(environment or {})},
            capture_output=True, text=True, timeout=60)

    def test_the_nushell_launcher_agrees_with_the_posix_launcher(self):
        for environment in ({}, {"PROXY_HTTP": "http://proxy.example.invalid:8080"},
                            {"LISTENING_PORT": "7897"},
                            {"PROXY_HTTP": "http://user:pass@proxy.example.invalid:8080?token=a=b"},
                            {"PROXY_HTTP": "http://proxy.example.invalid:8080",
                             "PROXY_SOCKS": "socks5h://proxy.example.invalid:1080",
                             "PROXY_NO": "localhost,example.invalid"}):
            with self.subTest(environment=sorted(environment)):
                posix = self.fixture.run(["env"], environment)
                nushell = self.nu("with-proxy env", environment)
                self.assertEqual(posix.returncode, 0, posix.stderr)
                self.assertEqual(nushell.returncode, 0, nushell.stderr)
                self.assertEqual(proxy_variables(nushell.stdout),
                                 proxy_variables(posix.stdout))

    def test_the_nushell_launcher_runs_the_child_directly_without_an_endpoint(self):
        inherited = {name: "http://stale.example.invalid:1" for name in INHERITED_VARIABLES}
        result = self.nu("with-proxy --if-available env", inherited)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(proxy_variables(result.stdout), {})
        self.assertNotIn("stale.example.invalid", result.stdout)

    def test_the_nushell_launcher_leaves_the_session_unchanged(self):
        inherited = {name: "http://stale.example.invalid:1" for name in INHERITED_VARIABLES}
        result = self.nu(
            'let before = ($env | columns | where {|name| $name in $proxy_variables } | sort); '
            'let child = (with-proxy env | lines | where {|line| $line =~ "proxy" } | length); '
            'let after = ($env | columns | where {|name| $name in $proxy_variables } | sort); '
            'print $"($child) ($before == $after)"',
            inherited)
        self.assertEqual(result.returncode, 0, result.stderr)
        child, unchanged = result.stdout.split()
        self.assertGreater(int(child), 0)
        self.assertEqual(unchanged, "true")

    def test_the_nushell_launcher_preserves_the_arguments_and_the_exit_status(self):
        result = self.nu('with-proxy /bin/sh -c \'printf "%s|" "$@"\' sh one "two three"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "one|two three|")
        failed = self.nu('with-proxy /bin/sh -c "exit 7"')
        self.assertEqual(failed.returncode, 7)

    def test_the_nushell_session_helper_reads_the_shared_decision(self):
        environment = {"PROXY_HTTP": "http://proxy.example.invalid:8080"}
        shared = self.fixture.run(["--print-env"], environment)
        self.assertEqual(shared.returncode, 0, shared.stderr)
        expected = dict(line.split("=", 1) for line in shared.stdout.splitlines())
        result = self.nu(
            'noproxy; $env | transpose key value '
            '| where {|pair| $pair.key in $proxy_variables } '
            '| each {|pair| $"($pair.key)=($pair.value)" } | str join "\\n"',
            environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        observed = dict(line.split("=", 1) for line in result.stdout.splitlines() if line)
        # Nu's environment is case-insensitive, so the session keeps one
        # spelling per variable; the values are the shared ones.
        for name in ("http_proxy", "https_proxy", "ALL_PROXY", "NO_PROXY", "PROXY"):
            self.assertEqual(observed[name], expected[name])

    def test_the_nushell_session_helper_refuses_a_rejected_override(self):
        result = self.nu("noproxy",
                         {"PROXY_HTTP": "http://proxy.example.invalid:8080\nINJECTED=1"})
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("INJECTED", result.stdout)

    def test_the_nushell_unproxy_clears_the_supported_variables(self):
        inherited = {name: "http://stale.example.invalid:1" for name in INHERITED_VARIABLES}
        result = self.nu(
            "noproxy; unproxy; $env | columns "
            '| where {|name| $name in $proxy_variables } | to json --raw',
            inherited)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "[]")


if __name__ == "__main__":
    unittest.main()
