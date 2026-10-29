"""Modern CLI selection and ownership-safe uutils alias migration."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import tomllib
except ImportError:
    tomllib = None

SOURCE = Path(__file__).resolve().parents[1]
MERGE = SOURCE / 'deployment/merge_pixi.py'


@unittest.skipUnless(os.name == 'posix', 'Unix plans; native Windows has a separate boundary suite')
class CliCatalogTests(unittest.TestCase):
    def test_developer_uses_the_common_finder_and_lister_and_explicit_coreutils(self):
        with tempfile.TemporaryDirectory(prefix='dotfiles-cli-plan-') as temporary:
            home = Path(temporary) / 'not-created'
            result = subprocess.run([
                '/bin/bash', str(SOURCE / 'bootstrap.sh'), '--home', str(home), '--plan',
                '--platform', 'linux', '--arch', 'x86_64', '--bundles', 'developer',
            ], check=False, env={'HOME': temporary, 'PATH': '/usr/bin:/bin'},
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(home.exists())
            plan = json.loads(result.stdout)
            self.assertTrue({'eza', 'fzf', 'coreutils'} <= set(plan['tools']))
            for command in ('lsd', 'sk', 'sk-tmux', 'cp', 'rm', 'stat', 'ls'):
                self.assertNotIn(command, plan['tools'])
            packages = {package['environment']: package for package in plan['bundlePackages']}
            self.assertNotIn('lsd', packages)
            self.assertNotIn('skim', packages)
            self.assertEqual(packages['uutils-coreutils']['exposed'], {'coreutils': 'coreutils'})


@unittest.skipUnless(tomllib, 'registry assertions require Python 3.11 or newer')
class CoreutilsRegistryMigrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='dotfiles-coreutils-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.registry = self.root / 'pixi-global.toml'
        self.backup = self.root / 'pixi-global.toml.before-coreutils-namespacing.bak'
        self.desired = self.root / 'desired.toml'
        self.desired.write_text('''version = 1
[envs.uutils-coreutils]
channels = ["conda-forge"]
dependencies = { uutils-coreutils = "==0.12.0" }
exposed = { coreutils = "coreutils" }
''')
        self.original = b'''# Preserve this exact original for rollback.
version = 1
[envs.uutils-coreutils]
channels = ["device-channel", "conda-forge"]
dependencies = { uutils-coreutils = "==0.11.0", device-library = "==1.0" }
exposed = { coreutils = "coreutils", cp = "cp", rm = "rm", stat = "stat", ls = "ls", cat = "custom-cat", date = "custom-date", device-copy = "cp", device-command = "device-command" }
[envs.device]
channels = ["device-channel"]
dependencies = { device = "==1.0" }
exposed = { device = "device" }
[envs.lsd]
dependencies = { lsd-rust = "==1.1.5" }
exposed = { lsd = "lsd" }
[envs.skim]
dependencies = { skim = "==5.7.4" }
exposed = { sk = "sk" }
'''
        self.registry.write_bytes(self.original)
        self.registry.chmod(0o640)

    def merge(self):
        return subprocess.run([sys.executable, str(MERGE), str(self.desired), str(self.registry)],
                              check=False, capture_output=True, text=True, timeout=15)

    def read(self):
        return tomllib.loads(self.registry.read_text())['envs']

    def test_selected_migration_retires_only_owned_aliases_and_keeps_a_private_snapshot(self):
        result = self.merge()
        self.assertEqual(result.returncode, 0, result.stderr)
        environments = self.read()
        owned = environments['uutils-coreutils']
        self.assertEqual(owned['exposed'], {
            'coreutils': 'coreutils', 'cat': 'custom-cat', 'date': 'custom-date',
            'device-copy': 'cp', 'device-command': 'device-command',
        })
        self.assertEqual(owned['dependencies'], {'uutils-coreutils': '==0.12.0', 'device-library': '==1.0'})
        self.assertEqual(owned['channels'], ['conda-forge', 'device-channel'])
        self.assertEqual(environments['device']['exposed'], {'device': 'device'})
        self.assertEqual(environments['lsd']['exposed'], {'lsd': 'lsd'})
        self.assertEqual(environments['skim']['exposed'], {'sk': 'sk'})
        self.assertEqual(self.backup.read_bytes(), self.original)
        if os.name == 'posix':
            self.assertEqual(self.backup.stat().st_mode & 0o777, 0o600)
            self.assertEqual(self.registry.stat().st_mode & 0o777, 0o640)
        first = self.registry.read_bytes()
        self.assertEqual(self.merge().returncode, 0)
        self.assertEqual(self.registry.read_bytes(), first)
        self.assertEqual(self.backup.read_bytes(), self.original)

    def test_unselected_environment_is_preserved_and_old_desired_state_can_restore_aliases(self):
        self.desired.write_text('version = 1\n[envs]\n')
        self.assertEqual(self.merge().returncode, 0)
        self.assertEqual(self.read()['uutils-coreutils']['exposed']['cp'], 'cp')
        self.assertFalse(self.backup.exists())
        before = self.registry.read_bytes()
        self.write_namespaced_desired()
        self.assertEqual(self.merge().returncode, 0)
        self.assertNotIn('cp', self.read()['uutils-coreutils']['exposed'])
        self.desired.write_text('''version = 1
[envs.uutils-coreutils]
exposed = { coreutils = "coreutils", cp = "cp", rm = "rm" }
''')
        self.assertEqual(self.merge().returncode, 0)
        self.assertEqual(self.read()['uutils-coreutils']['exposed']['cp'], 'cp')
        self.assertEqual(self.read()['uutils-coreutils']['exposed']['rm'], 'rm')
        self.assertEqual(self.backup.read_bytes(), before)

    def write_namespaced_desired(self):
        self.desired.write_text('''version = 1
[envs.uutils-coreutils]
exposed = { coreutils = "coreutils" }
''')

    def test_collision_failure_preserves_registry_and_does_not_publish_backup(self):
        with self.registry.open('a') as handle:
            handle.write('[envs.conflict]\nexposed = { coreutils = "another-command" }\n')
        before = self.registry.read_bytes()
        result = self.merge()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('exposed command', result.stderr)
        self.assertEqual(self.registry.read_bytes(), before)
        self.assertFalse(self.backup.exists())

    def test_unsafe_backup_destination_fails_before_registry_mutation(self):
        outside = self.root / 'outside'
        outside.write_text('keep device data\n')
        try:
            self.backup.symlink_to(outside)
        except OSError:
            self.skipTest('platform policy prevents creating symlinks')
        result = self.merge()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('backup must be a regular file', result.stderr)
        self.assertEqual(self.registry.read_bytes(), self.original)
        self.assertEqual(outside.read_text(), 'keep device data\n')


if __name__ == '__main__':
    unittest.main()
