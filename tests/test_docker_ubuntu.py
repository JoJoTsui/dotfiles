"""Container output is checked before the host reads any artifact bytes."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from docker_ubuntu import artifact_hashes


class DockerArtifactTests(unittest.TestCase):
    def test_complete_regular_file_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'logs').mkdir()
            (root / 'logs/run.log').write_bytes(b'complete output\n')
            self.assertEqual(artifact_hashes(root), {
                'logs/run.log': hashlib.sha256(b'complete output\n').hexdigest()})

    def test_escaping_symlink_is_rejected_before_reading_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'valid.log').write_text('valid')
            (root / 'escaped').symlink_to('/outside/credential-file')
            with patch.object(Path, 'read_bytes', side_effect=AssertionError('read before validation')):
                with self.assertRaisesRegex(RuntimeError, 'symlink'):
                    artifact_hashes(root)
