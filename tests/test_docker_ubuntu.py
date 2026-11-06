"""Container output is checked before the host reads any artifact bytes."""
import hashlib
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import docker_ubuntu
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


class DockerFailureCleanupTests(unittest.TestCase):
    def run_gate(self, *, exit_code=1, running=True, created=True,
                 run_raises=False, stop_code=0, kill_code=0, inspect_raises=False):
        with tempfile.TemporaryDirectory(prefix='dotfiles-docker-failure-') as temporary:
            artifacts = Path(temporary) / 'run'
            containers = {}
            runs, overlap, actions = [], [], []
            commit = 'a' * 40

            def query(command, *, env=None):
                if command[0] == 'git':
                    return '' if 'status' in command else commit
                if command[1:3] == ['context', 'show']:
                    return 'test'
                if command[1:3] == ['context', 'inspect']:
                    return 'unix:///fixture.sock'
                if command[1] == 'info':
                    if 'Plugins' in command[-1]:
                        return json.dumps([{'Path': '/fixture/buildx', 'Name': 'buildx'}])
                    return json.dumps({'OSType': 'linux', 'Architecture': 'amd64'})
                if command[1:3] == ['image', 'inspect']:
                    if '--platform' in command:
                        return json.dumps([{'Architecture': 'amd64', 'Os': 'linux',
                                            'RepoDigests': ['ubuntu@sha256:' + 'b' * 64], 'Id': 'image'}])
                    return 'image'
                if command[1:3] == ['volume', 'create']:
                    return command[-1]
                if command[1] == 'ps':
                    name = command[command.index('--filter') + 1].removeprefix('name=^/').removesuffix('$')
                    return name if name in containers else ''
                if command[1] == 'inspect':
                    actions.append('inspect')
                    if inspect_raises:
                        raise subprocess.CalledProcessError(1, command)
                    return str(containers[command[-1]]).lower()
                raise AssertionError(command)

            def logged(command, log, *, env, timeout):
                log.write_text('synthetic Docker response\n')
                operation = command[1]
                if operation == 'run':
                    name = command[command.index('--name') + 1]
                    overlap.append(any(containers.values()))
                    runs.append(name)
                    if len(runs) == 1:
                        if created:
                            containers[name] = running
                        if run_raises:
                            raise OSError('client connection lost')
                        return exit_code
                    containers[name] = False
                elif operation in ('stop', 'kill'):
                    actions.append(operation)
                    code = stop_code if operation == 'stop' else kill_code
                    if code == 0:
                        containers[command[-1]] = False
                    return code
                elif operation == 'cp':
                    name = command[-2].split(':', 1)[0]
                    if name not in containers:
                        return 1
                    gate = Path(command[-1])
                    gate.mkdir()
                    (gate / 'report.json').write_text(json.dumps({
                        'status': 'failed' if name == runs[0] else 'passed'}))
                elif operation == 'rm':
                    containers.pop(command[-1])
                return 0

            with patch.object(sys, 'argv', ['docker_ubuntu.py', '--artifacts', str(artifacts)]), \
                    patch.object(docker_ubuntu, 'query', side_effect=query), \
                    patch.object(docker_ubuntu, 'logged', side_effect=logged), \
                    patch.object(docker_ubuntu.shutil, 'which', return_value='/fixture/docker'), \
                    contextlib.redirect_stdout(io.StringIO()):
                status = docker_ubuntu.main()
            report = json.loads((artifacts / 'docker-report.json').read_text())
            self.assertEqual(status, 1)
            return report, runs, overlap, actions

    def test_client_failure_stops_container_before_the_next_baseline(self):
        report, runs, overlap, actions = self.run_gate()
        self.assertEqual(len(runs), 2)
        self.assertEqual(overlap, [False, False])
        self.assertIn('stop', actions)
        self.assertEqual(report['baselines'][0]['status'], 'failed')

    def test_timeout_and_client_exception_use_the_same_shutdown_path(self):
        for arguments in ({'exit_code': 124}, {'run_raises': True}):
            with self.subTest(arguments=arguments):
                _report, runs, overlap, actions = self.run_gate(**arguments)
                self.assertEqual(len(runs), 2)
                self.assertEqual(overlap, [False, False])
                self.assertIn('stop', actions)

    def test_kill_fallback_confirms_shutdown(self):
        _report, runs, overlap, actions = self.run_gate(stop_code=1)
        self.assertEqual(len(runs), 2)
        self.assertEqual(overlap, [False, False])
        self.assertIn('kill', actions)
        self.assertGreaterEqual(actions.count('inspect'), 2)

    def test_unstoppable_or_uninspectable_container_blocks_remaining_baselines(self):
        for arguments in ({'stop_code': 1, 'kill_code': 1}, {'inspect_raises': True}):
            with self.subTest(arguments=arguments):
                report, runs, _overlap, _actions = self.run_gate(**arguments)
                self.assertEqual(len(runs), 1)
                self.assertEqual(report['baselines'][1]['status'], 'blocked')

    def test_exited_or_never_created_container_allows_next_baseline_without_stop(self):
        for arguments in ({'running': False}, {'created': False, 'exit_code': 125}):
            with self.subTest(arguments=arguments):
                _report, runs, overlap, actions = self.run_gate(**arguments)
                self.assertEqual(len(runs), 2)
                self.assertEqual(overlap, [False, False])
                self.assertNotIn('stop', actions)
