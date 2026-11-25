# Native adapters share the source catalogs and Chezmoi merge template.
$script:TargetedAgent = ''
$script:TargetedPolicies = @()
$script:TargetedRenderDirectory = ''

function Test-AgentSelected($Row) {
    if ($Row.agent -in $selectedAgents) { return $true }
    if ($script:TargetedAgent) { return $script:TargetedAgent -eq 'dsh-tui' -and $Row.agent -eq 'dsh' }
    return $Row.selection -eq 'always'
}

function Get-SelectedClientSettings {
    foreach ($row in (Read-Catalog 'deployment/client-settings/targets.tsv')) {
        if (-not $script:TargetedAgent -or $row.columns[3] -in $script:TargetedPolicies) { $row }
    }
}

# A reparse point is recognized through its directory entry, so a link whose
# target is missing is detected too: the attributes of a dangling link cannot
# be read, and a link is never a safe managed path.
function Test-ReparsePath([string]$Path) {
    if (-not $Path) { return $false }
    $attributes = 0
    try { $attributes = [IO.File]::GetAttributes($Path) }
    catch [IO.FileNotFoundException] { }
    catch [IO.DirectoryNotFoundException] { }
    catch { }
    if ($attributes -band [IO.FileAttributes]::ReparsePoint) { return $true }
    $parent = [IO.Path]::GetDirectoryName($Path)
    $name = [IO.Path]::GetFileName($Path)
    if (-not $parent -or -not $name) { return $false }
    if (-not [IO.Directory]::Exists($parent)) { return $false }
    $entry = Get-ChildItem -LiteralPath $parent -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq $name } | Select-Object -First 1
    if ($null -eq $entry) { return $false }
    if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) { return $true }
    $linkType = $entry.PSObject.Properties['LinkType']
    return ($null -ne $linkType -and [bool]$linkType.Value)
}
function Assert-SafePath([string]$Path, [switch]$SourcePath) {
    $candidate = [IO.Path]::GetFullPath($Path)
    if (-not $SourcePath -and $candidate -ne $TargetHome -and -not $candidate.StartsWith($TargetHome + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        Stop-Deployment 'managed path is outside TargetHome'
    }
    while ($candidate) {
        if (Test-ReparsePath $candidate) { Stop-Deployment "managed path is a symlink or reparse point: $candidate" }
        if ($candidate -eq $TargetHome -or ($SourcePath -and $candidate -eq $Source)) { break }
        $parent = [IO.Path]::GetDirectoryName($candidate)
        if ($candidate -eq $parent) { break }
        $candidate = $parent
    }
}
function Assert-Relative([string]$Value) {
    if (-not $Value -or [IO.Path]::IsPathRooted($Value) -or $Value -match '(^|[\\/])\.\.([\\/]|$)') { Stop-Deployment 'catalog paths must be relative' }
}
function Assert-CopyTree([string]$From, [string]$To) {
    Assert-SafePath $From -SourcePath
    Assert-SafePath $To
    if ([IO.Directory]::Exists($From)) {
        if ([IO.File]::Exists($To)) { Stop-Deployment 'payload directory conflicts with a device file' }
        foreach ($item in (Get-ChildItem -LiteralPath $From -Force)) { Assert-CopyTree $item.FullName (Join-Path $To $item.Name) }
    } elseif ([IO.File]::Exists($From)) {
        if ([IO.Directory]::Exists($To)) { Stop-Deployment 'payload file conflicts with a device directory' }
    } else { Stop-Deployment 'payload source is not a regular file or directory' }
}
function Assert-InstallerDirectory([string]$Path) {
    Assert-SafePath $Path
    if ([IO.Directory]::Exists($Path)) {
        foreach ($item in (Get-ChildItem -LiteralPath $Path -Force)) { Assert-InstallerDirectory $item.FullName }
    }
}
# The launchers a usable PortableGit runtime exposes.
function Get-PortableGitLaunchers { return @('bin/git.exe', 'bin/bash.exe', 'git-bash.exe') }
# Whether every launcher is a regular file. A runtime is usable only when
# all of them are there: the staged tree and the installed runtime are both
# checked, so an incomplete runtime is never reported as verified. A launcher
# that is a link is not a regular file either.
function Test-PortableGitLaunchers([string]$Path) {
    foreach ($entry in (Get-PortableGitLaunchers)) {
        $launcher = Join-Path $Path $entry
        if (Test-ReparsePath $launcher) { return $false }
        if (-not [IO.File]::Exists($launcher)) { return $false }
    }
    return $true
}
# The installation destination and its launcher paths must not be links: a
# substituted destination or parent is refused before anything is written.
# The launcher files themselves are absent before the first install, so only
# their paths are checked here.
function Assert-PortableGitLauncherPaths([string]$Path) {
    Assert-SafePath $Path
    foreach ($entry in (Get-PortableGitLaunchers)) {
        Assert-SafePath (Join-Path $Path $entry)
    }
}
# A runtime is usable only when every launcher is a regular file. The staged
# tree passes this check before it replaces the active runtime, so an
# incomplete extraction never takes the device's Git Bash away.
function Assert-PortableGitLaunchers([string]$Path) {
    Assert-PortableGitLauncherPaths $Path
    foreach ($entry in (Get-PortableGitLaunchers)) {
        if (-not [IO.File]::Exists((Join-Path $Path $entry))) {
            Stop-Deployment "the PortableGit runtime is missing its launcher: $entry"
        }
    }
}
# Remove a tree the deployment owns and replaces, one entry at a time. A link
# is removed as a link and is never entered: Windows PowerShell 5.1 deletes
# the target of a junction when a recursive removal reaches it, and that
# target can belong to the device. The links inside a vendor tree are the
# vendor's own files, so the deployment may replace them.
function Remove-DirectoryLink([string]$Path) {
    # The directory API removes the reparse point itself. The provider
    # fallback covers the runtimes where a link to a directory needs it.
    try { [IO.Directory]::Delete($Path, $false); return } catch { }
    Remove-Item -LiteralPath $Path -Force
}
function Remove-ReplacedTree([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if ($null -eq $item) { return }
    if ($item.PSIsContainer -and -not (Test-ReparsePath $Path)) {
        foreach ($child in (Get-ChildItem -LiteralPath $Path -Force)) { Remove-ReplacedTree $child.FullName }
    }
    if (Test-ReparsePath $Path) {
        if ($item.PSIsContainer) { Remove-DirectoryLink $Path }
        else { Remove-Item -LiteralPath $Path -Force }
        return
    }
    if ($item.PSIsContainer) { [IO.Directory]::Delete($Path) }
    else { Remove-Item -LiteralPath $Path -Force }
}
function Assert-OwnedState {
    # A restricted or opted-out run never writes the Magpie CLI or its
    # launchers, so symlinks at those Magpie-only paths stay device-owned and
    # are not rejected. Every other managed path keeps the normal guard.
    param([bool]$MagpieEnabled = $true)
    Assert-SafePath $TargetHome
    $ancestor = [IO.Path]::GetDirectoryName($TargetHome)
    while ($ancestor) {
        if (Test-ReparsePath $ancestor) { Stop-Deployment 'TargetHome parent is a symlink or reparse point' }
        $ancestor = [IO.Path]::GetDirectoryName($ancestor)
    }
    $managedPaths = @('.local', '.local/bin', '.local/share', '.local/state', '.local/run', '.config',
        '.config/chezmoi', '.config/dotfiles', '.cache', '.cache/tmp', '.pixi', '.pixi/bin',
        '.bun', '.bun/bin', '.bun/managed', '.bun/install/global')
    if (-not $script:TargetedAgent) {
        $managedPaths += @('.local/lib', '.pixi/bin/pixi.exe', '.pixi/manifests', '.pixi/manifests/pixi-global.toml',
            '.cargo', '.cargo/bin', '.rustup', 'AppData', 'AppData/Roaming', 'AppData/Local', '.config/atuin',
            '.config/atuin/config.toml', '.local/share/atuin', '.codex', '.claude', '.kimi-code', '.pi',
            '.pi/agent', '.qoder', '.minimax', '.minimax-code', '.minimax-code-install-logs')
    } elseif ($script:TargetedAgent -eq 'qoder') {
        $managedPaths += '.qoder'
    } elseif ($script:TargetedAgent -eq 'minimax') {
        $managedPaths += @('.minimax', '.minimax-code', '.minimax-code-install-logs')
    }
    if ($MagpieEnabled) {
        $managedPaths += @('.local/share/dotfiles/magpie', '.local/share/dotfiles/magpie/bin', '.local/bin/magpie.cmd')
    }
    foreach ($relative in $managedPaths) {
        Assert-SafePath (Join-Path -Path $TargetHome -ChildPath ([string]$relative))
    }
    if ($script:TargetedAgent) {
        foreach ($relative in @('.cache/chezmoi', '.env_core')) {
            Assert-SafePath (Join-Path $TargetHome $relative)
        }
        Assert-ClientSettingsPaths
        return
    }
    if (-not $env:DOTFILES_SKILLS_DIR) {
        Assert-InstallerDirectory (Join-Path $TargetHome '.cache/dotfiles/skills')
    }
    foreach ($name in @('meta.db', 'history.db', 'records.db', 'key', 'session', 'host_id')) { Assert-SafePath (Join-Path -Path $TargetHome -ChildPath ".local/share/atuin/$name") }
    foreach ($asset in $exceptions) {
        $assetTarget = [string]$asset.target
        Assert-Relative $assetTarget
        $assetPath = Join-Path -Path $TargetHome -ChildPath $assetTarget
        if ($asset.name -eq 'git-bash') {
            # Verified PortableGit installs internal vendor links. A reuse
            # does not write that tree. Protect the root and launchers here;
            # the installer replaces the owned tree and removes the vendor
            # links with it.
            Assert-PortableGitLauncherPaths $assetPath
        } else { Assert-InstallerDirectory $assetPath }
    }
    foreach ($row in (Read-Catalog 'deployment/agent-payload/targets.tsv')) {
        Assert-Relative $row.columns[1]; Assert-Relative $row.columns[2]
        $destination = Join-Path -Path $TargetHome -ChildPath ([string]$row.columns[2])
        if ($row.columns[0] -notin @('tree', 'file', 'block', 'retire')) { Stop-Deployment 'unknown agent payload kind' }
        Assert-SafePath $destination
        if ($row.columns[0] -eq 'retire') { continue }
        if ($row.columns[1] -eq 'skills') {
            # Skills are fetched after this preflight. The library the
            # deployment copies from is validated now, and the destination
            # root is a safe parent path. The device entries inside that
            # root belong to the device: the copy adapter preserves and
            # reports a collision instead of writing through it, so this
            # preflight never traverses them.
            if ([IO.File]::Exists($destination)) { Stop-Deployment 'skill root conflicts with a device file' }
            if ($env:DOTFILES_SKILLS_DIR) { Assert-SkillSource $env:DOTFILES_SKILLS_DIR }
            continue
        }
        Assert-CopyTree (Join-Path $Source "deployment/agent-payload/$($row.columns[1])") $destination
    }
    Assert-ClientSettingsPaths
    foreach ($relative in @('nushell', 'uv', 'pip')) { Assert-SafePath (Join-Path $roots.appData $relative) }
    foreach ($relative in @('nushell/env.nu', 'nushell/config.nu', 'nushell/proxy.nu', 'nushell/zoxide.nu', 'nushell/direnv.nu', 'nushell/micromamba.nu', 'uv/uv.toml', 'pip/pip.ini')) {
        Assert-SafePath (Join-Path $roots.appData $relative)
    }
}
function Assert-ClientSettingsPaths {
    foreach ($row in (Get-SelectedClientSettings)) {
        foreach ($part in $row.columns) { Assert-Relative $part }
        Assert-SafePath (Join-Path $Source "deployment/client-settings/$($row.columns[1])") -SourcePath
        Assert-SafePath (Join-Path -Path $TargetHome -ChildPath ([string]$row.columns[2]))
        Assert-SafePath (Join-Path $TargetHome ".local/state/dotfiles/client-settings/$($row.columns[3]).json")
    }
}
function Set-EnvironmentRoots {
    $script:DeviceEnvironment = [ordered]@{
        HOME = $TargetHome; USERPROFILE = $TargetHome; APPDATA = $roots.appData; LOCALAPPDATA = $roots.localAppData
        XDG_CONFIG_HOME = $roots.config; XDG_DATA_HOME = $roots.data; XDG_STATE_HOME = $roots.state; XDG_CACHE_HOME = $roots.cache
        XDG_RUNTIME_DIR = Join-Path $TargetHome '.local/run'; PIXI_HOME = $roots.pixi; PIXI_CACHE_DIR = Join-Path $roots.cache 'pixi'
        BUN_INSTALL = $roots.bun; BUN_INSTALL_CACHE_DIR = Join-Path $roots.cache 'bun/install'
        CARGO_HOME = $roots.cargo; RUSTUP_HOME = $roots.rustup
        UV_CACHE_DIR = Join-Path $roots.cache 'uv'; UV_TOOL_DIR = Join-Path $roots.data 'uv/tools'; UV_TOOL_BIN_DIR = Join-Path $TargetHome '.local/bin'
        PIP_CACHE_DIR = Join-Path $roots.cache 'pip'; NPM_CONFIG_USERCONFIG = Join-Path $TargetHome '.npmrc'; NPM_CONFIG_CACHE = Join-Path $roots.cache 'npm'
        npm_config_prefix = Join-Path $TargetHome '.local'; ATUIN_CONFIG_DIR = Join-Path $roots.config 'atuin'; ATUIN_DATA_DIR = Join-Path $roots.data 'atuin'
        _ZO_DATA_DIR = Join-Path $roots.data 'zoxide'
        CODEX_HOME = Join-Path $TargetHome '.codex'; KIMI_CODE_HOME = Join-Path $TargetHome '.kimi-code'; PI_CODING_AGENT_DIR = Join-Path $TargetHome '.pi/agent'
        OPENCODE_CONFIG_DIR = Join-Path $roots.config 'opencode'; OPENCODE_CONFIG = Join-Path $roots.config 'opencode/opencode.jsonc'
        MINIMAX_DATA_DIR = Join-Path $TargetHome '.minimax'; QODER_CONFIG_DIR = Join-Path $TargetHome '.qoder'
        KIMI_SHELL_PATH = Join-Path $roots.data 'dotfiles/git-bash/bin/bash.exe'
        CLAUDE_CODE_GIT_BASH_PATH = Join-Path $roots.data 'dotfiles/git-bash/bin/bash.exe'
        TEMP = Join-Path $roots.cache 'tmp'; TMP = Join-Path $roots.cache 'tmp'; TMPDIR = Join-Path $roots.cache 'tmp'
        DOTFILES_PLATFORM = 'windows'; DOTFILES_ROLE = $selection.role; DOTFILES_ARCH = 'x86_64'; DOTFILES_BUNDLES = 'none'
        DOTFILES_MIRROR = $selection.mirror
    }
    if ($selectedBundles.Count) { $DeviceEnvironment.DOTFILES_BUNDLES = $selectedBundles -join ',' }
    foreach ($name in $DeviceEnvironment.Keys) { [Environment]::SetEnvironmentVariable($name, $DeviceEnvironment[$name], 'Process') }
    foreach ($name in @('DOTFILES_CLASS', 'DOTFILES_PROFILE', 'CLAUDE_CONFIG_DIR', 'OPENCODE_CONFIG_CONTENT', 'OPENCODE_CLI_CONFIG_CONTENT', 'ATUIN_OTEL', 'MAVIS_DATA_DIR', 'QODER_HOME', 'QODER_USER_CONFIG_DIR')) { [Environment]::SetEnvironmentVariable($name, $null, 'Process') }
    $env:PATH = ((Join-Path $roots.bun 'bin'), (Join-Path $TargetHome '.local/bin'), (Join-Path $roots.pixi 'bin'), (Join-Path $roots.cargo 'bin'), (Join-Path $roots.data 'dotfiles/git-bash/bin')) -join [IO.Path]::PathSeparator
    $env:PATH += [IO.Path]::PathSeparator + $script:InitialPath
}
function Invoke-Tool([string]$Executable, [string[]]$Arguments, [switch]$Quiet, [switch]$ShowFailureOutput) {
    $savedPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $global:LASTEXITCODE = 0
        $output = (& $Executable @Arguments 2>&1 | Out-String)
        $exitCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $savedPreference }
    if ($exitCode) {
        $script:FailureCode = $exitCode
        if ($ShowFailureOutput -and $output.Trim()) {
            Stop-Deployment ("required command failed: " + $output.Trim())
        }
        Stop-Deployment 'required command failed'
    }
    if (-not $Quiet) { [Console]::Out.Write($output) }
    return $output
}
function Write-Utf8([string]$Path, [string]$Text) {
    Assert-SafePath $Path
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Path)) | Out-Null
    [IO.File]::WriteAllText($Path, $Text, (New-Object Text.UTF8Encoding($false)))
}
function Set-Private([string]$Path) {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { return }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $directory = [IO.Directory]::Exists($Path)
    $acl = if ($directory) { New-Object Security.AccessControl.DirectorySecurity }
           else { New-Object Security.AccessControl.FileSecurity }
    $acl.SetAccessRuleProtection($true, $false)
    $rule = if ($directory) {
        New-Object Security.AccessControl.FileSystemAccessRule($identity, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    } else {
        New-Object Security.AccessControl.FileSystemAccessRule($identity, 'FullControl', 'Allow')
    }
    $acl.AddAccessRule($rule)
    Set-Acl -LiteralPath $Path -AclObject $acl
}
function Copy-RegularTree([string]$From, [string]$To) {
    Assert-CopyTree $From $To
    if ([IO.Directory]::Exists($From)) {
        [IO.Directory]::CreateDirectory($To) | Out-Null
        foreach ($item in (Get-ChildItem -LiteralPath $From -Force)) { Copy-RegularTree $item.FullName (Join-Path $To $item.Name) }
    } else {
        [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($To)) | Out-Null
        [IO.File]::Copy($From, $To, $true)
    }
}
function Assert-SourceTree([string]$From) {
    if (Test-ReparsePath $From) { Stop-Deployment "skill overlay is a symlink or reparse point: $From" }
    if ([IO.Directory]::Exists($From)) {
        foreach ($item in (Get-ChildItem -LiteralPath $From -Force)) { Assert-SourceTree $item.FullName }
    } elseif (-not [IO.File]::Exists($From)) { Stop-Deployment "unsupported skill overlay resource: $From" }
}
function Copy-StagedRegularTree([string]$From, [string]$To) {
    Assert-SourceTree $From
    if ([IO.Directory]::Exists($From)) {
        [IO.Directory]::CreateDirectory($To) | Out-Null
        foreach ($item in (Get-ChildItem -LiteralPath $From -Force)) { Copy-StagedRegularTree $item.FullName (Join-Path $To $item.Name) }
    } else {
        [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($To)) | Out-Null
        [IO.File]::Copy($From, $To, $true)
    }
}
function Test-SkillLink([string]$Path) {
    # A link is recognized even when its target is missing: the deployment
    # preserves it and never writes through it.
    return (Test-ReparsePath $Path)
}
function Test-SkillPath([string]$Path) {
    return ([IO.File]::Exists($Path) -or [IO.Directory]::Exists($Path) -or (Test-SkillLink $Path))
}
function Get-DotfilesStateRoot {
    $stateRoot = $null
    if ($roots -is [hashtable]) { if ($roots.ContainsKey('state')) { $stateRoot = $roots['state'] } }
    elseif ($roots.PSObject.Properties.Name -contains 'state') { $stateRoot = $roots.state }
    if (-not $stateRoot) { $stateRoot = $env:XDG_STATE_HOME }
    if (-not $stateRoot) { $stateRoot = Join-Path $TargetHome '.local/state' }
    return $stateRoot
}
function Get-SkillSelections {
    $map = @{}
    foreach ($row in (Read-Catalog 'deployment/skills.tsv')) {
        $name = [string]$row.columns[0]
        if (-not $name -or $name.StartsWith('#')) { continue }
        $selection = [string]$row.columns[5]; if (-not $selection) { $selection = 'auto' }
        $map[$name] = $selection
    }
    return $map
}
function Test-SkillSelected([string]$Name, $Selections) {
    if (-not $Selections.ContainsKey($Name)) { return $false }
    if ($Selections[$Name] -eq 'auto') { return $true }
    $requested = ",$env:DOTFILES_SKILLS,"
    return ($requested -like "*,$($Selections[$Name]),*" -or $requested -like "*,$Name,*")
}
function Get-DisabledSkills {
    $disabled = @()
    if (Test-Path -LiteralPath (Join-Path $Source 'deployment/disabled-skills.tsv')) {
        $disabled = @(Read-Catalog 'deployment/disabled-skills.tsv' | ForEach-Object { $_.columns[0] })
    }
    return $disabled
}
# The library the deployment copies the selected skills from. Only a selected
# skill is written, so only its source is validated: a source that carries a
# link would copy bytes from outside the library.
function Assert-SkillSource([string]$Library) {
    if (-not [IO.Directory]::Exists($Library)) { Stop-Deployment "skill library is not a directory: $Library" }
    Assert-SafePath $Library -SourcePath
    $selections = Get-SkillSelections
    $disabled = Get-DisabledSkills
    foreach ($entry in (Get-ChildItem -LiteralPath $Library -Force)) {
        if ($disabled -contains $entry.Name) { continue }
        if (-not (Test-SkillSelected $entry.Name $selections)) { continue }
        Assert-SkillTree $entry.FullName
    }
}
# A skill source holds regular files and directories only.
function Assert-SkillTree([string]$Path) {
    Assert-SafePath $Path -SourcePath
    if ([IO.Directory]::Exists($Path)) {
        foreach ($item in (Get-ChildItem -LiteralPath $Path -Force)) { Assert-SkillTree $item.FullName }
    } elseif (-not [IO.File]::Exists($Path)) {
        Stop-Deployment "skill source is not a regular file or directory: $Path"
    }
}
function Get-SkillRoots {
    $owned = @()
    foreach ($row in (Read-Catalog 'deployment/agent-payload/targets.tsv')) {
        if ($row.columns[0] -eq 'tree' -and $row.columns[1] -eq 'skills') { $owned += [string]$row.columns[2] }
    }
    return $owned
}
function Get-ManagedSkillRows {
    $state = Join-Path (Get-DotfilesStateRoot) 'dotfiles/managed-skills.tsv'
    $rows = @()
    if (-not [IO.File]::Exists($state)) { return $rows }
    foreach ($line in [IO.File]::ReadAllLines($state)) {
        if (-not $line -or $line.StartsWith('#')) { continue }
        $fields = $line.Split('|')
        if ($fields.Count -ge 2) { $rows += ($fields[0] + '|' + $fields[1]) }
    }
    return $rows
}
function Get-GeneratedSkillRows {
    $state = Join-Path (Get-DotfilesStateRoot) 'dotfiles/generated-skills.tsv'
    $rows = @()
    if (-not [IO.File]::Exists($state)) { return $rows }
    foreach ($line in [IO.File]::ReadAllLines($state)) {
        if (-not $line -or $line.StartsWith('#')) { continue }
        $rows += $line
    }
    return $rows
}
function Test-GeneratedSkill([string]$Name, [string]$Root) {
    foreach ($line in (Get-GeneratedSkillRows)) {
        $fields = $line.Split('|')
        if ($fields.Count -ge 2 -and $fields[0] -eq $Name -and $fields[1] -eq $Root) { return $true }
    }
    return $false
}
# The entries of a skill tree, relative to its root. A link is an entry of
# its own: the comparison never follows it, so a device link is never read
# through and never mistaken for the staged bytes.
function Get-SkillTreeEntries([string]$Root, [string]$Base = '') {
    if (-not [IO.Directory]::Exists($Root)) { return @() }
    if (-not $Base) { $Base = $Root }
    $entries = @()
    foreach ($item in (Get-ChildItem -LiteralPath $Root -Force)) {
        $relative = $item.FullName.Substring($Base.Length).TrimStart([char[]]@('\', '/'))
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { $entries += ('l ' + $relative); continue }
        if ($item.PSIsContainer) { $entries += ('d ' + $relative); $entries += @(Get-SkillTreeEntries $item.FullName $Base) }
        else { $entries += ('f ' + $relative) }
    }
    return $entries
}
function Test-SkillTreeIdentical([string]$From, [string]$To) {
    if (-not [IO.Directory]::Exists($From) -or -not [IO.Directory]::Exists($To)) { return $false }
    $fromEntries = @(Get-SkillTreeEntries $From | Sort-Object)
    $toEntries = @(Get-SkillTreeEntries $To | Sort-Object)
    if (Compare-Object $fromEntries $toEntries) { return $false }
    foreach ($entry in $fromEntries) {
        if (-not $entry.StartsWith('f ')) { continue }
        $relative = $entry.Substring(2)
        $left = Join-Path $From $relative; $right = Join-Path $To $relative
        if ((Get-FileHash -LiteralPath $left -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $right -Algorithm SHA256).Hash) { return $false }
    }
    return $true
}
# Whether a tree holds a link. The walk never descends into one, so the
# target of a link is never read.
function Test-TreeHasLink([string]$Path) {
    if (-not $Path) { return $false }
    if (Test-ReparsePath $Path) { return $true }
    foreach ($item in (Get-ChildItem -LiteralPath $Path -Force -ErrorAction SilentlyContinue)) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { return $true }
        if ($item.PSIsContainer -and (Test-TreeHasLink $item.FullName)) { return $true }
    }
    return $false
}
# Remove a tree the deployment owns. The removal never follows a link:
# Windows PowerShell 5.1 deletes the target of a junction when a recursive
# removal reaches it, and that target belongs to the device, not to the
# deployment. A tree that holds a link is refused instead, so the caller
# preserves and reports it.
function Remove-OwnedTree([string]$Path) {
    if (Test-TreeHasLink $Path) { return $false }
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if ($null -eq $item) { return $true }
    if (-not $item.PSIsContainer) { Remove-Item -LiteralPath $Path -Force; return $true }
    foreach ($child in (Get-ChildItem -LiteralPath $Path -Force)) { Remove-OwnedTree $child.FullName }
    Remove-Item -LiteralPath $Path -Force
    return $true
}
function Copy-ManagedSkill([string]$From, [string]$To, [string]$Name, [string]$Root) {
    if (Test-SkillLink $To) {
        [Console]::Error.WriteLine("dotfiles: preserved skill $Name in $Root; a device symlink has that name")
        return
    }
    if (Test-SkillPath $To) {
        if (-not [IO.Directory]::Exists($To)) {
            [Console]::Error.WriteLine("dotfiles: preserved skill $Name in $Root; a device file has that name")
            return
        }
        if ($script:PreviousManaged -contains ($Name + '|' + $Root)) {
            if (-not (Remove-OwnedTree $To)) {
                [Console]::Error.WriteLine("dotfiles: preserved managed skill $Name in $Root; it holds a link, so the deployment did not replace it")
                return
            }
        } elseif (Test-SkillTreeIdentical $From $To) {
            $script:SkillWritten += ($Name + '|' + $Root)
            return
        } else {
            [Console]::Error.WriteLine("dotfiles: preserved skill $Name in $Root; a device directory has that name and its bytes differ")
            return
        }
    }
    Copy-RegularTree $From $To
    $script:SkillWritten += ($Name + '|' + $Root)
}
# A generated skill owns one file. A device directory that holds exactly
# these bytes is adopted without a rewrite; a directory that holds anything
# else keeps its own bytes and stays the device's.
function Test-GeneratedSkillIdentical([string]$From, [string]$To) {
    if (-not [IO.Directory]::Exists($To)) { return $false }
    $source = Join-Path $From 'SKILL.md'
    $target = Join-Path $To 'SKILL.md'
    if (-not [IO.File]::Exists($source) -or -not [IO.File]::Exists($target)) { return $false }
    if (Test-SkillLink $target) { return $false }
    $entries = @(Get-ChildItem -LiteralPath $To -Force)
    if ($entries.Count -ne 1 -or $entries[0].Name -ne 'SKILL.md') { return $false }
    return ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -eq
        (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash)
}
# Copy one generated skill into a managed root. Returns $true only when the
# deployment owns the destination afterwards (copied, refreshed, adopted
# identical bytes, or kept unchanged because a link made a replacement
# unsafe); a preserved device entry returns $false so the caller never
# records it as owned.
function Copy-GeneratedSkill([string]$From, [string]$To, [string]$Name, [string]$Root) {
    if (Test-SkillLink $To) {
        [Console]::Error.WriteLine("dotfiles: preserved skill $Name in $Root; a device symlink has that name")
        return $false
    }
    if (Test-SkillPath $To) {
        if (-not [IO.Directory]::Exists($To)) {
            [Console]::Error.WriteLine("dotfiles: preserved skill $Name in $Root; a device file has that name")
            return $false
        }
        if (Test-SkillLink (Join-Path $To 'SKILL.md')) {
            [Console]::Error.WriteLine("dotfiles: preserved skill $Name in $Root; a device symlink has that name")
            return $false
        }
        if (-not (Test-GeneratedSkill $Name $Root)) {
            if (Test-GeneratedSkillIdentical $From $To) { return $true }
            [Console]::Error.WriteLine("dotfiles: preserved skill $Name in $Root; a device directory has that name and its bytes differ")
            return $false
        }
        if (Test-GeneratedSkillIdentical $From $To) { return $true }
        if (-not (Remove-OwnedTree $To)) {
            [Console]::Error.WriteLine("dotfiles: preserved generated skill $Name in $Root; it holds a link, so the deployment did not replace it")
            return $true
        }
    }
    Copy-RegularTree $From $To
    return $true
}
function Copy-GeneratedSkills {
    $rows = @(Get-GeneratedSkillRows)
    $wanted = @()
    foreach ($line in $rows) {
        $fields = $line.Split('|'); if ($fields.Count -lt 2) { continue }
        $name = $fields[0]; $root = $fields[1]
        $generatedSource = Join-Path $TargetHome ".agents/skills/$name"
        if (-not [IO.Directory]::Exists($generatedSource)) { continue }
        foreach ($targetRoot in (Get-SkillRoots)) {
            if ($targetRoot -eq $root) { continue }
            # Only an owned destination is recorded: a preserved device entry
            # must stay unrecorded so a later apply never claims it.
            if (Copy-GeneratedSkill $generatedSource (Join-Path $TargetHome "$targetRoot/$name") $name $targetRoot) {
                $generator = if ($fields.Count -ge 3) { $fields[2] } else { 'generated' }
                $wanted += ($name + '|' + $targetRoot + '|' + $generator)
            }
        }
    }
    if ($wanted.Count) {
        $all = @($rows + $wanted | Sort-Object -Unique)
        Write-Utf8 (Join-Path (Get-DotfilesStateRoot) 'dotfiles/generated-skills.tsv') ("# name|root|generator`n" + ($all -join "`n") + "`n")
    }
}
function Complete-SkillInventory {
    $owned = @(Get-SkillRoots)
    $selections = Get-SkillSelections
    $kept = @()
    foreach ($row in $script:PreviousManaged) {
        $fields = $row.Split('|'); if ($fields.Count -lt 2) { continue }
        $name = $fields[0]; $root = $fields[1]
        if ($owned -notcontains $root) {
            [Console]::Error.WriteLine("dotfiles: preserved skill $name in $root; the deployment does not own that root")
            $kept += $row; continue
        }
        if ($selections.ContainsKey($name) -and (Test-SkillSelected $name $selections)) { $kept += $row; continue }
        $path = Join-Path $TargetHome "$root/$name"
        if (-not (Test-SkillPath $path)) { continue }
        if (Test-GeneratedSkill $name $root) {
            [Console]::Error.WriteLine("dotfiles: preserved generated skill $name in $root")
            $kept += $row; continue
        }
        if (Test-SkillLink $path) {
            [Console]::Error.WriteLine("dotfiles: preserved managed skill $name in $root; refused to follow a symlink")
            $kept += $row; continue
        }
        if (-not [IO.Directory]::Exists($path)) {
            [Console]::Error.WriteLine("dotfiles: preserved managed skill $name in $root; it is not a managed directory")
            $kept += $row; continue
        }
        if (-not (Remove-OwnedTree $path)) {
            [Console]::Error.WriteLine("dotfiles: preserved managed skill $name in $root; it holds a link, so the deployment did not prune it")
            $kept += $row; continue
        }
        [Console]::Error.WriteLine("dotfiles: pruned managed skill $name from $root")
    }
    $all = @($script:SkillWritten + $kept | Sort-Object -Unique)
    Write-Utf8 (Join-Path (Get-DotfilesStateRoot) 'dotfiles/managed-skills.tsv') ("# name|root`n" + ($all -join "`n") + "`n")
    foreach ($root in $owned) {
        $directory = Join-Path $TargetHome $root
        if (-not [IO.Directory]::Exists($directory)) { continue }
        foreach ($entry in (Get-ChildItem -LiteralPath $directory -Force)) {
            $name = $entry.Name
            if ($all -contains ($name + '|' + $root)) { continue }
            if (Test-GeneratedSkill $name $root) { continue }
            if ($selections.ContainsKey($name) -and (Test-SkillSelected $name $selections)) { continue }
            if ($selections.ContainsKey($name)) {
                [Console]::Error.WriteLine("dotfiles: preserved skill $name in $root; the selection does not include it")
            } else {
                [Console]::Error.WriteLine("dotfiles: preserved device skill $name in $root")
            }
        }
    }
}
function Copy-InstructionBlock([string]$From, [string]$To) {
    $existing = ''; if ([IO.File]::Exists($To)) { $existing = [IO.File]::ReadAllText($To) }
    $start = '<!-- DOTFILES_AGENT_START -->'; $end = '<!-- DOTFILES_AGENT_END -->'
    $starts = ([regex]::Matches($existing, [regex]::Escape($start))).Count
    $ends = ([regex]::Matches($existing, [regex]::Escape($end))).Count
    if ($starts -gt 1 -or $ends -gt 1 -or $starts -ne $ends) { Stop-Deployment 'duplicate or unfinished managed instruction markers' }
    $body = [IO.File]::ReadAllText($From)
    # Native Windows boundary: always use the windows overlay.
    $overlay = Join-Path (Split-Path -Parent $From) 'overlays/windows.md'
    if (-not [IO.File]::Exists($overlay)) { Stop-Deployment "missing platform overlay: $overlay" }
    $body = $body + "`n`n" + [IO.File]::ReadAllText($overlay)
    $block = $start + "`n" + $body + $end
    if ($starts) {
        $begin = $existing.IndexOf($start); $finish = $existing.IndexOf($end)
        if ($finish -lt $begin) { Stop-Deployment 'unfinished managed instruction markers' }
        $text = $existing.Substring(0, $begin) + $block + $existing.Substring($finish + $end.Length)
    } else {
        $text = $existing
        if ($text) { $text += "`n" }
        $text += $block + "`n"
    }
    Write-Utf8 $To $text
}
function Remove-InstructionBlock([string]$To) {
    Assert-SafePath $To
    if (-not [IO.File]::Exists($To)) { return }
    $existing = [IO.File]::ReadAllText($To)
    $start = '<!-- DOTFILES_AGENT_START -->'; $end = '<!-- DOTFILES_AGENT_END -->'
    $starts = ([regex]::Matches($existing, [regex]::Escape($start))).Count
    $ends = ([regex]::Matches($existing, [regex]::Escape($end))).Count
    if ($starts -gt 1 -or $ends -gt 1 -or $starts -ne $ends) { Stop-Deployment 'duplicate or unfinished managed instruction markers' }
    if (-not $starts) { return }
    $begin = $existing.IndexOf($start); $finish = $existing.IndexOf($end)
    if ($finish -lt $begin) { Stop-Deployment 'unfinished managed instruction markers' }
    $prefix = $existing.Substring(0, $begin)
    if ($prefix.EndsWith("`n")) {
        $prefix = $prefix.Substring(0, $prefix.Length - 1)
        if ($prefix.EndsWith("`r")) { $prefix = $prefix.Substring(0, $prefix.Length - 1) }
    }
    $suffix = $existing.Substring($finish + $end.Length) -replace '^\r?\n', ''
    $text = $prefix + $suffix
    if ([string]::IsNullOrWhiteSpace($text)) { Remove-Item -LiteralPath $To }
    else { Write-Utf8 $To $text }
}
function Test-SkillArchive([string]$Archive) {
    $entries = & tar -tzf $Archive
    if ($LASTEXITCODE -ne 0) { return $false }
    foreach ($entry in $entries) {
        if ($entry -match '^(/|\.\.(/|$))' -or $entry -match '(^|/)\.\.(/|$)') { return $false }
    }
    $modes = & tar -tvzf $Archive
    foreach ($mode in $modes) { if ($mode.Substring(0, 1) -eq 'l') { return $false } }
    return $true
}
function Import-SkillLibrary {
    $script:Step = 'apply-source.skills'
    if ($env:DOTFILES_SKILLS_DIR) {
        if (-not (Test-Path -LiteralPath $env:DOTFILES_SKILLS_DIR -PathType Container)) { Stop-Deployment 'DOTFILES_SKILLS_DIR is not a directory' }
        $script:SkillLibrary = $env:DOTFILES_SKILLS_DIR
        return
    }
    # A reviewed lock is mandatory: every selected skill needs a matching
    # valid pin before any remote fetch or staging mutation. The explicit
    # offline library (DOTFILES_SKILLS_DIR) above is the only bypass.
    $lockRelative = 'deployment/skills.lock.tsv'
    if (-not (Test-Path -LiteralPath (Join-Path $Source $lockRelative))) { Stop-Deployment "missing skill lock: $lockRelative" }
    $pins = @{}
    foreach ($entry in (Read-Catalog $lockRelative)) {
        if ($entry.columns.Count -lt 4 -or -not $entry.columns[0]) { Stop-Deployment 'malformed skill lock entry' }
        $lockName = [string]$entry.columns[0]; $lockKind = [string]$entry.columns[1]; $lockPin = [string]$entry.columns[3]
        if ($pins.ContainsKey($lockName)) { Stop-Deployment 'duplicate skill lock entry' }
        if (($lockKind -eq 'git' -and $lockPin -cnotmatch '^[a-f0-9]{40}$') -or
            ($lockKind -eq 'tarball' -and $lockPin -cnotmatch '^[a-f0-9]{64}$') -or
            ($lockKind -ne 'git' -and $lockKind -ne 'tarball')) { Stop-Deployment "invalid skill pin: $lockName" }
        $pins[$lockName] = $entry.columns
    }
    if (-not $pins.Count) { Stop-Deployment "empty skill lock: $lockRelative" }
    $selected = @()
    foreach ($row in (Read-Catalog 'deployment/skills.tsv')) {
        $name = [string]$row.columns[0]
        $skillSelection = $row.columns[5]; if (-not $skillSelection) { $skillSelection = 'auto' }
        if (-not $name -or $name.StartsWith('#')) { continue }
        # Tagged skills are not deployed automatically; a host asks for them.
        if ($skillSelection -ne 'auto') {
            $requested = ",$env:DOTFILES_SKILLS,"
            if ($requested -notlike "*,$skillSelection,*" -and $requested -notlike "*,$name,*") { continue }
        }
        $locked = $pins[$name]
        if (-not $locked -or $locked[1] -ne $row.columns[1] -or $locked[2] -ne $row.columns[2]) { Stop-Deployment "skill lock source mismatch: $name" }
        $selected += ,$row
    }
    $stage = Join-Path $env:TEMP ('skills-' + [Guid]::NewGuid().ToString('N'))
    $cache = Join-Path $roots.cache 'dotfiles/skills'
    Assert-InstallerDirectory $cache
    [IO.Directory]::CreateDirectory($stage) | Out-Null
    [IO.Directory]::CreateDirectory((Join-Path $cache 'git')) | Out-Null
    [IO.Directory]::CreateDirectory((Join-Path $cache 'tarballs')) | Out-Null
    $marker = Join-Path $cache '.refreshed'
    $refresh = $true
    if ($env:DOTFILES_SKILLS_REFRESH -eq '0') { $refresh = $false }
    elseif ($env:DOTFILES_SKILLS_REFRESH -ne '1' -and (Test-Path -LiteralPath $marker)) {
        $maxAge = '21600'; if ($env:DOTFILES_SKILLS_MAX_AGE) { $maxAge = $env:DOTFILES_SKILLS_MAX_AGE }
        $age = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() - [int64](Get-Content -LiteralPath $marker -Raw)
        $refresh = $age -ge [int64]$maxAge
    }
    $refreshSucceeded = $true
    $lockRows = @('# name|kind|source|resolved')
    foreach ($row in $selected) {
        $name = $row.columns[0]; $kind = $row.columns[1]; $sourceUrl = $row.columns[2]
        $path = $row.columns[4]; if (-not $path) { $path = '' }
        $pin = [string]$pins[$name][3]
        if ($kind -eq 'git') {
            $slug = $sourceUrl -replace '^[A-Za-z][A-Za-z0-9+.-]*://', '' -replace '/+$', '' -replace '[^A-Za-z0-9._-]', '_'
            $repo = Join-Path $cache "git/$slug"
            if (-not (Test-Path -LiteralPath (Join-Path $repo '.git'))) {
                Invoke-Tool git @('init', '--quiet', $repo) -Quiet | Out-Null
                Invoke-Tool git @('-C', $repo, 'remote', 'add', 'origin', $sourceUrl) -Quiet | Out-Null
            }
            # A cache miss is routine. PowerShell 5.1 can make native stderr
            # terminating even when redirected, so use a quiet Git probe.
            & git -C $repo rev-parse --verify --quiet "$pin^{commit}" | Out-Null
            if ($LASTEXITCODE -ne 0) { Invoke-Tool git @('-C', $repo, 'fetch', '--quiet', '--depth', '1', 'origin', $pin) -Quiet | Out-Null }
            $resolved = $pin
            $archive = Join-Path $stage "$name.tar"
            $depth = ($path -split '/').Count
            # Git archive emits no enclosing directory for a repository-root skill.
            if ($path -eq '.') { $depth = 0 }
            & git -C $repo archive --output=$archive $resolved $path 2>$null
            if ($LASTEXITCODE -ne 0) { Stop-Deployment "cannot read skill $name from $sourceUrl" }
            $destination = Join-Path $stage $name
            [IO.Directory]::CreateDirectory($destination) | Out-Null
            & tar -xf $archive -C $destination --strip-components=$depth
            if ($LASTEXITCODE -ne 0) { Stop-Deployment "cannot extract skill $name" }
            Remove-Item -LiteralPath $archive -Force
            $layouts = @()
            if (Test-Path -LiteralPath (Join-Path $Source 'deployment/skill-layouts.tsv')) {
                $layouts = @(Read-Catalog 'deployment/skill-layouts.tsv' | Where-Object { $_.columns[0] -eq $name })
            }
            if ($layouts.Count) {
                $mapped = Join-Path $stage "$name.layout"
                [IO.Directory]::CreateDirectory($mapped) | Out-Null
                foreach ($layout in $layouts) {
                    $from = [string]$layout.columns[1]; $to = [string]$layout.columns[2]
                    $origin = if ($layout.columns.Count -ge 4 -and $layout.columns[3]) { [string]$layout.columns[3] } else { 'upstream' }
                    foreach ($relative in @($from, $to)) {
                        if (-not $relative -or [IO.Path]::IsPathRooted($relative) -or ($relative -split '[/\\]') -contains '..') { Stop-Deployment "unsafe skill layout: $name" }
                    }
                    $outputPath = Join-Path $mapped $to
                    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($outputPath)) | Out-Null
                    if ($origin -eq 'repo') {
                        $inputPath = Join-Path $Source "deployment/skill-overlays/$name/$from"
                        Assert-SafePath $inputPath -SourcePath
                        Copy-StagedRegularTree $inputPath $outputPath
                    } elseif ($origin -eq 'upstream') {
                        $inputPath = Join-Path $destination $from
                        Copy-Item -LiteralPath $inputPath -Destination $outputPath -Recurse
                    } else { Stop-Deployment "unknown skill layout origin: $name" }
                }
                Remove-Item -LiteralPath $destination -Recurse -Force
                Move-Item -LiteralPath $mapped -Destination $destination
            }
            if (-not (Test-Path -LiteralPath (Join-Path $destination 'SKILL.md'))) { Stop-Deployment "skill $name has no SKILL.md" }
            $lockRows += "$name|git|$sourceUrl|$resolved"
        } elseif ($kind -eq 'tarball') {
            $slug = $sourceUrl -replace '^[A-Za-z][A-Za-z0-9+.-]*://', '' -replace '/+$', '' -replace '[^A-Za-z0-9._-]', '_'
            $cached = Join-Path $cache "tarballs/$slug.tgz"
            if ($refresh -or -not (Test-Path -LiteralPath $cached)) {
                $download = "$cached.part"
                try {
                    Invoke-WebRequest -Uri $sourceUrl -OutFile $download -UseBasicParsing -TimeoutSec 90
                }
                catch {
                    $refreshSucceeded = $false
                    Remove-Item -LiteralPath $download -Force -ErrorAction SilentlyContinue
                    if (-not (Test-Path -LiteralPath $cached)) { Stop-Deployment "cannot download skill $name" }
                }
                if (Test-Path -LiteralPath $download) {
                    if ((Get-FileHash -LiteralPath $download -Algorithm SHA256).Hash.ToLowerInvariant() -ne $pin) {
                        Remove-Item -LiteralPath $download -Force
                        Stop-Deployment "skill archive checksum mismatch: $name; review an explicit skill update"
                    }
                    Move-Item -LiteralPath $download -Destination $cached -Force
                }
            }
            $digest = (Get-FileHash -LiteralPath $cached -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($digest -ne $pin) { Stop-Deployment "skill archive checksum mismatch: $name" }
            if (-not (Test-SkillArchive $cached)) { Stop-Deployment "unsafe skill archive: $name" }
            $destination = Join-Path $stage $name
            [IO.Directory]::CreateDirectory($destination) | Out-Null
            & tar -xzf $cached -C $destination
            if (-not (Test-Path -LiteralPath (Join-Path $destination 'SKILL.md'))) { Stop-Deployment "skill $name has no SKILL.md" }
            $lockRows += "$name|tarball|$sourceUrl|$digest"
        } else { Stop-Deployment "unknown skill kind: $kind" }
        $smokeRelative = 'deployment/skill-smoke.tsv'
        if (Test-Path -LiteralPath (Join-Path $Source $smokeRelative)) {
            foreach ($smoke in (Read-Catalog $smokeRelative | Where-Object { $_.columns[0] -eq $name })) {
                if ($smoke.columns.Count -ne 3) { Stop-Deployment "malformed skill smoke row: $name" }
                $smokeScript = [string]$smoke.columns[1]; $smokeArgument = [string]$smoke.columns[2]
                Assert-Relative $smokeScript
                if (-not $smokeArgument -or $smokeArgument -match '\s') { Stop-Deployment "unsafe skill smoke argument: $name" }
                Invoke-Tool node @((Join-Path $destination $smokeScript), $smokeArgument) -Quiet -ShowFailureOutput | Out-Null
            }
        }
    }
    if ($refresh -and $refreshSucceeded) {
        Set-Content -LiteralPath $marker -Value ([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())
    }
    [IO.Directory]::CreateDirectory((Join-Path $roots.state 'dotfiles')) | Out-Null
    Set-Content -LiteralPath (Join-Path $roots.state 'dotfiles/skills.lock.tsv') -Value ($lockRows -join "`n")
    $script:SkillLibrary = $stage
}
function Copy-AgentPayload {
    $script:Step = 'apply-source.agent-payload'
    $disabled = Get-DisabledSkills
    $backup = $null
    $selections = Get-SkillSelections
    $script:SkillWritten = @()
    $script:PreviousManaged = @(Get-ManagedSkillRows)
    foreach ($row in (Read-Catalog 'deployment/agent-payload/discovery-roots.tsv')) {
        $root = [string]$row.columns[0]; Assert-Relative $root
        foreach ($name in $disabled) {
            Assert-Relative $name
            $target = Join-Path $TargetHome "$root/$name"
            Assert-SafePath $target
            if (-not (Test-Path -LiteralPath $target)) { continue }
            if (-not $backup) { $backup = Join-Path $TargetHome ('.local/state/dotfiles/disabled-integrations/skills.' + [Guid]::NewGuid().ToString('N')) }
            $saved = Join-Path $backup "$root/$name"
            Assert-SafePath $saved
            [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($saved)) | Out-Null
            Move-Item -LiteralPath $target -Destination $saved
            Add-Content -LiteralPath (Join-Path $backup 'restore.tsv') -Value "$root/$name|$saved"
        }
    }
    foreach ($row in (Read-Catalog 'deployment/agent-payload/targets.tsv')) {
        $from = Join-Path $Source "deployment/agent-payload/$($row.columns[1])"; $to = Join-Path $TargetHome $row.columns[2]
        if ($row.columns[1] -eq 'skills' -and $script:SkillLibrary) { $from = $script:SkillLibrary }
        if ($row.columns[0] -eq 'block') { Copy-InstructionBlock $from $to }
        elseif ($row.columns[0] -eq 'retire') { Remove-InstructionBlock $to }
        elseif ($row.columns[0] -eq 'tree' -and $row.columns[1] -eq 'skills') {
            [IO.Directory]::CreateDirectory($to) | Out-Null
            foreach ($entry in (Get-ChildItem -LiteralPath $from -Force)) {
                if ($disabled -contains $entry.Name) { continue }
                if (-not (Test-SkillSelected $entry.Name $selections)) { continue }
                Copy-ManagedSkill $entry.FullName (Join-Path $to $entry.Name) $entry.Name $row.columns[2]
            }
        }
        elseif ($row.columns[0] -in @('file', 'tree')) { Copy-RegularTree $from $to }
        else { Stop-Deployment 'unknown agent payload kind' }
    }
    Copy-GeneratedSkills
    Complete-SkillInventory
}
function Merge-ClientSettings {
    $script:Step = 'apply-source.client-settings'
    # The Unix installer alone requests the narrowly scoped model restoration,
    # and only the Unix magpie step requests the gateway wiring.
    $env:DOTFILES_SETTINGS_KEEP_PLAIN_OPUS = '0'
    $env:DOTFILES_SETTINGS_MAGPIE = 'false'
    $stage = Join-Path $env:TEMP ('client-settings-' + [Guid]::NewGuid().ToString('N'))
    [IO.Directory]::CreateDirectory($stage) | Out-Null
    try {
        $clientSettings = @(Get-SelectedClientSettings)
        foreach ($row in $clientSettings) {
            $env:DOTFILES_SETTINGS_FORMAT = $row.columns[0]; $env:DOTFILES_SETTINGS_POLICY = $row.columns[3]
            $env:DOTFILES_SETTINGS_SOURCE = Join-Path $Source "deployment/client-settings/$($row.columns[1])"
            $env:DOTFILES_SETTINGS_TARGET = Join-Path $TargetHome $row.columns[2]
            $env:DOTFILES_SETTINGS_BASELINE = Join-Path $roots.state "dotfiles/client-settings/$($row.columns[3]).json"
            # A policy can own several targets; key the staged file by target.
            $key = $row.columns[2] -replace '[/.]', '_'
            foreach ($kind in @('config', 'baseline')) {
                $env:DOTFILES_SETTINGS_OUTPUT = $kind
                $rendered = Join-Path $stage "$key.$kind"
                try {
                    # Chezmoi writes exact bytes; PowerShell's native stdout
                    # pipeline normalizes line endings and the final newline.
                    Invoke-Tool $script:Chezmoi (@($script:ChezmoiArguments) + @('--output', $rendered, 'execute-template', '--file', (Join-Path $Source 'deployment/client-settings/merge.tmpl'))) -Quiet | Out-Null
                } catch { Stop-Deployment "cannot merge client config ($($row.columns[0])): $($row.columns[2]); check its syntax" }
                Set-Private $rendered
            }
        }
        foreach ($row in $clientSettings) {
            $destination = Join-Path $TargetHome $row.columns[2]
            $baseline = Join-Path $roots.state "dotfiles/client-settings/$($row.columns[3]).json"
            $key = $row.columns[2] -replace '[/.]', '_'
            [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination)) | Out-Null
            [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($baseline)) | Out-Null
            $rendered = Join-Path $stage "$key.config"
            # Preserve the device file and its mtime when the merge is a no-op.
            if (-not [IO.File]::Exists($destination) -or
                (Get-FileHash -LiteralPath $rendered -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash) {
                Move-Item -LiteralPath $rendered -Destination $destination -Force
            }
            Move-Item -LiteralPath (Join-Path $stage "$key.baseline") -Destination $baseline -Force
            Set-Private $destination; Set-Private $baseline
        }
    } finally {
        Remove-Item -LiteralPath $stage -Recurse -Force
        foreach ($name in @('FORMAT', 'POLICY', 'SOURCE', 'TARGET', 'BASELINE', 'OUTPUT', 'KEEP_PLAIN_OPUS', 'MAGPIE')) { [Environment]::SetEnvironmentVariable("DOTFILES_SETTINGS_$name", $null, 'Process') }
    }
}
function Copy-NativeConfiguration {
    $script:Step = 'apply-source.native-discovery'
    # A rendered config directory may also contain device history/plugins.
    # Copy only source-owned files; never replicate those runtime resources.
    foreach ($item in (Get-ChildItem -LiteralPath (Join-Path $Source 'dot_config/nushell') -File)) {
        $filename = $item.Name -replace '\.tmpl$', ''
        Copy-RegularTree (Join-Path $roots.config "nushell/$filename") (Join-Path $roots.appData "nushell/$filename")
    }
    Copy-RegularTree (Join-Path $roots.config 'uv/uv.toml') (Join-Path $roots.appData 'uv/uv.toml')
    Copy-RegularTree (Join-Path $roots.config 'pip/pip.conf') (Join-Path $roots.appData 'pip/pip.ini')
    $environmentScript = "# Process-scoped managed Windows roots.`n"
    foreach ($name in $DeviceEnvironment.Keys) {
        $literal = $DeviceEnvironment[$name].Replace("'", "''")
        $environmentScript += "[Environment]::SetEnvironmentVariable('$name', '$literal', 'Process')`n"
    }
    $environmentScript += '$dotfilesInheritedPath = $env:PATH; $env:PATH = @((Join-Path $env:BUN_INSTALL ''bin''), (Join-Path $env:HOME ''.local/bin''), (Join-Path $env:PIXI_HOME ''bin''), (Join-Path $env:CARGO_HOME ''bin''), (Join-Path $env:XDG_DATA_HOME ''dotfiles/git-bash/bin'')) -join '';''; $env:PATH += '';'' + $dotfilesInheritedPath; Remove-Variable dotfilesInheritedPath' + "`n"
    Write-Utf8 (Join-Path $roots.config 'dotfiles/windows-env.ps1') $environmentScript
    $literalConfig = (Join-Path $roots.config 'dotfiles/windows-env.ps1').Replace("'", "''")
    Write-Utf8 (Join-Path $TargetHome '.local/bin/dotfiles-shell.ps1') (". '$literalConfig'`n" + '& (Join-Path $env:PIXI_HOME ''bin/nu.exe'') @args; exit $LASTEXITCODE' + "`n")
    Write-Utf8 (Join-Path $TargetHome '.local/bin/dotfiles-history.ps1') (". '$literalConfig'`n" + '& (Join-Path $env:PIXI_HOME ''bin/python.exe'') (Join-Path $env:HOME ''.local/lib/dotfiles/history.py'') @args; exit $LASTEXITCODE' + "`n")
    Write-Utf8 (Join-Path $TargetHome '.local/bin/dotfiles-git-bash.ps1') (". '$literalConfig'`n" + '& $env:KIMI_SHELL_PATH --login @args; exit $LASTEXITCODE' + "`n")
    foreach ($name in @('dotfiles-shell', 'dotfiles-history', 'dotfiles-git-bash')) {
        Write-Utf8 (Join-Path $TargetHome ".local/bin/$name.cmd") ("@echo off`r`npowershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File `"%~dp0$name.ps1`" %*`r`nexit /b %errorlevel%`r`n")
    }
}
function Set-ChezmoiArguments([string]$ConfigDirectory = (Join-Path $roots.config 'chezmoi')) {
    $script:ChezmoiArguments = @('--source', $Source, '--destination', $TargetHome, '--config', (Join-Path $ConfigDirectory 'chezmoi.toml'), '--cache', (Join-Path $roots.cache 'chezmoi'), '--persistent-state', (Join-Path $ConfigDirectory 'chezmoistate.boltdb'), '--no-tty', '--force')
}
function Initialize-Chezmoi {
    Invoke-Tool $script:Chezmoi (@($script:ChezmoiArguments) + @('init', '--data=false')) -Quiet | Out-Null
}
function Test-ManagedGitBashEnvironment([string]$Existing, [string]$Rendered) {
    $existingText = $Existing.Replace("`r`n", "`n")
    $renderedText = $Rendered.Replace("`r`n", "`n").TrimEnd("`n")
    # A targeted update can select a different host role. The two generated
    # polling values are safe and the full apply still owns changing them.
    $roleDefault = '(?m)^: "\$\{CHOKIDAR_USEPOLLING:=[01]\}"$'
    $existingText = $existingText -creplace $roleDefault, ': "${CHOKIDAR_USEPOLLING:=0}"'
    $renderedText = $renderedText -creplace $roleDefault, ': "${CHOKIDAR_USEPOLLING:=0}"'
    if (-not $renderedText -or -not $existingText.StartsWith($renderedText, [StringComparison]::Ordinal)) {
        return $false
    }
    # Appended blank lines and comments do not change the generated program.
    # Any other edit could stop or redirect the launcher before it runs Pi,
    # even when the file passes Bash's syntax check.
    return $existingText.Substring($renderedText.Length) -cmatch '\A(?:\n[ \t]*(?:#[^\n\r]*)?)*\z'
}
function Prepare-AgentUpdate {
    $script:TargetedRenderDirectory = Get-Scratch 'agent-render'
    Set-Private $script:TargetedRenderDirectory
    Set-ChezmoiArguments $script:TargetedRenderDirectory
    Initialize-Chezmoi
    if ($script:TargetedAgent -eq 'qoder') { return }
    $shellEnvironment = Join-Path $TargetHome '.env_core'
    # The Git Bash companions source this at runtime. Repair a missing
    # prerequisite but do not overwrite an existing device file.
    if (-not [IO.File]::Exists($shellEnvironment)) {
        if ([IO.Directory]::Exists($shellEnvironment)) { Stop-Deployment '.env_core is a directory; repair the Git Bash environment before updating' }
        Invoke-Tool $script:Chezmoi (@($script:ChezmoiArguments) + @('apply', $shellEnvironment)) -Quiet | Out-Null
    }
    $gitBash = Join-Path $roots.data 'dotfiles/git-bash/bin/bash.exe'
    Assert-SafePath $gitBash
    if (-not [IO.File]::Exists($gitBash)) { Stop-Deployment 'managed Git Bash is missing; run full bootstrap before updating' }
    $rendered = Join-Path $script:TargetedRenderDirectory 'env_core.expected'
    Invoke-Tool $script:Chezmoi (@($script:ChezmoiArguments) + @('--output', $rendered, 'cat', $shellEnvironment)) -Quiet | Out-Null
    $savedFailureCode = $script:FailureCode
    try {
        if (-not (Test-ManagedGitBashEnvironment ([IO.File]::ReadAllText($shellEnvironment)) ([IO.File]::ReadAllText($rendered)))) {
            throw 'shell environment differs from the generated script'
        }
        Invoke-Tool $gitBash @('--noprofile', '--norc', '-p', '-n', $shellEnvironment.Replace('\', '/')) -Quiet | Out-Null
    } catch {
        Stop-Deployment '.env_core failed the Git Bash check; preserve local shell inputs in .config/dotfiles/env.local.sh and restore the managed environment before updating'
    } finally {
        $script:FailureCode = $savedFailureCode
    }
}
function Apply-Source {
    $script:Step = 'apply-source'
    Set-ChezmoiArguments
    Initialize-Chezmoi
    Invoke-Tool $script:Chezmoi (@($script:ChezmoiArguments) + @('apply')) -Quiet | Out-Null
    Import-SkillLibrary
    Copy-AgentPayload
    Merge-ClientSettings
    Copy-NativeConfiguration
}
function Get-AssetString($Record, [string]$Field) {
    if ($null -eq $Record) { Stop-Deployment "missing Windows asset record for field: $Field" }
    $value = $Record.$Field
    if ($null -eq $value) { Stop-Deployment "missing Windows asset field: $Field" }
    while ($value -is [Array]) {
        if ($value.Count -ne 1) { Stop-Deployment "Windows asset field is not a scalar: $Field" }
        $value = $value[0]
    }
    if ($value -isnot [string] -or -not $value) { Stop-Deployment "Windows asset field is not a string: $Field" }
    return $value
}
function Get-Asset([string]$Name) {
    $records = New-Object System.Collections.ArrayList
    $pending = New-Object System.Collections.Stack
    $pending.Push($exceptions)
    while ($pending.Count -gt 0) {
        $candidate = $pending.Pop()
        if ($candidate -is [Array]) {
            foreach ($item in $candidate) { $pending.Push($item) }
        } else { [void]$records.Add($candidate) }
    }
    $asset = @($records.ToArray() | Where-Object { $_.name -eq $Name })
    if ($asset.Count -ne 1) { Stop-Deployment "missing pinned Windows asset: $Name" }
    $record = $asset[0]
    return [pscustomobject]@{
        name = (Get-AssetString $record 'name')
        version = (Get-AssetString $record 'version')
        url = (Get-AssetString $record 'url')
        sha256 = (Get-AssetString $record 'sha256')
        kind = (Get-AssetString $record 'kind')
        entry = (Get-AssetString $record 'entry')
        target = (Get-AssetString $record 'target')
    }
}
function Get-Pin([string]$Name) {
    foreach ($row in (Read-Catalog 'deployment/common-tools.tsv')) {
        foreach ($spec in $row.columns[1].Split(',')) {
            if ($spec.StartsWith($Name + '==')) { return $spec.Substring($Name.Length + 2) }
        }
    }
    Stop-Deployment "missing common runtime pin: $Name"
}
function Get-Scratch([string]$Name) {
    $directory = Join-Path $env:TEMP ($Name + '-' + [Guid]::NewGuid().ToString('N'))
    Assert-SafePath $directory
    [IO.Directory]::CreateDirectory($directory) | Out-Null
    return $directory
}
function Download-Verified($Asset, [string]$Destination) {
    $url = Get-AssetString $Asset 'url'
    $sha256 = Get-AssetString $Asset 'sha256'
    if ($url -notmatch '^https://' -or $sha256 -notmatch '^[a-f0-9]{64}$') { Stop-Deployment "installer catalog requires HTTPS and a pinned SHA-256: $($Asset.name)" }
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    for ($attempt = 0; $attempt -lt 3; $attempt++) {
        try { Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $Destination -TimeoutSec 180; break }
        catch { if ($attempt -eq 2) { Stop-Deployment "cannot download required pinned asset: $($Asset.name)" } }
    }
    $actual = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $sha256) { Stop-Deployment "SHA-256 mismatch for $($Asset.name); payload was not executed" }
}
function Expand-VerifiedZip([string]$Archive, [string]$Directory) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($Archive)
    try {
        foreach ($entry in $zip.Entries) {
            Assert-Relative $entry.FullName
            $destination = [IO.Path]::GetFullPath((Join-Path $Directory $entry.FullName))
            if (-not $destination.StartsWith($Directory + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { Stop-Deployment 'archive entry is outside the managed extraction directory' }
            if ($entry.FullName.EndsWith('/')) { [IO.Directory]::CreateDirectory($destination) | Out-Null }
            else {
                [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination)) | Out-Null
                [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $destination, $true)
            }
        }
    } finally { $zip.Dispose() }
}
function Test-AssetVersion($Asset, [string]$Diagnostic) {
    $prefix = switch ($Asset.name) {
        'bun' { '' }
        'jq' { 'jq-' }
        'git-bash' { 'git version ' }
        'chezmoi' { 'chezmoi version v' }
        default { $Asset.name + ' ' }
    }
    # Match the tool's complete version token. Comma/whitespace delimit native
    # build metadata; a longer version or prerelease must not satisfy the pin.
    $pattern = '(?m)^' + [regex]::Escape($prefix + $Asset.version) + '(?=[\s,]|$)'
    return $Diagnostic.Trim() -cmatch $pattern
}
# The recovery directory carries this marker, so the deployment can prove
# that the directory it finds beside the installation path is its own. A
# sibling entry without the marker belongs to the device: it is never
# deleted and never restored as a runtime.
$script:PortableGitRecoveryMarker = '.dotfiles-portablegit-recovery'
$script:PortableGitRecoveryToken = 'dotfiles portablegit recovery v1'
# Whether the marker inside the directory is the deployment's own. A link is
# never followed: reading through it would read a device file and claim a
# recovery tree the deployment does not own.
function Test-PortableGitRecoveryMarker([string]$Path) {
    $marker = Join-Path $Path $script:PortableGitRecoveryMarker
    if (Test-ReparsePath $marker) { return $false }
    if (-not [IO.File]::Exists($marker)) { return $false }
    try { return ([IO.File]::ReadAllText($marker).Trim() -eq $script:PortableGitRecoveryToken) }
    catch { return $false }
}
function Test-PortableGitRecovery([string]$Path) {
    if (-not [IO.Directory]::Exists($Path)) { return $false }
    if (Test-ReparsePath $Path) { return $false }
    return (Test-PortableGitRecoveryMarker $Path)
}
# Mark the runtime that is about to move aside, so an interrupted
# publication leaves a recovery directory the deployment owns.
function Set-PortableGitRecovery([string]$Path) {
    $marker = Join-Path $Path $script:PortableGitRecoveryMarker
    if (Test-ReparsePath $marker) { Stop-Deployment "the PortableGit recovery marker is a symlink or reparse point: $marker" }
    # A device entry that carries the marker's name is never overwritten:
    # the deployment could no longer prove it owns the recovery tree, so it
    # stops and leaves the entry alone.
    if ((Test-Path -LiteralPath $marker) -and -not (Test-PortableGitRecoveryMarker $Path)) {
        Stop-Deployment "the PortableGit recovery marker is occupied by an entry the deployment does not own: $marker"
    }
    [IO.File]::WriteAllText($marker, $script:PortableGitRecoveryToken)
}
# The marker belongs to the recovery directory, not to an active runtime. Only
# an owned marker is removed: a device file that carries the marker's name
# is left alone.
function Clear-PortableGitRecovery([string]$Path) {
    if (-not (Test-PortableGitRecoveryMarker $Path)) { return $false }
    Remove-Item -LiteralPath (Join-Path $Path $script:PortableGitRecoveryMarker) -Force
    return $true
}
# Remove a recovery directory the deployment owns. An entry it cannot prove
# it owns is preserved and reported by the caller.
function Remove-OwnedPortableGitRecovery([string]$Path) {
    if (-not (Test-PortableGitRecovery $Path)) { return $false }
    Remove-ReplacedTree $Path | Out-Null
    return $true
}
# Restore the previous runtime after a failed or interrupted publication.
# Only an owned recovery directory is restored, so a device entry is never
# adopted as the runtime.
function Restore-PortableGitRecovery([string]$Previous, [string]$Target) {
    if (-not (Test-PortableGitRecovery $Previous)) { return $false }
    Move-Item -LiteralPath $Previous -Destination $Target
    Clear-PortableGitRecovery $Target | Out-Null
    return $true
}
# Recover the last runtime the deployment verified. The marked recovery
# directory becomes the active runtime again, and an unverified candidate at
# the installation path is discarded, so the device keeps a usable Git Bash
# while the new runtime is staged. An entry the deployment does not own is
# left alone.
function Recover-PortableGitRecovery([string]$Previous, [string]$Target) {
    if (-not (Test-PortableGitRecovery $Previous)) { return $false }
    if ([IO.Directory]::Exists($Target)) { Remove-ReplacedTree $Target }
    Restore-PortableGitRecovery $Previous $Target | Out-Null
    return $true
}
# PortableGit is a 7-Zip SFX archive. It extracts into a clean directory, so
# the staged runtime never merges with the active one.
function Expand-PortableGitArchive([string]$Archive, [string]$Destination) {
    Assert-SafePath $Destination
    [IO.Directory]::CreateDirectory($Destination) | Out-Null
    $argumentLine = '-o"' + $Destination + '" -y'
    $process = Start-Process -FilePath $Archive -ArgumentList $argumentLine -Wait -PassThru -WindowStyle Hidden
    if ($process.ExitCode) { $script:FailureCode = $process.ExitCode; Stop-Deployment 'required command failed' }
}
# Whether the installation at the path is the verified runtime of this pin.
# Every launcher must be a regular file and git must report the pinned
# version: an incomplete runtime is not a reuse, so it is replaced and the
# recovery backup it holds is not discarded. A probe that cannot run is not
# a reuse either: the staged install replaces it.
function Test-PortableGitRuntime($Asset, [string]$Target) {
    if (-not (Test-PortableGitLaunchers $Target)) { return $false }
    $diagnostic = Join-Path $Target 'bin/git.exe'
    $savedFailureCode = $script:FailureCode
    try { $version = Invoke-Tool $diagnostic @('--version') -Quiet }
    catch { $version = '' }
    finally { $script:FailureCode = $savedFailureCode }
    return (Test-AssetVersion $Asset $version)
}
# Replace the active runtime with the verified staged one. The previous
# runtime moves aside first, so a failed publication restores it instead of
# leaving the device without a usable Git Bash.
function Publish-PortableGit($Asset, [string]$Staging, [string]$Target, [string]$Previous) {
    # The recovery path holds a runtime the deployment moved aside, or
    # nothing. A device entry there is never deleted and never restored.
    $owned = Test-PortableGitRecovery $Previous
    if ([IO.Directory]::Exists($Target)) {
        # The recovery path must be free or owned. An unknown sibling entry
        # belongs to the device, so it is preserved and the publication
        # stops instead of deleting it.
        if ((Test-Path -LiteralPath $Previous) -and -not $owned) {
            Stop-Deployment "the PortableGit recovery path is occupied by an entry the deployment does not own: $Previous; move it aside to upgrade"
        }
        if ($owned) {
            # The marked recovery is the last runtime the deployment
            # verified. It stays the rollback source until the new runtime
            # is verified, so the known-good tree is never deleted before
            # its replacement is proven, and the unverified candidate at
            # the installation path is the one that is replaced.
            Remove-ReplacedTree $Target
        } else {
            # The runtime is marked before it moves aside, so an interrupted
            # publication leaves a recovery directory the deployment owns.
            Set-PortableGitRecovery $Target
            Move-Item -LiteralPath $Target -Destination $Previous
        }
    }
    # The rollback source is the marked recovery directory, if there is one.
    $rollback = Test-PortableGitRecovery $Previous
    try {
        Move-Item -LiteralPath $Staging -Destination $Target
        Assert-PortableGitLaunchers $Target
        $version = Invoke-Tool (Join-Path $Target 'bin/git.exe') @('--version') -Quiet
        if (-not (Test-AssetVersion $Asset $version)) { Stop-Deployment 'the published PortableGit runtime did not report its pinned version' }
    } catch {
        # The previous runtime is restored, so the device keeps a usable Git
        # Bash and a retry starts from a known state.
        if (Test-Path -LiteralPath $Target) { Remove-ReplacedTree $Target }
        if ($rollback) { Restore-PortableGitRecovery $Previous $Target | Out-Null }
        throw
    }
    if ($rollback) { Remove-ReplacedTree $Previous }
}
# The PortableGit lifecycle. The same pin reuses the verified installation.
# Another pin is staged, verified, and published with a recovery to the
# previous runtime. The vendor links inside the tree are the vendor's own
# files, so they do not prevent the upgrade; a substituted destination or
# parent path is still refused.
function Install-PortableGit($Asset, [string]$Target) {
    $script:Step = 'install-managers.git-bash'
    Assert-PortableGitLauncherPaths $Target
    if ([IO.File]::Exists($Target)) { Stop-Deployment 'a file occupies the PortableGit installation path' }
    # The marker belongs to a recovery directory. An active runtime that
    # still carries an owned one was interrupted before it moved aside; a
    # device file that carries the marker's name is left alone.
    if ([IO.Directory]::Exists($Target)) { Clear-PortableGitRecovery $Target | Out-Null }
    $previous = Join-Path ([IO.Path]::GetDirectoryName($Target)) '.git-bash.previous'
    if (Test-PortableGitRuntime $Asset $Target) {
        # The same pin reuses its verified installation. A retained recovery
        # directory is stale once the active one is verified, but only an
        # owned one is removed: an unknown sibling entry stays untouched.
        Remove-OwnedPortableGitRecovery $previous | Out-Null
        return
    }
    # An interrupted publication left the recovery directory beside the
    # installation path. It is recovered first, so the device keeps a usable
    # Git Bash while the new runtime is staged and a failed publication
    # restores it again. Only an owned recovery directory is recovered; an
    # unknown sibling entry is preserved.
    Recover-PortableGitRecovery $previous $Target | Out-Null
    if (Test-PortableGitRuntime $Asset $Target) {
        # The recovered runtime is the pinned one: it is reused as it is.
        return
    }
    $scratch = Get-Scratch 'git-bash'
    try {
        $archive = Join-Path -Path $scratch -ChildPath ([string]$Asset.entry)
        Download-Verified $Asset $archive
        $script:Step = 'install-managers.git-bash.extract'
        $staging = Join-Path $scratch 'staging'
        Expand-PortableGitArchive $archive $staging
        # The staged runtime exposes every launcher as a regular file and
        # reports the pinned version before it replaces the active runtime.
        Assert-PortableGitLaunchers $staging
        $script:Step = 'install-managers.git-bash.verify'
        $version = Invoke-Tool (Join-Path $staging 'bin/git.exe') @('--version') -Quiet
        if (-not (Test-AssetVersion $Asset $version)) { Stop-Deployment 'installed git-bash did not report its pinned version' }
        $script:Step = 'install-managers.git-bash.publish'
        Publish-PortableGit $Asset $staging $Target $previous
    } finally { Remove-ReplacedTree $scratch }
}
function Install-Asset([string]$Name) {
    $asset = Get-Asset $Name
    $assetTarget = [string]$asset.target
    $target = Join-Path -Path $TargetHome -ChildPath $assetTarget
    Assert-SafePath $target
    if ($Name -eq 'git-bash') {
        # PortableGit owns its own lifecycle: the same-pin reuse, the staged
        # upgrade, and the recovery to the previous runtime.
        Install-PortableGit $asset $target
        return
    }
    $diagnostic = $target
    if ($Name -eq 'helix') { $diagnostic = Join-Path $target 'hx.exe' }
    if ([IO.File]::Exists($diagnostic)) {
        $version = Invoke-Tool $diagnostic @('--version') -Quiet
        if (Test-AssetVersion $asset $version) { return }
    }
    $script:Step = "install-managers.$Name"
    $scratch = Get-Scratch $Name
    try {
        $archive = Join-Path -Path $scratch -ChildPath ([string]$asset.entry)
        if ($asset.kind -in @('zip', 'helix')) { $archive += '.zip' }
        Download-Verified $asset $archive
        if ($asset.kind -in @('zip', 'helix')) {
            $extracted = Join-Path $scratch 'payload'
            Expand-VerifiedZip $archive $extracted
            $files = @(Get-ChildItem -LiteralPath $extracted -Filter $asset.entry -Recurse -File)
            if ($files.Count -ne 1) { Stop-Deployment "required archive entry not found: $Name" }
            if ($asset.kind -eq 'helix') { Copy-RegularTree $files[0].DirectoryName $target }
            else { Copy-RegularTree $files[0].FullName $target }
        } elseif ($asset.kind -eq 'portable-git') {
            Stop-Deployment 'a portable-git asset is installed by the PortableGit lifecycle'
        } elseif ($asset.kind -eq 'rustup') {
            Invoke-Tool $archive @('-y', '--no-modify-path', '--default-toolchain', 'none', '--profile', 'minimal') -Quiet | Out-Null
        } elseif ($asset.kind -eq 'exe') { Copy-RegularTree $archive $target }
        else { Stop-Deployment 'unknown Windows asset type' }
        $script:Step = "install-managers.$Name.verify"
        $version = Invoke-Tool $diagnostic @('--version') -Quiet
        if (-not (Test-AssetVersion $asset $version)) { Stop-Deployment "installed $Name did not report its pinned version" }
    } finally { Remove-Item -LiteralPath $scratch -Recurse -Force }
}
function Install-Managers {
    $script:Step = 'install-managers.chezmoi'
    $script:Chezmoi = Get-Input 'DOTFILES_CHEZMOI_BIN'
    if ($script:Chezmoi) {
        if (-not [IO.Path]::IsPathRooted($script:Chezmoi) -or -not [IO.File]::Exists($script:Chezmoi)) { Stop-Deployment 'Chezmoi override must be an absolute executable file' }
    } else {
        Install-Asset 'chezmoi'
        $script:Chezmoi = Join-Path $TargetHome '.local/bin/chezmoi.exe'
    }
    if (-not $ApplyOnly -and -not $AgentsOnly) {
        $script:Pixi = Get-Input 'DOTFILES_PIXI_BIN'
        if ($script:Pixi) {
            $version = Invoke-Tool $script:Pixi @('--version') -Quiet
            if ($version.Trim() -ne ('pixi ' + (Get-Asset 'pixi').version)) { Stop-Deployment 'Pixi override must match the pinned version' }
        } else {
            Install-Asset 'pixi'
            $script:Pixi = Join-Path $roots.pixi 'bin/pixi.exe'
        }
    }
}
function Install-Common {
    $script:Step = 'install-common.merge-manifest'
    Invoke-Tool $script:Pixi @('exec', '--spec', ('python==' + (Get-Pin 'python')), 'python', (Join-Path $Source 'deployment/merge_pixi.py'), (Join-Path $roots.config 'dotfiles/pixi-global.toml'), (Join-Path $roots.config 'dotfiles/pixi-bundles.toml'), (Join-Path $roots.pixi 'manifests/pixi-global.toml')) -Quiet | Out-Null
    $script:Step = 'install-common.pixi-sync'
    Invoke-Tool $script:Pixi @('global', 'sync') -Quiet | Out-Null
    foreach ($name in @('bun', 'atuin', 'git-bash', 'helix', 'jq', 'rustup')) { Install-Asset $name }
    Copy-RegularTree (Join-Path $roots.bun 'bin/bun.exe') (Join-Path $roots.pixi 'bin/bun.exe')
    Copy-RegularTree (Join-Path $roots.data 'dotfiles/helix/hx.exe') (Join-Path $roots.pixi 'bin/hx.exe')
    $env:HELIX_RUNTIME = Join-Path $roots.data 'dotfiles/helix/runtime'
    foreach ($directory in @((Join-Path $roots.bun 'bin'), (Join-Path $roots.pixi 'bin'))) {
        Write-Utf8 (Join-Path $directory 'bunx.cmd') "@echo off`r`n`"%~dp0bun.exe`" x %*`r`nexit /b %errorlevel%`r`n"
        Write-Utf8 (Join-Path $directory 'bunx') ('#!/bin/sh' + "`n" + 'exec "$(dirname -- "$0")/bun.exe" x "$@"' + "`n")
    }
    $script:Step = 'install-common.verify-exposure'
    foreach ($package in @($packages) + @($bundlePackages)) {
        foreach ($command in $package.exposed.Keys) {
            $exe = Join-Path $roots.pixi "bin/$command.exe"; $cmd = Join-Path $roots.pixi "bin/$command.cmd"
            if (-not [IO.File]::Exists($exe) -and -not [IO.File]::Exists($cmd)) { Stop-Deployment "required command not exposed by Pixi: $command" }
        }
    }
}
function Get-ManagedWindowsLauncherTarget([string]$Path) {
    $text = [IO.File]::ReadAllText($Path)
    if ($text.Length -gt 8192) { return }
    if ($Path.EndsWith('.cmd', [StringComparison]::OrdinalIgnoreCase)) {
        $grammar = '\A@echo off\r?\n(?:rem Managed by dotfiles;\r?\n)?(?:setlocal DisableDelayedExpansion\r?\n"(?<node>(?:[^"%\r\n]|%%)+)" )?"(?<target>[^"\r\n]+)" %\*\r?\nexit /b %errorlevel%\r?\n\z'
        $match = [regex]::Match($text, $grammar)
        if (-not $match.Success) { return }
        $target = $match.Groups['target'].Value
        $relativePrefix = '%~dp0..\..\'
        if ($target.StartsWith($relativePrefix)) {
            $relativeTarget = $target.Substring($relativePrefix.Length)
            if ($relativeTarget -and $relativeTarget -notmatch '%|(^|[\\/])\.\.([\\/]|$)' -and
                -not [IO.Path]::IsPathRooted($relativeTarget)) {
                return [pscustomobject]@{ target = $relativeTarget; relative = $true }
            }
            return
        }
        if (-not $match.Groups['node'].Success -and $target -notmatch '%' -and [IO.Path]::IsPathRooted($target)) {
            return [pscustomobject]@{ target = $target; relative = $false }
        }
        return
    }
    $quoted = @'
'(?:[^'\r\n]|'"'"')*'
'@
    $device = 'dotfiles_device=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd) || exit 1'
    $relative = [regex]::Escape($device) + '\r?\n\. "\$dotfiles_device/\.env_core"\r?\nexec (?:' +
        $quoted + ' )?"\$dotfiles_device/"(?<target>' + $quoted + ') "\$@"\r?\n'
    $absolute = 'exec (?<target>' + $quoted + ') "\$@"\r?\n'
    $match = [regex]::Match($text, '\A#!/bin/sh\r?\n(?:# Managed by dotfiles;\r?\n)?(?:(?<relative>' +
        $relative + ')|' + $absolute + ')\z')
    if ($match.Success) {
        $target = $match.Groups['target'].Value
        $apostrophe = [string][char]39
        $escaped = $apostrophe + '"' + $apostrophe + '"' + $apostrophe
        $target = $target.Substring(1, $target.Length - 2).Replace($escaped, $apostrophe)
        $isRelative = $match.Groups['relative'].Success
        if ($isRelative -and ($target -match '(^|[\\/])\.\.([\\/]|$)' -or [IO.Path]::IsPathRooted($target))) { return }
        return [pscustomobject]@{ target = $target; relative = $isRelative }
    }
}

function Assert-AgentLauncher([string]$Path, [string]$OldTarget) {
    Assert-SafePath $Path
    if ([IO.Directory]::Exists($Path)) { Stop-Deployment "agent launcher is a directory: $Path" }
    if (-not [IO.File]::Exists($Path)) { return }
    $existing = Get-ManagedWindowsLauncherTarget $Path
    $expected = if ($OldTarget.StartsWith('/.bun/')) { $OldTarget.TrimStart('/') }
                else { $TargetHome.Replace('\', '/') + $OldTarget }
    if (-not $existing -or -not $existing.target.Replace('\', '/').StartsWith($expected, [StringComparison]::OrdinalIgnoreCase) -or
        ($existing.relative -ne $OldTarget.StartsWith('/.bun/'))) {
        Stop-Deployment "agent launcher would replace a device file: $Path"
    }
}

function Write-AgentLauncher([string]$Path, [string]$Text) {
    if ($script:TargetedAgent) {
        # Mark targeted replacements so a later repair can recognize them
        # even if the command is broken. The assertion also accepts older
        # launchers that point into the selected managed package.
        $cmd = $Path.EndsWith('.cmd', [StringComparison]::OrdinalIgnoreCase)
        $header = if ($cmd) { '@echo off' } else { '#!/bin/sh' }
        $marker = if ($cmd) { 'rem Managed by dotfiles;' } else { '# Managed by dotfiles;' }
        $eol = if ($cmd) { "`r`n" } else { "`n" }
        $Text = $Text.Insert($header.Length + $eol.Length, $marker + $eol)
    }
    Write-Utf8 $Path $Text
}

function Install-Qoder([string]$Version, [string]$ManifestBase) {
    $root = Join-Path $TargetHome '.qoder'
    $cli = Join-Path $root "bin/qodercli/qodercli-$Version.exe"
    Assert-SafePath $cli
    $cachedValid = $false
    if ([IO.File]::Exists($cli)) {
        $script:Step = 'install-agents.qoder.cached-version'
        $savedFailureCode = $script:FailureCode
        try { $cachedValid = (Invoke-Tool $cli @('--version') -Quiet).Trim() -ceq $Version }
        catch { $cachedValid = $false }
        finally { $script:FailureCode = $savedFailureCode }
    }
    if (-not $cachedValid) {
        $script:Step = 'install-agents.qoder.manifest'
        $manifestUrl = "$ManifestBase/$Version/manifest.json"
        if ($manifestUrl -notmatch '^https://') { Stop-Deployment 'Qoder manifest must use HTTPS' }
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $manifest = Invoke-RestMethod -Uri $manifestUrl -UseBasicParsing
        if ("$($manifest.latest)" -ne $Version) { Stop-Deployment "Qoder manifest did not advertise the pinned version $Version" }
        $build = [Environment]::OSVersion.Version.Build
        $candidates = @($manifest.files | Where-Object { $_.os -eq 'windows' -and $_.arch -in @('amd64', 'x64') })
        $file = $candidates | Where-Object {
            # Optional fields can be absent altogether, including the upper
            # build bound on the pinned standard archive.
            $metadata = $_ | Select-Object variant, runtime, min_windows_build, max_windows_build
            $metadata.variant -ne 'legacy' -and $metadata.runtime -ne 'node-sea' -and
            (-not $metadata.min_windows_build -or $build -ge [int]$metadata.min_windows_build) -and
            (-not $metadata.max_windows_build -or $build -le [int]$metadata.max_windows_build)
        } | Select-Object -First 1
        if (-not $file) { $file = $candidates | Select-Object -First 1 }
        if (-not $file) { Stop-Deployment 'Qoder has no Windows x64 release for the pinned version' }
        if ("$($file.url)" -notmatch '^https://' -or "$($file.sha256)" -notmatch '^[a-f0-9]{64}$') {
            Stop-Deployment 'Qoder manifest requires HTTPS and a pinned SHA-256'
        }
        $scratch = Get-Scratch 'qoder'
        try {
            $script:Step = 'install-agents.qoder.download'
            $archive = Join-Path $scratch 'qodercli.zip'
            Invoke-WebRequest -UseBasicParsing -Uri $file.url -OutFile $archive -TimeoutSec 300
            $actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($actual -ne $file.sha256) { Stop-Deployment 'Qoder SHA-256 mismatch; payload was not executed' }
            $script:Step = 'install-agents.qoder.extract'
            $extracted = Join-Path $scratch 'payload'
            Expand-VerifiedZip $archive $extracted
            $binary = Join-Path $extracted 'qodercli.exe'
            if (-not [IO.File]::Exists($binary)) { Stop-Deployment 'Qoder archive did not contain qodercli.exe' }
            $script:Step = 'install-agents.qoder.verify'
            $diagnostic = Invoke-Tool $binary @('--version') -Quiet
            if ($diagnostic.Trim() -cne $Version) { Stop-Deployment 'downloaded Qoder did not report its pinned version' }
            $script:Step = 'install-agents.qoder.install'
            Copy-RegularTree $binary $cli
        } finally {
            Remove-Item -LiteralPath $scratch -Recurse -Force -ErrorAction SilentlyContinue
        }
        if (-not [IO.File]::Exists($cli)) { Stop-Deployment "Qoder installation did not place $cli" }
    }
    foreach ($relative in @('.local/bin', '.bun/bin')) {
        Assert-SafePath (Join-Path $TargetHome $relative)
        [IO.Directory]::CreateDirectory((Join-Path $TargetHome $relative)) | Out-Null
    }
    foreach ($name in @('qodercli', 'qoder')) {
        $targetPath = $cli
        foreach ($relative in @('.local/bin', '.bun/bin')) {
            $launcher = Join-Path $TargetHome "$relative/$name.cmd"
            Write-AgentLauncher $launcher ("@echo off`r`n" + '"' + $targetPath + '" %*' + "`r`nexit /b %errorlevel%`r`n")
            $singleQuote = [string][char]39; $doubleQuote = [string][char]34
            $posixPath = $targetPath.Replace('\', '/')
            $quoted = $singleQuote + $posixPath.Replace($singleQuote, ($singleQuote + $doubleQuote + $singleQuote + $doubleQuote + $singleQuote)) + $singleQuote
            $posix = '#!/bin/sh' + "`n" + 'exec ' + $quoted + ' "$@"' + "`n"
            Write-AgentLauncher (Join-Path $TargetHome "$relative/$name") $posix
        }
    }
    $script:Step = 'install-agents.qoder.diagnostic'
    foreach ($name in @('qoder', 'qodercli')) {
        $diagnostic = Invoke-Tool (Join-Path $TargetHome ".local/bin/$name.cmd") @('--version') -Quiet
        [Console]::Out.Write($diagnostic)
        if ($diagnostic.Trim() -cne $Version) { Stop-Deployment "$name diagnostic did not report its pinned version" }
    }
}

function Test-WindowsX64Executable([string]$Path) {
    if (-not [IO.File]::Exists($Path) -or ([IO.File]::GetAttributes($Path) -band [IO.FileAttributes]::ReparsePoint)) { return $false }
    $reader = New-Object IO.BinaryReader([IO.File]::OpenRead($Path))
    try {
        if ($reader.BaseStream.Length -lt 64 -or $reader.ReadUInt16() -ne 0x5A4D) { return $false }
        $reader.BaseStream.Position = 0x3C
        $header = $reader.ReadInt32()
        if ($header -lt 64 -or $header -gt ($reader.BaseStream.Length - 6)) { return $false }
        $reader.BaseStream.Position = $header
        return $reader.ReadUInt32() -eq 0x00004550 -and $reader.ReadUInt16() -eq 0x8664
    } finally { $reader.Dispose() }
}

function Get-BunAgentEntry($Row, [string]$Project, [string]$Command) {
    $packagePath = 'node_modules/' + $Row.package
    $packageDirectory = Join-Path $Project $packagePath
    $claude = $Row.package -ceq '@anthropic-ai/claude-code' -and $Command -ceq 'claude'
    $metadata = Join-Path $packageDirectory 'package.json'
    if ($claude) {
        Assert-SafePath $packageDirectory
        if ([IO.File]::GetAttributes($metadata) -band [IO.FileAttributes]::ReparsePoint) {
            Stop-Deployment 'Claude wrapper metadata must be a regular file'
        }
    }
    $package = [IO.File]::ReadAllText($metadata) | ConvertFrom-Json
    if ($claude) {
        # This npm wrapper advertises bin/claude.exe even when it still
        # contains the shell stub shipped in its tarball. The frozen project
        # also installs the pinned platform package that the wrapper uses.
        $platformName = '@anthropic-ai/claude-code-win32-x64'
        $optionalPin = $package.optionalDependencies.PSObject.Properties[$platformName]
        if ($package.name -cne $Row.package -or $package.version -cne $Row.version -or
            -not $optionalPin -or $optionalPin.Value -cne $Row.version) {
            Stop-Deployment 'Claude does not declare its pinned Windows x64 package'
        }
        $platformPaths = @(('node_modules/' + $platformName), ($packagePath + '/node_modules/' + $platformName))
        $installed = @($platformPaths | Where-Object { [IO.Directory]::Exists((Join-Path $Project $_)) })
        if ($installed.Count -ne 1) { Stop-Deployment 'Claude requires one pinned Windows x64 package in its frozen Bun project' }
        $platformDirectory = Join-Path $Project $installed[0]
        Assert-SafePath $platformDirectory
        $platformMetadata = Join-Path $platformDirectory 'package.json'
        if ([IO.File]::GetAttributes($platformMetadata) -band [IO.FileAttributes]::ReparsePoint) {
            Stop-Deployment 'Claude Windows x64 package metadata must be a regular file'
        }
        $nativePackage = [IO.File]::ReadAllText($platformMetadata) | ConvertFrom-Json
        if ($nativePackage.name -cne $platformName -or $nativePackage.version -cne $Row.version -or
            'win32' -cnotin $nativePackage.os -or 'x64' -cnotin $nativePackage.cpu) {
            Stop-Deployment 'Claude Windows x64 package does not match the pinned version and target'
        }
        if (-not (Test-WindowsX64Executable (Join-Path $platformDirectory 'claude.exe'))) {
            Stop-Deployment 'Claude Windows x64 package does not contain a Windows x64 PE executable'
        }
        return $installed[0] + '/claude.exe'
    }
    $entry = if ($package.bin -is [string]) { $package.bin } else { $package.bin.$Command }
    Assert-Relative $entry
    return $packagePath + '/' + $entry
}

function Test-AgentVersion([string]$Output, [string]$Version) {
    $line = ($Output -split '\r?\n', 2)[0]
    $token = '(?<![A-Za-z0-9._+\-])v?' + [regex]::Escape($Version) + '(?![A-Za-z0-9._+\-])'
    return [regex]::IsMatch($line, $token)
}

function Test-BunAgentEntries($Row, [string]$Project, [string]$Node) {
    $savedFailureCode = $script:FailureCode
    try {
        foreach ($command in $Row.commands.Split(',')) {
            $entry = Get-BunAgentEntry $Row $Project $command
            $executable = Join-Path $Project $entry
            if (-not [IO.File]::Exists($executable)) { return $false }
            $output = if ($entry.EndsWith('.exe', [StringComparison]::OrdinalIgnoreCase)) {
                Invoke-Tool $executable @('--version') -Quiet
            } else {
                Invoke-Tool $Node @($executable, '--version') -Quiet
            }
            if (-not (Test-AgentVersion $output $Row.version)) { return $false }
        }
        return $true
    } catch {
        return $false
    } finally {
        $script:FailureCode = $savedFailureCode
    }
}

function Install-Agents {
    $script:Step = 'install-agents.runtime'
    $statePath = Join-Path (Get-DotfilesStateRoot) 'dotfiles/agents.lock.tsv'
    Assert-SafePath $statePath
    if ([IO.Directory]::Exists($statePath)) { Stop-Deployment 'agent state file is a directory' }
    $bun = Get-Input 'DOTFILES_BUN_BIN' (Join-Path $roots.bun 'bin/bun.exe')
    $node = Get-Input 'DOTFILES_NODE_BIN' (Join-Path $roots.pixi 'bin/node.exe')
    if ((Invoke-Tool $bun @('--version') -Quiet).Trim() -ne (Get-Pin 'bun')) { Stop-Deployment 'Bun must match the common runtime pin' }
    if ((Invoke-Tool $node @('--version') -Quiet).Trim() -ne ('v' + (Get-Pin 'nodejs'))) { Stop-Deployment 'Node must match the common runtime pin' }
    $env:PATH = [IO.Path]::GetDirectoryName($node) + ';' + [IO.Path]::GetDirectoryName($bun) + ';' + $env:PATH
    $installedRows = @{}
    foreach ($row in (Get-AgentCatalog)) {
        if (-not (Test-AgentPlatform $row.platforms)) { continue }
        $name = $row.agent
        if (-not (Test-AgentSelected $row)) { continue }
        if ($script:TargetedAgent) {
            $oldTarget = if ($row.provider -eq 'native') { '/.qoder/bin/qodercli/' } else { "/.bun/managed/$name/node_modules/" }
            foreach ($relative in @('.bun/bin', '.local/bin')) {
                foreach ($command in $row.commands.Split(',')) {
                    Assert-AgentLauncher (Join-Path $TargetHome "$relative/$command.cmd") $oldTarget
                    Assert-AgentLauncher (Join-Path $TargetHome "$relative/$command") $oldTarget
                }
            }
        }
        if ($row.provider -eq 'bun') {
            if ([version](Get-Pin 'nodejs') -lt [version]$row.minimumNode) { Stop-Deployment "Node does not meet $name's minimum version" }
            $project = Join-Path $roots.bun "managed/$name"
            foreach ($relative in @('', 'node_modules', 'package.json', 'bun.lock')) { Assert-SafePath (Join-Path $project $relative) }
            [IO.Directory]::CreateDirectory($project) | Out-Null
            foreach ($filename in @('package.json', 'bun.lock')) { Copy-RegularTree (Join-Path $Source "deployment/agents/$name/$filename") (Join-Path $project $filename) }
            $script:Step = "install-agents.$name.install"
            $env:npm_config_global = 'false'; $env:pnpm_config_global = 'false'; $env:npm_config_location = 'project'
            Invoke-Tool $bun @('install', '--cwd', $project, '--frozen-lockfile') -Quiet | Out-Null
            if ($script:TargetedAgent -and -not (Test-BunAgentEntries $row $project $node)) {
                [Console]::Out.WriteLine("dotfiles: repairing the installed $name package before rebuilding its launchers")
                Invoke-Tool $bun @('install', '--cwd', $project, '--frozen-lockfile', '--force') -Quiet | Out-Null
            }
            foreach ($command in $row.commands.Split(',')) {
                $entry = Get-BunAgentEntry $row $project $command
                $executable = Join-Path $project $entry
                if (-not [IO.File]::Exists($executable)) { Stop-Deployment "$name did not expose $command" }
                $usesNode = -not $entry.EndsWith('.exe', [StringComparison]::OrdinalIgnoreCase)
                foreach ($relative in @('.bun/bin', '.local/bin')) {
                    $launcher = Join-Path $TargetHome "$relative/$command.cmd"
                    $relativeEntry = ('.bun/managed/' + $name + '/' + $entry).Replace('/', '\')
                    if ($usesNode) {
                        $nodeCmd = $node.Replace('%', '%%')
                        $launcherText = "@echo off`r`nsetlocal DisableDelayedExpansion`r`n`"$nodeCmd`" `"%~dp0..\..\$relativeEntry`" %*`r`nexit /b %errorlevel%`r`n"
                    } else {
                        # Some platform-specific packages expose a native .exe bin.
                        # Do not pass a PE executable to Node as a JavaScript file.
                        $launcherText = "@echo off`r`n`"%~dp0..\..\$relativeEntry`" %*`r`nexit /b %errorlevel%`r`n"
                    }
                    Write-AgentLauncher $launcher $launcherText
                    # Match npm's Windows discovery contract: native clients use
                    # .cmd, while Git Bash resolves the bare POSIX companion.
                    $singleQuote = [string][char]39; $doubleQuote = [string][char]34
                    $quotedEntry = $singleQuote + $relativeEntry.Replace('\', '/').Replace($singleQuote, ($singleQuote + $doubleQuote + $singleQuote + $doubleQuote + $singleQuote)) + $singleQuote
                    $posix = '#!/bin/sh' + "`n" + 'dotfiles_device=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd) || exit 1' + "`n"
                    $posix += '. "$dotfiles_device/.env_core"' + "`n"
                    if ($usesNode) {
                        $quotedNode = $singleQuote + $node.Replace('\', '/').Replace($singleQuote, ($singleQuote + $doubleQuote + $singleQuote + $doubleQuote + $singleQuote)) + $singleQuote
                        $posix += 'exec ' + $quotedNode + ' "$dotfiles_device/"' + $quotedEntry + ' "$@"' + "`n"
                    } else {
                        $posix += 'exec "$dotfiles_device/"' + $quotedEntry + ' "$@"' + "`n"
                    }
                    Write-AgentLauncher (Join-Path $TargetHome "$relative/$command") $posix
                }
                $script:Step = "install-agents.$name.diagnostic"
                # Probe the package bin using its native format; the acceptance
                # runner also checks the public .cmd launchers.
                if ($usesNode) {
                    $diagnostic = Invoke-Tool $node @($executable, '--version') -Quiet -ShowFailureOutput
                } else {
                    $diagnostic = Invoke-Tool $executable @('--version') -Quiet -ShowFailureOutput
                }
                if (-not (Test-AgentVersion $diagnostic $row.version)) { Stop-Deployment "$name diagnostic did not report its pinned version" }
                [Console]::Out.Write($diagnostic)
            }
        } elseif ($row.provider -eq 'native') {
            Install-Qoder $row.version $row.lock
        } else {
            Stop-Deployment "unsupported agent provider '$($row.provider)' for $name"
        }
        $installedRows[$name] = $name + '|' + $row.provider + '|' + $row.version + '|' + $row.version
    }
    $script:Step = 'install-agents.record-state'
    # Publish successful results only. This run has no new observation for
    # an agent it skipped, so keep that agent's previous record.
    $stateRows = @()
    if ([IO.File]::Exists($statePath)) {
        foreach ($line in [IO.File]::ReadAllLines($statePath)) {
            $name = ($line -split '\|', 2)[0]
            if (-not $installedRows.ContainsKey($name)) { $stateRows += $line }
        }
    }
    $stateRows += @($installedRows.Values)
    $stateText = (($stateRows | Sort-Object) -join "`n")
    if ($stateText) { $stateText += "`n" }
    $temporary = $statePath + '.tmp-' + [Guid]::NewGuid().ToString('N')
    try {
        Write-Utf8 $temporary $stateText
        Move-Item -LiteralPath $temporary -Destination $statePath -Force
    } finally {
        Remove-Item -LiteralPath $temporary -ErrorAction SilentlyContinue
    }
    if ($script:TargetedPolicies.Count) { Merge-ClientSettings }
}
function Get-MagpieRelease {
    # The shared release catalog owns the Magpie CLI version every target
    # shares and the digest that verifies each asset. The native Windows
    # adapter consumes the windows-amd64 row and never resolves a release at
    # run time: the URL and the digest are the pin. Windows ARM is outside
    # the supported architecture matrix, so the windows-arm64 row is never
    # consumed here.
    $catalog = Join-Path $Source 'deployment/magpie/releases.tsv'
    if (-not [IO.File]::Exists($catalog)) { Stop-Deployment 'missing Magpie release catalog' }
    $rows = @()
    $seen = @{}
    foreach ($line in [IO.File]::ReadAllLines($catalog)) {
        if (-not $line -or $line.StartsWith('#')) { continue }
        $fields = $line.Split('|')
        if ($fields.Count -ne 5) { Stop-Deployment "invalid Magpie release catalog row: $line" }
        $name = $fields[0]; $version = $fields[1]; $target = $fields[2]; $url = $fields[3]; $sha256 = $fields[4]
        if ($name -ne 'magpie') { Stop-Deployment "unknown Magpie release: $name" }
        if ($version -notmatch '^[0-9]+(\.[0-9]+)*$') { Stop-Deployment "invalid Magpie release version: $version" }
        if ($target -notin @('linux-amd64', 'linux-arm64', 'macos-amd64', 'macos-arm64', 'windows-amd64', 'windows-arm64')) {
            Stop-Deployment "invalid Magpie release target: $target"
        }
        if ($seen.ContainsKey($target)) { Stop-Deployment "duplicate Magpie release target: $target" }
        $seen[$target] = $true
        if ($url -notmatch '^https://') { Stop-Deployment "the Magpie release URL must use HTTPS: $target" }
        if ($sha256 -notmatch '^[a-f0-9]{64}$') { Stop-Deployment "the Magpie release digest must be a lowercase SHA-256: $target" }
        $rows += [pscustomobject]@{ name = $name; version = $version; target = $target; url = $url; sha256 = $sha256 }
    }
    if ($rows.Count -eq 0) { Stop-Deployment 'the Magpie release catalog has no rows' }
    return $rows
}
function Get-MagpiePin {
    # The pin the native Windows target installs.
    $pin = @(Get-MagpieRelease | Where-Object { $_.target -eq 'windows-amd64' })
    if ($pin.Count -ne 1) { Stop-Deployment 'the Magpie release catalog has no windows-amd64 row' }
    return $pin[0]
}
function Test-MagpieVersion([string]$Diagnostic, [string]$Version) {
    if (-not $Diagnostic -or -not $Version) { return $false }
    # Compare whole whitespace-delimited tokens, as the Unix adapter does.
    # A substring match accepts a longer version (0.1.44040), a prerelease
    # (0.1.4404-rc1), a build suffix (0.1.4404+build), or a prefixed token
    # (x0.1.4404) as the exact pin, so require a token boundary on both sides.
    $pattern = '(^|\s)' + [regex]::Escape($Version) + '(\s|$)'
    return [bool]($Diagnostic -cmatch $pattern)
}
function Get-MagpieCmdLauncher {
    # cmd.exe may parse a batch file with a legacy code page, so the absolute
    # home path must never be embedded as UTF-8 text: a non-ASCII home name is
    # corrupted and a literal % or ! changes cmd's expansion. Resolve the
    # binary from the launcher's own directory instead. %~dp0 is that directory
    # with a trailing backslash; the launcher lives in .local/bin and the binary
    # in .local/share/dotfiles/magpie/bin, so every byte below is ASCII no
    # matter what HOME contains. Keep delayed expansion disabled, quote the
    # executable, forward %* and propagate the exit code.
    $relative = '..\share\dotfiles\magpie\bin\magpie.exe'
    return "@echo off`r`nsetlocal DisableDelayedExpansion`r`n" + '"%~dp0' + $relative + '" %*' + "`r`nexit /b %errorlevel%`r`n"
}
function Get-MagpiePosixLauncher {
    return "#!/bin/sh`n" + 'exec "$(dirname -- "$0")/magpie.exe" "$@"' + "`n"
}
function Get-MagpieTextHash([string]$Text) {
    $bytes = (New-Object Text.UTF8Encoding($false)).GetBytes($Text)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $digest = $sha.ComputeHash($bytes) }
    finally { $sha.Dispose() }
    return ([BitConverter]::ToString($digest)).Replace('-', '').ToLowerInvariant()
}
function Test-MagpieLauncher([string]$Path, [string]$Text) {
    # Returns $true only when a launcher already holds exactly the bytes this
    # deployment writes, so a repeated run adopts it without a rewrite. Any
    # other existing entry is preserved and reported before the CLI or a
    # launcher is mutated: a link is never followed and a device file is never
    # overwritten.
    if (Test-ReparsePath $Path) {
        Stop-Deployment "a symlink occupies the Magpie launcher $Path; move it aside before applying"
    }
    if ([IO.Directory]::Exists($Path)) {
        Stop-Deployment "a directory occupies the Magpie launcher $Path; move it aside before applying"
    }
    if (-not [IO.File]::Exists($Path)) { return $false }
    if ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() -ne (Get-MagpieTextHash $Text)) {
        Stop-Deployment "an existing Magpie launcher at $Path is not the managed launcher; move it aside before applying"
    }
    return $true
}
function Install-MagpieCli {
    $script:Step = 'install-magpie-cli'
    $pin = Get-MagpiePin
    $directory = Join-Path $roots.data 'dotfiles/magpie/bin'
    $cli = Join-Path $directory 'magpie.exe'
    $cmdLauncher = Join-Path $TargetHome '.local/bin/magpie.cmd'
    $posixLauncher = Join-Path $directory 'magpie'
    Assert-SafePath $directory
    Assert-SafePath $cli
    Assert-SafePath (Join-Path $TargetHome '.local/bin')

    # A cached binary is executed only after its digest matches the pin. The
    # --version string alone does not identify the bytes, so an unowned device
    # binary that happens to report the pinned version is preserved, never
    # replaced, and never run.
    $cachedValid = $false
    if ([IO.File]::Exists($cli)) {
        $script:Step = 'install-magpie-cli.cached-digest'
        $actual = (Get-FileHash -LiteralPath $cli -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $pin.sha256) {
            Stop-Deployment "a device binary at $cli does not match the pinned Magpie SHA-256; preserved it unchanged; move it aside before applying"
        }
        $script:Step = 'install-magpie-cli.cached-version'
        $savedFailureCode = $script:FailureCode
        try { $cached = (Invoke-Tool $cli @('--version') -Quiet).Trim() }
        catch { $cached = '' }
        finally { $script:FailureCode = $savedFailureCode }
        if (-not (Test-MagpieVersion $cached $pin.version)) {
            Stop-Deployment "the pinned Magpie binary at $cli did not report its pinned version"
        }
        $cachedValid = $true
    } elseif ([IO.Directory]::Exists($cli)) {
        Stop-Deployment "a directory occupies the Magpie CLI path $cli; move it aside before applying"
    }

    # Both launcher paths are checked before the binary is downloaded or any
    # launcher is written, so a conflict fails without mutating the CLI or the
    # launchers. Byte-identical launchers from an earlier run are adopted.
    $script:Step = 'install-magpie-cli.launchers'
    $cmdText = Get-MagpieCmdLauncher
    $posixText = Get-MagpiePosixLauncher
    $adoptCmd = Test-MagpieLauncher $cmdLauncher $cmdText
    $adoptPosix = Test-MagpieLauncher $posixLauncher $posixText

    if (-not $cachedValid) {
        $script:Step = 'install-magpie-cli.download'
        $scratch = Get-Scratch 'magpie'
        try {
            $archive = Join-Path $scratch 'magpie.exe'
            # The download requires HTTPS and the pinned digest, and the
            # payload is verified before it is executed or placed.
            Download-Verified ([pscustomobject]@{ name = 'magpie'; url = $pin.url; sha256 = $pin.sha256 }) $archive
            $script:Step = 'install-magpie-cli.verify'
            $savedFailureCode = $script:FailureCode
            try { $reported = (Invoke-Tool $archive @('--version') -Quiet).Trim() }
            catch { $reported = '' }
            finally { $script:FailureCode = $savedFailureCode }
            if (-not (Test-MagpieVersion $reported $pin.version)) { Stop-Deployment 'the downloaded Magpie CLI did not report its pinned version' }
            $script:Step = 'install-magpie-cli.install'
            Copy-RegularTree $archive $cli
        } finally { Remove-Item -LiteralPath $scratch -Recurse -Force -ErrorAction SilentlyContinue }
    }
    if (-not $adoptCmd) { Write-Utf8 $cmdLauncher $cmdText }
    if (-not $adoptPosix) { Write-Utf8 $posixLauncher $posixText }
    [Console]::Out.WriteLine("dotfiles: magpie: the CLI $($pin.version) is installed")
}
function Prepare-Shell {
    $script:Step = 'prepare-shell'
    $autoload = Join-Path $roots.data 'nushell/vendor/autoload'
    Assert-SafePath $autoload
    [IO.Directory]::CreateDirectory($autoload) | Out-Null
    $stage = Get-Scratch 'shell'
    $nu = Join-Path $roots.pixi 'bin/nu.exe'
    try {
        $hooks = [ordered]@{
            'starship.nu' = @((Join-Path $roots.pixi 'bin/starship.exe'), 'init', 'nu')
            'pixi-completions.nu' = @($script:Pixi, 'completion', '--shell', 'nushell')
            'fzf.nu' = @((Join-Path $roots.pixi 'bin/fzf.exe'), '--nushell')
            'atuin.nu' = @((Join-Path $roots.pixi 'bin/atuin.exe'), 'init', 'nu')
        }
        foreach ($filename in $hooks.Keys) {
            $command = $hooks[$filename]
            $text = Invoke-Tool $command[0] $command[1..($command.Count - 1)] -Quiet
            if ($filename -eq 'fzf.nu') {
                # The upstream history switch is evaluated when Nu loads the
                # generated script. Keep Atuin's Ctrl-R and device env values.
                $prefix = 'let __dotfiles_fzf_history_command = ($env | get -o FZF_CTRL_R_COMMAND)' + "`n" + '$env.FZF_CTRL_R_COMMAND = ""'
                $suffix = 'if $__dotfiles_fzf_history_command == null { hide-env FZF_CTRL_R_COMMAND } else { $env.FZF_CTRL_R_COMMAND = $__dotfiles_fzf_history_command }'
                $text = $prefix + "`n" + $text + "`n" + $suffix + "`n"
            }
            Write-Utf8 (Join-Path $stage $filename) $text
            Invoke-Tool $nu @('--config', (Join-Path $stage $filename), '--env-config', (Join-Path $roots.config 'nushell/env.nu'), '-c', 'null') -Quiet | Out-Null
        }
        Invoke-Tool $nu @('--config', (Join-Path $roots.config 'nushell/config.nu'), '--env-config', (Join-Path $roots.config 'nushell/env.nu'), '-c', 'null') -Quiet | Out-Null
        # The completion module owns the pinned loader: it publishes the
        # generation to every active loader and retires a generation only after
        # no loader imports it. Both paths are checked before it writes. The
        # native directory belongs to this deployment, which copies its own
        # prepared startup resources into it, so the loader there is owned by
        # declaration and the module always publishes it.
        $nativeAutoload = Join-Path $roots.appData 'nushell/vendor/autoload'
        Assert-SafePath (Join-Path $autoload 'nu-scripts.nu')
        Assert-SafePath (Join-Path $nativeAutoload 'nu-scripts.nu')
        Invoke-Tool (Join-Path $roots.pixi 'bin/python.exe') @((Join-Path $TargetHome '.local/lib/dotfiles/completions.py'), '--nu', $nu, '--loader', (Join-Path $autoload 'nu-scripts.nu'), '--loader', (Join-Path $nativeAutoload 'nu-scripts.nu')) -Quiet | Out-Null
        $preparedFiles = @($hooks.Keys)
        foreach ($filename in $preparedFiles) {
            Assert-SafePath (Join-Path $autoload $filename)
            Assert-SafePath (Join-Path $roots.appData "nushell/vendor/autoload/$filename")
        }
        foreach ($filename in $preparedFiles) { Copy-RegularTree (Join-Path $stage $filename) (Join-Path $autoload $filename) }
        # Default Windows Nu resolves its user data fallback before env.nu.
        # These owned real files support ordinary deployment to a native home;
        # isolated launchers establish XDG roots before starting Nu.
        foreach ($filename in $preparedFiles) { Copy-RegularTree (Join-Path $stage $filename) (Join-Path $roots.appData "nushell/vendor/autoload/$filename") }
        Invoke-Tool (Join-Path $roots.pixi 'bin/python.exe') @((Join-Path $TargetHome '.local/lib/dotfiles/history.py'), 'check') -Quiet | Out-Null
        $status = Invoke-Tool (Join-Path $roots.pixi 'bin/python.exe') @((Join-Path $TargetHome '.local/lib/dotfiles/history.py'), 'status') -Quiet
        [Console]::Out.Write($status)
    } finally { Remove-Item -LiteralPath $stage -Recurse -Force }
}
