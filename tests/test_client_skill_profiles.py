"""Pi and OpenCode receive the selected profile through the shared tree.

The shared tree is the profile root of both clients: their merged settings
register the designated home's tree, and that tree holds the selected profile
plus the generated Herdr skill. The tests prove the registered path, the
profile contents, the generated skill, the absence of a second discovery, and
that a profile change reaches the next apply without leftovers.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from fixtures.skill_discovery import opencode_skills, pi_resources, resolve_skill_path
from pins import agent_pins, common_pin

SOURCE = Path(__file__).resolve().parents[1]
STATIC_LIBRARY = SOURCE / "tests/fixtures/skill-library"
FAKE_HERDR = SOURCE / "tests/fixtures/fake-herdr"

# The roots the deployment owns. Pi and OpenCode share the first one; Claude
# and MiniMax receive a filtered copy of the same profile.
MANAGED_ROOTS = (".agents/skills", ".claude/skills", ".minimax/skills")
# The client roots the deployment never writes. A name both roots provide is a
# duplicate discovery the deployment reports.
CLIENT_ROOTS = (".pi/agent/skills", ".config/opencode/skills")

FAKE_SKILL = """---
name: herdr
description: "Fake Herdr skill used by the deployment tests."
---

# Herdr

The fake Herdr prints this skill.
"""

# The fake Bun installs the frozen project of an agent by creating the
# command entrypoints the deployment exposes.
BUN_HELPER = """import pathlib, sys
pins = {pins!r}
project = pathlib.Path(sys.argv[sys.argv.index('--cwd') + 1])
pin = pins[project.name]
for command in pin['commands'].split(','):
    launcher = project / 'node_modules/.bin' / command
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text('#!/bin/sh\\necho ' + pin['version'] + '\\n')
    launcher.chmod(0o755)
"""


class ProfileFixture:
    """A disposable home that receives a simulated deployment."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dotfiles-client-profile-", dir="/tmp")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "device"
        self.chezmoi = os.environ.get("DOTFILES_TEST_CHEZMOI") or shutil.which("chezmoi")
        if not self.chezmoi:
            self.skipTest("actual payload apply requires chezmoi")
        self.library = self.root / "skill-library"
        shutil.copytree(STATIC_LIBRARY, self.library)
        # A tagged skill, so the selected profile is observable without
        # fetching anything.
        tagged = self.library / "caveman-review"
        tagged.mkdir()
        (tagged / "SKILL.md").write_text(
            "---\nname: caveman-review\ndescription: fixture skill\n---\nbody\n")

    def deploy(self, *arguments, skills=None, environment=None):
        variables = {"HOME": str(self.root / "original"), "PATH": "/usr/bin:/bin",
                     "DOTFILES_CHEZMOI_BIN": self.chezmoi,
                     "DOTFILES_SKILLS_DIR": str(self.library)}
        if skills is not None:
            variables["DOTFILES_SKILLS"] = skills
        if environment:
            variables.update(environment)
        return subprocess.run(
            ["/bin/bash", str(SOURCE / "bootstrap.sh"), "--source", str(SOURCE),
             "--home", str(self.home), "--platform", "linux", "--role", "workstation",
             *arguments],
            cwd=SOURCE, env=variables, capture_output=True, text=True, timeout=600)

    def apply(self, **keywords):
        """An apply-only deployment: files, no installer."""
        return self.deploy("--apply-only", **keywords)

    def profile_root(self):
        """The shared tree the deployment owns."""
        return self.home / ".agents/skills"

    def pi_skill_paths(self):
        """The skill paths Pi reads from its merged settings."""
        settings = json.loads((self.home / ".pi/agent/settings.json").read_text())
        return settings["skills"]

    def opencode_skill_paths(self):
        """The skill paths OpenCode reads from its merged settings."""
        text = (self.home / ".config/opencode/opencode.jsonc").read_text()
        return json.loads(text)["skills"]

    def profile_names(self):
        """The names the shared tree provides."""
        return {path.parent.name for path in self.profile_root().glob("*/SKILL.md")}

    def inventory(self):
        """The managed skill inventory the deployment recorded."""
        state = self.home / ".local/state/dotfiles/managed-skills.tsv"
        if not state.is_file():
            return set()
        return {tuple(line.split("|"))
                for line in state.read_text(encoding="utf-8").splitlines()
                if line and not line.startswith("#")}

    def client_environment(self):
        """An environment that keeps a client inside the disposable home."""
        environment = dict(os.environ)
        environment.update({
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "XDG_DATA_HOME": str(self.home / ".local/share"),
            "XDG_STATE_HOME": str(self.home / ".local/state"),
            "XDG_CACHE_HOME": str(self.home / ".cache"),
            "DO_NOT_TRACK": "1",
        })
        return environment


class ClientProfileRootTests(ProfileFixture, unittest.TestCase):
    """The merged settings of both clients point at the shared profile root."""

    def test_pi_registers_the_designated_home_profile_root(self):
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.pi_skill_paths(), [str(self.profile_root())])
        # The registered path is the tree that holds the profile, not a path
        # of the host account.
        self.assertTrue(self.profile_names())
        host_tree = Path(os.environ.get("HOME", "/")).resolve() / ".agents/skills"
        self.assertNotEqual(self.profile_root(), host_tree)

    def test_opencode_registers_the_designated_home_profile_root(self):
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.opencode_skill_paths(), [str(self.profile_root())])
        self.assertTrue(self.profile_names())
        host_tree = Path(os.environ.get("HOME", "/")).resolve() / ".agents/skills"
        self.assertNotEqual(self.profile_root(), host_tree)

    def test_the_profile_root_holds_the_selected_profile(self):
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        names = self.profile_names()
        for name in ("tdd", "show-me", "humanizer", "humanizer-zh", "implement-spec"):
            self.assertIn(name, names)
        # A tagged skill is not part of the default profile.
        self.assertNotIn("caveman-review", names)

    def test_a_requested_tag_reaches_the_profile_root(self):
        result = self.apply(skills="caveman")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("caveman-review", self.profile_names())

    def test_the_deployment_owns_one_skill_root_for_opencode(self):
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        roots = {root for _, root in self.inventory()}
        self.assertTrue(roots.issubset(set(MANAGED_ROOTS)), roots)
        # The default root of OpenCode is the device's own; the deployment
        # never writes it and never records it.
        self.assertFalse((self.home / ".config/opencode/skills").exists())
        self.assertNotIn(".config/opencode/skills", roots)
        self.assertTrue(roots.isdisjoint(CLIENT_ROOTS), roots)

    def test_pi_own_root_repeats_no_name_the_profile_root_provides(self):
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        # The deployment writes no skill into the root Pi scans itself, so
        # Pi discovers no profile name twice.
        self.assertFalse((self.home / ".pi/agent/skills").exists())
        self.assertNotIn(".pi/agent/skills", {root for _, root in self.inventory()})

    def test_a_device_duplicate_in_the_pi_own_root_is_reported_and_preserved(self):
        device = self.home / ".pi/agent/skills/tdd"
        device.mkdir(parents=True)
        (device / "SKILL.md").write_text(
            "---\nname: tdd\ndescription: device skill\n---\ndevice bytes\n")
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("skill tdd is in both", result.stderr)
        self.assertIn(".pi/agent/skills", result.stderr)
        # The device entry stays: the client owns that root.
        self.assertEqual((device / "SKILL.md").read_text(),
                         "---\nname: tdd\ndescription: device skill\n---\ndevice bytes\n")

    def test_a_device_duplicate_in_the_opencode_default_root_is_reported_and_preserved(self):
        device = self.home / ".config/opencode/skills/tdd"
        device.mkdir(parents=True)
        (device / "SKILL.md").write_text(
            "---\nname: tdd\ndescription: device skill\n---\ndevice bytes\n")
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("skill tdd is in both", result.stderr)
        self.assertIn(".config/opencode/skills", result.stderr)
        # The device entry stays: the client owns that root.
        self.assertEqual((device / "SKILL.md").read_text(),
                         "---\nname: tdd\ndescription: device skill\n---\ndevice bytes\n")

    def test_a_profile_change_reaches_the_next_apply_without_leftovers(self):
        first = self.apply(skills="caveman")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("caveman-review", self.profile_names())
        second = self.apply()
        self.assertEqual(second.returncode, 0, second.stderr)
        # The profile root both clients registered now holds the smaller
        # profile, and the deselected skill is gone from it.
        self.assertNotIn("caveman-review", self.profile_names())
        self.assertFalse((self.profile_root() / "caveman-review").exists())
        self.assertEqual(self.pi_skill_paths(), [str(self.profile_root())])
        self.assertEqual(self.opencode_skill_paths(), [str(self.profile_root())])
        self.assertIn("pruned managed skill caveman-review", second.stderr)


class GeneratedSkillProfileTests(ProfileFixture, unittest.TestCase):
    """The generated Herdr skill belongs to the profile root of both clients."""

    def setUp(self):
        super().setUp()
        self.skill = self.root / "herdr-skill.md"
        self.skill.write_text(FAKE_SKILL, encoding="utf-8")

    def fake_runtime(self):
        """A fake Bun, Node, and Herdr, so the generated skill reaches the tree."""
        binaries = self.root / "bin"
        binaries.mkdir(exist_ok=True)
        helper = self.root / "bun.py"
        helper.write_text(BUN_HELPER.format(pins=agent_pins()), encoding="utf-8")
        bun = binaries / "bun"
        bun.write_text(
            '#!/bin/sh\nif [ "$1" = --version ]; then echo ' + common_pin("bun") +
            '; else exec "' + sys.executable + '" "' + str(helper) + '" "$@"; fi\n',
            encoding="utf-8")
        bun.chmod(0o755)
        node = binaries / "node"
        node.write_text(f'#!/bin/sh\necho v{common_pin("nodejs")}\n', encoding="utf-8")
        node.chmod(0o755)
        herdr = binaries / "herdr"
        shutil.copyfile(FAKE_HERDR, herdr)
        herdr.chmod(0o755)
        return {"DOTFILES_BUN_BIN": str(bun), "DOTFILES_NODE_BIN": str(node),
                "PATH": f"{binaries}:/usr/bin:/bin",
                "HERDR_LOG": str(self.root / "herdr.log"),
                "HERDR_STATE": str(self.root / "herdr.state"),
                "HERDR_MARKER": str(self.root / "herdr-marker"),
                "HERDR_SKILL": str(self.skill)}

    def test_the_generated_skill_is_in_the_profile_root_of_both_clients(self):
        result = self.deploy("--agents-only", "--agents", "none",
                             environment=self.fake_runtime())
        self.assertEqual(result.returncode, 0, result.stderr)
        profile = self.home / ".agents/skills"
        generated = profile / "herdr/SKILL.md"
        self.assertTrue(generated.is_file())
        self.assertEqual(generated.read_text(), FAKE_SKILL)
        # Both clients read that tree, so the generated skill is in both
        # profile roots.
        self.assertEqual(self.pi_skill_paths(), [str(profile)])
        self.assertEqual(self.opencode_skill_paths(), [str(profile)])


@unittest.skipUnless(os.environ.get("DOTFILES_TEST_PI_MODULE") and os.environ.get("DOTFILES_TEST_NODE"),
                     "requires the pinned Pi SDK module and managed Node")
class PiProfileDiscoveryTests(ProfileFixture, unittest.TestCase):
    """The pinned Pi client discovers every profile name once."""

    def test_pi_discovers_the_profile_without_a_duplicate_name(self):
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        data = self.pi_skills()
        collisions = [item for item in data["diagnostics"] if item.get("type") == "collision"]
        self.assertEqual(collisions, [], collisions)
        names = {skill["name"] for skill in data["skills"]}
        self.assertTrue(self.profile_names().issubset(names), names)
        managed = [skill for skill in data["skills"]
                   if (path := resolve_skill_path(skill["filePath"], self.home)) is not None
                   and path.is_relative_to(self.profile_root().resolve())]
        self.assertEqual({skill["name"] for skill in managed}, self.profile_names())

    def test_pi_prefers_the_profile_root_over_a_device_duplicate(self):
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        device = self.home / ".pi/agent/skills/tdd"
        device.mkdir(parents=True)
        (device / "SKILL.md").write_text(
            "---\nname: tdd\ndescription: device skill\n---\ndevice bytes\n")
        data = self.pi_skills()
        winners = [skill for skill in data["skills"] if skill["name"] == "tdd"]
        self.assertEqual(len(winners), 1, winners)
        self.assertTrue(Path(winners[0]["filePath"]).resolve().is_relative_to(
            self.profile_root().resolve()), winners[0]["filePath"])
        # Pi reports the second copy and keeps the profile root.
        collisions = [item for item in data["diagnostics"] if item.get("type") == "collision"]
        self.assertEqual([item["collision"]["name"] for item in collisions], ["tdd"], collisions)
        self.assertTrue(Path(collisions[0]["collision"]["loserPath"]).resolve().is_relative_to(
            (self.home / ".pi/agent/skills").resolve()), collisions[0])

    def pi_skills(self):
        """What the pinned Pi client discovers in the disposable home."""
        environment = self.client_environment()
        environment["PI_CODING_AGENT_DIR"] = str(self.home / ".pi/agent")
        return pi_resources(os.environ["DOTFILES_TEST_NODE"],
                            os.environ["DOTFILES_TEST_PI_MODULE"], cwd=self.home,
                            env=environment, log=self.root / "pi.log")


@unittest.skipUnless(os.environ.get("DOTFILES_TEST_OPENCODE"),
                     "requires the pinned OpenCode CLI")
class OpenCodeProfileDiscoveryTests(ProfileFixture, unittest.TestCase):
    """The pinned OpenCode client discovers every profile name once."""

    def test_opencode_discovers_the_profile_without_a_duplicate_name(self):
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = self.profile_names()
        data = self.opencode_skill_records(expected)
        identifiers = [item["id"] for item in data]
        self.assertEqual(len(identifiers), len(set(identifiers)), identifiers)
        self.assertTrue(expected.issubset(set(identifiers)), expected - set(identifiers))
        managed = [item for item in data
                   if (path := resolve_skill_path(item["path"], self.home)) is not None
                   and path.is_relative_to(self.profile_root().resolve())]
        self.assertEqual({item["id"] for item in managed}, expected)

    def test_opencode_prefers_the_profile_root_over_a_device_duplicate(self):
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        device = self.home / ".config/opencode/skills/tdd"
        device.mkdir(parents=True)
        (device / "SKILL.md").write_text(
            "---\nname: tdd\ndescription: device skill\n---\ndevice bytes\n")
        data = self.opencode_skill_records({"tdd"})
        winners = [item for item in data if item["id"] == "tdd"]
        self.assertEqual(len(winners), 1, winners)
        self.assertTrue(Path(winners[0]["path"]).resolve().is_relative_to(
            self.profile_root().resolve()), winners[0]["path"])

    def opencode_skill_records(self, expected):
        """What the pinned OpenCode client discovers in the disposable home."""
        return opencode_skills(os.environ["DOTFILES_TEST_OPENCODE"], home=self.home,
                               cwd=self.home, env=self.client_environment(),
                               log=self.root / "opencode.log", expected=expected)


if __name__ == "__main__":
    unittest.main()
