"""Public PowerShell boundary; Linux results cover planning/rendering only."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import tarfile
import unittest
import zipfile
from pins import agent_pins, common_pin, native_agent_pins, windows_assets
from fixtures.skills import STATIC_LIBRARY, assert_skill_copies

SOURCE = Path(__file__).resolve().parents[1]
POWERSHELL = os.environ.get("DOTFILES_TEST_POWERSHELL") or shutil.which("pwsh") or shutil.which("powershell")


def magpie_releases():
    """The shared release catalog: the one owner of the version and digests."""
    rows = {}
    for line in (SOURCE / "deployment/magpie/releases.tsv").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        name, version, target, url, sha256 = line.split("|")
        rows[target] = {"name": name, "version": version, "target": target, "url": url, "sha256": sha256}
    return rows


def magpie_cmd_launcher_bytes():
    """The exact .cmd bytes: ASCII-only and relative to the launcher's own dir.

    The launcher lives in .local/bin and the binary in
    .local/share/dotfiles/magpie/bin, so %~dp0 plus this fixed suffix locates
    it without embedding HOME (which may be non-ASCII or contain % or !).
    """
    return (b"@echo off\r\nsetlocal DisableDelayedExpansion\r\n"
            b'"%~dp0..\\share\\dotfiles\\magpie\\bin\\magpie.exe" %*\r\n'
            b"exit /b %errorlevel%\r\n")


@unittest.skipUnless(POWERSHELL, "set DOTFILES_TEST_POWERSHELL for the public Windows boundary")
class WindowsBoundaryTests(unittest.TestCase):
    def setUp(self):
        # The native harness has already bootstrapped a manager home. Keep
        # fixture homes beside it, not below it, because Pi scans ancestor
        # directories for skills.
        self.temporary = tempfile.TemporaryDirectory(
            prefix="dotfiles-windows-", dir=os.environ.get("DOTFILES_TEST_WINDOWS_TEMP"))
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "device with spaces"
        self.original = self.root / "other-profile"
        self.original.mkdir()
        self.env = os.environ.copy()
        for name in tuple(self.env):
            if name.startswith(("DOTFILES_", "XDG_", "PIXI_", "BUN_", "CARGO_", "RUSTUP_", "ATUIN_", "UV_")) or name in (
                "GLM_API_TOKEN", "KIMI_API_KEY", "GLM_BASE_URL", "HTTP_PROXY_URL", "NODE_OPTIONS", "CLAUDE_CONFIG_DIR",
            ):
                self.env.pop(name)
        # Give PowerShell a disposable OS profile so its startup cache cannot
        # write into either the target home or the protected profile.
        runtime = self.root / 'powershell-runtime'
        self.env.update(HOME=str(runtime), USERPROFILE=str(runtime),
                        APPDATA=str(runtime / "roaming"), LOCALAPPDATA=str(runtime / "local"),
                        DOTFILES_SKILLS_DIR=str(SOURCE / "tests/fixtures/skill-library"))
        # PowerShell records noninteractive startup data by script path. Warm
        # the actual deployment entrypoint in plan mode; a separate no-op
        # script leaves bootstrap.ps1's first-run cache in the protected tree.
        warmup = self.deploy("-Plan")
        self.assertEqual(warmup.returncode, 0, warmup.stderr)
        self.assertFalse(self.home.exists())
        self.original_profile_state = self.original_profile_entries()

    def original_profile_entries(self):
        return tuple(sorted(path.relative_to(self.original).as_posix()
                            for path in self.original.rglob("*")))

    def assert_original_profile_unchanged(self):
        self.assertEqual(self.original_profile_entries(), self.original_profile_state)

    def deploy(self, *arguments, env=None):
        return subprocess.run([POWERSHELL, "-NoLogo", "-NoProfile", "-NonInteractive", "-File",
                               str(SOURCE / "bootstrap.ps1"), "-TargetHome", str(self.home), *arguments],
                              cwd=SOURCE, env=env or self.env, capture_output=True, text=True, timeout=90)

    def test_windows_asset_loader_returns_scalar_metadata(self):
        script = self.root / "asset-loader.ps1"
        script.write_text(r'''function Stop-Deployment([string]$Message) { throw $Message }
. (Join-Path $env:DOTFILES_TEST_SOURCE 'deployment/windows.ps1')
$exceptions = @([IO.File]::ReadAllText((Join-Path $env:DOTFILES_TEST_SOURCE 'deployment/windows-assets.json')) | ConvertFrom-Json)
$asset = Get-Asset 'chezmoi'
$asset | ConvertTo-Json -Compress
''')
        environment = dict(self.env, DOTFILES_TEST_SOURCE=str(SOURCE))
        result = subprocess.run([POWERSHELL, "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(script)],
                                cwd=SOURCE, env=environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        asset = json.loads(result.stdout)
        for field in ("name", "version", "url", "sha256", "kind", "entry", "target"):
            self.assertIsInstance(asset[field], str)
        self.assertTrue(asset["url"].startswith("https://"))
        self.assertRegex(asset["sha256"], r"^[a-f0-9]{64}$")

    def asset_version_fixture(self, name, *, cached=None, downloaded=None):
        asset = windows_assets()[name]
        target = self.home / asset['target']
        diagnostic = target / 'bin/git.exe' if name == 'git-bash' else target / 'hx.exe' if name == 'helix' else target
        diagnostic.parent.mkdir(parents=True, exist_ok=True)

        def payload(output):
            return (f'import sys\nassert sys.argv[1:] == ["--version"]\nprint({output!r})\n').encode()

        if cached is None:
            if diagnostic.exists():
                diagnostic.unlink()
        else:
            diagnostic.write_bytes(payload(cached))
        archive = self.root / 'asset-payload.py'
        archive.write_bytes(payload(downloaded or 'unexpected download'))
        temporary = self.home / '.cache/tmp'
        temporary.mkdir(parents=True, exist_ok=True)
        script = self.root / 'asset-version.ps1'
        script.write_text(r'''$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
function Stop-Deployment([string]$Message) { throw $Message }
$Source = $env:DOTFILES_TEST_SOURCE
$TargetHome = $env:DOTFILES_TEST_TARGET_HOME
. (Join-Path $env:DOTFILES_TEST_SOURCE 'deployment/windows.ps1')
$exceptions = @([IO.File]::ReadAllText((Join-Path $env:DOTFILES_TEST_SOURCE 'deployment/windows-assets.json')) | ConvertFrom-Json)
$script:FixtureDownloads = 0
function Download-Verified($Asset, [string]$Destination) {
    $script:FixtureDownloads++
    if ($env:DOTFILES_TEST_ALLOW_DOWNLOAD -ne '1') { throw 'unexpected download' }
    [IO.File]::Copy($env:DOTFILES_TEST_PAYLOAD, $Destination)
}
# Use synthetic diagnostic payloads on either OS while retaining the real
# subprocess runner, Install-Asset control flow, and output propagation.
$script:FixtureInvokeTool = ${function:Invoke-Tool}
function Invoke-Tool([string]$Executable, [string[]]$Arguments, [switch]$Quiet) {
    & $script:FixtureInvokeTool $env:DOTFILES_TEST_PYTHON (@($Executable) + $Arguments) -Quiet:$Quiet
}
Install-Asset $env:DOTFILES_TEST_ASSET
@{ downloads = $script:FixtureDownloads } | ConvertTo-Json -Compress
''')
        environment = dict(self.env, DOTFILES_TEST_SOURCE=str(SOURCE), DOTFILES_TEST_TARGET_HOME=str(self.home),
                           DOTFILES_TEST_PYTHON=sys.executable, DOTFILES_TEST_ASSET=name,
                           DOTFILES_TEST_ALLOW_DOWNLOAD='1' if downloaded is not None else '0',
                           DOTFILES_TEST_PAYLOAD=str(archive), TEMP=str(temporary))
        result = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-File', str(script)],
                                env=environment, capture_output=True, text=True, timeout=30)
        return result, diagnostic, archive.read_bytes()

    def test_asset_reuses_exact_tool_versions_with_native_build_metadata(self):
        pins = windows_assets()
        # These are native --version formats, including ChezMoi's fields,
        # Atuin/Helix build IDs, and Rustup's additional informational lines.
        diagnostics = {
            'pixi': f"pixi {pins['pixi']['version']}",
            'chezmoi': f"chezmoi version v{pins['chezmoi']['version']}, commit abc123, built by goreleaser",
            'bun': pins['bun']['version'],
            'atuin': f"atuin {pins['atuin']['version']} (NO_GIT)",
            'git-bash': f"git version {pins['git-bash']['version']}",
            'helix': f"helix {pins['helix']['version']} (a05c151b)",
            'jq': f"jq-{pins['jq']['version']}",
            'rustup': f"rustup {pins['rustup']['version']} (d8c92c676 2026-10-21)\ninfo: no rustc is currently active",
        }
        for name, diagnostic in diagnostics.items():
            with self.subTest(asset=name):
                result, _, _ = self.asset_version_fixture(name, cached=diagnostic)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)['downloads'], 0)

    def test_asset_repairs_cached_version_prefix_and_tool_name_collisions(self):
        pin = windows_assets()['jq']['version']
        for diagnostic in (f'jq-{pin}0', f'jq-{pin}-dev', f'other-tool {pin}', f'jq-0.0.0 (wanted {pin})'):
            with self.subTest(diagnostic=diagnostic):
                result, target, replacement = self.asset_version_fixture('jq', cached=diagnostic, downloaded=f'jq-{pin}')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)['downloads'], 1)
                self.assertEqual(target.read_bytes(), replacement)

    def test_asset_rejects_downloaded_version_prefix_and_tool_name_collisions(self):
        pin = windows_assets()['jq']['version']
        for diagnostic in (f'jq-{pin}0', f'jq-{pin}-dev', f'other-tool {pin}', f'jq-0.0.0 (wanted {pin})'):
            with self.subTest(diagnostic=diagnostic):
                result, _, _ = self.asset_version_fixture('jq', downloaded=diagnostic)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('did not report its pinned version', result.stderr)

    def test_payload_preflight_defers_unfetched_skills_without_creating_home(self):
        script = self.root / 'payload-preflight.ps1'
        script.write_text(r'''$ErrorActionPreference = 'Stop'
function Stop-Deployment([string]$Message) { throw $Message }
$Source = $env:DOTFILES_TEST_SOURCE
$TargetHome = $env:DOTFILES_TEST_TARGET_HOME
$roots = @{ appData = (Join-Path $TargetHome 'AppData/Roaming') }
$exceptions = @()
function Read-Catalog([string]$Relative) {
    foreach ($line in [IO.File]::ReadAllLines((Join-Path $Source $Relative))) {
        if ($line -and -not $line.StartsWith('#')) { @{ columns = $line.Split('|') } }
    }
}
. (Join-Path $Source 'deployment/windows.ps1')
$env:DOTFILES_SKILLS_DIR = $null
Assert-OwnedState
if (Test-Path -LiteralPath $TargetHome) { throw 'preflight created the target home' }
''')
        result = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-File', str(script)],
                                env=dict(self.env, DOTFILES_TEST_SOURCE=str(SOURCE),
                                         DOTFILES_TEST_TARGET_HOME=str(self.home)),
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_skill_cache_reparse_paths_fail_before_fetching_or_mutation(self):
        script = self.root / 'skill-cache-preflight.ps1'
        script.write_text(r'''$ErrorActionPreference = 'Stop'
function Stop-Deployment([string]$Message) { throw $Message }
$Source = $env:DOTFILES_TEST_SOURCE
$TargetHome = $env:DOTFILES_TEST_TARGET_HOME
$roots = @{
    cache = (Join-Path $TargetHome '.cache')
    state = (Join-Path $TargetHome '.local/state')
    appData = (Join-Path $TargetHome 'AppData/Roaming')
}
$exceptions = @()
function Read-Catalog([string]$Relative) {
    foreach ($line in [IO.File]::ReadAllLines((Join-Path $Source $Relative))) {
        if ($line -and -not $line.StartsWith('#')) { @{ columns = $line.Split('|') } }
    }
}
. (Join-Path $Source 'deployment/windows.ps1')
function Invoke-WebRequest { throw 'unexpected network request' }
function Invoke-Tool { throw 'unexpected tool invocation' }
if ($env:DOTFILES_TEST_CACHE_ACTION -eq 'preflight') { Assert-OwnedState }
else { Import-SkillLibrary }
throw 'unsafe skill cache was accepted'
''')
        sentinel = self.original / 'device-data'
        sentinel.write_bytes(b'protected device data\x00\n')
        before = {path.relative_to(self.original).as_posix(): path.read_bytes()
                  for path in self.original.rglob('*') if path.is_file()}
        cases = (
            ('.cache/dotfiles', True),
            ('.cache/dotfiles/skills', True),
            ('.cache/dotfiles/skills/git', True),
            ('.cache/dotfiles/skills/git/repository/.git/objects', True),
            ('.cache/dotfiles/skills/tarballs', True),
            ('.cache/dotfiles/skills/.refreshed', False),
            ('.cache/dotfiles/skills/tarballs/archive.tgz', False),
            ('.cache/dotfiles/skills/tarballs/archive.tgz.part', False),
        )
        for index, (relative, directory) in enumerate(cases):
            for action in ('preflight', 'import'):
                with self.subTest(path=relative, action=action):
                    home = self.root / f'cache-case-{index}-{action}'
                    linked = home / relative
                    linked.parent.mkdir(parents=True)
                    try:
                        linked.symlink_to(self.original if directory else sentinel, target_is_directory=directory)
                    except OSError:
                        self.skipTest('OS policy prohibits creating the test symlink')
                    temporary = home / '.cache/tmp'
                    temporary.mkdir(parents=True)
                    environment = dict(self.env, DOTFILES_TEST_SOURCE=str(SOURCE),
                                       DOTFILES_TEST_TARGET_HOME=str(home), DOTFILES_TEST_CACHE_ACTION=action,
                                       DOTFILES_SKILLS_DIR='', TEMP=str(temporary))
                    result = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-File', str(script)],
                                            env=environment, capture_output=True, text=True, timeout=30)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('symlink or reparse', result.stderr)
                    self.assertEqual(list(temporary.iterdir()), [], 'created skill staging before rejection')
                    self.assertFalse((home / '.local').exists())
                    after = {path.relative_to(self.original).as_posix(): path.read_bytes()
                             for path in self.original.rglob('*') if path.is_file()}
                    self.assertEqual(after, before)
                    self.assertEqual(sorted(path.name for path in self.original.iterdir()), ['device-data'])

    def test_skill_cache_reuses_regular_archive_and_offline_library(self):
        source_skill = self.root / 'SKILL.md'
        source_skill.write_text('# cached skill\n')
        archive = self.home / '.cache/dotfiles/skills/tarballs/example.invalid_skill.tgz.tgz'
        archive.parent.mkdir(parents=True)
        with tarfile.open(archive, 'w:gz') as payload:
            payload.add(source_skill, arcname='SKILL.md')
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        temporary = self.home / '.cache/tmp'
        temporary.mkdir(parents=True)
        script = self.root / 'skill-cache-regular.ps1'
        script.write_text(r'''$ErrorActionPreference = 'Stop'
function Stop-Deployment([string]$Message) { throw $Message }
$Source = $env:DOTFILES_TEST_SOURCE
$TargetHome = $env:DOTFILES_TEST_TARGET_HOME
$roots = @{ cache = (Join-Path $TargetHome '.cache'); state = (Join-Path $TargetHome '.local/state') }
. (Join-Path $Source 'deployment/windows.ps1')
function Read-Catalog([string]$Relative) {
    if ($Relative -eq 'deployment/skills.lock.tsv') {
        @{ columns = @('cached-skill', 'tarball', 'https://example.invalid/skill.tgz', $env:DOTFILES_TEST_DIGEST) }
    } elseif ($Relative -eq 'deployment/skills.tsv') {
        @{ columns = @('cached-skill', 'tarball', 'https://example.invalid/skill.tgz', '', '', 'auto') }
    } else { throw 'unexpected catalog' }
}
function Invoke-WebRequest { throw 'unexpected network request' }
Import-SkillLibrary
[Console]::Out.Write($script:SkillLibrary)
''')
        environment = dict(self.env, DOTFILES_TEST_SOURCE=str(SOURCE), DOTFILES_TEST_TARGET_HOME=str(self.home),
                           DOTFILES_TEST_DIGEST=digest, DOTFILES_SKILLS_DIR='', DOTFILES_SKILLS_REFRESH='0',
                           TEMP=str(temporary))
        result = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-File', str(script)],
                                env=environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((Path(result.stdout) / 'cached-skill/SKILL.md').read_text(), source_skill.read_text())
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), digest)
        self.assertIn(digest, (self.home / '.local/state/dotfiles/skills.lock.tsv').read_text())
        self.assertFalse((archive.parent.parent / '.refreshed').exists())
        offline_home = self.root / 'offline-device'
        offline = SOURCE / 'tests/fixtures/skill-library'
        result = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-File', str(script)],
                                env=dict(environment, DOTFILES_TEST_TARGET_HOME=str(offline_home),
                                         DOTFILES_SKILLS_DIR=str(offline)),
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout), offline)
        self.assertFalse(offline_home.exists(), 'offline library unexpectedly created cache/state')

    def test_git_skill_layout_supports_root_and_nested_packages(self):
        for skill_path in ('.', 'skills/demo'):
            with self.subTest(skill_path=skill_path):
                home = self.root / ('root-package' if skill_path == '.' else 'nested-package')
                repo = home / '.cache/dotfiles/skills/git/example.invalid_demo.git'
                package = repo / skill_path
                package.mkdir(parents=True)
                (package / 'SKILL.md').write_text('---\nname: demo\ndescription: fixture\n---\nbody\n')
                (package / 'agents').mkdir()
                (package / 'agents/openai.yaml').write_text('interface:\n  display_name: "Demo"\n')
                (package / 'LICENSE').write_text('synthetic license\n')
                (package / 'AGENTS.md').write_text('repository instructions; do not deploy\n')
                subprocess.run(['git', 'init', '-q', str(repo)], check=True)
                subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True)
                subprocess.run(['git', '-C', str(repo), '-c', 'user.name=t', '-c', 'user.email=t@example.invalid',
                                'commit', '-qm', 'fixture'], check=True)
                pin = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
                temporary = home / '.cache/tmp'
                temporary.mkdir()
                script = self.root / 'git-skill-layout.ps1'
                script.write_text(r'''$ErrorActionPreference = 'Stop'
function Stop-Deployment([string]$Message) { throw $Message }
$Source = $env:DOTFILES_TEST_SOURCE
$TargetHome = $env:DOTFILES_TEST_TARGET_HOME
$roots = @{ cache = (Join-Path $TargetHome '.cache'); state = (Join-Path $TargetHome '.local/state') }
. (Join-Path $Source 'deployment/windows.ps1')
function Read-Catalog([string]$Relative) {
    if ($Relative -eq 'deployment/skills.lock.tsv') {
        @{ columns = @('demo', 'git', 'https://example.invalid/demo.git', $env:DOTFILES_TEST_PIN, 'auto') }
    } elseif ($Relative -eq 'deployment/skills.tsv') {
        @{ columns = @('demo', 'git', 'https://example.invalid/demo.git', 'main', $env:DOTFILES_TEST_SKILL_PATH, 'auto') }
    } elseif ($Relative -eq 'deployment/skill-layouts.tsv') {
        @{ columns = @('demo', 'SKILL.md', 'SKILL.md') }
        @{ columns = @('demo', 'agents/openai.yaml', 'agents/openai.yaml') }
        @{ columns = @('demo', 'LICENSE', 'LICENSE') }
    } else { throw 'unexpected catalog' }
}
Import-SkillLibrary
[Console]::Out.Write($script:SkillLibrary)
''')
                environment = dict(self.env, DOTFILES_TEST_SOURCE=str(SOURCE), DOTFILES_TEST_TARGET_HOME=str(home),
                                   DOTFILES_TEST_PIN=pin, DOTFILES_TEST_SKILL_PATH=skill_path,
                                   DOTFILES_SKILLS_DIR='', DOTFILES_SKILLS_REFRESH='0', TEMP=str(temporary))
                result = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-File', str(script)],
                                        env=environment, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                copied = Path(result.stdout) / 'demo'
                self.assertEqual({p.relative_to(copied).as_posix() for p in copied.rglob('*') if p.is_file()},
                                 {'SKILL.md', 'agents/openai.yaml', 'LICENSE'})
                for relative in ('SKILL.md', 'agents/openai.yaml', 'LICENSE'):
                    self.assertEqual((copied / relative).read_bytes(), (package / relative).read_bytes())

    def skill_lock_gate_fixture(self, name):
        # A fixture source decouples the lock under test from the repo's real
        # lock; the catalog selects one auto tarball skill plus one tagged
        # skill that only a DOTFILES_SKILLS request selects.
        source = self.root / f'{name}-source'
        (source / 'deployment').mkdir(parents=True)
        (source / 'deployment/skills.tsv').write_text(
            '# name|kind|source|ref|path|selection\n'
            'demo|tarball|https://example.invalid/skill.tgz|||auto\n'
            'extra|tarball|https://example.invalid/other.tgz|||optional\n')
        script = self.root / f'{name}.ps1'
        script.write_text(r'''$ErrorActionPreference = 'Stop'
function Stop-Deployment([string]$Message) { throw $Message }
$Source = $env:DOTFILES_TEST_SOURCE
$TargetHome = $env:DOTFILES_TEST_TARGET_HOME
$roots = @{ cache = (Join-Path $TargetHome '.cache'); state = (Join-Path $TargetHome '.local/state') }
function Read-Catalog([string]$Relative) {
    foreach ($line in [IO.File]::ReadAllLines((Join-Path $Source $Relative))) {
        if ($line -and -not $line.StartsWith('#')) { @{ columns = $line.Split('|') } }
    }
}
. (Join-Path $env:DOTFILES_TEST_WINDOWS 'deployment/windows.ps1')
function Invoke-WebRequest { throw 'unexpected network request' }
function Invoke-Tool { throw 'unexpected tool invocation' }
Import-SkillLibrary
[Console]::Out.Write($script:SkillLibrary)
''')
        return source, script

    def run_skill_lock_gate(self, script, source, home, **overrides):
        temporary = home / '.cache/tmp'
        temporary.mkdir(parents=True)
        environment = dict(self.env, DOTFILES_TEST_SOURCE=str(source), DOTFILES_TEST_WINDOWS=str(SOURCE),
                           DOTFILES_TEST_TARGET_HOME=str(home), DOTFILES_SKILLS_DIR='',
                           DOTFILES_SKILLS_REFRESH='0', TEMP=str(temporary))
        environment.update(overrides)
        result = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-File', str(script)],
                                env=environment, capture_output=True, text=True, timeout=30)
        return result, temporary

    def test_skill_lock_gate_fails_before_remote_fetch(self):
        source, script = self.skill_lock_gate_fixture('skill-lock-gate')
        lock = source / 'deployment/skills.lock.tsv'
        valid = 'demo|tarball|https://example.invalid/skill.tgz|' + 'a' * 64 + '\n'
        cases = (
            ('missing', None, 'missing skill lock'),
            ('empty', '', 'empty skill lock'),
            ('comments-only', '# name|kind|source|resolved\n', 'empty skill lock'),
            ('malformed', 'demo|tarball|https://example.invalid/skill.tgz\n', 'malformed skill lock entry'),
            ('invalid-pin', 'demo|tarball|https://example.invalid/skill.tgz|not-a-sha\n', 'invalid skill pin: demo'),
            ('unknown-kind', 'demo|zip|https://example.invalid/skill.tgz|' + 'a' * 64 + '\n', 'invalid skill pin: demo'),
            ('duplicate', valid + valid, 'duplicate skill lock entry'),
            ('other-entry-only', 'other|tarball|https://example.invalid/skill.tgz|' + 'a' * 64 + '\n',
             'skill lock source mismatch: demo'),
            ('kind-mismatch', 'demo|git|https://example.invalid/skill.tgz|' + 'a' * 40 + '\n',
             'skill lock source mismatch: demo'),
            ('source-mismatch', 'demo|tarball|https://example.invalid/elsewhere.tgz|' + 'a' * 64 + '\n',
             'skill lock source mismatch: demo'),
        )
        for index, (label, content, message) in enumerate(cases):
            with self.subTest(case=label):
                if content is None:
                    if lock.exists():
                        lock.unlink()
                else:
                    lock.write_text(content)
                home = self.root / f'lock-gate-{index}'
                result, temporary = self.run_skill_lock_gate(script, source, home)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn(message, result.stderr)
                self.assertNotIn('unexpected network request', result.stderr)
                self.assertNotIn('unexpected tool invocation', result.stderr)
                self.assertEqual(list(temporary.iterdir()), [], 'created skill staging before lock rejection')
                self.assertFalse((home / '.cache/dotfiles').exists(), 'created skill cache before lock rejection')
                self.assertFalse((home / '.local').exists(), 'wrote state before lock rejection')

    def test_skill_lock_gate_accepts_valid_pin_selection_and_offline_bypass(self):
        source, script = self.skill_lock_gate_fixture('skill-lock-accept')
        skill_file = self.root / 'lock-accept-SKILL.md'
        skill_file.write_text('# locked skill\n')
        home = self.root / 'lock-accept-device'
        archive = home / '.cache/dotfiles/skills/tarballs/example.invalid_skill.tgz.tgz'
        archive.parent.mkdir(parents=True)
        with tarfile.open(archive, 'w:gz') as payload:
            payload.add(skill_file, arcname='SKILL.md')
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        (source / 'deployment/skills.lock.tsv').write_text(
            f'demo|tarball|https://example.invalid/skill.tgz|{digest}\n')
        # The locked auto skill imports from the cached archive without any
        # network access; the unselected tagged skill needs no lock entry.
        result, _ = self.run_skill_lock_gate(script, source, home)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((Path(result.stdout) / 'demo/SKILL.md').read_text(), skill_file.read_text())
        state_lock = (home / '.local/state/dotfiles/skills.lock.tsv').read_text()
        self.assertIn(f'demo|tarball|https://example.invalid/skill.tgz|{digest}', state_lock)
        self.assertNotIn('extra', state_lock)
        # Requesting the tagged skill without a lock entry fails before fetch.
        tagged_home = self.root / 'lock-accept-tagged'
        result, temporary = self.run_skill_lock_gate(script, source, tagged_home, DOTFILES_SKILLS='optional')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('skill lock source mismatch: extra', result.stderr)
        self.assertEqual(list(temporary.iterdir()), [], 'created skill staging before lock rejection')
        # The documented offline bypass works even without a lock file.
        (source / 'deployment/skills.lock.tsv').unlink()
        offline_home = self.root / 'lock-accept-offline'
        offline = SOURCE / 'tests/fixtures/skill-library'
        result, _ = self.run_skill_lock_gate(script, source, offline_home, DOTFILES_SKILLS_DIR=str(offline))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout), offline)
        # The fixture creates the temporary directory the run needs, so the
        # offline library itself must not add a cache or a state to the home.
        self.assertEqual(sorted(path.name for path in offline_home.iterdir()), ['.cache'],
                         'offline library unexpectedly created cache or state')
        self.assertEqual(sorted(path.name for path in (offline_home / '.cache').iterdir()), ['tmp'],
                         'offline library unexpectedly created a skill cache')

    def qoder_fixture(self, reported_version=None, exit_code=0):
        version = native_agent_pins()['qoder']['version']
        if reported_version is None:
            reported_version = version
        payload = ('#!' + sys.executable + '\n'
                   'import json, os, pathlib, sys\n'
                   'with pathlib.Path(os.environ["DOTFILES_TEST_QODER_LOG"]).open("a") as log:\n'
                   '    log.write(json.dumps({"binary":sys.argv[0],"arguments":sys.argv[1:],'
                   '"requested":os.environ.get("DOTFILES_TEST_QODER_REQUESTED", sys.argv[0])}) + "\\n")\n'
                   'if sys.argv[1:] != ["--version"]:\n'
                   '    raise SystemExit("self-install/update must not run")\n'
                   f'print({reported_version!r})\n'
                   f'raise SystemExit({exit_code})\n').encode()
        archive = self.root / 'qodercli.zip'
        with zipfile.ZipFile(archive, 'w') as package:
            package.writestr('qodercli.exe', payload)
        manifest = self.root / 'qoder-manifest.json'
        manifest.write_text(json.dumps({'latest': version, 'files': [{
            'os': 'windows', 'arch': 'amd64', 'url': 'https://example.invalid/qodercli.zip',
            'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
        }]}))
        temporary = self.home / '.cache/tmp'
        temporary.mkdir(parents=True, exist_ok=True)
        script = self.root / 'qoder-install.ps1'
        script.write_text(r'''$ErrorActionPreference = 'Stop'
function Stop-Deployment([string]$Message) { throw $Message }
$TargetHome = $env:DOTFILES_TEST_TARGET_HOME
. (Join-Path $env:DOTFILES_TEST_SOURCE 'deployment/windows.ps1')
function Invoke-RestMethod([string]$Uri, [switch]$UseBasicParsing) {
    if ($env:DOTFILES_TEST_QODER_CACHED -eq '1') { throw 'cached pin unexpectedly fetched a manifest' }
    if ($Uri -ne "https://example.invalid/$env:DOTFILES_TEST_QODER_VERSION/manifest.json") { throw 'unexpected manifest URL' }
    [IO.File]::ReadAllText($env:DOTFILES_TEST_QODER_MANIFEST) | ConvertFrom-Json
}
function Invoke-WebRequest([string]$Uri, [string]$OutFile, [switch]$UseBasicParsing, [int]$TimeoutSec) {
    if ($Uri -ne 'https://example.invalid/qodercli.zip') { throw 'unexpected archive URL' }
    [IO.File]::Copy($env:DOTFILES_TEST_QODER_ARCHIVE, $OutFile)
}
# Execute the synthetic archive payload through Python on either host. Keep
# the production subprocess runner and diagnostic output/error propagation.
$script:FixtureInvokeTool = ${function:Invoke-Tool}
function Invoke-Tool([string]$Executable, [string[]]$Arguments, [switch]$Quiet) {
    $env:DOTFILES_TEST_QODER_REQUESTED = $Executable
    if ($Executable.EndsWith('.cmd')) {
        $launcher = [IO.File]::ReadAllLines($Executable)
        $target = [regex]::Match($launcher[1], '^"([^"]+)" %\*$')
        if (-not $target.Success) { throw 'unexpected native Qoder launcher' }
        $Executable = $target.Groups[1].Value
    }
    & $script:FixtureInvokeTool $env:DOTFILES_TEST_PYTHON (@($Executable) + $Arguments) -Quiet:$Quiet
}
Install-Qoder $env:DOTFILES_TEST_QODER_VERSION 'https://example.invalid'
''')
        environment = dict(self.env, DOTFILES_TEST_SOURCE=str(SOURCE), DOTFILES_TEST_TARGET_HOME=str(self.home),
                           DOTFILES_TEST_PYTHON=sys.executable, DOTFILES_TEST_QODER_VERSION=version,
                           DOTFILES_TEST_QODER_ARCHIVE=str(archive), DOTFILES_TEST_QODER_MANIFEST=str(manifest),
                           DOTFILES_TEST_QODER_LOG=str(self.root / 'qoder-invocations.jsonl'), TEMP=str(temporary))
        return script, environment, payload

    def test_qoder_places_verified_pin_without_self_install_and_reuses_it(self):
        script, environment, payload = self.qoder_fixture()
        preserved = {
            '.qoder/entry/qoder.exe': b'device dispatcher selecting a newer release',
            '.qoder/bin/qodercli/qodercli-0.0.1.exe': b'older installed version',
            '.qoder/device-session': b'unrelated device state',
        }
        for relative, content in preserved.items():
            target = self.home / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        pinned = self.home / f'.qoder/bin/qodercli/qodercli-{environment["DOTFILES_TEST_QODER_VERSION"]}.exe'
        for cached in ('0', '1'):
            with self.subTest(cached=cached):
                result = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-File', str(script)],
                                        env=dict(environment, DOTFILES_TEST_QODER_CACHED=cached),
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.splitlines(), [environment['DOTFILES_TEST_QODER_VERSION']] * 2)
                self.assertEqual(pinned.read_bytes(), payload)
                for relative, content in preserved.items():
                    self.assertEqual((self.home / relative).read_bytes(), content)
                for relative in ('.local/bin', '.bun/bin'):
                    for command in ('qoder', 'qodercli'):
                        launcher = self.home / relative / command
                        self.assertIn('"' + str(pinned) + '" %*', launcher.with_suffix('.cmd').read_text())
                        self.assertIn(str(pinned).replace('\\', '/'), launcher.read_text())
                        if os.name != 'nt':
                            pinned.chmod(0o755)  # ZIP fixture is source text, rather than a native Windows PE.
                            diagnostic = subprocess.run(['sh', str(launcher), '--version'], env=environment,
                                                        capture_output=True, text=True, timeout=10)
                            self.assertEqual(diagnostic.returncode, 0, diagnostic.stderr)
                            self.assertEqual(diagnostic.stdout.strip(), environment['DOTFILES_TEST_QODER_VERSION'])
                self.assertEqual(list(Path(environment['TEMP']).iterdir()), [])
        invocations = [json.loads(line) for line in Path(environment['DOTFILES_TEST_QODER_LOG']).read_text().splitlines()]
        self.assertTrue(invocations)
        self.assertEqual(Path(invocations[0]['binary']).name, 'qodercli.exe')
        self.assertTrue(all(Path(call['binary']) == pinned for call in invocations[1:]), invocations)
        self.assertTrue(all(call['arguments'] == ['--version'] for call in invocations), invocations)
        for command in ('qoder', 'qodercli'):
            self.assertIn(str(self.home / '.local/bin' / (command + '.cmd')),
                          [call['requested'] for call in invocations])

    def test_qoder_rejects_wrong_or_failing_download_before_replacing_state(self):
        version = native_agent_pins()['qoder']['version']
        pinned = self.home / f'.qoder/bin/qodercli/qodercli-{version}.exe'
        preserved = {
            pinned: b'print("old invalid pin")\n',
            self.home / '.local/bin/qoder.cmd': b'old working launcher\r\n',
            self.home / '.qoder/entry/qoder.exe': b'device dispatcher',
        }
        for path, content in preserved.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        for reported, exit_code in ((version + '0', 0), (version + '-dev', 0), (version, 9)):
            with self.subTest(reported=reported, exit_code=exit_code):
                script, environment, _payload = self.qoder_fixture(reported, exit_code)
                result = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-File', str(script)],
                                        env=environment, capture_output=True, text=True, timeout=30)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('pinned version' if exit_code == 0 else 'required command failed', result.stderr)
                for path, content in preserved.items():
                    self.assertEqual(path.read_bytes(), content)
                self.assertEqual(list(Path(environment['TEMP']).iterdir()), [])

    def test_qoder_repairs_cached_suffix_or_failed_diagnostic_from_verified_archive(self):
        script, environment, payload = self.qoder_fixture()
        version = environment['DOTFILES_TEST_QODER_VERSION']
        pinned = self.home / f'.qoder/bin/qodercli/qodercli-{version}.exe'
        pinned.parent.mkdir(parents=True)
        for output, exit_code in ((version + '0', 0), (version, 7)):
            with self.subTest(output=output, exit_code=exit_code):
                pinned.write_text(f'print({output!r})\nraise SystemExit({exit_code})\n')
                result = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-File', str(script)],
                                        env=environment, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.splitlines(), [version] * 2)
                self.assertEqual(pinned.read_bytes(), payload)
                self.assertEqual(list(Path(environment['TEMP']).iterdir()), [])

    def test_qoder_checksum_failure_does_not_place_or_execute_payload(self):
        script, environment, _payload = self.qoder_fixture()
        manifest_path = Path(environment['DOTFILES_TEST_QODER_MANIFEST'])
        manifest = json.loads(manifest_path.read_text())
        manifest['files'][0]['sha256'] = '0' * 64
        manifest_path.write_text(json.dumps(manifest))
        result = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-File', str(script)],
                                env=environment, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Qoder SHA-256 mismatch', result.stderr)
        self.assertFalse((self.home / '.qoder').exists())
        self.assertFalse(Path(environment['DOTFILES_TEST_QODER_LOG']).exists())
        self.assertEqual(list(Path(environment['TEMP']).iterdir()), [])

    def test_skill_selection_inventory_and_prune_match_the_unix_boundary(self):
        chezmoi = os.environ.get('DOTFILES_TEST_CHEZMOI') or shutil.which('chezmoi')
        if not chezmoi:
            self.skipTest('actual source apply needs Chezmoi')
        library = self.root / 'selected library'
        shutil.copytree(SOURCE / 'tests/fixtures/skill-library', library)
        design = library / 'baoyu-diagram'
        design.mkdir()
        (design / 'SKILL.md').write_text('---\nname: baoyu-diagram\ndescription: mock design skill\n---\n')
        for root in ('.agents/skills', '.claude/skills', '.minimax/skills'):
            device = self.home / root / 'device-only'
            device.mkdir(parents=True)
            (device / 'SKILL.md').write_text('---\nname: device-only\ndescription: device skill\n---\n')
        collision = self.home / '.claude/skills/humanizer'
        collision.mkdir(parents=True)
        (collision / 'SKILL.md').write_text('device humanizer stays\n')
        selected = self.deploy('-ApplyOnly', env=dict(
            self.env, DOTFILES_CHEZMOI_BIN=chezmoi, DOTFILES_SKILLS_DIR=str(library), DOTFILES_SKILLS='design'))
        self.assertEqual(selected.returncode, 0, selected.stderr)
        for root in ('.agents/skills', '.claude/skills', '.minimax/skills'):
            self.assertTrue((self.home / root / 'baoyu-diagram/SKILL.md').is_file(), root)
            self.assertTrue((self.home / root / 'device-only/SKILL.md').is_file(), root)
        inventory = (self.home / '.local/state/dotfiles/managed-skills.tsv').read_text()
        self.assertIn('baoyu-diagram|.agents/skills', inventory)
        self.assertIn('baoyu-diagram|.claude/skills', inventory)
        self.assertIn('baoyu-diagram|.minimax/skills', inventory)
        self.assertEqual((self.home / '.claude/skills/humanizer/SKILL.md').read_text(),
                         'device humanizer stays\n')
        self.assertNotIn('humanizer|.claude/skills', inventory)
        deselected = self.deploy('-ApplyOnly', env=dict(
            self.env, DOTFILES_CHEZMOI_BIN=chezmoi, DOTFILES_SKILLS_DIR=str(library)))
        self.assertEqual(deselected.returncode, 0, deselected.stderr)
        for root in ('.agents/skills', '.claude/skills', '.minimax/skills'):
            self.assertFalse((self.home / root / 'baoyu-diagram').exists(), root)
            self.assertTrue((self.home / root / 'device-only/SKILL.md').is_file(), root)
        self.assertNotIn('baoyu-diagram|.claude/skills',
                         (self.home / '.local/state/dotfiles/managed-skills.tsv').read_text())
        self.assertEqual((self.home / '.claude/skills/humanizer/SKILL.md').read_text(),
                         'device humanizer stays\n')

    def test_generated_skill_is_copied_to_every_managed_root(self):
        chezmoi = os.environ.get('DOTFILES_TEST_CHEZMOI') or shutil.which('chezmoi')
        if not chezmoi:
            self.skipTest('actual source apply needs Chezmoi')
        generated = self.home / '.agents/skills/herdr'
        generated.mkdir(parents=True)
        (generated / 'SKILL.md').write_text('---\nname: herdr\ndescription: generated skill\n---\n')
        state = self.home / '.local/state/dotfiles/generated-skills.tsv'
        state.parent.mkdir(parents=True)
        state.write_text('# name|root|generator\nherdr|.agents/skills|herdr --skill\n')
        result = self.deploy('-ApplyOnly', env=dict(
            self.env, DOTFILES_CHEZMOI_BIN=chezmoi, DOTFILES_SKILLS_DIR=str(SOURCE / 'tests/fixtures/skill-library')))
        self.assertEqual(result.returncode, 0, result.stderr)
        for root in ('.claude/skills', '.minimax/skills'):
            self.assertEqual((self.home / root / 'herdr/SKILL.md').read_bytes(),
                             (generated / 'SKILL.md').read_bytes(), root)
        rows = state.read_text()
        self.assertIn('herdr|.claude/skills|herdr --skill', rows)
        self.assertIn('herdr|.minimax/skills|herdr --skill', rows)
        repeated = self.deploy('-ApplyOnly', env=dict(
            self.env, DOTFILES_CHEZMOI_BIN=chezmoi, DOTFILES_SKILLS_DIR=str(SOURCE / 'tests/fixtures/skill-library')))
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertEqual((self.home / '.claude/skills/herdr/SKILL.md').read_bytes(),
                         (generated / 'SKILL.md').read_bytes())

    def generated_skill_fixture(self):
        chezmoi = os.environ.get('DOTFILES_TEST_CHEZMOI') or shutil.which('chezmoi')
        if not chezmoi:
            self.skipTest('actual source apply needs Chezmoi')
        generated = self.home / '.agents/skills/herdr'
        generated.mkdir(parents=True)
        (generated / 'SKILL.md').write_text('---\nname: herdr\ndescription: generated skill\n---\n')
        state = self.home / '.local/state/dotfiles/generated-skills.tsv'
        state.parent.mkdir(parents=True)
        state.write_text('# name|root|generator\nherdr|.agents/skills|herdr --skill\n')
        return chezmoi, generated, state

    def deploy_generated(self, chezmoi):
        return self.deploy('-ApplyOnly', env=dict(
            self.env, DOTFILES_CHEZMOI_BIN=chezmoi,
            DOTFILES_SKILLS_DIR=str(SOURCE / 'tests/fixtures/skill-library')))

    def test_generated_skill_collisions_stay_device_owned_on_repeated_apply(self):
        chezmoi, generated, state = self.generated_skill_fixture()
        device = self.home / '.claude/skills/herdr'
        device.mkdir(parents=True)
        (device / 'SKILL.md').write_text('device herdr bytes\n')
        device_file = self.home / '.minimax/skills/herdr'
        device_file.parent.mkdir(parents=True)
        device_file.write_text('device file\n')
        for _ in range(2):
            result = self.deploy_generated(chezmoi)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((device / 'SKILL.md').read_text(), 'device herdr bytes\n')
            self.assertEqual(device_file.read_text(), 'device file\n')
            self.assertIn('preserved skill herdr in .claude/skills; '
                          'a device directory has that name and its bytes differ', result.stderr)
            self.assertIn('preserved skill herdr in .minimax/skills; a device file has that name',
                          result.stderr)
            rows = state.read_text()
            self.assertNotIn('herdr|.claude/skills', rows)
            self.assertNotIn('herdr|.minimax/skills', rows)
            self.assertIn('herdr|.agents/skills|herdr --skill', rows)

    def test_generated_skill_identical_directory_is_adopted_and_later_refreshed(self):
        chezmoi, generated, state = self.generated_skill_fixture()
        device = self.home / '.claude/skills/herdr'
        device.mkdir(parents=True)
        skill = device / 'SKILL.md'
        skill.write_bytes((generated / 'SKILL.md').read_bytes())
        stamp = 1000000000
        os.utime(skill, (stamp, stamp))
        result = self.deploy_generated(chezmoi)
        self.assertEqual(result.returncode, 0, result.stderr)
        # Adoption records the entry without rewriting the device's file.
        self.assertEqual(skill.stat().st_mtime, stamp)
        self.assertIn('herdr|.claude/skills|herdr --skill', state.read_text())
        # The adopted entry is owned now, so changed source bytes refresh it.
        (generated / 'SKILL.md').write_text('---\nname: herdr\ndescription: refreshed\n---\n')
        refreshed = self.deploy_generated(chezmoi)
        self.assertEqual(refreshed.returncode, 0, refreshed.stderr)
        self.assertEqual(skill.read_bytes(), (generated / 'SKILL.md').read_bytes())
        self.assertIn('herdr|.claude/skills|herdr --skill', state.read_text())

    def test_generated_skill_extra_file_prevents_adoption(self):
        chezmoi, generated, state = self.generated_skill_fixture()
        device = self.home / '.minimax/skills/herdr'
        device.mkdir(parents=True)
        (device / 'SKILL.md').write_bytes((generated / 'SKILL.md').read_bytes())
        (device / 'notes.md').write_text('device notes\n')
        for _ in range(2):
            result = self.deploy_generated(chezmoi)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((device / 'notes.md').read_text(), 'device notes\n')
            self.assertIn('preserved skill herdr in .minimax/skills; '
                          'a device directory has that name and its bytes differ', result.stderr)
            self.assertNotIn('herdr|.minimax/skills', state.read_text())

    def test_generated_skill_symlink_is_preserved_and_unrecorded(self):
        chezmoi, generated, state = self.generated_skill_fixture()
        outside = self.root / 'outside-herdr'
        outside.mkdir()
        (outside / 'SKILL.md').write_text('outside bytes\n')
        root = self.home / '.claude/skills'
        root.mkdir(parents=True)
        try:
            (root / 'herdr').symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('OS policy prohibits creating the test symlink')
        for _ in range(2):
            result = self.deploy_generated(chezmoi)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('preserved skill herdr in .claude/skills; a device symlink has that name',
                          result.stderr)
            self.assertNotIn('herdr|.claude/skills', state.read_text())
        self.assertEqual((outside / 'SKILL.md').read_text(), 'outside bytes\n')

    def device_skill_collisions(self, outside):
        """Device entries that carry the name of a selected skill."""
        link = self.home / '.claude/skills/tdd'
        link.parent.mkdir(parents=True)
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('OS policy prohibits creating the test symlink')
        device_file = self.home / '.minimax/skills/tdd'
        device_file.parent.mkdir(parents=True)
        device_file.write_text('device file\n')
        device_directory = self.home / '.agents/skills/tdd'
        device_directory.mkdir(parents=True)
        (device_directory / 'SKILL.md').write_text('device skill bytes\n')
        nested = self.root / 'nested-device-link'
        nested.mkdir()
        (nested / 'untouched').write_text('device bytes\n')
        try:
            (device_directory / 'linked').symlink_to(nested, target_is_directory=True)
        except OSError:
            self.skipTest('OS policy prohibits creating the test symlink')
        return link, device_file, device_directory

    def test_skill_collisions_are_preserved_with_an_offline_library(self):
        chezmoi = os.environ.get('DOTFILES_TEST_CHEZMOI') or shutil.which('chezmoi')
        if not chezmoi:
            self.skipTest('actual source apply needs Chezmoi')
        outside = self.root / 'outside-tdd'
        outside.mkdir()
        (outside / 'untouched').write_text('device bytes\n')
        link, device_file, device_directory = self.device_skill_collisions(outside)
        for _ in range(2):
            result = self.deploy('-ApplyOnly', env=dict(self.env, DOTFILES_CHEZMOI_BIN=chezmoi))
            self.assertEqual(result.returncode, 0, result.stderr)
            # A device link is preserved, reported, and never followed.
            self.assertTrue(link.is_symlink())
            self.assertEqual(sorted(path.name for path in outside.iterdir()), ['untouched'])
            self.assertIn('preserved skill tdd in .claude/skills; a device symlink has that name',
                          result.stderr)
            # A device file keeps its bytes.
            self.assertTrue(device_file.is_file())
            self.assertEqual(device_file.read_text(), 'device file\n')
            self.assertIn('preserved skill tdd in .minimax/skills; a device file has that name',
                          result.stderr)
            # A device directory keeps its bytes, and the preflight never
            # traverses the link inside it.
            self.assertEqual((device_directory / 'SKILL.md').read_text(), 'device skill bytes\n')
            self.assertTrue((device_directory / 'linked').is_symlink())
            self.assertEqual(sorted(path.name for path in (self.root / 'nested-device-link').iterdir()),
                             ['untouched'])
            self.assertIn('preserved skill tdd in .agents/skills; '
                          'a device directory has that name and its bytes differ', result.stderr)
            # A preserved entry is never recorded, so the device keeps it.
            inventory = (self.home / '.local/state/dotfiles/managed-skills.tsv').read_text()
            for root in ('.agents/skills', '.claude/skills', '.minimax/skills'):
                self.assertNotIn(f'tdd|{root}', inventory)

    def test_skill_collisions_are_preserved_with_a_fetched_library(self):
        # The fetched library is staged by the import step; the copy adapter
        # preserves the same collisions the offline library produces.
        skill_file = self.root / 'fetched-SKILL.md'
        skill_file.write_text('# fetched skill\n')
        home = self.root / 'fetched-device'
        archive = home / '.cache/dotfiles/skills/tarballs/example.invalid_skill.tgz.tgz'
        archive.parent.mkdir(parents=True)
        with tarfile.open(archive, 'w:gz') as payload:
            payload.add(skill_file, arcname='SKILL.md')
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        outside = self.root / 'outside-fetched'
        outside.mkdir()
        (outside / 'untouched').write_text('device bytes\n')
        link = home / '.claude/skills/demo'
        link.parent.mkdir(parents=True)
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('OS policy prohibits creating the test symlink')
        device_file = home / '.minimax/skills/demo'
        device_file.parent.mkdir(parents=True)
        device_file.write_text('device file\n')
        adopted = home / '.agents/skills/demo'
        adopted.mkdir(parents=True)
        (adopted / 'SKILL.md').write_bytes(skill_file.read_bytes())
        temporary = home / '.cache/tmp'
        temporary.mkdir(parents=True, exist_ok=True)
        script = self.root / 'fetched-collisions.ps1'
        script.write_text(r'''$ErrorActionPreference = 'Stop'
function Stop-Deployment([string]$Message) { throw $Message }
$Source = $env:DOTFILES_TEST_SOURCE
$TargetHome = $env:DOTFILES_TEST_TARGET_HOME
$roots = @{
    cache = (Join-Path $TargetHome '.cache')
    state = (Join-Path $TargetHome '.local/state')
    appData = (Join-Path $TargetHome 'AppData/Roaming')
}
$exceptions = @()
function Read-Catalog([string]$Relative) {
    if ($Relative -eq 'deployment/skills.lock.tsv') {
        @{ columns = @('demo', 'tarball', 'https://example.invalid/skill.tgz', $env:DOTFILES_TEST_DIGEST) }
    } elseif ($Relative -eq 'deployment/skills.tsv') {
        @{ columns = @('demo', 'tarball', 'https://example.invalid/skill.tgz', '', '', 'auto') }
    } else {
        foreach ($line in [IO.File]::ReadAllLines((Join-Path $Source $Relative))) {
            if ($line -and -not $line.StartsWith('#')) { @{ columns = $line.Split('|') } }
        }
    }
}
. (Join-Path $Source 'deployment/windows.ps1')
function Invoke-WebRequest { throw 'unexpected network request' }
Assert-OwnedState
Import-SkillLibrary
Copy-AgentPayload
''')
        environment = dict(self.env, DOTFILES_TEST_SOURCE=str(SOURCE), DOTFILES_TEST_TARGET_HOME=str(home),
                           DOTFILES_TEST_DIGEST=digest, DOTFILES_SKILLS_DIR='', DOTFILES_SKILLS_REFRESH='0',
                           TEMP=str(temporary))
        result = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-File', str(script)],
                                env=environment, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(link.is_symlink())
        self.assertEqual(sorted(path.name for path in outside.iterdir()), ['untouched'])
        self.assertIn('preserved skill demo in .claude/skills; a device symlink has that name', result.stderr)
        self.assertEqual(device_file.read_text(), 'device file\n')
        self.assertIn('preserved skill demo in .minimax/skills; a device file has that name', result.stderr)
        inventory = (home / '.local/state/dotfiles/managed-skills.tsv').read_text()
        self.assertNotIn('demo|.claude/skills', inventory)
        self.assertNotIn('demo|.minimax/skills', inventory)
        # A device directory that already holds the fetched bytes is adopted.
        self.assertIn('demo|.agents/skills', inventory)

    def test_dangling_skill_link_is_preserved_and_never_written_through(self):
        chezmoi = os.environ.get('DOTFILES_TEST_CHEZMOI') or shutil.which('chezmoi')
        if not chezmoi:
            self.skipTest('actual source apply needs Chezmoi')
        missing = self.root / 'missing-target'
        link = self.home / '.claude/skills/tdd'
        link.parent.mkdir(parents=True)
        try:
            link.symlink_to(missing, target_is_directory=True)
        except OSError:
            self.skipTest('OS policy prohibits creating the test symlink')
        result = self.deploy('-ApplyOnly', env=dict(self.env, DOTFILES_CHEZMOI_BIN=chezmoi))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(link.is_symlink())
        self.assertFalse(missing.exists(), 'the deployment created the target of a device link')
        self.assertIn('preserved skill tdd in .claude/skills; a device symlink has that name', result.stderr)
        inventory = (self.home / '.local/state/dotfiles/managed-skills.tsv').read_text()
        self.assertNotIn('tdd|.claude/skills', inventory)

    def test_recorded_skill_with_a_nested_junction_keeps_the_external_target(self):
        # Windows PowerShell 5.1 follows a junction during a recursive
        # removal, so replacing a recorded skill tree would delete the
        # target of a link inside it. The deployment must refuse that tree.
        if os.name != 'nt':
            self.skipTest('a nested junction requires native Windows')
        home = self.root / 'junction-device'
        skill = home / '.claude/skills/tdd'
        skill.mkdir(parents=True)
        (skill / 'SKILL.md').write_text('# device bytes\n')
        state = home / '.local/state/dotfiles/managed-skills.tsv'
        state.parent.mkdir(parents=True)
        state.write_text('# name|root\ntdd|.claude/skills\n')
        outside = self.root / 'junction-outside'
        outside.mkdir()
        sentinel = outside / 'sentinel.txt'
        sentinel.write_bytes(b'external sentinel\n')
        temporary = home / '.cache/tmp'
        temporary.mkdir(parents=True)
        script = self.root / 'junction-skill.ps1'
        script.write_text(r'''$ErrorActionPreference = 'Stop'
function Stop-Deployment([string]$Message) { throw $Message }
$Source = $env:DOTFILES_TEST_SOURCE
$TargetHome = $env:DOTFILES_TEST_TARGET_HOME
$roots = @{
    cache = (Join-Path $TargetHome '.cache')
    state = (Join-Path $TargetHome '.local/state')
    appData = (Join-Path $TargetHome 'AppData/Roaming')
}
$exceptions = @()
function Read-Catalog([string]$Relative) {
    foreach ($line in [IO.File]::ReadAllLines((Join-Path $Source $Relative))) {
        if ($line -and -not $line.StartsWith('#')) { @{ columns = $line.Split('|') } }
    }
}
. (Join-Path $Source 'deployment/windows.ps1')
function Invoke-WebRequest { throw 'unexpected network request' }
# The deployment owns the recorded directory, but the link inside it points
# outside the home.
New-Item -ItemType Junction -Path (Join-Path $TargetHome '.claude/skills/tdd/linked') -Value $env:DOTFILES_TEST_OUTSIDE | Out-Null
Assert-OwnedState
Import-SkillLibrary
Copy-AgentPayload
''')
        environment = dict(self.env, DOTFILES_TEST_SOURCE=str(SOURCE), DOTFILES_TEST_TARGET_HOME=str(home),
                           DOTFILES_TEST_OUTSIDE=str(outside),
                           DOTFILES_SKILLS_DIR=str(SOURCE / 'tests/fixtures/skill-library'),
                           TEMP=str(temporary))
        result = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-File', str(script)],
                                env=environment, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        # The external target survives: the deployment refused to remove a
        # tree that holds a link.
        self.assertTrue(sentinel.is_file())
        self.assertEqual(sentinel.read_bytes(), b'external sentinel\n')
        self.assertEqual(sorted(path.name for path in outside.iterdir()), ['sentinel.txt'])
        self.assertIn('preserved managed skill tdd in .claude/skills; it holds a link, '
                      'so the deployment did not replace it', result.stderr)
        # The recorded tree keeps its bytes and its link, and stays recorded.
        self.assertEqual((skill / 'SKILL.md').read_text(), '# device bytes\n')
        self.assertTrue((skill / 'linked').is_dir())
        self.assertIn('tdd|.claude/skills', state.read_text())
        # The other managed roots receive the skill unchanged.
        for root in ('.agents/skills', '.minimax/skills'):
            self.assertTrue((home / root / 'tdd/SKILL.md').is_file(), root)

    def test_unsafe_skill_parent_path_fails_without_writing_through(self):
        chezmoi = os.environ.get('DOTFILES_TEST_CHEZMOI') or shutil.which('chezmoi')
        if not chezmoi:
            self.skipTest('actual source apply needs Chezmoi')
        outside = self.root / 'outside-root'
        outside.mkdir()
        (outside / 'untouched').write_text('device bytes\n')
        root = self.home / '.claude/skills'
        root.parent.mkdir(parents=True)
        try:
            root.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('OS policy prohibits creating the test symlink')
        result = self.deploy('-ApplyOnly', env=dict(self.env, DOTFILES_CHEZMOI_BIN=chezmoi))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('symlink or reparse', result.stderr)
        # The deployment refused the root instead of writing the skills
        # through the device link.
        self.assertEqual(sorted(path.name for path in outside.iterdir()), ['untouched'])
        self.assert_original_profile_unchanged()

    def test_agent_launchers_use_validated_external_node_and_preserve_native_entries(self):
        node = os.environ.get('DOTFILES_TEST_NODE') or shutil.which('node')
        if not node:
            self.skipTest('external-runtime execution requires Node')
        version = subprocess.run([node, '--version'], capture_output=True, text=True, check=True).stdout.strip()
        tools = self.root / ("runtime tools 'quotes'" + (' %NODE% !node!' if os.name != 'nt' else ''))
        tools.mkdir()
        log = self.root / 'node-invocations.jsonl'
        native_log = self.root / 'native-invocations.jsonl'
        runtime = tools / ('node override.cmd' if os.name == 'nt' else 'node override.exe')
        node_script = tools / 'node.py'
        node_script.write_text('import json, pathlib, subprocess, sys\n'
                               f'with pathlib.Path({str(log)!r}).open("a") as log:\n'
                               '    log.write(json.dumps(sys.argv[1:]) + "\\n")\n'
                               f'raise SystemExit(subprocess.run([{node!r}, *sys.argv[1:]]).returncode)\n')
        bun = tools / ('bun.cmd' if os.name == 'nt' else 'bun')
        bun_script = tools / 'bun.py'
        native_payload = ('#!' + sys.executable + '\n'
                          'import json, pathlib, sys\n'
                          f'with pathlib.Path({str(native_log)!r}).open("a") as log:\n'
                          '    log.write(json.dumps(sys.argv[1:]) + "\\n")\n'
                          'if sys.argv[1:] == ["--version"]: print("4.5.6")\n'
                          'else:\n'
                          '    print(json.dumps(sys.argv[1:])); raise SystemExit(23)\n')
        javascript = ('const args=process.argv.slice(2);\n'
                      'if (JSON.stringify(args)===\'["--version"]\') console.log("1.2.3");\n'
                      'else { console.log(JSON.stringify(args)); process.exit(37); }\n')
        bun_script.write_text('import json, pathlib, sys\n'
                              'if sys.argv[1:] == ["--version"]:\n'
                              f'    print({common_pin("bun")!r}); raise SystemExit(0)\n'
                              'project = pathlib.Path(sys.argv[sys.argv.index("--cwd") + 1])\n'
                              'native = project.name == "codex"\n'
                              'package = project / "node_modules" / ("fixture-native" if native else "fixture-js")\n'
                              'package.mkdir(parents=True)\n'
                              'entry = "native entry.exe" if native else "javascript entry.js"\n'
                              '(package / "package.json").write_text(json.dumps({"bin":entry}))\n'
                              f'(package / entry).write_text({native_payload!r} if native else {javascript!r})\n'
                              '(package / entry).chmod(0o755)\n')
        for launcher, helper in ((runtime, node_script), (bun, bun_script)):
            if os.name == 'nt':
                launcher.write_text(f'@echo off\r\n"{sys.executable}" "{helper}" %*\r\nexit /b %errorlevel%\r\n')
            else:
                launcher.write_text('#!' + sys.executable + '\n' + helper.read_text())
                launcher.chmod(0o755)
        self.home.mkdir()
        (self.home / '.env_core').write_text('# isolated launcher environment\n')
        script = self.root / 'agent-launchers.ps1'
        script.write_text(r'''$ErrorActionPreference = 'Stop'
function Stop-Deployment([string]$Message) { throw $Message }
function Get-Input([string]$Name, [string]$Fallback) {
    $value = [Environment]::GetEnvironmentVariable($Name, 'Process')
    if ($value) { return $value }; return $Fallback
}
$TargetHome = $env:DOTFILES_TEST_TARGET_HOME
$Source = $env:DOTFILES_TEST_SOURCE
$roots = @{ bun = (Join-Path $TargetHome '.bun'); pixi = (Join-Path $TargetHome '.pixi') }
$selectedAgents = @('codex')
. (Join-Path $Source 'deployment/windows.ps1')
function Read-Catalog([string]$Relative) {
    if ($Relative -eq 'deployment/common-tools.tsv') {
        @{ columns = @('runtimes', "bun==$env:DOTFILES_TEST_BUN_VERSION,nodejs==$env:DOTFILES_TEST_NODE_VERSION") }
    } else { throw 'unexpected catalog' }
}
function Get-AgentCatalog {
    @(
        [pscustomobject]@{ record = 'codegraph'; agent = 'codegraph'; provider = 'bun'; package = 'fixture-js'
            version = '1.2.3'; policy = 'exact'; commands = 'fixture-js'; platforms = 'all'; order = 1
            selection = 'always'; herdr = '-'; minimumNode = '0.0.0'; trusted = ''; lock = ''; diagnostic = '-' }
        [pscustomobject]@{ record = 'codex'; agent = 'codex'; provider = 'bun'; package = 'fixture-native'
            version = '4.5.6'; policy = 'exact'; commands = 'fixture-native'; platforms = 'all'; order = 1
            selection = 'selectable'; herdr = 'codex'; minimumNode = '0.0.0'; trusted = ''; lock = ''; diagnostic = '-' }
    )
}
function Test-AgentPlatform([string]$Platforms) { return $true }
if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
    # The portable native-entry fixture contains Python source, rather than PE.
    $script:FixtureInvokeTool = ${function:Invoke-Tool}
    function Invoke-Tool([string]$Executable, [string[]]$Arguments, [switch]$Quiet, [switch]$ShowFailureOutput) {
        if ($Executable.EndsWith('native entry.exe')) {
            & $script:FixtureInvokeTool $env:DOTFILES_TEST_PYTHON (@($Executable) + $Arguments) -Quiet:$Quiet -ShowFailureOutput:$ShowFailureOutput
        } else {
            & $script:FixtureInvokeTool $Executable $Arguments -Quiet:$Quiet -ShowFailureOutput:$ShowFailureOutput
        }
    }
}
Install-Agents
''')
        environment = dict(self.env, DOTFILES_TEST_SOURCE=str(SOURCE), DOTFILES_TEST_TARGET_HOME=str(self.home),
                           DOTFILES_BUN_BIN=str(bun), DOTFILES_NODE_BIN=str(runtime),
                           DOTFILES_TEST_BUN_VERSION=common_pin('bun'), DOTFILES_TEST_NODE_VERSION=version.removeprefix('v'),
                           DOTFILES_TEST_PYTHON=sys.executable)
        result = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-File', str(script)],
                                env=environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.home / '.pixi/bin/node.exe').exists())
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual(calls[0], ['--version'])
        self.assertEqual(Path(calls[1][0]).name, 'javascript entry.js')
        self.assertEqual(calls[1][1:], ['--version'])
        self.assertEqual(len(calls), 2, 'native entry was incorrectly passed to Node')
        arguments = ['argument with spaces', "single ' and double \" quotes", '$literal; & values', '']
        for relative in ('.bun/bin', '.local/bin'):
            js = self.home / relative / 'fixture-js'
            cmd = js.with_suffix('.cmd').read_text()
            self.assertIn('"' + str(runtime).replace('%', '%%') + '"', cmd)
            self.assertIn('setlocal DisableDelayedExpansion', cmd)
            self.assertNotIn('.pixi\\bin\\node.exe', cmd)
            native = self.home / relative / 'fixture-native'
            self.assertNotIn(str(runtime), native.with_suffix('.cmd').read_text())
            self.assertNotIn('node.exe', native.read_text())
            if os.name == 'nt':
                probe = subprocess.run([str(js.with_suffix('.cmd')), *arguments], env=environment,
                                       capture_output=True, text=True, timeout=10)
            else:
                probe = subprocess.run(['sh', str(js), *arguments], env=environment,
                                       capture_output=True, text=True, timeout=10)
            self.assertEqual(probe.returncode, 37, probe.stderr)
            self.assertEqual(json.loads(probe.stdout), arguments)
            before_native = log.read_bytes()
            if os.name != 'nt':
                probe = subprocess.run(['sh', str(native), *arguments], env=environment,
                                       capture_output=True, text=True, timeout=10)
                self.assertEqual(probe.returncode, 23, probe.stderr)
                self.assertEqual(json.loads(probe.stdout), arguments)
            self.assertEqual(log.read_bytes(), before_native)
        self.assertEqual(len(log.read_text().splitlines()), 4)
        state = (self.home / '.local/state/dotfiles/agents.lock.tsv').read_text()
        self.assertIn('codex|bun|4.5.6|4.5.6', state)
        self.assertIn('codegraph|bun|1.2.3|1.2.3', state)

    def test_retirement_preserves_device_content_and_rejects_malformed_markers(self):
        script = self.root / 'retire.ps1'
        script.write_text(r'''$ErrorActionPreference = 'Stop'
function Stop-Deployment([string]$Message) { throw $Message }
$TargetHome = $env:DOTFILES_TEST_TARGET_HOME
. (Join-Path $env:DOTFILES_TEST_SOURCE 'deployment/windows.ps1')
$target = Join-Path $TargetHome 'rules.md'
Remove-InstructionBlock $target
''')
        self.home.mkdir()
        target = self.home / 'rules.md'
        start = '<!-- DOTFILES_AGENT_START -->'
        end = '<!-- DOTFILES_AGENT_END -->'
        environment = dict(self.env, DOTFILES_TEST_SOURCE=str(SOURCE), DOTFILES_TEST_TARGET_HOME=str(self.home))
        for content, expected in [(f'local\n\n{start}\nold\n{end}\n', 'local\n'),
                                  (f'{start}\nold\n{end}\n', None), ('local\n', 'local\n'),
                                  (f'{start}\nunfinished', 'unchanged')]:
            target.write_text(content)
            result = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-File', str(script)],
                                    env=environment, capture_output=True, text=True, timeout=30)
            if expected == 'unchanged':
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(target.read_text(), content)
            else:
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(target.read_text() if target.exists() else None, expected)

    def test_shell_preparation_rejects_autoload_symlinks_before_creating_directories(self):
        linked = self.home / '.local/share/nushell'
        linked.parent.mkdir(parents=True)
        try:
            linked.symlink_to(self.original, target_is_directory=True)
        except OSError:
            self.skipTest('OS policy prohibits creating the test symlink')
        script = self.root / 'prepare-shell-symlink.ps1'
        script.write_text(r'''$ErrorActionPreference = 'Stop'
function Stop-Deployment([string]$Message) { throw $Message }
$TargetHome = $env:DOTFILES_TEST_TARGET_HOME
$roots = @{ data = (Join-Path $TargetHome '.local/share') }
. (Join-Path $env:DOTFILES_TEST_SOURCE 'deployment/windows.ps1')
Prepare-Shell
''')
        result = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-File', str(script)],
                                env=dict(self.env, DOTFILES_TEST_SOURCE=str(SOURCE),
                                         DOTFILES_TEST_TARGET_HOME=str(self.home)),
                                capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('symlink or reparse', result.stderr)
        self.assert_original_profile_unchanged()

    def test_native_autoload_symlink_preserves_canonical_startup(self):
        canonical = self.home / '.local/share/nushell/vendor/autoload/starship.nu'
        canonical.parent.mkdir(parents=True)
        canonical.write_text('# existing working prompt\n')
        linked = self.home / 'AppData/Roaming/nushell/vendor'
        linked.parent.mkdir(parents=True)
        try:
            linked.symlink_to(self.original, target_is_directory=True)
        except OSError:
            self.skipTest('OS policy prohibits creating the test symlink')
        stage = self.home / '.cache/tmp/shell-stage'
        stage.mkdir(parents=True)
        script = self.root / 'prepare-native-symlink.ps1'
        script.write_text(r'''$ErrorActionPreference = 'Stop'
function Stop-Deployment([string]$Message) { throw $Message }
$TargetHome = $env:DOTFILES_TEST_TARGET_HOME
$roots = @{
    data = (Join-Path $TargetHome '.local/share')
    config = (Join-Path $TargetHome '.config')
    pixi = (Join-Path $TargetHome '.pixi')
    appData = (Join-Path $TargetHome 'AppData/Roaming')
}
. (Join-Path $env:DOTFILES_TEST_SOURCE 'deployment/windows.ps1')
$script:Pixi = 'controlled-pixi'
function Get-Scratch([string]$Name) { return $env:DOTFILES_TEST_STAGE }
function Invoke-Tool([string]$Executable, [string[]]$Arguments, [switch]$Quiet) {
    if ($Arguments.Count -and $Arguments[0].EndsWith('completions.py')) {
        [IO.File]::WriteAllText((Join-Path $env:DOTFILES_TEST_STAGE 'nu-scripts.nu'), '# prepared completions')
    }
    return '# validated generated resource'
}
Prepare-Shell
''')
        result = subprocess.run([POWERSHELL, '-NoProfile', '-NonInteractive', '-File', str(script)],
                                env=dict(self.env, DOTFILES_TEST_SOURCE=str(SOURCE),
                                         DOTFILES_TEST_TARGET_HOME=str(self.home), DOTFILES_TEST_STAGE=str(stage)),
                                check=False, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('symlink or reparse', result.stderr)
        self.assertEqual(canonical.read_text(), '# existing working prompt\n')
        self.assert_original_profile_unchanged()

    def test_requested_tool_failure_output_is_reported(self):
        command = self.root / ("diagnostic.cmd" if os.name == 'nt' else "diagnostic.sh")
        command.write_text("@echo off\r\necho synthetic version failure 1>&2\r\nexit /b 7\r\n" if os.name == 'nt'
                           else '#!/bin/sh\necho synthetic version failure >&2\nexit 7\n')
        command.chmod(0o755)
        script = self.root / "invoke-tool.ps1"
        script.write_text(r'''function Stop-Deployment([string]$Message) { throw $Message }
$TargetHome = $env:DOTFILES_TEST_TARGET_HOME
. (Join-Path $env:DOTFILES_TEST_SOURCE 'deployment/windows.ps1')
Invoke-Tool $env:DOTFILES_TEST_COMMAND @() -Quiet -ShowFailureOutput
''')
        environment = dict(self.env, DOTFILES_TEST_SOURCE=str(SOURCE),
                           DOTFILES_TEST_TARGET_HOME=str(self.home),
                           DOTFILES_TEST_COMMAND=str(command))
        result = subprocess.run([POWERSHELL, "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(script)],
                                cwd=SOURCE, env=environment, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("synthetic version failure", result.stdout + result.stderr)

    def test_native_plan_selects_role_and_default_owners_without_writes(self):
        result = self.deploy("-Plan", "-Profile", "windows-remote-compute", "-Arch", "x86_64")
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(plan["profile"], "windows-remote-compute")
        self.assertEqual(plan["mirror"], "tuna")
        self.assertEqual(plan["settings"]["primaryShell"], "nu")
        self.assertEqual(plan["settings"]["secondaryShells"], ["git-bash"])
        self.assertFalse(plan["settings"]["systemChanges"])
        self.assertFalse(plan["settings"]["loginShellChanges"])
        for tool in ("pixi", "bun", "atuin", "rtk", "nu", "uv", "zoxide", "tspin", "hx", "jq", "kimi", "pi", "opencode", "claude", "codex", "mcode", "qoder", "qodercli", "codegraph"):
            self.assertIn(tool, plan["tools"])
        packages = {item["environment"]: item for item in plan["packages"]}
        self.assertEqual(packages["rtk-cli"]["dependencies"], {"rtk-cli": "==" + common_pin("rtk-cli")})
        self.assertNotIn("zsh", packages)
        self.assertNotIn("bun", packages)
        self.assertEqual(plan["roots"]["appData"], str(self.home / "AppData/Roaming"))
        self.assertEqual(plan["roots"]["localAppData"], str(self.home / "AppData/Local"))
        self.assertFalse(self.home.exists())
        self.assert_original_profile_unchanged()

    def test_ordered_bootstrap_plan_preserves_legacy_actions(self):
        cases = (
            ((), ["install-common", "install-agents", "install-magpie-cli", "prepare-shell"],
             ["install-managers", "apply-source"], ["install-managers", "apply-source"]),
            (("-NoMagpie",), ["install-common", "install-agents", "prepare-shell"],
             ["install-managers", "apply-source"], ["install-managers", "apply-source"]),
            (("-ApplyOnly",), [], ["apply-source"], ["install-managers", "apply-source"]),
            (("-AgentsOnly",), ["install-agents"], ["apply-source"], ["install-managers", "apply-source"]),
        )
        for args, suffix, actions, steps in cases:
            with self.subTest(args=args):
                result = self.deploy("-Plan", *args, env=dict(self.env, DOTFILES_STEP_TRACE="1"))
                self.assertEqual(result.returncode, 0, result.stderr)
                plan = json.loads(result.stdout)
                self.assertEqual(plan["actions"], actions + suffix)
                self.assertEqual(plan["steps"], steps + suffix)
                self.assertNotIn(" started", result.stderr)
                self.assertFalse(self.home.exists())
        self.assert_original_profile_unchanged()

    def test_mirror_selection_is_planned_and_invalid_values_fail_before_writes(self):
        result = self.deploy('-Plan', env=dict(self.env, DOTFILES_MIRROR='upstream'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['mirror'], 'upstream')
        result = self.deploy('-ApplyOnly', env=dict(self.env, DOTFILES_MIRROR='invalid'))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DOTFILES_MIRROR', result.stderr)
        self.assertFalse(self.home.exists())

    def test_apply_only_copies_native_discovery_and_preserves_device_content(self):
        chezmoi = os.environ.get('DOTFILES_TEST_CHEZMOI') or shutil.which('chezmoi')
        if not chezmoi:
            self.skipTest('actual source apply needs Chezmoi')
        source = self.root / 'working source'
        shutil.copytree(SOURCE, source, ignore=shutil.ignore_patterns('.git', '__pycache__'))
        with (source / 'dot_env_core.tmpl').open('a') as handle:
            handle.write('\n# uncommitted-windows-source\n')
        settings = self.home / '.claude/settings.json'
        settings.parent.mkdir(parents=True)
        settings.write_text('{"deviceOnly":true,"permissions":{"allow":["Read(*)"]}}\n')
        instructions = self.home / '.codex/AGENTS.md'
        instructions.parent.mkdir()
        instructions.write_text('device instructions stay\n')
        retired = self.home / '.kimi-code/AGENTS.md'
        retired.parent.mkdir()
        retired.write_text('device kimi instructions\n\n<!-- DOTFILES_AGENT_START -->\nold managed text\n<!-- DOTFILES_AGENT_END -->\n')
        custom_skill = self.home / '.agents/skills/device-only/SKILL.md'
        custom_skill.parent.mkdir(parents=True)
        custom_skill.write_text('custom skill\n')
        registry = self.home / '.pixi/manifests/pixi-global.toml'
        registry.parent.mkdir(parents=True)
        registry.write_text('version = 1\n[envs.device]\ndependencies = { device = "==1.0" }\n')
        auth = self.home / '.codex/auth.json'
        auth.write_text('{"synthetic":"device-auth"}\n')
        history = self.home / '.local/share/atuin/history.db'
        history.parent.mkdir(parents=True)
        history.write_bytes(b'synthetic-existing-history')
        old_nu_history = self.home / '.config/nushell/history.txt'
        old_nu_history.parent.mkdir(parents=True)
        old_nu_history.write_text('synthetic-existing-xdg-history\n')
        native_nu_history = self.home / 'AppData/Roaming/nushell/history.txt'
        native_nu_history.parent.mkdir(parents=True)
        native_nu_history.write_text('synthetic-existing-native-history\n')
        environment = dict(self.env, DOTFILES_CHEZMOI_BIN=chezmoi, DOTFILES_STEP_TRACE='1',
                           GLM_API_TOKEN='synthetic-quote"\\\n$`', KIMI_API_KEY='synthetic-quote"\\\n$`')
        for role in ('remote-compute', 'workstation'):
            arguments = ('-ApplyOnly', '-Source', str(source), '-Role', role)
            planned = self.deploy('-Plan', *arguments, env=environment)
            self.assertEqual(planned.returncode, 0, planned.stderr)
            result = self.deploy(*arguments, env=environment)
            self.assertEqual(result.returncode, 0, result.stderr)
            observed = re.findall(r'^dotfiles: step ([a-z.-]+) started$', result.stderr, re.MULTILINE)
            self.assertEqual(observed, json.loads(planned.stdout)['steps'])
            self.assertIn('uncommitted-windows-source', (self.home / '.env_core').read_text())
            self.assertTrue(json.loads(settings.read_text())['deviceOnly'])
            self.assertNotIn('ANTHROPIC_AUTH_TOKEN', json.loads(settings.read_text())['env'])
            self.assertIn('device instructions stay', instructions.read_text())
            self.assertIn('## Native Windows specifics', instructions.read_text())
            self.assertEqual(retired.read_text(), 'device kimi instructions\n')
            self.assertEqual(custom_skill.read_text(), 'custom skill\n')
            assert_skill_copies(self, self.home, STATIC_LIBRARY,
                                ('show-me/SKILL.md', 'show-me/agents/openai.yaml'))
            self.assertEqual(auth.read_text(), '{"synthetic":"device-auth"}\n')
            self.assertEqual(history.read_bytes(), b'synthetic-existing-history')
            self.assertEqual(native_nu_history.read_text(), 'synthetic-existing-native-history\n')
            self.assertIn('[envs.device]', registry.read_text())
            native = self.home / 'AppData/Roaming'
            for relative in ('nushell/env.nu', 'nushell/config.nu', 'nushell/zoxide.nu', 'nushell/proxy.nu', 'uv/uv.toml', 'pip/pip.ini'):
                self.assertTrue((native / relative).is_file(), relative)
                self.assertFalse((native / relative).is_symlink(), relative)
            self.assertEqual((native / 'nushell/env.nu').read_bytes(), (self.home / '.config/nushell/env.nu').read_bytes())
            for relative in ('bootstrap.ps1', 'deployment', 'tests', '.github'):
                self.assertFalse((self.home / relative).exists(), relative)
            mcp = json.loads((self.home / '.claude.json').read_text())['mcpServers']['codegraph']
            self.assertEqual(mcp['command'], str(self.home / '.pixi/bin/node.exe'))
            self.assertEqual(mcp['args'][1:], ['serve', '--mcp'])
            self.assertEqual(Path(mcp['args'][0]).parts[-3:], ('@colbymchenry', 'codegraph', 'npm-shim.js'))
            self.assertEqual(json.loads((self.home / '.config/dotfiles/profile.json').read_text())['role'], role)
            # Role changes stop managing remote-only files without deleting
            # device content that was deployed by an earlier role.
            self.assertTrue((self.home / '.vscode-server/data/Machine/settings.json').exists())

    def test_plan_reports_verified_windows_exceptions_and_bundle_targets(self):
        result = self.deploy('-Plan', '-Agents', 'codex,kimi-code', '-Bundles', 'desktop')
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(plan['agents'], ['kimi', 'codex'])
        exceptions = {item['name']: item for item in plan['exceptions']}
        self.assertRegex(exceptions['bun']['sha256'], r'^[a-f0-9]{64}$')
        self.assertEqual(exceptions['atuin']['version'], windows_assets()['atuin']['version'])
        self.assertIn('git-bash', exceptions)
        for item in exceptions.values():
            self.assertTrue(item['url'].startswith('https://'))
            self.assertEqual(len(item['sha256']), 64)
        self.assertEqual(plan['bundles'], ['desktop'])
        self.assertIn('zed', plan['tools'])
        self.assertIn('firefox', plan['tools'])
        self.assertFalse(self.home.exists())

    def test_the_plan_reports_the_shared_magpie_pin_and_the_cli_slice(self):
        result = self.deploy("-Plan")
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        magpie = plan["magpie"]
        pin = magpie_releases()["windows-amd64"]
        # The shared catalog owns the version, the URL, and the digest.
        self.assertTrue(magpie["cli"])
        self.assertEqual(magpie["version"], pin["version"])
        self.assertEqual(magpie["target"], "windows-amd64")
        self.assertEqual(magpie["url"], pin["url"])
        self.assertEqual(magpie["sha256"], pin["sha256"])
        self.assertTrue(magpie["url"].startswith("https://"))
        self.assertRegex(magpie["sha256"], r"^[a-f0-9]{64}$")
        self.assertEqual(magpie["path"], ".local/share/dotfiles/magpie/bin/magpie.exe")
        # An installed CLI is not a wired gateway: the Windows boundary owns
        # neither the providers nor the clients, and the plan says so.
        self.assertFalse(magpie["gateway"])
        self.assertTrue(magpie["gatewayReason"])
        self.assertIn("install-magpie-cli", plan["actions"])
        self.assertLess(plan["actions"].index("install-magpie-cli"), plan["actions"].index("prepare-shell"))
        self.assertFalse(self.home.exists())

    def test_the_magpie_opt_out_removes_the_cli_slice_and_says_why(self):
        for arguments, environment in ((("-NoMagpie",), None), ((), {"DOTFILES_MAGPIE": "false"})):
            with self.subTest(arguments=arguments):
                result = self.deploy("-Plan", *arguments, env=dict(self.env, **(environment or {})))
                self.assertEqual(result.returncode, 0, result.stderr)
                plan = json.loads(result.stdout)
                self.assertFalse(plan["magpie"]["cli"])
                self.assertTrue(plan["magpie"]["reason"])
                self.assertNotIn("install-magpie-cli", plan["actions"])
                self.assertFalse(self.home.exists())

    def test_the_restricted_modes_skip_the_magpie_cli(self):
        for arguments, expected in ((("-ApplyOnly",), "apply-only"), (("-AgentsOnly",), "agents-only")):
            with self.subTest(arguments=arguments):
                result = self.deploy("-Plan", *arguments)
                self.assertEqual(result.returncode, 0, result.stderr)
                plan = json.loads(result.stdout)
                self.assertFalse(plan["magpie"]["cli"])
                self.assertIn(expected, plan["magpie"]["reason"])
                self.assertNotIn("install-magpie-cli", plan["actions"])
                self.assertFalse(self.home.exists())

    def magpie_fixture(self, digest=None, reported_version=None, exit_code=0, catalog_row=None):
        """A deployment source with a synthetic release catalog and payload."""
        source = Path(tempfile.mkdtemp(prefix="magpie-source-", dir=self.root))
        deployment = source / "deployment"
        (deployment / "magpie").mkdir(parents=True)
        shutil.copy2(SOURCE / "deployment/windows.ps1", deployment / "windows.ps1")
        version = magpie_releases()["windows-amd64"]["version"]
        if reported_version is None:
            reported_version = version
        payload = ('#!' + sys.executable + '\n'
                   'import sys\n'
                   'if sys.argv[1:] != ["--version"]:\n'
                   '    raise SystemExit("self-install/update must not run")\n'
                   f'print({reported_version!r})\n'
                   f'raise SystemExit({exit_code})\n').encode()
        archive = self.root / "magpie.exe"
        archive.write_bytes(payload)
        sha256 = hashlib.sha256(payload).hexdigest() if digest is None else digest
        if catalog_row is None:
            catalog_row = f"magpie|{version}|windows-amd64|https://example.invalid/magpie.exe|{sha256}"
        (source / "deployment/magpie/releases.tsv").write_text(
            "# name|version|target|url|sha256\n" + catalog_row + "\n", encoding="utf-8")
        temporary = self.home / ".cache/tmp"
        temporary.mkdir(parents=True, exist_ok=True)
        script = self.root / "magpie-install.ps1"
        script.write_text(r'''$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
function Stop-Deployment([string]$Message) { throw $Message }
$script:FailureCode = 1
$Source = $env:DOTFILES_TEST_SOURCE
$TargetHome = $env:DOTFILES_TEST_TARGET_HOME
$roots = @{
    data = (Join-Path $TargetHome '.local/share'); cache = (Join-Path $TargetHome '.cache')
    state = (Join-Path $TargetHome '.local/state'); config = (Join-Path $TargetHome '.config')
}
$exceptions = @()
. (Join-Path $env:DOTFILES_TEST_SOURCE 'deployment/windows.ps1')
function Invoke-WebRequest([string]$Uri, [string]$OutFile, [switch]$UseBasicParsing, [int]$TimeoutSec) {
    if ($env:DOTFILES_TEST_MAGPIE_DOWNLOAD -ne '1') { throw 'unexpected download' }
    if ($Uri -ne 'https://example.invalid/magpie.exe') { throw 'unexpected release URL' }
    [IO.File]::Copy($env:DOTFILES_TEST_MAGPIE_PAYLOAD, $OutFile)
}
# Execute the synthetic payload through Python on either host. The release
# reader, the digest check, and the install flow stay in place.
$script:FixtureInvokeTool = ${function:Invoke-Tool}
function Invoke-Tool([string]$Executable, [string]$Arguments, [switch]$Quiet) {
    & $script:FixtureInvokeTool $env:DOTFILES_TEST_PYTHON (@($Executable) + $Arguments) -Quiet:$Quiet
}
Install-MagpieCli
''')
        environment = dict(self.env, DOTFILES_TEST_SOURCE=str(source), DOTFILES_TEST_TARGET_HOME=str(self.home),
                           DOTFILES_TEST_PYTHON=sys.executable, DOTFILES_TEST_MAGPIE_PAYLOAD=str(archive),
                           DOTFILES_TEST_MAGPIE_DOWNLOAD='1', TEMP=str(temporary))
        return script, environment, payload

    def run_magpie_fixture(self, script, environment):
        return subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-File", str(script)],
                              env=environment, capture_output=True, text=True, timeout=60)

    def magpie_home_environment(self, environment, home):
        """Point the fixture and its scratch directory at an isolated home."""
        temporary = home / ".cache/tmp"
        temporary.mkdir(parents=True, exist_ok=True)
        return dict(environment, DOTFILES_TEST_TARGET_HOME=str(home), TEMP=str(temporary))

    def test_the_magpie_cli_install_verifies_the_digest_and_keeps_device_state(self):
        script, environment, payload = self.magpie_fixture()
        preserved = self.home / ".local/share/dotfiles/magpie/device-state.txt"
        preserved.parent.mkdir(parents=True, exist_ok=True)
        preserved.write_text("device state stays\n")
        result = self.run_magpie_fixture(script, environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        installed = self.home / ".local/share/dotfiles/magpie/bin/magpie.exe"
        self.assertEqual(installed.read_bytes(), payload)
        self.assertEqual((self.home / ".local/bin/magpie.cmd").read_bytes(), magpie_cmd_launcher_bytes())
        self.assertIn("magpie.exe", (self.home / ".local/share/dotfiles/magpie/bin/magpie").read_text())
        self.assertEqual(preserved.read_text(), "device state stays\n")
        self.assertEqual(list(Path(environment["TEMP"]).iterdir()), [])

    def test_a_cached_magpie_cli_is_reused_without_a_download(self):
        script, environment, payload = self.magpie_fixture()
        installed = self.home / ".local/share/dotfiles/magpie/bin/magpie.exe"
        installed.parent.mkdir(parents=True, exist_ok=True)
        installed.write_bytes(payload)
        result = self.run_magpie_fixture(script, dict(environment, DOTFILES_TEST_MAGPIE_DOWNLOAD='0'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(installed.read_bytes(), payload)
        self.assertTrue((self.home / ".local/bin/magpie.cmd").exists())

    def test_a_magpie_digest_mismatch_places_nothing(self):
        script, environment, _payload = self.magpie_fixture(digest="0" * 64)
        result = self.run_magpie_fixture(script, environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SHA-256 mismatch", result.stderr)
        self.assertFalse((self.home / ".local/share/dotfiles/magpie/bin/magpie.exe").exists())
        self.assertFalse((self.home / ".local/bin/magpie.cmd").exists())
        self.assertEqual(list(Path(environment["TEMP"]).iterdir()), [])

    def test_a_magpie_release_that_reports_another_version_is_not_placed(self):
        script, environment, _payload = self.magpie_fixture(reported_version="0.0.0")
        result = self.run_magpie_fixture(script, environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("did not report its pinned version", result.stderr)
        self.assertFalse((self.home / ".local/share/dotfiles/magpie/bin/magpie.exe").exists())
        self.assertEqual(list(Path(environment["TEMP"]).iterdir()), [])

    def test_a_magpie_release_with_a_nonexact_version_token_is_not_placed(self):
        version = magpie_releases()["windows-amd64"]["version"]
        for reported in (version + "0", version + "-rc1", version + "+build", "x" + version):
            with self.subTest(reported=reported):
                script, environment, _payload = self.magpie_fixture(reported_version=reported)
                result = self.run_magpie_fixture(script, environment)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("did not report its pinned version", result.stderr)
                self.assertFalse((self.home / ".local/share/dotfiles/magpie/bin/magpie.exe").exists())

    def test_the_magpie_catalog_must_carry_https_and_a_digest(self):
        version = magpie_releases()["windows-amd64"]["version"]
        cases = ((f"magpie|{version}|windows-amd64|http://example.invalid/magpie.exe|{'0' * 64}", "HTTPS"),
                 (f"magpie|{version}|windows-amd64|https://example.invalid/magpie.exe|not-a-digest", "SHA-256"),
                 (f"magpie|{version}|windows-arm64|https://example.invalid/magpie.exe|{'0' * 64}", "windows-amd64"))
        for row, expected in cases:
            with self.subTest(row=row):
                script, environment, _payload = self.magpie_fixture(catalog_row=row)
                result = self.run_magpie_fixture(script, environment)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)
                self.assertFalse((self.home / ".local/share/dotfiles/magpie/bin/magpie.exe").exists())
                self.assertEqual(list(Path(environment["TEMP"]).iterdir()), [])

    def test_a_cached_magpie_cli_with_a_mismatched_digest_is_preserved_and_not_executed(self):
        script, environment, _payload = self.magpie_fixture()
        version = magpie_releases()["windows-amd64"]["version"]
        marker = self.root / "mismatched-cli-was-executed"
        # A device binary that reports the pinned version is still not the
        # pinned bytes. Running it would create the marker; deploying must not.
        device_binary = ("#!" + sys.executable + "\n"
                         "import pathlib\n"
                         f"pathlib.Path({str(marker)!r}).write_text('executed')\n"
                         f"print({version!r})\n").encode()
        cli = self.home / ".local/share/dotfiles/magpie/bin/magpie.exe"
        cli.parent.mkdir(parents=True, exist_ok=True)
        cli.write_bytes(device_binary)
        result = self.run_magpie_fixture(script, dict(environment, DOTFILES_TEST_MAGPIE_DOWNLOAD='1'))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match the pinned Magpie SHA-256", result.stderr)
        self.assertEqual(cli.read_bytes(), device_binary)
        self.assertFalse(marker.exists(), "an unverified cached binary was executed")
        self.assertFalse((self.home / ".local/bin/magpie.cmd").exists())
        self.assertFalse((self.home / ".local/share/dotfiles/magpie/bin/magpie").exists())
        self.assertEqual(list(Path(environment["TEMP"]).iterdir()), [])

    def test_identical_magpie_launchers_are_adopted_and_repeated_runs_are_idempotent(self):
        script, environment, _payload = self.magpie_fixture()
        first = self.run_magpie_fixture(script, environment)
        self.assertEqual(first.returncode, 0, first.stderr)
        paths = (self.home / ".local/bin/magpie.cmd",
                 self.home / ".local/share/dotfiles/magpie/bin/magpie",
                 self.home / ".local/share/dotfiles/magpie/bin/magpie.exe")
        before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths}
        second = self.run_magpie_fixture(script, dict(environment, DOTFILES_TEST_MAGPIE_DOWNLOAD='0'))
        self.assertEqual(second.returncode, 0, second.stderr)
        for path, state in before.items():
            self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), state, path)

    def test_conflicting_magpie_launchers_are_preserved_and_block_the_install(self):
        cases = (
            (".local/bin/magpie.cmd", b"@echo off\r\ndevice launcher\r\n",
             ".local/share/dotfiles/magpie/bin/magpie"),
            (".local/share/dotfiles/magpie/bin/magpie", b"#!/bin/sh\ndevice companion\n",
             ".local/bin/magpie.cmd"),
        )
        for index, (relative, content, companion) in enumerate(cases):
            with self.subTest(conflict=relative):
                home = self.root / f"launcher-conflict-{index}"
                script, environment, _payload = self.magpie_fixture()
                environment = self.magpie_home_environment(environment, home)
                conflict = home / relative
                conflict.parent.mkdir(parents=True, exist_ok=True)
                conflict.write_bytes(content)
                result = self.run_magpie_fixture(script, dict(environment, DOTFILES_TEST_MAGPIE_DOWNLOAD='1'))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Magpie launcher", result.stderr)
                self.assertEqual(conflict.read_bytes(), content)
                self.assertFalse((home / companion).exists(), "mutated the other launcher on conflict")
                self.assertFalse((home / ".local/share/dotfiles/magpie/bin/magpie.exe").exists())
                self.assertEqual(list(Path(environment["TEMP"]).iterdir()), [])

    def test_a_symlinked_magpie_launcher_is_refused_without_writing_through(self):
        sentinel = self.original / "device-launcher"
        sentinel.write_bytes(b"device launcher\n")
        home = self.root / "magpie-symlink-device"
        link = home / ".local/bin/magpie.cmd"
        link.parent.mkdir(parents=True)
        try:
            link.symlink_to(sentinel)
        except OSError:
            self.skipTest('OS policy prohibits creating the test symlink')
        script, environment, _payload = self.magpie_fixture()
        environment = self.magpie_home_environment(environment, home)
        result = self.run_magpie_fixture(script, environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlink", result.stderr)
        self.assertTrue(link.is_symlink())
        self.assertEqual(sentinel.read_bytes(), b"device launcher\n")
        self.assertFalse((home / ".local/share/dotfiles/magpie/bin/magpie.exe").exists())
        self.assertEqual(list(Path(environment["TEMP"]).iterdir()), [])

    def test_the_magpie_cmd_launcher_ignores_percent_signs_in_the_home(self):
        # The launcher must not embed a home path, so a literal % in HOME cannot
        # become cmd.exe variable expansion. It is identical for every home.
        home = self.root / "device %MAGPIE% with spaces"
        script, environment, _payload = self.magpie_fixture()
        environment = self.magpie_home_environment(environment, home)
        result = self.run_magpie_fixture(script, environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        cmd = (home / ".local/bin/magpie.cmd").read_bytes()
        self.assertEqual(cmd, magpie_cmd_launcher_bytes())
        self.assertNotIn(str(home).encode(), cmd)
        self.assertNotIn(str(home / ".local/share/dotfiles/magpie/bin/magpie.exe").encode(), cmd)
        self.assertNotIn(b"%%", cmd)
        self.assertEqual((home / ".local/share/dotfiles/magpie/bin/magpie").read_text(),
                         '#!/bin/sh\nexec "$(dirname -- "$0")/magpie.exe" "$@"\n')

    def test_the_magpie_cmd_launcher_ignores_exclamation_marks_in_the_home(self):
        # cmd.exe expands a literal ! when delayed expansion is on. A literal !
        # in HOME can no longer reach the launcher, which stays byte-identical
        # and keeps delayed expansion disabled. This reads the generated bytes
        # only; no .cmd command execution is validated here.
        home = self.root / "device !MAGPIE! with spaces"
        script, environment, _payload = self.magpie_fixture()
        environment = self.magpie_home_environment(environment, home)
        result = self.run_magpie_fixture(script, environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        cmd = (home / ".local/bin/magpie.cmd").read_bytes()
        self.assertEqual(cmd, magpie_cmd_launcher_bytes())
        self.assertNotIn(b"!", cmd)
        self.assertNotIn(str(home).encode(), cmd)

    def test_the_magpie_cmd_launcher_is_ascii_for_a_non_ascii_home(self):
        # cmd.exe may decode a batch file with a legacy code page: embedded
        # UTF-8 home names get corrupted. The launcher references the binary
        # through %~dp0 instead, so its own bytes stay pure ASCII.
        home = self.root / "casa Única 日本語"
        script, environment, _payload = self.magpie_fixture()
        environment = self.magpie_home_environment(environment, home)
        result = self.run_magpie_fixture(script, environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        cmd = (home / ".local/bin/magpie.cmd").read_bytes()
        self.assertEqual(cmd, magpie_cmd_launcher_bytes())
        cmd.decode("ascii")  # the launcher bytes never encode the home name
        self.assertNotIn(str(home).encode("utf-8"), cmd)

    def test_opt_out_and_restricted_plans_do_not_need_the_magpie_catalog(self):
        source = self.root / "source without magpie catalog"
        # Copy only the public files a PowerShell plan reads from $Source. A
        # whole-tree copy would also stage ignored/untracked credential files
        # in this temporary deployment source.
        required = [
            ".chezmoi.toml.tmpl",                 # source-tree validation
            "deployment/windows.ps1",             # dot-sourced plan helpers
            "deployment/bundles.tsv",             # Get-Bundles
            "deployment/bundle-tools.tsv",        # Get-BundlePackages
            "deployment/common-tools.tsv",        # Get-Packages
            "deployment/windows-assets.json",     # exception records
            "deployment/agents/providers.tsv",    # agent provider catalog
            "deployment/agents/herdr-kinds.tsv",  # Herdr kind catalog
        ]
        # Bun locks are declared by the provider catalog itself. Only bun
        # records carry a lock path; a native record's column holds a URL.
        catalog = (SOURCE / "deployment/agents/providers.tsv").read_text(encoding="utf-8")
        for line in catalog.splitlines():
            if line and not line.startswith("#"):
                fields = line.split("|")
                if fields[1] == "bun":
                    required.append(fields[13])
        root = SOURCE.resolve()
        for relative in required:
            declared = Path(relative)
            self.assertFalse(declared.is_absolute(), relative)
            original = (root / declared).resolve()
            original.relative_to(root)  # a declared lock must stay in the source
            self.assertTrue(original.is_file(), relative)
            destination = source / declared
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, destination)
        copied = {path.relative_to(source).as_posix() for path in source.rglob("*") if path.is_file()}
        self.assertEqual(copied, set(required))
        # The Magpie release catalog is never copied: an opted-out or
        # restricted plan must not read it, and a full plan must fail on it.
        self.assertFalse((source / "deployment/magpie/releases.tsv").exists())
        for arguments, environment in (
            (("-NoMagpie",), None),
            ((), {"DOTFILES_MAGPIE": "false"}),
            (("-ApplyOnly",), None),
            (("-AgentsOnly",), None),
        ):
            with self.subTest(arguments=arguments, environment=environment):
                result = self.deploy("-Plan", *arguments, "-Source", str(source),
                                     env=dict(self.env, **(environment or {})))
                self.assertEqual(result.returncode, 0, result.stderr)
                plan = json.loads(result.stdout)
                self.assertFalse(plan["magpie"]["cli"])
                self.assertIsNone(plan["magpie"]["version"])
                self.assertNotIn("install-magpie-cli", plan["actions"])
        # A full plan still requires the one catalog the adapter owns.
        result = self.deploy("-Plan", "-Source", str(source))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Magpie release catalog", result.stderr)

    def test_opt_out_preflight_ignores_magpie_only_symlinks_without_weakening_other_guards(self):
        script = self.root / "magpie-preflight.ps1"
        script.write_text(r'''$ErrorActionPreference = 'Stop'
function Stop-Deployment([string]$Message) { throw $Message }
$TargetHome = $env:DOTFILES_TEST_TARGET_HOME
$Source = $env:DOTFILES_TEST_SOURCE
$roots = @{ appData = (Join-Path $TargetHome 'AppData/Roaming') }
$exceptions = @()
function Read-Catalog([string]$Relative) {
    foreach ($line in [IO.File]::ReadAllLines((Join-Path $Source $Relative))) {
        if ($line -and -not $line.StartsWith('#')) { @{ columns = $line.Split('|') } }
    }
}
. (Join-Path $Source 'deployment/windows.ps1')
if ($env:DOTFILES_TEST_MAGPIE_ENABLED -eq '0') { Assert-OwnedState -MagpieEnabled:$false }
else { Assert-OwnedState }
''')
        sentinel = self.original / "device-launcher"
        sentinel.write_bytes(b"device launcher\n")
        home = self.root / "magpie-preflight-device"
        for relative, target, directory in (
            (".local/share/dotfiles/magpie", self.original, True),
            (".local/bin/magpie.cmd", sentinel, False),
        ):
            link = home / relative
            link.parent.mkdir(parents=True, exist_ok=True)
            try:
                link.symlink_to(target, target_is_directory=directory)
            except OSError:
                self.skipTest('OS policy prohibits creating the test symlink')
        environment = dict(self.env, DOTFILES_TEST_SOURCE=str(SOURCE), DOTFILES_TEST_TARGET_HOME=str(home))
        skipped = self.run_magpie_fixture(script, dict(environment, DOTFILES_TEST_MAGPIE_ENABLED='0'))
        self.assertEqual(skipped.returncode, 0, skipped.stderr)
        guarded = self.run_magpie_fixture(script, dict(environment, DOTFILES_TEST_MAGPIE_ENABLED='1'))
        self.assertNotEqual(guarded.returncode, 0)
        self.assertIn("symlink or reparse", guarded.stderr)
        self.assertEqual(sentinel.read_bytes(), b"device launcher\n")
        self.assertEqual(sorted(path.name for path in self.original.iterdir()), ["device-launcher"])

    def test_normal_nu_startup_loads_the_rendered_environment_without_config_flags(self):
        tool_home = os.environ.get('DOTFILES_TEST_TOOL_HOME')
        chezmoi = os.environ.get('DOTFILES_TEST_CHEZMOI') or shutil.which('chezmoi')
        if not tool_home or not chezmoi:
            self.skipTest('normal startup requires the actual pinned Nu and renderer')
        executable = Path(tool_home) / '.pixi/envs/nushell/bin/nu'
        if not executable.is_file():
            self.skipTest('this local regression borrows the pinned Linux Nu executable')
        applied = self.deploy('-ApplyOnly', env=dict(self.env, DOTFILES_CHEZMOI_BIN=chezmoi))
        self.assertEqual(applied.returncode, 0, applied.stderr)
        environment = dict(self.env, HOME=str(self.home), USERPROFILE=str(self.home),
                           XDG_CONFIG_HOME=str(self.home / '.config'), XDG_DATA_HOME=str(self.home / '.local/share'),
                           APPDATA=str(self.home / 'AppData/Roaming'), PATH='/usr/bin:/bin')
        for name in ('EDITOR', 'UV_PYTHON_PREFERENCE'):
            environment.pop(name, None)
        from fixtures.windows_shell import ordinary_nu_settings
        result = ordinary_nu_settings(executable, environment)
        self.assertEqual(result.returncode, 0, result.stderr)
        values = json.loads(result.stdout)
        self.assertEqual(Path(values[0]), self.home / '.config/nushell')
        self.assertEqual(values[1:], ['hx', 'managed'])

    def test_invalid_selections_fail_before_mutation(self):
        for args in (('-Plan', '-Arch', 'arm64'), ('-Plan', '-Bundles', 'bio'),
                     ('-Plan', '-Profile', 'windows-workstation', '-Role', 'remote-compute'),
                     ('-Plan', '-Agents', 'unknown'), ('-ApplyOnly', '-AgentsOnly')):
            with self.subTest(args=args):
                result = self.deploy(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.home.exists())

    def test_native_installer_directory_rejects_nested_reparse_paths_before_application(self):
        chezmoi = os.environ.get('DOTFILES_TEST_CHEZMOI') or shutil.which('chezmoi')
        if not chezmoi:
            self.skipTest('actual source preservation requires Chezmoi')
        target = self.home / '.local/share/dotfiles/git-bash/bin'
        target.parent.mkdir(parents=True)
        try:
            target.symlink_to(self.original, target_is_directory=True)
        except OSError:
            self.skipTest('OS policy prohibits creating the test symlink')
        result = self.deploy('-ApplyOnly', env=dict(self.env, DOTFILES_CHEZMOI_BIN=chezmoi))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('symlink or reparse', result.stderr)
        self.assert_original_profile_unchanged()
        self.assertFalse((self.home / '.config').exists())

    def test_unchanged_codex_hooks_keep_exact_bytes_and_modification_time(self):
        chezmoi = os.environ.get('DOTFILES_TEST_CHEZMOI') or shutil.which('chezmoi')
        if not chezmoi:
            self.skipTest('actual hook preservation requires Chezmoi')
        hooks = self.home / '.codex/hooks.json'
        hooks.parent.mkdir(parents=True)
        fixtures = (
            b'{"hooks":{}}',
            '{\r\n\t"device": "caf\u00e9 \u4fdd\u7559",\r\n\t"hooks": {"Stop": []}\r\n}\r\n'.encode('utf-8'),
            b'{\n  // device formatting survives\n  "hooks": {"PreToolUse": []}\n}\n\n',
        )
        for original in fixtures:
            with self.subTest(original=original):
                hooks.write_bytes(original)
                os.utime(hooks, ns=(1_700_000_000_123_456_789, 1_700_000_000_123_456_789))
                modified = hooks.stat().st_mtime_ns
                result = self.deploy('-ApplyOnly', env=dict(self.env, DOTFILES_CHEZMOI_BIN=chezmoi))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(hooks.read_bytes(), original)
                self.assertEqual(hooks.stat().st_mtime_ns, modified)

    def test_codex_hook_migration_deploys_changes_then_preserves_result(self):
        chezmoi = os.environ.get('DOTFILES_TEST_CHEZMOI') or shutil.which('chezmoi')
        if not chezmoi:
            self.skipTest('actual hook migration requires Chezmoi')
        hooks = self.home / '.codex/hooks.json'
        hooks.parent.mkdir(parents=True)
        device = {'type': 'command', 'command': 'device-policy', 'timeout': 5}
        original = {'hooks': {'PreToolUse': [
            {'matcher': 'Bash', 'hooks': [{'type': 'command', 'command': 'rtk hook claude'}]},
            {'matcher': 'Bash', 'hooks': [device]},
        ]}}
        hooks.write_text(json.dumps(original), encoding='utf-8')
        result = self.deploy('-ApplyOnly', env=dict(self.env, DOTFILES_CHEZMOI_BIN=chezmoi))
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = {'hooks': {'PreToolUse': [
            {'matcher': 'Bash', 'hooks': [{'type': 'command', 'command': 'exit 0'}]},
            {'matcher': 'Bash', 'hooks': [device]},
        ]}}
        self.assertEqual(json.loads(hooks.read_bytes()), expected)
        migrated = hooks.read_bytes()
        os.utime(hooks, ns=(1_700_000_000_123_456_789, 1_700_000_000_123_456_789))
        modified = hooks.stat().st_mtime_ns
        result = self.deploy('-ApplyOnly', env=dict(self.env, DOTFILES_CHEZMOI_BIN=chezmoi))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(hooks.read_bytes(), migrated)
        self.assertEqual(hooks.stat().st_mtime_ns, modified)

    def test_invalid_client_syntax_preserves_every_client_and_hides_values(self):
        chezmoi = os.environ.get('DOTFILES_TEST_CHEZMOI') or shutil.which('chezmoi')
        if not chezmoi:
            self.skipTest('actual client preservation requires Chezmoi')
        claude = self.home / '.claude/settings.json'
        claude.parent.mkdir(parents=True)
        claude.write_text('{"deviceOnly":true}\n')
        kimi = self.home / '.kimi-code/config.toml'
        kimi.parent.mkdir()
        kimi.write_text('password = "synthetic-private-parser-value\n')
        hooks = self.home / '.codex/hooks.json'
        hooks.parent.mkdir()
        hooks.write_text('{"hooks":{"PreToolUse":[{"hooks":[{"type":"command","command":"rtk hook claude"}]}]}}\n')
        managed_paths = set()
        for row in (SOURCE / 'deployment/client-settings/targets.tsv').read_text().splitlines():
            if row and not row.startswith('#'):
                _, _, target, policy = row.split('|')
                managed_paths.add(self.home / target)
                managed_paths.add(self.home / f'.local/state/dotfiles/client-settings/{policy}.json')

        def snapshot():
            return {path: (path.read_bytes(), path.stat().st_mtime_ns) if path.exists() else None
                    for path in managed_paths}

        before = snapshot()
        result = self.deploy('-ApplyOnly', env=dict(self.env, DOTFILES_CHEZMOI_BIN=chezmoi))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('.kimi-code/config.toml', result.stderr)
        self.assertNotIn('synthetic-private-parser-value', result.stderr + result.stdout)
        self.assertEqual(snapshot(), before)


class WindowsMagpieCatalogTests(unittest.TestCase):
    """The shared release catalog is the only owner of the Magpie pin.

    These checks need no PowerShell: they read the catalog and the two
    Windows entry points. They do not claim that the Windows installation
    runs; the native gate owns that evidence.
    """

    def test_the_shared_catalog_pins_one_version_for_every_target(self):
        rows = magpie_releases()
        self.assertEqual(set(rows), {"linux-amd64", "linux-arm64", "macos-amd64", "macos-arm64",
                                     "windows-amd64", "windows-arm64"})
        self.assertEqual(len({row["version"] for row in rows.values()}), 1)
        for target, row in rows.items():
            with self.subTest(target=target):
                self.assertEqual(row["name"], "magpie")
                self.assertTrue(row["url"].startswith("https://"))
                self.assertRegex(row["sha256"], r"^[a-f0-9]{64}$")

    def test_the_windows_entry_points_read_the_shared_catalog(self):
        windows = (SOURCE / "deployment/windows.ps1").read_text(encoding="utf-8")
        bootstrap = (SOURCE / "bootstrap.ps1").read_text(encoding="utf-8")
        # The adapter reads the shared catalog and the one Windows target.
        self.assertIn("deployment/magpie/releases.tsv", windows)
        self.assertIn("windows-amd64", windows)
        target_list = re.search(r"\$target -notin @\(([^)]*)\)", windows)
        self.assertIsNotNone(target_list)
        self.assertEqual(set(re.findall(r"'([^']+)'", target_list.group(1))), set(magpie_releases()))
        # The entry point asks the adapter for the pin instead of naming a
        # release URL or a digest of its own.
        self.assertIn("Get-MagpiePin", bootstrap)
        for name, text in (("bootstrap.ps1", bootstrap), ("deployment/windows.ps1", windows)):
            with self.subTest(source=name):
                self.assertNotIn("magpie-cli-windows", text)
                self.assertNotIn("github.com/yetone/magpie", text)

    def test_the_windows_document_names_the_slice_and_its_limits(self):
        document = (SOURCE / "docs/WINDOWS_DEPLOYMENT.md").read_text(encoding="utf-8")
        self.assertIn("deployment/magpie/releases.tsv", document)
        self.assertIn("-NoMagpie", document)
        # The document separates the installed CLI from the gateway wiring.
        self.assertIn("magpie.exe", document)
        self.assertIn("does not wire", document)


class WindowsMagpieVersionTests(unittest.TestCase):
    """The Windows version check must accept only the pinned whole token.

    These checks need no PowerShell: they read the pattern Test-MagpieVersion
    builds and apply it with Python's regex engine, which shares the relevant
    syntax with .NET. They do not claim the PowerShell runtime ran; the native
    gate owns that evidence.
    """

    def version_regex(self):
        windows = (SOURCE / "deployment/windows.ps1").read_text(encoding="utf-8")
        match = re.search(
            r"\$pattern\s*=\s*'([^']*)'\s*\+\s*\[regex\]::Escape\(\$Version\)\s*\+\s*'([^']*)'",
            windows,
        )
        self.assertIsNotNone(match, "Test-MagpieVersion must escape the pin into a version pattern")
        prefix, suffix = match.groups()
        pin = magpie_releases()["windows-amd64"]["version"]
        return re.compile(prefix + re.escape(pin) + suffix)

    def test_only_the_exact_whitespace_token_is_accepted(self):
        pin = magpie_releases()["windows-amd64"]["version"]
        regex = self.version_regex()
        cases = (
            (pin, True),                              # exact
            (f"magpie {pin}", True),                  # exact after a tool name
            (f"magpie {pin} (commit abc123)", True),  # exact with trailing metadata
            (f"\t{pin}\t", True),                     # exact between other whitespace
            (f"{pin}0", False),                       # longer version
            (f"{pin}1", False),                       # longer version
            (f"{pin}-rc1", False),                    # prerelease
            (f"{pin}+build", False),                  # build suffix
            (f"x{pin}", False),                       # prefixed token
            (f"magpie x{pin}", False),                # prefixed token after a tool name
            (f"magpie {pin}0", False),                # longer version after a tool name
            (f"other {pin}-rc1", False),              # prerelease with leading text
            ("0.0.0", False),                         # another version
        )
        for reported, accepted in cases:
            with self.subTest(reported=reported, accepted=accepted):
                self.assertEqual(bool(regex.search(reported)), accepted)

    def test_the_windows_token_check_agrees_with_the_unix_adapter(self):
        # magpie.sh normalizes tabs/newlines to spaces, then requires the pin
        # between spaces: case " $reported " in *" $want "*.
        pin = magpie_releases()["windows-amd64"]["version"]
        regex = self.version_regex()
        cases = (pin, f"magpie {pin}", f"\t{pin}\t", f"{pin}0", f"{pin}-rc1",
                 f"{pin}+build", f"x{pin}", f"other {pin}+build", "0.0.0")
        for reported in cases:
            with self.subTest(reported=reported):
                normalized = reported.replace("\t", " ").replace("\n", " ")
                unix_match = f" {pin} " in f" {normalized} "
                self.assertEqual(bool(regex.search(reported)), unix_match)


class WindowsMagpieSafetyTests(unittest.TestCase):
    """Static checks for the Windows Magpie safety gates.

    These need no PowerShell. They read the two entry points and the document;
    the behavior tests in WindowsBoundaryTests run the same gates under the
    public PowerShell fixture. Neither claims native Windows acceptance.
    """

    def sources(self):
        return ((SOURCE / "bootstrap.ps1").read_text(encoding="utf-8"),
                (SOURCE / "deployment/windows.ps1").read_text(encoding="utf-8"))

    def test_a_cached_binary_is_hashed_before_it_is_executed(self):
        _bootstrap, windows = self.sources()
        digest = windows.index("install-magpie-cli.cached-digest")
        version = windows.index("install-magpie-cli.cached-version")
        self.assertLess(digest, version)
        self.assertIn("does not match the pinned Magpie SHA-256", windows)
        self.assertIn("preserved it unchanged", windows)

    def test_launchers_are_adopted_identically_and_conflicts_fail_before_mutation(self):
        _bootstrap, windows = self.sources()
        self.assertIn('"%~dp0', windows)
        self.assertIn("Test-MagpieLauncher", windows)
        self.assertIn("is not the managed launcher", windows)
        self.assertIn("move it aside before applying", windows)
        self.assertLess(windows.index("Test-MagpieLauncher"), windows.index("install-magpie-cli.download"))

    def test_the_cmd_launcher_disables_delayed_expansion_like_the_bun_launchers(self):
        # Reads the source only. It does not run PowerShell or cmd.exe and does
        # not claim that command execution was validated. The public PowerShell
        # fixture owns the generated-byte assertion for a home containing !.
        _bootstrap, windows = self.sources()
        directive = '@echo off`r`nsetlocal DisableDelayedExpansion`r`n'
        self.assertIn(directive, windows, "the Bun launchers must disable delayed expansion")
        body = windows.split("function Get-MagpieCmdLauncher", 1)[1]
        body = body.split("function Get-MagpiePosixLauncher", 1)[0]
        self.assertIn(directive, body, "the Magpie .cmd must disable delayed expansion too")
        # Argument forwarding and exit-code propagation are unchanged.
        self.assertIn('" %*', body)
        self.assertIn("exit /b %errorlevel%", body)

    def test_the_cmd_launcher_resolves_the_binary_relatively_and_stays_ascii(self):
        # Non-PowerShell assertion: the launcher is built from %~dp0 plus a
        # fixed ASCII suffix, never from the (possibly non-ASCII) home path.
        _bootstrap, windows = self.sources()
        body = windows.split("function Get-MagpieCmdLauncher", 1)[1]
        body = body.split("function Get-MagpiePosixLauncher", 1)[0]
        self.assertIn("%~dp0", body)
        self.assertIn(r"..\share\dotfiles\magpie\bin\magpie.exe", body)
        self.assertNotIn("$Cli", body, "the launcher must not embed a home path")
        self.assertNotIn("Replace('%', '%%')", body, "no home literal needs percent escaping")
        self.assertNotIn("TargetHome", body)
        relative = re.search(r"\$relative = '([^']+)'", body)
        self.assertIsNotNone(relative, "the launcher must define a fixed ASCII relative suffix")
        target = ('"%~dp0' + relative.group(1) + '" %*').encode("ascii")
        self.assertIn(target, magpie_cmd_launcher_bytes())

    def test_opt_out_gates_the_catalog_and_the_magpie_path_guards(self):
        bootstrap, windows = self.sources()
        self.assertIn("if ($magpie.enabled) { $magpiePin = Get-MagpiePin }", bootstrap)
        self.assertIn("Assert-OwnedState -MagpieEnabled $magpie.enabled", bootstrap)
        self.assertIn("param([bool]$MagpieEnabled = $true)", windows)
        self.assertIn("if ($MagpieEnabled) {", windows)
        self.assertIn("'.local/bin/magpie.cmd'", windows)

    def test_the_document_records_the_safety_boundary(self):
        document = (SOURCE / "docs/WINDOWS_DEPLOYMENT.md").read_text(encoding="utf-8")
        for phrase in ("is hashed before it is", "preserved unchanged", "percent characters",
                       "adopted without a rewrite", "read no Magpie release catalog"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, document)


@unittest.skipUnless(os.name == 'nt' and os.environ.get('DOTFILES_TEST_NATIVE_WINDOWS_INSTALL') == '1',
                     'actual Windows installation runs on the native runner')
class WindowsNativeInstallTests(unittest.TestCase):
    setUp = WindowsBoundaryTests.setUp
    original_profile_entries = WindowsBoundaryTests.original_profile_entries
    assert_original_profile_unchanged = WindowsBoundaryTests.assert_original_profile_unchanged
    def deploy(self, *arguments, env=None):
        return subprocess.run([POWERSHELL, '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                               '-File', str(SOURCE / 'bootstrap.ps1'), '-TargetHome', str(self.home), *arguments],
                              cwd=SOURCE, env=env or self.env, capture_output=True, text=True, timeout=2400)

    def assert_bundle_exposures(self, bundles, environment):
        """Check a selected bundle's Windows-supported tools on the native runtime.

        The Linux bundle evidence runs the same diagnostic shape; this establishes
        it on native Windows instead of inferring it from package metadata.
        """
        selected = {name for name in bundles if name}
        commands = set()
        for line in (SOURCE / 'deployment/bundle-tools.tsv').read_text(encoding='utf-8').splitlines():
            if not line or line.startswith('#'):
                continue
            bundle, _environment, _specifications, exposures, _channels, platforms = line.split('|')
            if bundle not in selected or (platforms != 'all' and 'windows' not in platforms.split(',')):
                continue
            for exposure in exposures.split(','):
                commands.add(exposure.split('=', 1)[0])
        self.assertTrue(commands, 'no Windows-supported tool matched the selected bundle')
        for command in sorted(commands):
            location = self.home / '.pixi/bin' / (command + '.exe')
            with self.subTest(bundle=command):
                self.assertTrue(location.is_file() and not location.is_symlink(),
                                f'managed bundle exposure: {location}')
                self.assert_runs_harmless_diagnostic(location, command, environment)

    def assert_runs_harmless_diagnostic(self, location, command, environment):
        """Accept the first harmless diagnostic the exposed bundle command runs.

        `--version` is the recorded evidence where it works. A GUI entry point can
        refuse it without a graphical session, and bundles.tsv declares that
        session a host prerequisite this deployment never provisions, so `--help`
        is the fallback, matching the harmless `--help` diagnostic used elsewhere.
        """
        for arguments in (['--version'], ['--help']):
            diagnostic = subprocess.run([str(location), *arguments], env=environment,
                                        capture_output=True, text=True, timeout=180)
            if diagnostic.returncode == 0:
                return arguments[0]
        self.fail(f'bundle command is exposed but runs no harmless diagnostic: {command}')

    def test_default_install_reapply_and_native_diagnostics(self):
        role = os.environ.get('DOTFILES_TEST_WINDOWS_ROLE', 'workstation')
        self.env['DOTFILES_ROLE'] = role
        bundles = [name for name in os.environ.get('DOTFILES_TEST_WINDOWS_BUNDLES', '').split(',') if name]
        selection = ('-Bundles', ','.join(bundles)) if bundles else ()
        arguments = ('-Role', role, *selection)
        traced = dict(self.env, DOTFILES_STEP_TRACE='1')
        planned = self.deploy('-Plan', *arguments, env=traced)
        self.assertEqual(planned.returncode, 0, planned.stderr)
        self.assertFalse(self.home.exists())
        result = self.deploy(*arguments, env=traced)
        self.assertEqual(result.returncode, 0, result.stderr)
        observed = re.findall(r'^dotfiles: step ([a-z.-]+) started$', result.stderr, re.MULTILINE)
        self.assertEqual(observed, json.loads(planned.stdout)['steps'])
        self.assertIn('sync pending activation', result.stdout)
        environment = self.env.copy()
        environment.update(HOME=str(self.home), USERPROFILE=str(self.home), APPDATA=str(self.home / 'AppData/Roaming'),
                           LOCALAPPDATA=str(self.home / 'AppData/Local'), XDG_CONFIG_HOME=str(self.home / '.config'),
                           XDG_DATA_HOME=str(self.home / '.local/share'), XDG_STATE_HOME=str(self.home / '.local/state'),
                           XDG_CACHE_HOME=str(self.home / '.cache'), PIXI_HOME=str(self.home / '.pixi'),
                           ATUIN_CONFIG_DIR=str(self.home / '.config/atuin'), ATUIN_DATA_DIR=str(self.home / '.local/share/atuin'),
                           KIMI_SHELL_PATH=str(self.home / '.local/share/dotfiles/git-bash/bin/bash.exe'),
                           CODEX_HOME=str(self.home / '.codex'), KIMI_CODE_HOME=str(self.home / '.kimi-code'),
                           PI_CODING_AGENT_DIR=str(self.home / '.pi/agent'),
                           OPENCODE_CONFIG=str(self.home / '.config/opencode/opencode.jsonc'),
                           CODEGRAPH_NO_DOWNLOAD='1', DO_NOT_TRACK='1', CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1')
        environment['PATH'] = ';'.join(str(self.home / relative) for relative in ('.bun/bin', '.local/bin', '.pixi/bin')) + ';' + environment['PATH']
        commands = {'bun': (windows_assets()['bun']['version'], '.bun/bin/bun.exe'),
                    'atuin': (windows_assets()['atuin']['version'], '.pixi/bin/atuin.exe'),
                    'nu': (common_pin('nushell'), '.pixi/bin/nu.exe'),
                    'rtk': (common_pin('rtk-cli'), '.pixi/bin/rtk.exe'),
                    'hx': (windows_assets()['helix']['version'], '.pixi/bin/hx.exe'),
                    'jq': (windows_assets()['jq']['version'], '.pixi/bin/jq.exe'),
                    'kimi': (agent_pins()['kimi']['version'], '.bun/bin/kimi.cmd'),
                    'pi': (agent_pins()['pi']['version'], '.bun/bin/pi.cmd'),
                    'opencode': (agent_pins()['opencode']['version'], '.bun/bin/opencode.cmd'),
                    'claude': (agent_pins()['claude']['version'], '.bun/bin/claude.cmd'),
                    'codex': (agent_pins()['codex']['version'], '.bun/bin/codex.cmd'),
                    'minimax': (agent_pins()['minimax']['version'], '.bun/bin/mcode.cmd'),
                    'qoder': (native_agent_pins()['qoder']['version'], '.local/bin/qoder.cmd'),
                    'qodercli': (native_agent_pins()['qoder']['version'], '.local/bin/qodercli.cmd'),
                    'codegraph': (agent_pins()['codegraph']['version'], '.bun/bin/codegraph.cmd')}
        for name, (pin, relative) in commands.items():
            with self.subTest(command=name):
                diagnostic = subprocess.run([str(self.home / relative), '--version'], env=environment,
                                            capture_output=True, text=True, timeout=60)
                self.assertEqual(diagnostic.returncode, 0, diagnostic.stderr)
                self.assertIn(pin, diagnostic.stdout)
        # The full deployment installs the pinned Magpie CLI, and the
        # installed bytes are the release the shared catalog pins.
        magpie = self.home / '.local/share/dotfiles/magpie/bin/magpie.exe'
        self.assertTrue(magpie.is_file())
        self.assertEqual(hashlib.sha256(magpie.read_bytes()).hexdigest(),
                         magpie_releases()['windows-amd64']['sha256'])
        launcher = self.home / '.local/bin/magpie.cmd'
        self.assertTrue(launcher.is_file())
        diagnostic = subprocess.run([str(launcher), '--version'], env=environment,
                                    capture_output=True, text=True, timeout=60)
        self.assertEqual(diagnostic.returncode, 0, diagnostic.stderr)
        self.assertIn(magpie_releases()['windows-amd64']['version'], diagnostic.stdout + diagnostic.stderr)
        doctor = subprocess.run([str(self.home / '.bun/bin/kimi.cmd'), 'doctor'], env=environment,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(doctor.returncode, 0, doctor.stderr)
        self.assertTrue(Path(environment['KIMI_SHELL_PATH']).is_file())
        if bundles:
            self.assert_bundle_exposures(bundles, environment)
        # Native managed Nu discovers its configured home without --config flags.
        ordinary = environment.copy()
        # Nu's native fallback uses Known Folder APIs. Do not remove the XDG
        # startup boundary in a disposable-home test and scaffold the real CI
        # user's RoamingAppData. Ordinary managed launch has no --config flags.
        from fixtures.windows_shell import ordinary_nu_settings
        probe = ordinary_nu_settings(self.home / '.pixi/bin/nu.exe', ordinary)
        self.assertEqual(probe.returncode, 0, probe.stderr)
        values = json.loads(probe.stdout)
        self.assertEqual(Path(values[0]), self.home / '.config/nushell')
        self.assertEqual(values[1:], ['hx', 'managed'])
        # Actual shell discovery must exercise the launchers used in each
        # managed shell, including Git Bash's bare companion scripts.
        pins = [pin for name, (pin, _) in commands.items() if name in ('kimi', 'pi', 'opencode', 'claude', 'codex', 'minimax', 'qoder', 'qodercli', 'codegraph')]
        nu_versions = subprocess.run([str(self.home / '.pixi/bin/nu.exe'), '-e',
                                      'print ([(^kimi --version) (^pi --version) (^opencode --version) '
                                      '(^claude --version) (^codex --version) (^mcode --version) '
                                      '(^qodercli --version) (^codegraph --version)] | to json --raw); exit'],
                                     env=ordinary, capture_output=True, text=True, timeout=120)
        self.assertEqual(nu_versions.returncode, 0, nu_versions.stderr)
        for pin in pins:
            self.assertIn(pin, nu_versions.stdout)
        pip = subprocess.run([str(self.home / '.pixi/bin/python.exe'), '-m', 'pip', 'config', 'debug'],
                             env=ordinary, capture_output=True, text=True, timeout=30)
        self.assertEqual(pip.returncode, 0, pip.stderr)
        self.assertIn(str(self.home / 'AppData/Roaming/pip/pip.ini'), pip.stdout)
        self.assertIn('mirrors.tuna.tsinghua.edu.cn', pip.stdout)
        uv_environment = ordinary.copy()
        for name in tuple(uv_environment):
            if name.startswith(('UV_DEFAULT_INDEX', 'UV_INDEX', 'PIP_INDEX', 'UV_CONFIG_FILE')):
                uv_environment.pop(name)
        uv = subprocess.run([str(self.home / '.pixi/bin/uv.exe'), 'pip', 'install', '--dry-run', '--system',
                             '--offline', '--no-cache', '-v', 'dotfiles-native-absent-discovery-probe'],
                            cwd=self.home, env=uv_environment, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(uv.returncode, 0)  # The synthetic package is deliberately unavailable.
        self.assertIn('mirrors.tuna.tsinghua.edu.cn', uv.stdout + uv.stderr)
        bash = subprocess.run([environment['KIMI_SHELL_PATH'], '--noprofile', '-c',
                               '. "$HOME/.env_core"; command -v nu; command -v atuin; atuin config get --resolved db_path'],
                              env=environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(bash.returncode, 0, bash.stderr)
        self.assertIn('.pixi', bash.stdout)
        self.assertEqual(Path(bash.stdout.splitlines()[-1]), self.home / '.local/share/atuin/history.db')
        bash_versions = subprocess.run([environment['KIMI_SHELL_PATH'], '--noprofile', '-c',
                                        'set -e; . "$HOME/.env_core"; command -v bunx; kimi --version; pi --version; opencode --version; '
                                        'claude --version; codex --version; mcode --version; qodercli --version; codegraph --version'],
                                       env=environment, capture_output=True, text=True, timeout=120)
        self.assertEqual(bash_versions.returncode, 0, bash_versions.stderr)
        for pin in pins:
            self.assertIn(pin, bash_versions.stdout)
        from fixtures.windows_clients import verify_clients
        verify_clients(self, SOURCE, environment)
        console_report = self.root / 'native-console-report.json'
        console = subprocess.run([str(self.home / '.pixi/bin/python.exe'), str(SOURCE / 'tests/fixtures/windows_console.py'),
                                  '--home', str(self.home), '--source', str(SOURCE), '--report', str(console_report)],
                                 env=environment, creationflags=subprocess.CREATE_NEW_CONSOLE, timeout=300)
        self.assertEqual(console.returncode, 0, console_report.read_text() if console_report.exists() else 'native console fixture produced no report')
        self.assertEqual(json.loads(console_report.read_text())['status'], 'passed')
        native_atuin = str(self.home / '.pixi/bin/atuin.exe')
        no_console = subprocess.run([str(self.home / '.pixi/bin/python.exe'),
                                     str(SOURCE / 'dot_local/lib/dotfiles/history.py'), 'join'],
                                    env=environment, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(no_console.returncode, 0)
        self.assertIn('interactive Windows console', no_console.stderr)
        # File-only migration also runs with native Rust/SQLite, never a Known
        # Folder importer. The same two public probes passed locally on Linux.
        from test_portable_history_import import PortableHistoryImportTests
        saved_tools = {name: os.environ.get(name) for name in ('DOTFILES_TEST_ATUIN', 'DOTFILES_TEST_PYTHON')}
        os.environ.update(DOTFILES_TEST_ATUIN=native_atuin, DOTFILES_TEST_PYTHON=str(self.home / '.pixi/bin/python.exe'))
        try:
            import test_portable_history_import as portable
            portable.ATUIN = native_atuin
            portable.PYTHON = str(self.home / '.pixi/bin/python.exe')
            for method in ('test_explicit_nu_text_uses_only_selected_file_and_filters_before_activation',
                           'test_nu_sqlite_preserves_public_metadata_and_signed_session'):
                probe = PortableHistoryImportTests(method)
                probe.setUp()
                try:
                    getattr(probe, method)()
                finally:
                    probe.doCleanups()
        finally:
            for name, value in saved_tools.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        protected = self.home / '.codex/auth.json'
        protected.write_text('{"synthetic":"native-preserve"}')
        again = self.deploy('-Role', role, '-Agents', 'none')
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(protected.read_text(), '{"synthetic":"native-preserve"}')
        self.assertTrue((self.home / '.bun/bin/codex.cmd').exists())




if __name__ == "__main__":
    unittest.main()
