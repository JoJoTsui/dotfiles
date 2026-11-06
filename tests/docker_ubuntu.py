"""Run the Ubuntu/T9K gates sequentially on a local Docker engine.

Requires Python 3.11+ and Docker. The source must be committed and clean.
Docker receives a shallow source export and a private, credential-free client
configuration. Test containers have a read-only root and a fresh non-root home.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import time
import uuid

SOURCE = Path(__file__).resolve().parents[1]
RELEASES = ('20.04', '24.04')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def query(command, *, env=None):
    return subprocess.check_output(command, env=env, cwd=SOURCE, text=True, timeout=90).strip()


def atomic_json(path, value):
    temporary = path.with_name('.' + path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.chmod(0o600)
    temporary.replace(path)


def logged(command, log, *, env, timeout):
    with log.open('wb') as stream:
        process = subprocess.Popen(command, env=env, cwd=SOURCE, stdout=stream,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            return process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            return 124


def artifact_hashes(root):
    files = []
    for directory, directories, names in os.walk(root, followlinks=False):
        for name in directories + names:
            path = Path(directory) / name
            mode = path.lstat().st_mode
            require(not stat.S_ISLNK(mode), 'copied artifact is a symlink: ' + str(path.relative_to(root)))
            require(stat.S_ISDIR(mode) or stat.S_ISREG(mode), 'copied artifact is not a regular file or directory')
            if stat.S_ISREG(mode):
                files.append(path)
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(files)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True, help='new absolute directory outside the source')
    parser.add_argument('--ubuntu-release', choices=RELEASES, action='append', help='default: both releases sequentially')
    args = parser.parse_args()
    os.umask(0o077)
    artifacts = args.artifacts
    require(artifacts.is_absolute() and not artifacts.exists() and not artifacts.is_symlink(), 'artifacts must be a fresh absolute path')
    require(not artifacts.resolve().is_relative_to(SOURCE), 'artifacts must be outside the source')
    require(not query(['git', 'status', '--porcelain']), 'commit source changes before freezing the test export')
    commit = query(['git', 'rev-parse', 'HEAD'])
    docker = shutil.which('docker')
    require(docker is not None, 'Docker CLI is unavailable')
    context = query([docker, 'context', 'show'])
    endpoint = query([docker, 'context', 'inspect', context, '--format', '{{.Endpoints.docker.Host}}'])
    require(endpoint.startswith('unix://'), 'this gate requires an explicitly local Docker endpoint')
    plugins = json.loads(query([docker, 'info', '--format', '{{json .ClientInfo.Plugins}}']))
    plugin_dirs = sorted({str(Path(item['Path']).parent) for item in plugins if item['Name'] == 'buildx'})
    require(plugin_dirs, 'installed Docker Buildx plugin is required')
    artifacts.mkdir(parents=True, mode=0o700)
    client = artifacts / 'docker-client'
    client.mkdir(mode=0o700)
    atomic_json(client / 'config.json', {'auths': {}, 'cliPluginsExtraDirs': plugin_dirs})
    # Retain only public connection/plugin settings, never host credentials,
    # default build proxies, client roots, or shell configuration.
    env = {'HOME': str(artifacts), 'PATH': '/usr/bin:/bin:/usr/sbin:/sbin',
           'DOCKER_CONFIG': str(client), 'DOCKER_HOST': endpoint, 'LANG': 'C.UTF-8'}
    git_env = dict(env, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0')
    snapshot = artifacts / 'source-export'
    code = logged(['git', 'clone', '--quiet', '--depth', '1', '--no-hardlinks', SOURCE.as_uri(), str(snapshot)],
                  artifacts / 'source-export.log', env=git_env, timeout=120)
    require(code == 0 and query(['git', '-C', str(snapshot), 'rev-parse', 'HEAD'], env=git_env) == commit,
            'failed to freeze the exact source commit')
    info = json.loads(query([docker, 'info', '--format', '{{json .}}'], env=env))
    require(info['OSType'] == 'linux', 'Ubuntu verification requires a Linux Docker engine')
    execution = 'emulated' if info['Architecture'] not in ('x86_64', 'amd64') else 'native'
    task = 'dotfiles-t9k-' + uuid.uuid4().hex[:12]
    report = {'status': 'running', 'commit': commit, 'docker_context': context,
              'engine': {key: info.get(key) for key in ('ServerVersion', 'OSType', 'Architecture', 'KernelVersion', 'NCPU', 'MemTotal')},
              'execution': execution, 'cpus': 4, 'memory_bytes': 8 * 1024**3,
              'source_export': str(snapshot), 'baselines': []}
    output = artifacts / 'docker-report.json'
    atomic_json(output, report)
    abort_remaining = False
    for release in args.ubuntu_release or RELEASES:
        case = artifacts / ('ubuntu-' + release)
        case.mkdir(mode=0o700)
        name = task + '-' + release.replace('.', '-')
        volume = name + '-home'
        image = name + ':verified-source'
        row = {'ubuntu_release': release, 'status': 'running', 'container': name, 'volume': volume, 'image': image}
        report['baselines'].append(row)
        if abort_remaining:
            row.update(status='blocked', failure='previous task container could not be stopped', retained_runtime=False)
            atomic_json(output, report)
            continue
        atomic_json(output, report)
        print(f'Ubuntu {release}: pulling amd64 baseline', flush=True)
        try:
            code = logged([docker, 'pull', '--platform', 'linux/amd64', 'ubuntu:' + release],
                          case / 'pull.log', env=env, timeout=900)
            require(code == 0, 'Ubuntu image pull failed')
            metadata = json.loads(query([docker, 'image', 'inspect', '--platform', 'linux/amd64', 'ubuntu:' + release], env=env))[0]
            require(metadata['Architecture'] == 'amd64' and metadata['Os'] == 'linux', 'base image is not Linux amd64')
            base = next(item for item in metadata['RepoDigests'] if item.split('@')[0].endswith('ubuntu'))
            row.update(base_image=base, base_image_id=metadata['Id'])
            print(f'Ubuntu {release}: building isolated test image', flush=True)
            code = logged([docker, 'build', '--platform', 'linux/amd64', '--build-arg', 'BASE_IMAGE=' + base,
                           '--build-arg', 'UBUNTU_RELEASE=' + release, '--label', 'io.dotfiles.verification.task=' + task,
                           '-f', str(snapshot / 'tests/docker/Dockerfile'), '-t', image, str(snapshot)],
                          case / 'build.log', env=env, timeout=1800)
            require(code == 0, 'test image build failed')
            row['test_image_id'] = query([docker, 'image', 'inspect', image, '--format', '{{.Id}}'], env=env)
            query([docker, 'volume', 'create', '--label', 'io.dotfiles.verification.task=' + task, volume], env=env)
            row['volume_created'] = True
            print(f'Ubuntu {release}: full remote-compute deployment and behavior checks', flush=True)
            started = time.monotonic()
            code = logged([docker, 'run', '--name', name, '--label', 'io.dotfiles.verification.task=' + task,
                           '--platform', 'linux/amd64', '--init', '--cpus', '4', '--memory', '8g', '--pids-limit', '512',
                           '--env', 'DOTFILES_TEST_EXECUTION_MODE=' + execution,
                           '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                           '--mount', 'type=volume,source=' + volume + ',target=/home/verifier',
                           '--tmpfs', '/tmp:rw,exec,nosuid,nodev,size=2g', image],
                          case / 'container.log', env=env, timeout=14400)
            row.update(exit_code=code, elapsed_seconds=round(time.monotonic() - started, 3))
            if code == 124:
                stopped = logged([docker, 'stop', '--time', '10', name], case / 'stop.log', env=env, timeout=30)
                if stopped:
                    stopped = logged([docker, 'kill', name], case / 'kill.log', env=env, timeout=30)
                if stopped:
                    abort_remaining = True
                    raise RuntimeError('timed-out task container could not be stopped; remaining baselines blocked')
                abort_remaining = True
                running = query([docker, 'inspect', '--format', '{{.State.Running}}', name], env=env)
                if running != 'false':
                    raise RuntimeError('timed-out task container remains running; remaining baselines blocked')
                abort_remaining = False
            copied = logged([docker, 'cp', name + ':/home/verifier/artifacts', str(case / 'gate')],
                            case / 'copy.log', env=env, timeout=120)
            row['artifacts_copied'] = copied == 0
            require(copied == 0, 'complete gate artifact copy failed')
            artifact_hashes(case)
            gate_path = case / 'gate/report.json'
            gate = json.loads(gate_path.read_text()) if gate_path.is_file() else {}
            row['gate_status'] = gate.get('status', 'not reached')
            require(code == 0 and gate.get('status') == 'passed', 'container deployment gate failed')
            row['status'] = 'passed'
            # Only the task's own successful container and home volume are removed.
            removed = logged([docker, 'rm', name], case / 'remove-container.log', env=env, timeout=30)
            volume_removed = logged([docker, 'volume', 'rm', volume], case / 'remove-volume.log', env=env, timeout=30)
            row['cleanup'] = {'container_removed': removed == 0, 'volume_removed': volume_removed == 0}
            row['retained_runtime'] = removed != 0 or volume_removed != 0
            require(removed == 0 and volume_removed == 0, 'task container or volume cleanup failed')
        except (RuntimeError, OSError, subprocess.SubprocessError, ValueError) as error:
            row.update(status='failed', failure=str(error) if isinstance(error, RuntimeError) else type(error).__name__)
            row.setdefault('retained_runtime', row.get('volume_created', False))
        try:
            row['artifact_sha256'] = artifact_hashes(case)
            row['artifact_count'] = len(row['artifact_sha256'])
        except RuntimeError as error:
            row.update(status='failed', failure=str(error))
        atomic_json(output, report)
        print(f'Ubuntu {release}: {row["status"]}', flush=True)
    report['source_unchanged'] = query(['git', 'rev-parse', 'HEAD']) == commit and not query(['git', 'status', '--porcelain'])
    report['status'] = 'passed' if all(row['status'] == 'passed' for row in report['baselines']) else 'failed'
    if not report['source_unchanged']:
        report.update(status='failed', failure='source changed during Docker verification')
    atomic_json(output, report)
    print(str(output), flush=True)
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
