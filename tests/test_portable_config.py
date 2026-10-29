"""Runtime regressions for portable settings and bounded Nu activation."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
CHEZMOI = os.environ.get('DOTFILES_TEST_CHEZMOI') or shutil.which('chezmoi')
NU = os.environ.get('DOTFILES_TEST_NU') or shutil.which('nu')
MAMBA = os.environ.get('DOTFILES_TEST_MAMBA') or shutil.which('micromamba')


class TemporaryDevice(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='dotfiles-config-')
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name) / 'device with spaces'
        self.home.mkdir()
        self.env = {'HOME': str(self.home), 'PATH': '/usr/bin:/bin', 'TERM': 'xterm-256color',
                    'XDG_CONFIG_HOME': str(self.home / '.config'),
                    'XDG_DATA_HOME': str(self.home / '.local/share'),
                    'XDG_STATE_HOME': str(self.home / '.local/state'),
                    'XDG_CACHE_HOME': str(self.home / '.cache'),
                    'DOTFILES_SKILLS_DIR': str(SOURCE / 'tests/fixtures/skill-library')}

    def nu(self, script, *, rendered=False):
        flags = ['--config', str(self.home / '.config/nushell/config.nu'),
                 '--env-config', str(self.home / '.config/nushell/env.nu')] if rendered else ['--no-config-file']
        result = subprocess.run([NU, *flags, '-c', script], env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout


@unittest.skipUnless(CHEZMOI and NU and os.name == 'posix', 'requires Chezmoi and Nu on Unix')
class PortableConfigTests(TemporaryDevice):
    def deploy(self, mirror='tuna', bundles='none', arch='x86_64'):
        result = subprocess.run(['/bin/bash', str(SOURCE / 'bootstrap.sh'), '--home', str(self.home),
                                 '--class', 'linux', '--arch', arch, '--apply-only', '--bundles', bundles],
                                env=dict(self.env, DOTFILES_CHEZMOI_BIN=CHEZMOI, DOTFILES_MIRROR=mirror),
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_mirror_selection_matches_posix_nu_and_package_configs(self):
        for mirror, python, rust in [('tuna', 'https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple',
                                      'https://mirrors.tuna.tsinghua.edu.cn/rustup'),
                                     ('upstream', 'https://pypi.org/simple', 'https://static.rust-lang.org')]:
            self.deploy(mirror)
            actual = json.loads(self.nu('[$env.PIP_INDEX_URL $env.UV_DEFAULT_INDEX $env.RUSTUP_DIST_SERVER] | to json', rendered=True))
            self.assertEqual(actual, [python, python, rust])
            posix = subprocess.check_output(['/bin/sh', '-c', '. "$HOME/.env_core"; printf "%s\\n" "$PIP_INDEX_URL" "$UV_DEFAULT_INDEX" "$RUSTUP_DIST_SERVER"'], env=self.env, text=True)
            self.assertEqual(posix.splitlines(), actual)
            for path in ['.config/uv/uv.toml', '.config/pip/pip.conf']:
                self.assertIn(python, (self.home / path).read_text())
            if mirror == 'upstream':
                for path in ['.cargo/config.toml', '.condarc', '.env_core']:
                    self.assertNotIn('tuna.tsinghua', (self.home / path).read_text())

    def test_mirror_plans_expose_selection_and_invalid_input_fails_without_writes(self):
        target = self.home / 'not-created'
        command = ['/bin/bash', str(SOURCE / 'bootstrap.sh'), '--home', str(target), '--plan']
        result = subprocess.run(command, env=dict(self.env, DOTFILES_MIRROR='upstream'), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['mirror'], 'upstream')
        result = subprocess.run(command, env=dict(self.env, DOTFILES_MIRROR='invalid'), capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(target.exists())

    def test_device_overrides_survive_reapply_and_git_keeps_ownership_checks(self):
        local = self.home / '.config/dotfiles'
        local.mkdir(parents=True)
        files = {'env.local.sh': 'export EDITOR=device-posix\n',
                 'env.local.nu': '$env.EDITOR = "device-nu"\n',
                 'nu.local.nu': 'def device-value [] { "device-command" }\n',
                 'bash.local.sh': 'alias device-command="echo device"\n',
                 'zsh.local.zsh': 'alias device-command="echo device"\n'}
        for name, content in files.items():
            (local / name).write_text(content)
        git = self.home / '.config/git/local.conf'
        git.parent.mkdir()
        git.write_text('[user]\nemail = device@example.invalid\n')
        for _ in range(2):
            self.deploy()
            self.assertEqual(json.loads(self.nu('[$env.EDITOR (device-value)] | to json', rendered=True)),
                             ['device-nu', 'device-command'])
            posix = subprocess.check_output(['/bin/sh', '-c', '. "$HOME/.env_core"; printf "%s" "$EDITOR"'], env=self.env, text=True)
            self.assertEqual(posix, 'device-posix')
            identity = subprocess.check_output(['git', 'config', '--global', '--includes', 'user.email'], env=self.env, text=True).strip()
            self.assertEqual(identity, 'device@example.invalid')
            trusted = subprocess.run(['git', 'config', '--global', '--includes', '--get-all', 'safe.directory'], env=self.env, text=True, capture_output=True)
            self.assertNotIn('*', trusted.stdout.splitlines())
            for name, content in files.items():
                self.assertEqual((local / name).read_text(), content)



@unittest.skipUnless(NU and MAMBA, 'requires Nu and Micromamba')
class MicromambaActivationTests(TemporaryDevice):
    def setUp(self):
        super().setUp()
        self.prefix = self.home / 'mamba/envs/demo'
        (self.prefix / 'conda-meta').mkdir(parents=True)
        (self.prefix / 'conda-meta/history').write_text('')
        self.env.update(MAMBA_EXE=str(MAMBA), MAMBA_ROOT_PREFIX=str(self.home / 'mamba'))
        self.module = 'use ' + json.dumps(str(SOURCE / 'dot_config/nushell/micromamba.nu')) + ' *; '

    def test_metadata_activation_and_deactivation_restore_device_values(self):
        (self.prefix / 'conda-meta/state').write_text(json.dumps({'env_vars': {
            'PACKAGE_REQUIRED': 'line one\nquoted "value"', 'DEVICE_VALUE': 'environment', 'REMOVE_ME': '***unset***'}}))
        package = self.prefix / 'etc/conda/env_vars.d'
        package.mkdir(parents=True)
        (package / 'package.json').write_text('{"PACKAGE_DEFAULT":"from-package"}')
        actual = json.loads(self.nu(self.module + '''$env.DEVICE_VALUE = "device"; $env.REMOVE_ME = "original"
let original = $env.PATH
activate demo
let active = [$env.PACKAGE_REQUIRED $env.PACKAGE_DEFAULT $env.DEVICE_VALUE ($env.REMOVE_ME? | default "missing") $env.CONDA_DEFAULT_ENV]
deactivate
{active: $active, restored: [$env.DEVICE_VALUE $env.REMOVE_ME ($env.PACKAGE_REQUIRED? | default "missing") ($env.PATH == $original)]} | to json'''))
        self.assertEqual(actual['active'], ['line one\nquoted "value"', 'from-package', 'environment', 'missing', 'demo'])
        self.assertEqual(actual['restored'], ['device', 'original', 'missing', True])

    def test_hook_environment_refuses_partial_activation_without_changing_path(self):
        hooks = self.prefix / 'etc/conda/activate.d'
        hooks.mkdir(parents=True)
        (hooks / 'required.sh').write_text('export PACKAGE_REQUIRED=hook\n')
        actual = json.loads(self.nu(self.module + '''let original = $env.PATH
let failure = try { activate demo; "unexpected success" } catch {|error| $error.msg }
{error: $failure, unchanged: ($env.PATH == $original), active: ($env.CONDA_DEFAULT_ENV? | default "none")} | to json'''))
        self.assertIn('micromamba run', actual['error'])
        self.assertTrue(actual['unchanged'])
        self.assertEqual(actual['active'], 'none')
