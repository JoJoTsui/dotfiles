# Native adapters share the source catalogs and Chezmoi merge template.
$script:TargetedAgent = ''
$script:TargetedPolicies = @()

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
        foreach ($relative in @('.config/chezmoi/chezmoi.toml', '.config/chezmoi/chezmoistate.boltdb', '.cache/chezmoi', '.env_core')) {
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
        Assert-InstallerDirectory (Join-Path -Path $TargetHome -ChildPath $assetTarget)
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
    $acl = New-Object Security.AccessControl.FileSecurity
    $acl.SetAccessRuleProtection($true, $false)
    $rule = New-Object Security.AccessControl.FileSystemAccessRule($identity, 'FullControl', 'Allow')
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
            & git -C $repo cat-file -e "$pin^{commit}" 2>$null | Out-Null
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
                    foreach ($relative in @($from, $to)) {
                        if (-not $relative -or [IO.Path]::IsPathRooted($relative) -or ($relative -split '[/\\]') -contains '..') { Stop-Deployment "unsafe skill layout: $name" }
                    }
                    $inputPath = Join-Path $destination $from
                    $outputPath = Join-Path $mapped $to
                    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($outputPath)) | Out-Null
                    Copy-Item -LiteralPath $inputPath -Destination $outputPath -Recurse
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
function Set-ChezmoiArguments {
    $script:ChezmoiArguments = @('--source', $Source, '--destination', $TargetHome, '--config', (Join-Path $roots.config 'chezmoi/chezmoi.toml'), '--cache', (Join-Path $roots.cache 'chezmoi'), '--persistent-state', (Join-Path $roots.config 'chezmoi/chezmoistate.boltdb'), '--no-tty', '--force')
}
function Initialize-Chezmoi {
    Invoke-Tool $script:Chezmoi (@($script:ChezmoiArguments) + @('init', '--data=false')) -Quiet | Out-Null
}
function Prepare-AgentUpdate {
    Set-ChezmoiArguments
    $shellEnvironment = Join-Path $TargetHome '.env_core'
    if (-not [IO.File]::Exists((Join-Path $roots.config 'chezmoi/chezmoi.toml'))) { Initialize-Chezmoi }
    # The Git Bash companions source this at runtime. Repair a missing
    # prerequisite and leave an existing shell environment for a full apply.
    if (-not [IO.File]::Exists($shellEnvironment)) {
        Invoke-Tool $script:Chezmoi (@($script:ChezmoiArguments) + @('apply', $shellEnvironment)) -Quiet | Out-Null
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
function Install-Asset([string]$Name) {
    $asset = Get-Asset $Name
    $assetTarget = [string]$asset.target
    $target = Join-Path -Path $TargetHome -ChildPath $assetTarget
    Assert-SafePath $target
    $diagnostic = $target
    if ($Name -eq 'git-bash') { $diagnostic = Join-Path $target 'bin/git.exe' }
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
            # PortableGit is a 7-Zip SFX archive. Extract it directly into the
            # managed directory and let the version check validate the result.
            $script:Step = "install-managers.$Name.extract"
            $argumentLine = '-o"' + $target + '" -y'
            $process = Start-Process -FilePath $archive -ArgumentList $argumentLine -Wait -PassThru -WindowStyle Hidden
            if ($process.ExitCode) { $script:FailureCode = $process.ExitCode; Stop-Deployment 'required command failed' }
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
function Assert-AgentLauncher([string]$Path, [string]$OldTarget) {
    Assert-SafePath $Path
    if ([IO.Directory]::Exists($Path)) { Stop-Deployment "agent launcher is a directory: $Path" }
    if (-not [IO.File]::Exists($Path)) { return }
    $existing = [IO.File]::ReadAllText($Path).Replace('\', '/')
    $header = if ($Path.EndsWith('.cmd', [StringComparison]::OrdinalIgnoreCase)) { '@echo off' } else { '#!/bin/sh' }
    if (-not ($existing.StartsWith($header) -and ($existing.Contains('Managed by dotfiles;') -or $existing.Contains($OldTarget)))) {
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
            $_.variant -ne 'legacy' -and $_.runtime -ne 'node-sea' -and
            (-not $_.min_windows_build -or $build -ge [int]$_.min_windows_build) -and
            (-not $_.max_windows_build -or $build -le [int]$_.max_windows_build)
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

function Get-BunAgentEntry($Package, [string]$Command) {
    if ($Package.bin -is [string]) { return $Package.bin }
    return $Package.bin.$Command
}

function Test-BunAgentEntries($Row, [string]$PackageDirectory, [string]$Node) {
    $savedFailureCode = $script:FailureCode
    try {
        $package = [IO.File]::ReadAllText((Join-Path $PackageDirectory 'package.json')) | ConvertFrom-Json
        foreach ($command in $Row.commands.Split(',')) {
            $entry = Get-BunAgentEntry $package $command
            Assert-Relative $entry
            $executable = Join-Path $PackageDirectory $entry
            if (-not [IO.File]::Exists($executable)) { return $false }
            $output = if ($entry.EndsWith('.exe', [StringComparison]::OrdinalIgnoreCase)) {
                Invoke-Tool $executable @('--version') -Quiet
            } else {
                Invoke-Tool $Node @($executable, '--version') -Quiet
            }
            if (-not $output.Contains($Row.version)) { return $false }
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
            $packageDirectory = Join-Path $project ('node_modules/' + $row.package)
            if ($script:TargetedAgent -and -not (Test-BunAgentEntries $row $packageDirectory $node)) {
                [Console]::Out.WriteLine("dotfiles: repairing the installed $name package before rebuilding its launchers")
                Invoke-Tool $bun @('install', '--cwd', $project, '--frozen-lockfile', '--force') -Quiet | Out-Null
            }
            $package = [IO.File]::ReadAllText((Join-Path $packageDirectory 'package.json')) | ConvertFrom-Json
            foreach ($command in $row.commands.Split(',')) {
                $entry = Get-BunAgentEntry $package $command
                Assert-Relative $entry
                $javascript = Join-Path $packageDirectory $entry
                if (-not [IO.File]::Exists($javascript)) { Stop-Deployment "$name did not expose $command" }
                $usesNode = -not $entry.EndsWith('.exe', [StringComparison]::OrdinalIgnoreCase)
                foreach ($relative in @('.bun/bin', '.local/bin')) {
                    $launcher = Join-Path $TargetHome "$relative/$command.cmd"
                    $relativeEntry = ('.bun/managed/' + $name + '/node_modules/' + $row.package + '/' + $entry).Replace('/', '\')
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
                    $diagnostic = Invoke-Tool $node @($javascript, '--version') -Quiet -ShowFailureOutput
                } else {
                    $diagnostic = Invoke-Tool $javascript @('--version') -Quiet -ShowFailureOutput
                }
                if (-not $diagnostic.Contains($row.version)) { Stop-Deployment "$name diagnostic did not report its pinned version" }
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
        Invoke-Tool (Join-Path $roots.pixi 'bin/python.exe') @((Join-Path $TargetHome '.local/lib/dotfiles/completions.py'), '--nu', $nu, '--autoload-dir', $stage) -Quiet | Out-Null
        $preparedFiles = @($hooks.Keys) + @('nu-scripts.nu')
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
