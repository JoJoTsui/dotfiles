# Native Windows user deployment. Compatible with Windows PowerShell 5.1.
[CmdletBinding()]
param(
    [Alias('Home')][string]$TargetHome,
    [string]$Source = $PSScriptRoot,
    [string]$Platform,
    [string]$Role,
    [string]$Profile,
    [string]$Class,
    [string]$Arch,
    [string]$Agents,
    [string]$Bundles,
    [switch]$Plan,
    [switch]$ApplyOnly,
    [switch]$AgentsOnly
)
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$script:Step = 'selection'
$script:FailureCode = 1

function Stop-Deployment([string]$Message) { throw $Message }
function Get-Input([string]$Name, [string]$Fallback = '') {
    $value = [Environment]::GetEnvironmentVariable($Name, 'Process')
    if ([string]::IsNullOrEmpty($value)) { return $Fallback }
    return $value
}
function Read-Catalog([string]$RelativePath) {
    foreach ($line in [IO.File]::ReadAllLines((Join-Path $Source $RelativePath))) {
        if ($line.Length -and -not $line.StartsWith('#')) {
            [pscustomobject]@{ columns = [string[]]($line.Split('|')) }
        }
    }
}
function Get-Selection {
    $selectedPlatform = Get-Input 'DOTFILES_PLATFORM' 'windows'
    $selectedRole = Get-Input 'DOTFILES_ROLE' 'workstation'
    $preset = Get-Input 'DOTFILES_PROFILE'
    $legacy = Get-Input 'DOTFILES_CLASS'
    if ($legacy) {
        if ($legacy -ne 'win') { Stop-Deployment 'native PowerShell accepts the legacy win class only' }
        $selectedPlatform = 'windows'; $selectedRole = 'workstation'
    }
    if ($preset) {
        if ($preset -notmatch '^windows-(workstation|remote-compute)$') { Stop-Deployment 'native PowerShell requires a windows profile' }
        $selectedRole = $preset.Substring(8)
    }
    # Component environment selections override environment presets.
    $selectedPlatform = Get-Input 'DOTFILES_PLATFORM' $selectedPlatform
    $selectedRole = Get-Input 'DOTFILES_ROLE' $selectedRole
    if ($Class) {
        if ($Class -ne 'win') { Stop-Deployment 'native PowerShell accepts the legacy win class only' }
        $selectedPlatform = 'windows'; $selectedRole = 'workstation'
    }
    if ($Profile) {
        if ($Profile -notmatch '^windows-(workstation|remote-compute)$') { Stop-Deployment 'native PowerShell requires a windows profile' }
        if ($Class -and $Profile -ne 'windows-workstation') { Stop-Deployment 'conflicting profile and class selections' }
        $selectedPlatform = 'windows'; $selectedRole = $Profile.Substring(8)
    }
    if (($Class -or $Profile) -and (($Role -and $Role -ne $selectedRole) -or ($Platform -and $Platform -ne $selectedPlatform))) {
        Stop-Deployment 'conflicting platform/role and profile/class selections'
    }
    if ($Platform) { $selectedPlatform = $Platform }
    if ($Role) { $selectedRole = $Role }
    if ($selectedPlatform -ne 'windows') { Stop-Deployment 'use bootstrap.sh for Linux, macOS or WSL' }
    if ($selectedRole -notin @('workstation', 'remote-compute')) { Stop-Deployment 'invalid role; choose workstation or remote-compute' }
    $architecture = Get-Input 'DOTFILES_ARCH' (Get-Input 'PROCESSOR_ARCHITEW6432' (Get-Input 'PROCESSOR_ARCHITECTURE' 'x86_64'))
    if ($Arch) { $architecture = $Arch }
    if ($architecture -in @('ARM64', 'arm64', 'aarch64')) { Stop-Deployment 'Windows ARM is outside the supported architecture matrix' }
    if ($architecture -notin @('AMD64', 'amd64', 'x86_64')) { Stop-Deployment 'unsupported architecture; native Windows requires x86_64' }
    return [ordered]@{ platform = 'windows'; role = $selectedRole; arch = 'x86_64'; profile = "windows-$selectedRole" }
}
function Get-Agents {
    $selection = Get-Input 'DOTFILES_AGENTS' 'all'
    if ($script:EntryParameters.ContainsKey('Agents')) { $selection = $Agents }
    if ($selection -eq 'all') { return @('kimi', 'pi', 'opencode', 'claude', 'codex') }
    if ($selection -eq 'none') { return @() }
    if (-not $selection -or $selection -match '(^,|,$|,,)') { Stop-Deployment 'invalid agent selection' }
    $requested = @($selection.Split(',') | ForEach-Object { $_ -replace '^kimi-code$', 'kimi' -replace '^claude-code$', 'claude' })
    foreach ($name in $requested) {
        if ($name -notin @('kimi', 'pi', 'opencode', 'claude', 'codex')) { Stop-Deployment 'unknown agent; choose kimi, pi, opencode, claude, codex' }
    }
    return @('kimi', 'pi', 'opencode', 'claude', 'codex' | Where-Object { $_ -in $requested })
}
function Get-Bundles {
    $selection = Get-Input 'DOTFILES_BUNDLES' 'none'
    if ($script:EntryParameters.ContainsKey('Bundles')) { $selection = $Bundles }
    if ($selection -eq 'none') { return @() }
    if (-not $selection -or $selection -match '(^,|,$|,,)') { Stop-Deployment 'invalid bundle selection' }
    $requested = @($selection.Split(','))
    $selected = @()
    foreach ($row in (Read-Catalog 'deployment/bundles.tsv')) {
        if ($row.columns[0] -in $requested) {
            if ('windows-x86_64' -notin $row.columns[1].Split(',')) { Stop-Deployment "unsupported bundle '$($row.columns[0])' for windows-x86_64" }
            $selected += $row.columns[0]
        }
    }
    foreach ($name in $requested) { if ($name -notin $selected) { Stop-Deployment 'unknown bundle' } }
    return $selected
}
function Get-Packages {
    foreach ($row in (Read-Catalog 'deployment/common-tools.tsv')) {
        if ($row.columns[3] -ne 'all') { continue }
        $dependencies = [ordered]@{}; $exposed = [ordered]@{}
        foreach ($specification in $row.columns[1].Split(',')) { $parts = $specification.Split(@('=='), [StringSplitOptions]::None); $dependencies[$parts[0]] = '==' + $parts[1] }
        foreach ($mapping in $row.columns[2].Split(',')) { $parts = $mapping.Split('='); $exposed[$parts[0]] = $parts[1] }
        [ordered]@{ environment = $row.columns[0]; dependencies = $dependencies; exposed = $exposed }
    }
}
function Get-BundlePackages {
    foreach ($row in (Read-Catalog 'deployment/bundle-tools.tsv')) {
        if ($row.columns[0] -notin $selectedBundles -or ($row.columns[5] -ne 'all' -and 'windows' -notin $row.columns[5].Split(','))) { continue }
        $dependencies = [ordered]@{}; $exposed = [ordered]@{}
        foreach ($specification in $row.columns[2].Split(',')) { $parts = $specification.Split(@('=='), [StringSplitOptions]::None); $dependencies[$parts[0]] = '==' + $parts[1] }
        foreach ($mapping in $row.columns[3].Split(',')) { $parts = $mapping.Split('='); $exposed[$parts[0]] = $parts[1] }
        [ordered]@{ bundle = $row.columns[0]; environment = $row.columns[1]; dependencies = $dependencies; exposed = $exposed; channels = @($row.columns[4].Split(',')) }
    }
}

$script:EntryParameters = $PSBoundParameters
try {
    if ($ApplyOnly -and $AgentsOnly) { Stop-Deployment 'ApplyOnly and AgentsOnly are mutually exclusive' }
    $selection = Get-Selection
    if (-not $TargetHome) { $TargetHome = Get-Input 'USERPROFILE' (Get-Input 'HOME') }
    if (-not $TargetHome -or -not [IO.Path]::IsPathRooted($TargetHome)) { Stop-Deployment 'TargetHome must be an absolute path' }
    $TargetHome = [IO.Path]::GetFullPath($TargetHome).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
    $Source = [IO.Path]::GetFullPath($Source)
    if (-not [IO.File]::Exists((Join-Path $Source '.chezmoi.toml.tmpl'))) { Stop-Deployment 'Source must be the dotfiles working tree' }
    $selectedAgents = @(Get-Agents)
    $selectedBundles = @(Get-Bundles)
    $packages = @(Get-Packages)
    $bundlePackages = @(Get-BundlePackages)
    $exceptions = @([IO.File]::ReadAllText((Join-Path $Source 'deployment/windows-assets.json')) | ConvertFrom-Json)
    $roots = [ordered]@{
        config = Join-Path $TargetHome '.config'; data = Join-Path $TargetHome '.local/share'
        state = Join-Path $TargetHome '.local/state'; cache = Join-Path $TargetHome '.cache'
        pixi = Join-Path $TargetHome '.pixi'; bun = Join-Path $TargetHome '.bun'
        cargo = Join-Path $TargetHome '.cargo'; rustup = Join-Path $TargetHome '.rustup'
        appData = Join-Path $TargetHome 'AppData/Roaming'; localAppData = Join-Path $TargetHome 'AppData/Local'
    }
    $agentPackages = @(); $tools = @('pixi', 'chezmoi', 'rustup', 'bun', 'bunx', 'atuin', 'hx', 'jq', 'bash', 'sh')
    foreach ($package in $packages) { $tools += @($package.exposed.Keys) }
    foreach ($package in $bundlePackages) { $tools += @($package.exposed.Keys) }
    foreach ($row in (Read-Catalog 'deployment/agents/catalog.tsv')) {
        if ($row.columns[0] -eq 'codegraph' -or $row.columns[0] -in $selectedAgents) {
            $tools += $row.columns[3].Split(',')
            $agentPackages += [ordered]@{ name = $row.columns[0]; package = $row.columns[1]; version = $row.columns[2]; manager = 'bun'; minimumNode = $row.columns[4]; lock = "deployment/agents/$($row.columns[0])/bun.lock" }
        }
    }
    $actions = @('install-managers', 'apply-source', 'install-common', 'install-agents', 'prepare-shell')
    if ($ApplyOnly) { $actions = @('apply-source') }
    if ($AgentsOnly) { $actions = @('apply-source', 'install-agents') }
    $result = [ordered]@{
        platform = $selection.platform; role = $selection.role; arch = $selection.arch; profile = $selection.profile
        source = $Source; home = $TargetHome; roots = $roots; agents = $selectedAgents; bundles = $selectedBundles
        tools = @($tools | Select-Object -Unique); packages = $packages; bundlePackages = $bundlePackages; agentPackages = $agentPackages; actions = $actions; exceptions = $exceptions
        managers = [ordered]@{ pixi = ($exceptions | Where-Object { $_.name -eq 'pixi' }).version; chezmoi = ($exceptions | Where-Object { $_.name -eq 'chezmoi' }).version; rustup = ($exceptions | Where-Object { $_.name -eq 'rustup' }).version }
        settings = [ordered]@{ mode = 'copy'; primaryShell = 'nu'; secondaryShells = @('git-bash'); systemChanges = $false; loginShellChanges = $false }
    }
    if (-not $TargetHome -or $TargetHome -eq [IO.Path]::GetPathRoot($TargetHome).TrimEnd([IO.Path]::DirectorySeparatorChar) -or $TargetHome -eq $Source) { Stop-Deployment 'TargetHome cannot be the filesystem root or Source' }
    if ($Plan) { $result | ConvertTo-Json -Depth 12; exit 0 }
    if (-not $ApplyOnly -and [Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { Stop-Deployment 'native installation requires Windows; Linux planning/rendering is separate evidence' }
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -and -not $EntryParameters.ContainsKey('TargetHome')) { Stop-Deployment 'foreign rendering requires an explicitly isolated TargetHome' }
    . (Join-Path $Source 'deployment/windows.ps1')
    $script:InitialPath = $env:PATH
    $script:Step = 'validate-state'
    Assert-OwnedState
    Set-EnvironmentRoots
    $script:Step = 'prepare-state'
    foreach ($relative in @('.local/bin', '.config/chezmoi', '.cache/tmp', '.local/run')) { [IO.Directory]::CreateDirectory((Join-Path $TargetHome $relative)) | Out-Null }
    Install-Managers
    Apply-Source
    if ($AgentsOnly) { Install-Agents }
    elseif (-not $ApplyOnly) { Install-Common; Install-Agents; Prepare-Shell }
    [Console]::Out.WriteLine("dotfiles: applied $($selection.profile) to $TargetHome (copy mode)")
} catch {
    [Console]::Error.WriteLine('dotfiles: ' + $_.Exception.Message)
    if ($_.InvocationInfo.ScriptLineNumber) {
        [Console]::Error.WriteLine("dotfiles: source line $($_.InvocationInfo.ScriptLineNumber)")
    }
    [Console]::Error.WriteLine("dotfiles: step $script:Step failed (exit $script:FailureCode)")
    exit $script:FailureCode
}
