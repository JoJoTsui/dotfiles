"""The managed Codex resume command, without a real Codex or a real gateway.

The command under test is the public seam: it hands an argv and an
environment to ``codex``. A fake ``codex`` records both, so the tests assert
what the next process sees rather than how the wrapper is written.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

try:
    from . import codex_resume_runtime
except ImportError:  # pragma: no cover - direct module execution
    import codex_resume_runtime

SOURCE = Path(__file__).resolve().parents[1]
COMMAND = SOURCE / "dot_local/bin/executable_dotfiles-codex-resume"

FAKE_CODEX = '''#!/usr/bin/env python3
"""A fake Codex CLI that records the argv and environment it was given."""
import json
import os
import pathlib
import sys

if "--version" in sys.argv[1:]:
    # The command reads the version before it resumes anything. A version
    # query is not a resume, so it is not recorded.
    print("codex-cli " + os.environ.get("FAKE_CODEX_VERSION", "0.169.0"))
    raise SystemExit(0)

record = pathlib.Path(os.environ["FAKE_CODEX_RECORD"])
payload = {
    "argv": sys.argv[1:],
    "env": {
        key: value
        for key, value in os.environ.items()
        if key.startswith("DOTFILES_CODEX_RESUME_")
    },
}
record.write_text(json.dumps(payload, indent=2))
'''

MAGPIE_TOKEN = "placeholder-gateway-token"

PROFILE = """model_provider = "magpie"
model = "magpie/conductor"
model_catalog_json = "magpie-models.json"

[model_providers.magpie]
name = "magpie"
base_url = "http://127.0.0.1:39411/v1"
wire_api = "responses"
experimental_bearer_token = "{token}"
http_headers = {{ "x-openai-actor-authorization" = "magpie" }}
"""


class CodexResumeCommandTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-codex-resume-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.codex_home = self.home / ".codex"
        self.codex_home.mkdir(parents=True)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.record = self.root / "codex-record.json"
        fake = self.bin / "codex"
        fake.write_text(FAKE_CODEX)
        fake.chmod(0o755)
        self.env = {
            "HOME": str(self.home),
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "FAKE_CODEX_RECORD": str(self.record),
            "CODEX_HOME": str(self.codex_home),
        }

    def write_profile(self, token=MAGPIE_TOKEN):
        (self.codex_home / "magpie.config.toml").write_text(PROFILE.format(token=token))

    def write_base_config(self, text):
        (self.codex_home / "config.toml").write_text(text)

    def run_command(self, *args):
        return subprocess.run(
            [str(COMMAND), *args],
            env=self.env,
            capture_output=True,
            text=True,
        )

    def recorded(self):
        self.assertTrue(self.record.exists(), "the fake codex was never run")
        return json.loads(self.record.read_text())

    def overrides(self, payload=None):
        payload = payload or self.recorded()
        argv = payload["argv"]
        values = []
        for index, item in enumerate(argv):
            if item == "-c" or item == "--config":
                values.append(argv[index + 1])
            elif item.startswith("--config="):
                values.append(item.split("=", 1)[1])
        return values

    def test_resume_covers_every_directory_and_non_interactive_threads(self):
        result = self.run_command()
        self.assertEqual(result.returncode, 0, result.stderr)
        argv = self.recorded()["argv"]
        self.assertEqual(argv[:3], ["resume", "--all", "--include-non-interactive"])

    def test_resume_passes_a_session_id_a_last_flag_and_a_prompt(self):
        result = self.run_command("0199abcd-session", "--last", "continue please")
        self.assertEqual(result.returncode, 0, result.stderr)
        argv = self.recorded()["argv"]
        self.assertIn("0199abcd-session", argv)
        self.assertIn("--last", argv)
        self.assertIn("continue please", argv)

    def test_a_model_override_is_refused(self):
        result = self.run_command("-m", "gpt-6.1-sol")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.record.exists(), "the forbidden run reached codex")
        self.assertIn("saved model", result.stderr)

    def test_a_provider_override_is_refused(self):
        result = self.run_command("--model-provider", "magpie")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.record.exists(), "the forbidden run reached codex")
        self.assertIn("saved provider", result.stderr)

    def test_a_config_model_override_is_refused(self):
        result = self.run_command("-c", "model=gpt-6.1-sol")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.record.exists(), "the forbidden run reached codex")
        self.assertIn("saved model", result.stderr)

    def test_a_config_provider_override_is_refused(self):
        result = self.run_command("-c", "model_provider=magpie")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.record.exists(), "the forbidden run reached codex")
        self.assertIn("saved provider", result.stderr)

    def test_a_config_effort_override_is_refused(self):
        result = self.run_command("-c", "model_reasoning_effort=high")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.record.exists(), "the forbidden run reached codex")
        self.assertIn("saved reasoning effort", result.stderr)

    def test_a_spaced_config_override_is_refused(self):
        # Codex trims the key of an override before it applies it, so the
        # spaced form selects the very same setting.
        for override, phrase in (
            (' model = "gpt-6.1-sol"', "saved model"),
            ('\tmodel_provider\t= "magpie"', "saved provider"),
            (' model_reasoning_effort = "high" ', "saved reasoning effort"),
        ):
            with self.subTest(override=override):
                result = self.run_command("-c", override)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.record.exists(), "the forbidden run reached codex")
                self.assertIn(phrase, result.stderr)

    def test_a_magpie_provider_override_is_refused(self):
        # The command owns model_providers.magpie: it derives it from
        # Magpie's profile and attaches the gateway credential to it. An
        # override of that table is not a harmless preference: it would
        # reroute the thread away from its saved provider, and the
        # credential travels with the provider. The definitions the command
        # appends come after the user's overrides, so such an override would
        # be overwritten in silence.
        for override in (
            "model_providers.magpie.base_url=http://127.0.0.1:1/v1",
            "model_providers.magpie.wire_api=chat",
            "model_providers.magpie.env_key=OTHER_TOKEN",
        ):
            with self.subTest(override=override):
                result = self.run_command("-c", override)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse(self.record.exists(), "the forbidden run reached codex")
                self.assertIn("model_providers.magpie", result.stderr)
                self.assertIn("saved provider", result.stderr)

    def test_a_spaced_magpie_provider_override_is_refused(self):
        # Codex trims the key of an override before it applies it, so the
        # spaced form selects the very same provider definition.
        for override in (
            ' model_providers.magpie.base_url = "http://127.0.0.1:1/v1"',
            '\tmodel_providers.magpie.wire_api\t= "chat"',
        ):
            with self.subTest(override=override):
                result = self.run_command("-c", override)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse(self.record.exists(), "the forbidden run reached codex")
                self.assertIn("model_providers.magpie", result.stderr)
                self.assertIn("saved provider", result.stderr)

    def test_another_provider_override_still_reaches_codex(self):
        # A provider the command does not generate is the user's own
        # business and keeps working.
        result = self.run_command("-c", "model_providers.other.base_url=http://127.0.0.1:9/v1")
        self.assertEqual(result.returncode, 0, result.stderr)
        values = self.overrides()
        self.assertIn("model_providers.other.base_url=http://127.0.0.1:9/v1", values)

    def test_the_usage_describes_the_rule_of_last(self):
        # Codex reads the positionals itself: without --last the first
        # positional is the session id and the second is the prompt; with
        # --last the first positional is the prompt of the most recent
        # thread.
        result = self.run_command("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--last", result.stdout)
        self.assertIn("prompt", result.stdout)
        self.assertIn("drop --last", result.stdout)

    def test_last_with_a_session_id_is_refused(self):
        # With --last and no prompt, codex resume reads the session id as
        # the prompt of the most recent thread. Passing it through would
        # type the id as a prompt, silently.
        result = self.run_command("--last", "01a1eff0-1111-2222-3333-444455556666")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(self.record.exists(), "the forbidden run reached codex")
        self.assertIn("drop --last to resume that thread", result.stderr)

    def test_last_with_an_ordinary_prompt_keeps_working(self):
        result = self.run_command("--last", "continue please")
        self.assertEqual(result.returncode, 0, result.stderr)
        argv = self.recorded()["argv"]
        self.assertIn("--last", argv)
        self.assertIn("continue please", argv)

    def test_a_session_id_without_last_keeps_working(self):
        result = self.run_command("01a1eff0-1111-2222-3333-444455556666")
        self.assertEqual(result.returncode, 0, result.stderr)
        argv = self.recorded()["argv"]
        self.assertIn("01a1eff0-1111-2222-3333-444455556666", argv)
        self.assertNotIn("--last", argv)

    def test_an_old_codex_is_refused(self):
        self.env["FAKE_CODEX_VERSION"] = "0.168.0"
        result = self.run_command()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.record.exists(), "the forbidden run reached codex")
        self.assertIn("0.168.0", result.stderr)
        self.assertIn("0.169.0", result.stderr)

    def test_the_pinned_codex_is_accepted(self):
        self.env["FAKE_CODEX_VERSION"] = "0.169.0"
        result = self.run_command()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.record.exists())

    def test_a_profile_override_is_refused(self):
        result = self.run_command("-p", "magpie")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.record.exists(), "the forbidden run reached codex")
        self.assertIn("per-thread", result.stderr)

    def test_the_provider_layer_selects_no_model_no_provider_and_no_effort(self):
        self.write_profile()
        result = self.run_command()
        self.assertEqual(result.returncode, 0, result.stderr)
        values = self.overrides()
        self.assertTrue(values, "no provider definition reached codex")
        selected = [value for value in values if value.split("=", 1)[0] in {
            "model", "model_provider", "model_reasoning_effort",
        }]
        self.assertEqual(selected, [], "the layer selected a model, a provider, or an effort")
        self.assertIn('model_providers.magpie.base_url="http://127.0.0.1:39411/v1"', values)
        self.assertIn('model_providers.magpie.wire_api="responses"', values)

    def test_the_credential_reaches_the_child_through_the_environment_only(self):
        self.write_profile()
        result = self.run_command()
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = self.recorded()
        argv = " ".join(payload["argv"])
        self.assertNotIn(MAGPIE_TOKEN, argv, "the credential entered argv")
        values = self.overrides(payload)
        self.assertNotIn(
            "model_providers.magpie.experimental_bearer_token=" + MAGPIE_TOKEN,
            values,
            "the credential entered a configuration override",
        )
        self.assertEqual(payload["env"]["DOTFILES_CODEX_RESUME_MAGPIE_TOKEN"], MAGPIE_TOKEN)
        self.assertTrue(
            any(value.startswith("model_providers.magpie.env_key=") for value in values),
            "the provider does not read the credential from the environment",
        )

    def test_the_device_provider_definition_wins_over_the_magpie_profile(self):
        self.write_profile()
        self.write_base_config(
            '[model_providers.magpie]\nname = "device magpie"\n'
            'base_url = "http://127.0.0.1:39555/v1"\nwire_api = "responses"\n'
        )
        result = self.run_command()
        self.assertEqual(result.returncode, 0, result.stderr)
        values = self.overrides()
        self.assertEqual(values, [], "the device's own definition was overridden")
        self.assertIn("device", result.stderr)

    def test_a_missing_magpie_profile_degrades_to_a_plain_resume(self):
        result = self.run_command()
        self.assertEqual(result.returncode, 0, result.stderr)
        argv = self.recorded()["argv"]
        self.assertEqual(argv[:3], ["resume", "--all", "--include-non-interactive"])
        self.assertEqual(self.overrides(), [])
        self.assertIn("magpie.config.toml", result.stderr)

    def test_a_linked_magpie_profile_is_refused(self):
        # The deployment's Codex boundary refuses an aliased path; the resume
        # command reads the same path and degrades instead of reading through
        # the link.
        outside = self.root / "outside-magpie.config.toml"
        outside.write_text(PROFILE.format(token=MAGPIE_TOKEN))
        link = self.codex_home / "magpie.config.toml"
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest("the host does not allow a symlink")
        result = self.run_command()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.overrides(), [], "the linked profile was read through the link")
        self.assertIn("symlink", result.stderr)

    def test_a_linked_base_configuration_is_refused(self):
        outside = self.root / "outside-config.toml"
        outside.write_text('[model_providers.other]\nname = "other"\nbase_url = "http://127.0.0.1:39666/v1"\n')
        link = self.codex_home / "config.toml"
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest("the host does not allow a symlink")
        self.write_profile()
        result = self.run_command()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.overrides(), [], "the linked configuration was read through the link")
        self.assertIn("symlink", result.stderr)

    def test_the_command_changes_no_file_in_the_codex_home(self):
        self.write_profile()
        self.write_base_config(
            '[model_providers.other]\nname = "other"\nbase_url = "http://127.0.0.1:39666/v1"\n'
        )
        before = {
            path.name: path.read_bytes()
            for path in sorted(self.codex_home.iterdir())
        }
        result = self.run_command()
        self.assertEqual(result.returncode, 0, result.stderr)
        after = {
            path.name: path.read_bytes()
            for path in sorted(self.codex_home.iterdir())
        }
        self.assertEqual(before, after)

    def test_a_credential_is_never_expanded_by_the_shell(self):
        token = "$(touch %s/pwned) `id`" % self.root
        self.write_profile(token=token)
        result = self.run_command()
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = self.recorded()
        self.assertEqual(payload["env"]["DOTFILES_CODEX_RESUME_MAGPIE_TOKEN"], token)
        self.assertFalse((self.root / "pwned").exists(), "the shell expanded the credential")

    def test_a_magpie_profile_without_a_usable_provider_degrades_to_a_plain_resume(self):
        (self.codex_home / "magpie.config.toml").write_text(
            'model_provider = "magpie"\n\n[model_providers.magpie]\nbase_url = "http://127.0.0.1:39411/v1"\n'
        )
        result = self.run_command()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.overrides(), [])
        self.assertIn("magpie.config.toml", result.stderr)

    def test_a_credential_header_reaches_the_child_through_the_environment(self):
        (self.codex_home / "magpie.config.toml").write_text(
            'model_provider = "magpie"\n\n'
            "[model_providers.magpie]\n"
            'name = "magpie"\n'
            'base_url = "http://127.0.0.1:39411/v1"\n'
            'wire_api = "responses"\n'
            'http_headers = { "Authorization" = "placeholder-header-token" }\n'
        )
        result = self.run_command()
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = self.recorded()
        self.assertNotIn("placeholder-header-token", " ".join(payload["argv"]))
        values = self.overrides(payload)
        self.assertTrue(
            any(value.startswith("model_providers.magpie.env_http_headers.Authorization=") for value in values),
            "the credential header did not move to the environment",
        )
        self.assertTrue(
            any(name.endswith("AUTHORIZATION") for name in payload["env"]),
            "the credential header did not reach the environment",
        )

    def test_the_command_is_a_managed_executable_script(self):
        self.assertTrue(COMMAND.exists(), "the managed command is missing")
        body = COMMAND.read_text()
        self.assertTrue(body.startswith("#!/usr/bin/env bash"))
        self.assertIn("set -uo pipefail", body)


@unittest.skipUnless(
    os.environ.get("DOTFILES_TEST_CODEX_RESUME") == "1",
    "the runtime class is opt-in: set DOTFILES_TEST_CODEX_RESUME=1 and run "
    "`DOTFILES_TEST_CODEX_RESUME=1 python3 -m unittest tests.test_codex_resume -v`",
)
class CodexResumeRuntimeTests(unittest.TestCase):
    """The real resume path against two fake loopback providers."""

    @classmethod
    def setUpClass(cls):
        codex_bin = os.environ.get("DOTFILES_TEST_CODEX") or shutil.which("codex")
        if not codex_bin:
            raise unittest.SkipTest("the real Codex CLI is not installed")
        cls.report = codex_resume_runtime.run_scenarios(codex_bin, str(COMMAND))

    def scenario(self, name):
        for entry in self.report["scenarios"]:
            if entry["name"] == name:
                return entry
        self.fail("the scenario %s did not run" % name)

    def test_the_version_under_test_is_the_pinned_one(self):
        self.assertIn("0.169.0", self.report["codex_version"])

    def test_the_live_gateway_is_never_part_of_the_experiment(self):
        for name, port in self.report["ports"].items():
            if name == "live_gateway_excluded":
                continue
            self.assertNotEqual(port, 3425)

    def test_a_thread_of_another_provider_fails_through_the_magpie_profile(self):
        error = self.scenario("red-non-magpie-thread-through-magpie-profile")["error"]
        self.assertIn("Cannot change this thread's model provider", error["message"])

    def test_a_magpie_thread_fails_without_the_provider_definition(self):
        error = self.scenario("red-magpie-thread-without-provider-definition")["error"]
        self.assertEqual(error["type"], "modelProviderNotConfigured")

    def test_the_command_resumes_a_magpie_thread_with_its_own_settings(self):
        entry = self.scenario("green-magpie-thread-through-the-command")
        self.assertEqual(entry["resume"]["modelProvider"], "magpie")
        self.assertEqual(entry["resume"]["model"], "gpt-6.1-terra")
        self.assertEqual(entry["resume"]["reasoningEffort"], "high")
        request = entry["thread_request"]
        self.assertIsNotNone(request, "the resumed turn reached no endpoint")
        # The request of the resumed thread is the one whose cache key
        # matches the thread's creation request. A request of Codex's own
        # carries the configuration's effort instead, and is not asserted on.
        saved = self.report["known_threads"].get(request["prompt_cache_key"])
        self.assertIsNotNone(saved, "the resumed turn belongs to an unknown thread")
        self.assertEqual(saved["label"], "magpie")
        self.assertEqual(request["model"], "gpt-6.1-terra")
        self.assertEqual(request["effort"], "high")

    def test_the_command_resumes_a_thread_of_another_provider(self):
        entry = self.scenario("green-other-provider-thread-through-the-command")
        self.assertEqual(entry["resume"]["modelProvider"], "alpha")
        self.assertEqual(entry["resume"]["model"], "gpt-6.1-sol")
        self.assertEqual(entry["resume"]["reasoningEffort"], "medium")
        request = entry["thread_request"]
        self.assertIsNotNone(request, "the resumed turn reached no endpoint")
        saved = self.report["known_threads"].get(request["prompt_cache_key"])
        self.assertIsNotNone(saved, "the resumed turn belongs to an unknown thread")
        self.assertEqual(saved["label"], "alpha")
        self.assertEqual(request["model"], "gpt-6.1-sol")
        self.assertEqual(request["effort"], "medium")

    def test_the_provider_layer_selects_nothing(self):
        entry = self.scenario("green-magpie-thread-through-the-command")
        argv = entry["command_argv"][-1]
        selected = [
            value
            for value in argv
            if value.startswith(("model=", "model_provider=", "model_reasoning_effort="))
        ]
        self.assertEqual(selected, [], "the layer selected a model, a provider, or an effort")
        self.assertTrue(
            any(value.startswith("model_providers.magpie.base_url=") for value in argv),
            "the provider definition did not reach codex",
        )

    def test_a_new_session_keeps_the_defaults_of_its_own_layer(self):
        entry = self.scenario("new-session-defaults")
        alpha = entry["received"]["alpha"]
        magpie = entry["received"]["magpie"]
        self.assertEqual(alpha[0]["model"], "gpt-6.1-sol")
        self.assertEqual(alpha[0]["effort"], "medium")
        self.assertEqual(magpie[0]["model"], "gpt-6.1-terra")
        self.assertEqual(magpie[0]["effort"], "high")
        plain = [item for item in magpie[1:]]
        self.assertTrue(plain, "the plain profile session reached no endpoint")
        self.assertEqual(plain[-1]["model"], "gpt-6.1-terra")

    def test_the_base_config_and_its_other_providers_are_preserved(self):
        self.assertTrue(self.report["base_config_unchanged"])
        self.assertTrue(self.report["other_provider_preserved"])

    def test_the_picker_in_a_pty_resumes_the_thread(self):
        entry = self.scenario("picker-in-a-pty")
        if entry.get("status") == "blocked":
            self.skipTest("the host does not hand out pseudo terminals: %s" % entry.get("error"))
        self.assertEqual(entry["status"], "ran", entry.get("error"))
        self.assertFalse(entry["update_prompt_seen"], "the update prompt was on the screen")
        request = entry["thread_request"]
        self.assertIsNotNone(request, "the resumed turn reached no endpoint")
        # The resumed turn carries the settings of the thread it resumed,
        # whichever row the picker highlighted: the thread is the one whose
        # creation request carries the cache key of the turn, and the turn
        # may have reached any of the fake providers.
        saved = self.report["known_threads"].get(request["prompt_cache_key"])
        self.assertIsNotNone(saved, "the resumed turn belongs to an unknown thread")
        self.assertEqual(
            request["label"],
            saved["provider"],
            "the turn did not reach the provider of the thread it resumed",
        )
        self.assertEqual(request["model"], saved["model"])
        self.assertEqual(request["effort"], saved["effort"])


class PickerListTests(unittest.TestCase):
    """The rule that tells a loaded session list from a loading one.

    The picker renders in two stages: the header and the footer are on the
    screen while the list is still loading. A Return sent in that state
    accepts no row, so the driver has to wait for the list itself.

    The rule is exercised here without a Codex and without a pseudo
    terminal: it reads the screen text of the two stages.
    """

    # The screen of the picker while the list is still loading: the header
    # and the footer are there, the counter reads "0 / 0… · 0%".
    LOADING = (
        "Resume a previous session Filter: Cwd All Status: Active Archived "
        "Sort: Updated Created\n"
        "Type to search Loading sessions… ──────────── 0 / 0… · 0% ─ enter "
        "resume esc start new …\n"
    )

    # The screen of the picker once the list has rows: the counter reads
    # "1 / 4" and the rows follow.
    LOADED = (
        "Resume a previous session Filter: Cwd All Status: Active Archived "
        "Sort: Updated Created\n"
        "Type to search ──────────── 1 / 4… · 25% ─ enter resume esc start new …\n"
        "› 2s ago ● picker target thread 5s ago ● alpha thread 8s ago ● "
        "magpie thread 12s ago ● plain magpie session\n"
        "1 / 4\n"
    )

    def test_a_loading_list_is_not_loaded(self):
        self.assertFalse(
            codex_resume_runtime.session_list_loaded(self.LOADING),
            "a list that is still loading was taken for a loaded one",
        )

    def test_a_loaded_list_is_loaded(self):
        self.assertTrue(
            codex_resume_runtime.session_list_loaded(self.LOADED),
            "a loaded list was not recognized",
        )

    def test_the_picker_markers_alone_do_not_tell_a_loaded_list(self):
        # The markers of the picker are the header and the footer. They are
        # on the screen while the list is still loading, so a wait for them
        # ends too early: this is the defect of the round-3 driver.
        self.assertTrue(
            any(marker in self.LOADING for marker in codex_resume_runtime.PICKER_MARKERS),
            "the loading screen does not show the picker at all",
        )
        self.assertFalse(
            codex_resume_runtime.session_list_loaded(self.LOADING),
            "the markers of the picker were taken for a loaded list",
        )

    def test_a_counter_without_a_total_is_not_loaded(self):
        self.assertFalse(codex_resume_runtime.session_list_loaded("0 / 0… · 0%"))
        self.assertFalse(codex_resume_runtime.session_list_loaded("1 / 0"))

    def test_the_counter_of_the_loading_stage_is_never_satisfied(self):
        # Whatever the screen shows, the loading counter ("0 / 0… · 0%")
        # alone never counts as a loaded list.
        for text in (
            "0 / 0… · 0%",
            "0 / 0",
            "Loading sessions… 0 / 0… · 0%",
        ):
            with self.subTest(text=text):
                self.assertFalse(codex_resume_runtime.session_list_loaded(text))


class PickerSelectionTests(unittest.TestCase):
    """The rule that finds the resumed turn in the picker's requests.

    The round-3 finding was in this rule, not in the driver, so it is
    exercised here without a Codex and without a pseudo terminal: the
    requests of every fake provider are put in one list, and the thread
    that was resumed is the one whose creation request carries the cache
    key of the turn.
    """

    KNOWN = {
        "cache-alpha": {
            "label": "alpha",
            "provider": "alpha",
            "model": "gpt-6.1-sol",
            "effort": "medium",
        },
        "cache-magpie": {
            "label": "magpie",
            "provider": "magpie",
            "model": "gpt-6.1-terra",
            "effort": "high",
        },
    }

    def request(self, **overrides):
        record = {
            "seq": 1,
            "label": "magpie",
            "prompt_cache_key": "cache-magpie",
            "model": "gpt-6.1-terra",
            "effort": "high",
            "user_text": "picker turn",
        }
        record.update(overrides)
        return record

    def test_the_turn_of_a_thread_of_another_provider_is_found(self):
        # The round-2 rule looked at the Magpie provider alone, so the turn
        # of a thread of another provider was never seen.
        received = [
            self.request(
                label="alpha",
                prompt_cache_key="cache-alpha",
                model="gpt-6.1-sol",
                effort="medium",
            )
        ]
        found = codex_resume_runtime.resumed_thread_request(
            received, self.KNOWN, "picker turn"
        )
        self.assertIsNotNone(found, "the turn of the alpha provider was not found")
        self.assertEqual(found["label"], "alpha")
        self.assertEqual(found["prompt_cache_key"], "cache-alpha")

    def test_the_provider_scoped_rule_of_round_two_misses_the_turn(self):
        # The shape of the old rule, kept as the red of the finding: the
        # requests of one provider only, and no turn of another provider.
        received = [self.request(label="alpha")]
        magpie_only = [item for item in received if item["label"] == "magpie"]
        self.assertIsNone(
            codex_resume_runtime.thread_request(
                magpie_only, "cache-alpha", "picker turn"
            ),
            "the old rule was expected to miss the turn of another provider",
        )

    def test_the_auxiliary_request_of_codex_is_not_mistaken_for_the_turn(self):
        # The request that generates a thread title belongs to a thread of
        # Codex's own and carries a cache key that is not known.
        received = [
            self.request(seq=1, prompt_cache_key="cache-of-codex-own", user_text=""),
            self.request(seq=2),
        ]
        found = codex_resume_runtime.resumed_thread_request(
            received, self.KNOWN, "picker turn"
        )
        self.assertEqual(found["prompt_cache_key"], "cache-magpie")

    def test_the_turn_that_carries_the_prompt_wins(self):
        received = [
            self.request(seq=1, user_text="an earlier turn of the same thread"),
            self.request(seq=2, user_text="picker turn"),
        ]
        found = codex_resume_runtime.resumed_thread_request(
            received, self.KNOWN, "picker turn"
        )
        self.assertEqual(found["seq"], 2)

    def test_a_turn_of_an_unknown_thread_is_not_accepted(self):
        received = [self.request(prompt_cache_key="cache-of-an-unknown-thread")]
        self.assertIsNone(
            codex_resume_runtime.resumed_thread_request(
                received, self.KNOWN, "picker turn"
            )
        )


if __name__ == "__main__":
    unittest.main()
