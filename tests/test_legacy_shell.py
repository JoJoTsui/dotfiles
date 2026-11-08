"""Reversible shell migration from a rehearsed home into a confined live tree."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('legacy_shell', SOURCE / 'deployment/legacy/migrate-shell.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class LegacyShellTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='legacy-shell-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.rendered, self.home, self.live = (self.root / name for name in ('rendered', 'home', 'live'))
        for path in (self.rendered, self.home, self.live):
            path.mkdir()
        for name in ('.config', '.local'):
            (self.live / name).mkdir()
            (self.home / name).symlink_to(self.live / name)
        (self.live / '.env_core').write_text('DEVICE_FIXTURE=preserve\n')
        (self.home / '.env_core').symlink_to(self.live / '.env_core')
        (self.live / '.bashrc').write_text('personal bash commands\n')
        (self.home / '.bashrc').symlink_to(self.live / '.bashrc')
        old_env = self.home / '.config/nushell/env.nu'
        old_env.parent.mkdir(parents=True)
        old_env.write_text('$env.PERSONAL = "preserve"\n')
        for relative in migration.FILES + ('.env_core',):
            path = self.rendered / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('rendered fixture\n')
        (self.rendered / '.bashrc').write_text('if true; then "$DOTFILES_COMMON_BIN/wt" config shell init bash; fi\n')
        for relative in ('.local/share/nushell/vendor/autoload/starship.nu',
                         '.local/share/nushell/completions/nu-scripts/revision/completion.nu'):
            path = self.rendered / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(self.rendered) + '/resource\n')

    def test_preserves_device_environment_and_hooks_and_reapplication(self):
        hook = self.home / '.config/dotfiles/nu.local.nu'
        hook.parent.mkdir(parents=True)
        hook.write_text('# personal Nu commands\n')
        changes = migration.plan(self.rendered, self.home, self.live)
        original = (self.home / '.env_core').read_bytes()
        count, backup = migration.apply(changes, self.live / '.local/state/recovery')
        self.assertGreater(count, 0)
        self.assertEqual(backup.stat().st_mode & 0o777, 0o700)
        self.assertTrue((self.home / '.env_core').read_bytes().startswith(original))
        self.assertEqual((self.home / '.env_core').read_bytes().count(migration.START), 1)
        self.assertTrue((self.home / '.bashrc').read_text().startswith('personal bash commands\n'))
        self.assertEqual((self.home / '.config/dotfiles/legacy-env.nu').read_text(), '$env.PERSONAL = "preserve"\n')
        self.assertEqual(hook.read_text(), '# personal Nu commands\n')
        loader = self.home / '.local/share/nushell/vendor/autoload/starship.nu'
        self.assertIn(str(self.home), loader.read_text())
        count, _ = migration.apply(migration.plan(self.rendered, self.home, self.live), self.live / '.local/state/recovery')
        self.assertEqual(count, 0)
        self.assertEqual((self.home / '.env_core').read_bytes().count(migration.START), 1)

    def test_reapplication_keeps_personal_text_after_owned_environment_block(self):
        state = self.live / '.local/state/recovery'
        migration.apply(migration.plan(self.rendered, self.home, self.live), state)
        with (self.home / '.env_core').open('ab') as stream:
            stream.write(b'\n# personal additions after managed content\n')
        count, _ = migration.apply(migration.plan(self.rendered, self.home, self.live), state)
        self.assertEqual(count, 0)
        self.assertTrue((self.home / '.env_core').read_bytes().endswith(b'# personal additions after managed content\n'))

    def test_incomplete_owned_environment_block_is_rejected(self):
        (self.home / '.env_core').write_bytes(b'original\n' + migration.START + b'incomplete')
        with self.assertRaisesRegex(ValueError, 'no closing marker'):
            migration.plan(self.rendered, self.home, self.live)

    def test_destination_escape_rejected_before_any_application(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (self.live / '.local').rmdir()
        (self.live / '.local').symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'escapes live tree'):
            migration.plan(self.rendered, self.home, self.live)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual((self.live / '.env_core').read_text(), 'DEVICE_FIXTURE=preserve\n')

    def test_missing_prepared_resource_rejected_without_changes(self):
        (self.rendered / migration.FILES[-1]).unlink()
        with self.assertRaisesRegex(ValueError, 'resource is missing'):
            migration.plan(self.rendered, self.home, self.live)
        self.assertEqual((self.live / '.env_core').read_text(), 'DEVICE_FIXTURE=preserve\n')

    def test_environment_escape_is_rejected_before_reading_private_bytes(self):
        outside = self.root / 'private-outside'
        outside.write_bytes(b'private fixture')
        (self.home / '.env_core').unlink()
        (self.home / '.env_core').symlink_to(outside)
        original = Path.read_bytes

        def read(path):
            self.assertNotEqual(path.resolve(), outside)
            return original(path)

        with mock.patch.object(Path, 'read_bytes', read):
            with self.assertRaisesRegex(ValueError, 'escapes live tree'):
                migration.plan(self.rendered, self.home, self.live)
