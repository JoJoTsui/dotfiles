# Native adapters share the source catalogs and Chezmoi merge template.
function Assert-SafePath([string]$Path, [switch]$SourcePath) {
    $candidate = [IO.Path]::GetFullPath($Path)
    if (-not $SourcePath -and $candidate -ne $TargetHome -and -not $candidate.StartsWith($TargetHome + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        Stop-Deployment 'managed path is outside TargetHome'
    }
    while ($candidate) {
        $attributes = 0
        try { $attributes = [IO.File]::GetAttributes($candidate) }
        catch [IO.FileNotFoundException] { }
        catch [IO.DirectoryNotFoundException] { }
        if ($attributes -band [IO.FileAttributes]::ReparsePoint) { Stop-Deployment "managed path is a symlink or reparse point: $candidate" }
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
    Assert-SafePath $TargetHome
    $ancestor = [IO.Path]::GetDirectoryName($TargetHome)
    while ($ancestor) {
        $attributes = 0
        try { $attributes = [IO.File]::GetAttributes($ancestor) }
        catch [IO.FileNotFoundException] { }
        catch [IO.DirectoryNotFoundException] { }
        if ($attributes -band [IO.FileAttributes]::ReparsePoint) { Stop-Deployment 'TargetHome parent is a symlink or reparse point' }
        $ancestor = [IO.Path]::GetDirectoryName($ancestor)
    }
    foreach ($relative in @('.local', '.local/bin', '.local/lib', '.local/share', '.local/state', '.local/run', '.config', '.config/chezmoi', '.config/dotfiles', '.cache', '.cache/tmp', '.pixi', '.pixi/bin', '.pixi/bin/pixi.exe', '.pixi/manifests', '.pixi/manifests/pixi-global.toml', '.bun', '.bun/bin', '.bun/managed', '.bun/install/global', '.cargo', '.cargo/bin', '.rustup', 'AppData', 'AppData/Roaming', 'AppData/Local', '.config/atuin', '.config/atuin/config.toml', '.local/share/atuin', '.codex', '.claude', '.kimi-code', '.pi', '.pi/agent', '.qoder', '.minimax', '.minimax-code', '.minimax-code-install-logs')) {
        Assert-SafePath (Join-Path -Path $TargetHome -ChildPath ([string]$relative))
    }
    foreach ($name in @('meta.db', 'history.db', 'records.db', 'key', 'session', 'host_id')) { Assert-SafePath (Join-Path -Path $TargetHome -ChildPath ".local/share/atuin/$name") }
    foreach ($asset in $exceptions) {
        $assetTarget = [string]$asset.target
        Assert-Relative $assetTarget
        Assert-InstallerDirectory (Join-Path -Path $TargetHome -ChildPath $assetTarget)
    }
    foreach ($row in (Read-Catalog 'deployment/agent-payload/targets.tsv')) {
        Assert-Relative $row.columns[1]; Assert-Relative $row.columns[2]
        Assert-CopyTree (Join-Path $Source "deployment/agent-payload/$($row.columns[1])") (Join-Path -Path $TargetHome -ChildPath ([string]$row.columns[2]))
    }
    foreach ($row in (Read-Catalog 'deployment/client-settings/targets.tsv')) {
        foreach ($part in $row.columns) { Assert-Relative $part }
        Assert-SafePath (Join-Path $Source "deployment/client-settings/$($row.columns[1])") -SourcePath
        Assert-SafePath (Join-Path -Path $TargetHome -ChildPath ([string]$row.columns[2]))
        Assert-SafePath (Join-Path $TargetHome ".local/state/dotfiles/client-settings/$($row.columns[3]).json")
    }
    foreach ($relative in @('nushell', 'uv', 'pip')) { Assert-SafePath (Join-Path $roots.appData $relative) }
    foreach ($relative in @('nushell/env.nu', 'nushell/config.nu', 'nushell/proxy.nu', 'nushell/zoxide.nu', 'nushell/direnv.nu', 'nushell/micromamba.nu', 'uv/uv.toml', 'pip/pip.ini')) {
        Assert-SafePath (Join-Path $roots.appData $relative)
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
function Copy-InstructionBlock([string]$From, [string]$To) {
    $existing = ''; if ([IO.File]::Exists($To)) { $existing = [IO.File]::ReadAllText($To) }
    $start = '<!-- DOTFILES_AGENT_START -->'; $end = '<!-- DOTFILES_AGENT_END -->'
    $starts = ([regex]::Matches($existing, [regex]::Escape($start))).Count
    $ends = ([regex]::Matches($existing, [regex]::Escape($end))).Count
    if ($starts -gt 1 -or $ends -gt 1 -or $starts -ne $ends) { Stop-Deployment 'duplicate or unfinished managed instruction markers' }
    $body = [IO.File]::ReadAllText($From)
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
    $stage = Join-Path $env:TEMP ('skills-' + [Guid]::NewGuid().ToString('N'))
    $cache = Join-Path $roots.cache 'dotfiles/skills'
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
    $lockRows = @('# name|kind|source|resolved')
    foreach ($row in (Read-Catalog 'deployment/skills.tsv')) {
        $name = $row.columns[0]; $kind = $row.columns[1]; $sourceUrl = $row.columns[2]
        $ref = $row.columns[3]; $path = $row.columns[4]; if (-not $path) { $path = '' }
        if (-not $name -or $name.StartsWith('#')) { continue }
        if ($kind -eq 'git') {
            $slug = $sourceUrl -replace '^[A-Za-z][A-Za-z0-9+.-]*://', '' -replace '/+$', '' -replace '[^A-Za-z0-9._-]', '_'
            $repo = Join-Path $cache "git/$slug"
            if (-not (Test-Path -LiteralPath (Join-Path $repo '.git'))) {
                Invoke-Tool git @('clone', '--quiet', '--no-checkout', '--depth', '1', '--branch', $ref, $sourceUrl, $repo) -Quiet | Out-Null
            } elseif ($refresh) {
                & git -C $repo fetch --quiet --depth 1 origin $ref 2>$null | Out-Null
            }
            $resolved = (& git -C $repo rev-parse FETCH_HEAD 2>$null)
            if (-not $resolved) { $resolved = (& git -C $repo rev-parse HEAD 2>$null) }
            if (-not $resolved) { Stop-Deployment "cannot resolve skill source: $name" }
            $archive = Join-Path $stage "$name.tar"
            $depth = ($path -split '/').Count
            & git -C $repo archive --output=$archive $resolved $path 2>$null
            if ($LASTEXITCODE -ne 0) { Stop-Deployment "cannot read skill $name from $sourceUrl" }
            $destination = Join-Path $stage $name
            [IO.Directory]::CreateDirectory($destination) | Out-Null
            & tar -xf $archive -C $destination --strip-components=$depth
            if ($LASTEXITCODE -ne 0) { Stop-Deployment "cannot extract skill $name" }
            Remove-Item -LiteralPath $archive -Force
            if (-not (Test-Path -LiteralPath (Join-Path $destination 'SKILL.md'))) { Stop-Deployment "skill $name has no SKILL.md" }
            $lockRows += "$name|git|$sourceUrl|$resolved"
        } elseif ($kind -eq 'tarball') {
            $slug = $sourceUrl -replace '^[A-Za-z][A-Za-z0-9+.-]*://', '' -replace '/+$', '' -replace '[^A-Za-z0-9._-]', '_'
            $cached = Join-Path $cache "tarballs/$slug.tgz"
            if ($refresh -or -not (Test-Path -LiteralPath $cached)) {
                try { Invoke-WebRequest -Uri $sourceUrl -OutFile $cached -UseBasicParsing -TimeoutSec 90 }
                catch { if (-not (Test-Path -LiteralPath $cached)) { Stop-Deployment "cannot download skill $name" } }
            }
            if (-not (Test-SkillArchive $cached)) { Stop-Deployment "unsafe skill archive: $name" }
            $destination = Join-Path $stage $name
            [IO.Directory]::CreateDirectory($destination) | Out-Null
            & tar -xzf $cached -C $destination
            if (-not (Test-Path -LiteralPath (Join-Path $destination 'SKILL.md'))) { Stop-Deployment "skill $name has no SKILL.md" }
            $lockRows += "$name|tarball|$sourceUrl|cached"
        } else { Stop-Deployment "unknown skill kind: $kind" }
    }
    Set-Content -LiteralPath $marker -Value ([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())
    [IO.Directory]::CreateDirectory((Join-Path $roots.state 'dotfiles')) | Out-Null
    Set-Content -LiteralPath (Join-Path $roots.state 'dotfiles/skills.lock.tsv') -Value ($lockRows -join "`n")
    $script:SkillLibrary = $stage
}
function Copy-AgentPayload {
    $script:Step = 'apply-source.agent-payload'
    foreach ($row in (Read-Catalog 'deployment/agent-payload/targets.tsv')) {
        $from = Join-Path $Source "deployment/agent-payload/$($row.columns[1])"; $to = Join-Path $TargetHome $row.columns[2]
        if ($row.columns[1] -eq 'skills' -and $script:SkillLibrary) { $from = $script:SkillLibrary }
        if ($row.columns[0] -eq 'block') { Copy-InstructionBlock $from $to }
        elseif ($row.columns[0] -in @('file', 'tree')) { Copy-RegularTree $from $to }
        else { Stop-Deployment 'unknown agent payload kind' }
    }
}
function Merge-ClientSettings {
    $script:Step = 'apply-source.client-settings'
    $stage = Join-Path $env:TEMP ('client-settings-' + [Guid]::NewGuid().ToString('N'))
    [IO.Directory]::CreateDirectory($stage) | Out-Null
    try {
        foreach ($row in (Read-Catalog 'deployment/client-settings/targets.tsv')) {
            $env:DOTFILES_SETTINGS_FORMAT = $row.columns[0]; $env:DOTFILES_SETTINGS_POLICY = $row.columns[3]
            $env:DOTFILES_SETTINGS_SOURCE = Join-Path $Source "deployment/client-settings/$($row.columns[1])"
            $env:DOTFILES_SETTINGS_TARGET = Join-Path $TargetHome $row.columns[2]
            $env:DOTFILES_SETTINGS_BASELINE = Join-Path $roots.state "dotfiles/client-settings/$($row.columns[3]).json"
            # A policy can own several targets; key the staged file by target.
            $key = $row.columns[2] -replace '[/.]', '_'
            foreach ($kind in @('config', 'baseline')) {
                $env:DOTFILES_SETTINGS_OUTPUT = $kind
                try {
                    $text = Invoke-Tool $script:Chezmoi (@($script:ChezmoiArguments) + @('execute-template', '--file', (Join-Path $Source 'deployment/client-settings/merge.tmpl'))) -Quiet
                } catch { Stop-Deployment "cannot merge client config ($($row.columns[0])): $($row.columns[2]); check its syntax" }
                Write-Utf8 (Join-Path $stage "$key.$kind") $text
                Set-Private (Join-Path $stage "$key.$kind")
            }
        }
        foreach ($row in (Read-Catalog 'deployment/client-settings/targets.tsv')) {
            $destination = Join-Path $TargetHome $row.columns[2]
            $baseline = Join-Path $roots.state "dotfiles/client-settings/$($row.columns[3]).json"
            $key = $row.columns[2] -replace '[/.]', '_'
            [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination)) | Out-Null
            [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($baseline)) | Out-Null
            Move-Item -LiteralPath (Join-Path $stage "$key.config") -Destination $destination -Force
            Move-Item -LiteralPath (Join-Path $stage "$key.baseline") -Destination $baseline -Force
            Set-Private $destination; Set-Private $baseline
        }
    } finally {
        Remove-Item -LiteralPath $stage -Recurse -Force
        foreach ($name in @('FORMAT', 'POLICY', 'SOURCE', 'TARGET', 'BASELINE', 'OUTPUT')) { [Environment]::SetEnvironmentVariable("DOTFILES_SETTINGS_$name", $null, 'Process') }
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
function Apply-Source {
    $script:Step = 'apply-source'
    $script:ChezmoiArguments = @('--source', $Source, '--destination', $TargetHome, '--config', (Join-Path $roots.config 'chezmoi/chezmoi.toml'), '--cache', (Join-Path $roots.cache 'chezmoi'), '--persistent-state', (Join-Path $roots.config 'chezmoi/chezmoistate.boltdb'), '--no-tty', '--force')
    Invoke-Tool $script:Chezmoi (@($script:ChezmoiArguments) + @('init', '--data=false')) -Quiet | Out-Null
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
        if ($version.Contains($asset.version)) { return }
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
        if (-not $version.Contains($asset.version)) { Stop-Deployment "installed $Name did not report its pinned version" }
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
function Install-Qoder([string]$Version, [string]$ManifestBase) {
    $root = Join-Path $TargetHome '.qoder'
    $cli = Join-Path $root "bin/qodercli/qodercli-$Version.exe"
    $dispatcher = Join-Path $root 'entry/qoder.exe'
    if (-not [IO.File]::Exists($cli)) {
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
            $script:Step = 'install-agents.qoder.install'
            Invoke-Tool $binary @('install', '--force', '--skip-path') -Quiet | Out-Null
        } finally {
            Remove-Item -LiteralPath $scratch -Recurse -Force -ErrorAction SilentlyContinue
        }
        if (-not [IO.File]::Exists($cli)) { Stop-Deployment "Qoder installation did not place $cli" }
    }
    foreach ($relative in @('.local/bin', '.bun/bin')) {
        Assert-SafePath (Join-Path $TargetHome $relative)
        [IO.Directory]::CreateDirectory((Join-Path $TargetHome $relative)) | Out-Null
    }
    $entry = @(
        $dispatcher,
        (Join-Path $root 'entry/qoder.cmd'),
        (Join-Path $root 'entry/qoder')
    ) | Where-Object { [IO.File]::Exists($_) } | Select-Object -First 1
    if (-not $entry) { $entry = $cli }
    foreach ($definition in @(@{ Name = 'qodercli'; Target = $cli }, @{ Name = 'qoder'; Target = $entry })) {
        $name = $definition.Name; $targetPath = $definition.Target
        foreach ($relative in @('.local/bin', '.bun/bin')) {
            $launcher = Join-Path $TargetHome "$relative/$name.cmd"
            Write-Utf8 $launcher ("@echo off`r`n" + '"' + $targetPath + '" %*' + "`r`nexit /b %errorlevel%`r`n")
            $singleQuote = [string][char]39; $doubleQuote = [string][char]34
            $posixPath = $targetPath.Replace('\', '/')
            $quoted = $singleQuote + $posixPath.Replace($singleQuote, ($singleQuote + $doubleQuote + $singleQuote + $doubleQuote + $singleQuote)) + $singleQuote
            $posix = '#!/bin/sh' + "`n" + 'exec ' + $quoted + ' "$@"' + "`n"
            Write-Utf8 (Join-Path $TargetHome "$relative/$name") $posix
        }
    }
    $script:Step = 'install-agents.qoder.diagnostic'
    $diagnostic = Invoke-Tool $cli @('--version') -Quiet
    [Console]::Out.Write($diagnostic)
    if (-not $diagnostic.Contains($Version)) { Stop-Deployment 'qoder diagnostic did not report its pinned version' }
}

function Install-Agents {
    $script:Step = 'install-agents.runtime'
    $bun = Get-Input 'DOTFILES_BUN_BIN' (Join-Path $roots.bun 'bin/bun.exe')
    $node = Get-Input 'DOTFILES_NODE_BIN' (Join-Path $roots.pixi 'bin/node.exe')
    if ((Invoke-Tool $bun @('--version') -Quiet).Trim() -ne (Get-Pin 'bun')) { Stop-Deployment 'Bun must match the common runtime pin' }
    if ((Invoke-Tool $node @('--version') -Quiet).Trim() -ne ('v' + (Get-Pin 'nodejs'))) { Stop-Deployment 'Node must match the common runtime pin' }
    $env:PATH = [IO.Path]::GetDirectoryName($node) + ';' + [IO.Path]::GetDirectoryName($bun) + ';' + $env:PATH
    foreach ($row in (Read-Catalog 'deployment/agents/catalog.tsv')) {
        $name = $row.columns[0]
        if ($name -ne 'codegraph' -and $name -notin $selectedAgents) { continue }
        if ([version](Get-Pin 'nodejs') -lt [version]$row.columns[4]) { Stop-Deployment "Node does not meet $name's minimum version" }
        $project = Join-Path $roots.bun "managed/$name"
        foreach ($relative in @('', 'node_modules', 'package.json', 'bun.lock')) { Assert-SafePath (Join-Path $project $relative) }
        [IO.Directory]::CreateDirectory($project) | Out-Null
        foreach ($filename in @('package.json', 'bun.lock')) { Copy-RegularTree (Join-Path $Source "deployment/agents/$name/$filename") (Join-Path $project $filename) }
        $script:Step = "install-agents.$name.install"
        $env:npm_config_global = 'false'; $env:pnpm_config_global = 'false'; $env:npm_config_location = 'project'
        Invoke-Tool $bun @('install', '--cwd', $project, '--frozen-lockfile') -Quiet | Out-Null
        $packageDirectory = Join-Path $project ('node_modules/' + $row.columns[1])
        $package = [IO.File]::ReadAllText((Join-Path $packageDirectory 'package.json')) | ConvertFrom-Json
        foreach ($command in $row.columns[3].Split(',')) {
            $entry = $package.bin
            if ($entry -isnot [string]) { $entry = $package.bin.$command }
            Assert-Relative $entry
            $javascript = Join-Path $packageDirectory $entry
            if (-not [IO.File]::Exists($javascript)) { Stop-Deployment "$name did not expose $command" }
            $usesNode = -not $entry.EndsWith('.exe', [StringComparison]::OrdinalIgnoreCase)
            foreach ($relative in @('.bun/bin', '.local/bin')) {
                $launcher = Join-Path $TargetHome "$relative/$command.cmd"
                $relativeEntry = ('.bun/managed/' + $name + '/node_modules/' + $row.columns[1] + '/' + $entry).Replace('/', '\')
                if ($usesNode) {
                    $launcherText = "@echo off`r`n`"%~dp0..\..\.pixi\bin\node.exe`" `"%~dp0..\..\$relativeEntry`" %*`r`nexit /b %errorlevel%`r`n"
                } else {
                    # Some platform-specific packages expose a native .exe bin.
                    # Do not pass a PE executable to Node as a JavaScript file.
                    $launcherText = "@echo off`r`n`"%~dp0..\..\$relativeEntry`" %*`r`nexit /b %errorlevel%`r`n"
                }
                Write-Utf8 $launcher $launcherText
                # Match npm's Windows discovery contract: native clients use
                # .cmd, while Git Bash resolves the bare POSIX companion.
                $singleQuote = [string][char]39; $doubleQuote = [string][char]34
                $quotedEntry = $singleQuote + $relativeEntry.Replace('\', '/').Replace($singleQuote, ($singleQuote + $doubleQuote + $singleQuote + $doubleQuote + $singleQuote)) + $singleQuote
                $posix = '#!/bin/sh' + "`n" + 'dotfiles_device=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd) || exit 1' + "`n"
                $posix += '. "$dotfiles_device/.env_core"' + "`n"
                if ($usesNode) {
                    $posix += 'exec "$dotfiles_device/.pixi/bin/node.exe" "$dotfiles_device/"' + $quotedEntry + ' "$@"' + "`n"
                } else {
                    $posix += 'exec "$dotfiles_device/"' + $quotedEntry + ' "$@"' + "`n"
                }
                Write-Utf8 (Join-Path $TargetHome "$relative/$command") $posix
            }
            $script:Step = "install-agents.$name.diagnostic"
            # Probe the package bin using its native format; the acceptance
            # runner also checks the public .cmd launchers.
            if ($usesNode) {
                $diagnostic = Invoke-Tool $node @($javascript, '--version') -Quiet -ShowFailureOutput
            } else {
                $diagnostic = Invoke-Tool $javascript @('--version') -Quiet -ShowFailureOutput
            }
            if (-not $diagnostic.Contains($row.columns[2])) { Stop-Deployment "$name diagnostic did not report its pinned version" }
            [Console]::Out.Write($diagnostic)
        }
    }
    foreach ($row in (Read-Catalog 'deployment/agents/native.tsv')) {
        $name = $row.columns[0]
        if ($name -notin $selectedAgents) { continue }
        if ($name -eq 'qoder') { Install-Qoder $row.columns[1] $row.columns[4] }
        else { Stop-Deployment "unsupported native agent: $name" }
    }
}
function Prepare-Shell {
    $script:Step = 'prepare-shell'
    $autoload = Join-Path $roots.data 'nushell/vendor/autoload'
    [IO.Directory]::CreateDirectory($autoload) | Out-Null
    $stage = Get-Scratch 'shell'
    $nu = Join-Path $roots.pixi 'bin/nu.exe'
    try {
        $hooks = [ordered]@{
            'starship.nu' = @((Join-Path $roots.pixi 'bin/starship.exe'), 'init', 'nu')
            'pixi-completions.nu' = @($script:Pixi, 'completion', '--shell', 'nushell')
            'atuin.nu' = @((Join-Path $roots.pixi 'bin/atuin.exe'), 'init', 'nu')
        }
        foreach ($filename in $hooks.Keys) {
            $command = $hooks[$filename]
            $text = Invoke-Tool $command[0] $command[1..($command.Count - 1)] -Quiet
            Write-Utf8 (Join-Path $stage $filename) $text
            Invoke-Tool $nu @('--config', (Join-Path $stage $filename), '--env-config', (Join-Path $roots.config 'nushell/env.nu'), '-c', 'null') -Quiet | Out-Null
        }
        Invoke-Tool $nu @('--config', (Join-Path $roots.config 'nushell/config.nu'), '--env-config', (Join-Path $roots.config 'nushell/env.nu'), '-c', 'null') -Quiet | Out-Null
        foreach ($filename in $hooks.Keys) { Assert-SafePath (Join-Path $autoload $filename) }
        foreach ($filename in $hooks.Keys) { Copy-RegularTree (Join-Path $stage $filename) (Join-Path $autoload $filename) }
        # Default Windows Nu resolves its user data fallback before env.nu.
        # These owned real files support ordinary deployment to a native home;
        # isolated launchers establish XDG roots before starting Nu.
        foreach ($filename in $hooks.Keys) { Copy-RegularTree (Join-Path $stage $filename) (Join-Path $roots.appData "nushell/vendor/autoload/$filename") }
        Invoke-Tool (Join-Path $roots.pixi 'bin/python.exe') @((Join-Path $TargetHome '.local/lib/dotfiles/history.py'), 'check') -Quiet | Out-Null
        $status = Invoke-Tool (Join-Path $roots.pixi 'bin/python.exe') @((Join-Path $TargetHome '.local/lib/dotfiles/history.py'), 'status') -Quiet
        [Console]::Out.Write($status)
    } finally { Remove-Item -LiteralPath $stage -Recurse -Force }
}
