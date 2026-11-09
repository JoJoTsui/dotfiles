"""Real Atuin import through the Linux-only legacy storage adapter."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests import test_history_behavior as shared


@unittest.skipUnless(sys.platform == "linux", "legacy notebook-local storage requires Linux")
class LocalHistoryBehaviorTests(unittest.TestCase):
    # Reuse the isolated pinned-tool setup without inheriting the shared tests.
    setUp = shared.HistoryBehaviorTests.setUp
    shell_binaries = shared.HistoryBehaviorTests.shell_binaries
    atuin_command = shared.HistoryBehaviorTests.atuin_command
    history = shared.HistoryBehaviorTests.history

    def test_local_history_import_preserves_settings_and_survives_runtime_loss(self):
        from tests.test_local_history import storage, SCRIPT
        runtime = tempfile.TemporaryDirectory(prefix='history-import-runtime-')
        self.addCleanup(runtime.cleanup)
        seeded = self.atuin_command('history', 'start', 'echo retained-before-import')
        self.assertEqual(seeded.returncode, 0, seeded.stderr)
        # A newer installed version is accepted when the actual transfer schemas
        # agree; the catalog itself remains unchanged.
        profile = self.home / '.config/dotfiles/profile.json'
        metadata = json.loads(profile.read_text())
        metadata['atuinVersion'] = '18.0.0'
        profile.write_text(json.dumps(metadata))
        store = storage.Store(self.home, self.home, Path(runtime.name), self.atuin)
        with store.lock():
            store.migrate(SCRIPT)
        enabled = store.state / 'enabled.json'
        original_settings = enabled.read_bytes()
        fixture = self.root / 'older-nu-history.txt'
        secret = 'ghp_' + 'D' * 36
        fixture.write_text(f'echo recovered-native-history\necho excluded-native-{secret}\n')
        source_bytes = fixture.read_bytes()
        imported = self.history('import', 'nu', '--file', str(fixture))
        self.assertEqual(imported.returncode, 0, imported.stderr)
        self.assertEqual(enabled.read_bytes(), original_settings)
        self.assertEqual(fixture.read_bytes(), source_bytes)
        wrapper = self.home / '.local/bin/atuin'

        def search(query):
            return subprocess.run([str(wrapper), 'search', '--cmd-only', query],
                                  env=self.env, capture_output=True, text=True, timeout=20)

        self.assertIn('recovered-native-history', search('recovered-native-history').stdout)
        self.assertIn('retained-before-import', search('retained-before-import').stdout)
        self.assertEqual(search('excluded-native-').stdout, '')
        shutil.rmtree(runtime.name)
        self.assertIn('recovered-native-history', search('recovered-native-history').stdout)
        repeated = self.history('import', 'nu', '--file', str(fixture))
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertIn('already imported', repeated.stdout)
        self.assertEqual(enabled.read_bytes(), original_settings)

if __name__ == "__main__":
    unittest.main()
