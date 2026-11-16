# Native Windows user deployment. Compatible with Windows PowerShell 5.1.
[CmdletBinding()]
param(
    [Alias('Home')][string]$TargetHome,
    [string]$Source = $PSScriptRoot,
    [string]$Platform,
    [string]$Role,
    [Alias('Profile')][string]$ProfilePreset,
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
function Get-AgentCatalog {
    # The per-agent provider catalog is the only source of agent installation
    # data. The POSIX adapter reads the same records.
    $rows = @()
    foreach ($line in [IO.File]::ReadAllLines((Join-Path $Source 'deployment/agents/providers.tsv'))) {
        if (-not $line -or $line.StartsWith('#')) { continue }
        $fields = $line.Split('|')
        $rows += [pscustomobject]@{
            record = $line
            agent = $fields[0]; provider = $fields[1]; package = $fields[2]; packageKind = $fields[3]
            version = $fields[4]; policy = $fields[5]; commands = $fields[6]; platforms = $fields[7]
            order = [int]$fields[8]; selection = $fields[9]; herdr = $fields[10]
            minimumNode = $fields[11]; trusted = $fields[12]
            lock = $fields[13]; diagnostic = $fields[14]
        }
    }
    return $rows
}
function Get-HerdrKinds {
    $kinds = @()
    foreach ($line in [IO.File]::ReadAllLines((Join-Path $Source 'deployment/agents/herdr-kinds.tsv'))) {
        if ($line -and -not $line.StartsWith('#')) { $kinds += $line }
    }
    return $kinds
}
function Test-AgentPlatform([string]$Platforms) {
    foreach ($item in $Platforms.Split(',')) {
        if ($item -eq 'all' -or $item -eq 'windows') { return $true }
    }
    return $false
}
function Select-AgentRecords {
    # The records of one agent that can serve the platform, in chain order.
    param($Catalog, [string]$Agent)
    $viable = @($Catalog | Where-Object { $_.agent -eq $Agent -and (Test-AgentPlatform $_.platforms) })
    return @($viable | Sort-Object order)
}
function Test-AgentCatalog {
    # An invalid record stops the deployment before it creates any state or
    # file, and the message names the offending record.
    $catalog = @(Get-AgentCatalog)
    $kinds = @(Get-HerdrKinds)
    $seen = @{}
    foreach ($row in $catalog) {
        $label = "$($row.agent)/$($row.provider)"
        if ($row.provider -notin @('bun', 'native', 'homebrew')) {
            Stop-Deployment "invalid agent provider catalog record (unknown provider '$($row.provider)'): $label"
        }
        if ($row.policy -notin @('exact', 'floor')) {
            Stop-Deployment "invalid agent provider catalog record (unknown version policy '$($row.policy)'): $label"
        }
        foreach ($platform in $row.platforms.Split(',')) {
            if ($platform -notin @('all', 'unix', 'windows', 'linux', 'macos', 'wsl')) {
                Stop-Deployment "invalid agent provider catalog record (unsupported platform '$platform'): $label"
            }
        }
        if ($row.order -lt 1) { Stop-Deployment "invalid agent provider catalog record (order starts at 1): $label" }
        if ($row.selection -notin @('selectable', 'always')) {
            Stop-Deployment "invalid agent provider catalog record (unknown selection '$($row.selection)'): $label"
        }
        if (-not $row.commands -or $row.commands.StartsWith(',') -or $row.commands.EndsWith(',')) {
            Stop-Deployment "invalid agent provider catalog record (commands): $label"
        }
        if (-not $row.version) { Stop-Deployment "invalid agent provider catalog record (version): $label" }
        if ($row.herdr -ne '-' -and $row.herdr -notin $kinds) {
            Stop-Deployment "invalid agent provider catalog record (unknown Herdr kind '$($row.herdr)'): $label"
        }
        if ($seen.ContainsKey($label)) { Stop-Deployment "duplicate agent provider catalog record: $label" }
        $seen[$label] = $true
        if ($row.provider -eq 'bun') {
            if (-not $row.package) { Stop-Deployment "invalid agent provider catalog record (missing package): $label" }
            if ($row.packageKind -ne '-') {
                Stop-Deployment "invalid agent provider catalog record (a Bun record has no package kind): $label"
            }
            if ($row.policy -ne 'exact') {
                Stop-Deployment "invalid agent provider catalog record (a deployment-owned provider keeps an exact pin): $label"
            }
            if (-not [IO.File]::Exists((Join-Path $Source $row.lock))) {
                Stop-Deployment "missing supported Bun lock for $($row.agent): $($row.lock)"
            }
        }
        if ($row.provider -eq 'native') {
            if (-not $row.package) { Stop-Deployment "invalid agent provider catalog record (missing native release): $label" }
            if ($row.packageKind -ne '-') {
                Stop-Deployment "invalid agent provider catalog record (a native record has no package kind): $label"
            }
            if ($row.policy -ne 'exact') {
                Stop-Deployment "invalid agent provider catalog record (a deployment-owned provider keeps an exact pin): $label"
            }
            if (-not $row.lock.StartsWith('https://')) {
                Stop-Deployment "invalid agent provider catalog record (native release manifest must use HTTPS): $label"
            }
        }
        if ($row.provider -eq 'homebrew') {
            if (-not $row.package) { Stop-Deployment "invalid agent provider catalog record (missing Homebrew package): $label" }
            if ($row.packageKind -notin @('formula', 'cask')) {
                Stop-Deployment "invalid agent provider catalog record (unknown Homebrew package kind '$($row.packageKind)'): $label"
            }
            if ($row.policy -ne 'floor') {
                Stop-Deployment "invalid agent provider catalog record (an installer-owned provider carries a floor): $label"
            }
        }
    }
    foreach ($agent in @($catalog | ForEach-Object { $_.agent } | Select-Object -Unique)) {
        $records = @($catalog | Where-Object { $_.agent -eq $agent })
        if (@($records | ForEach-Object { $_.herdr } | Select-Object -Unique).Count -ne 1) {
            Stop-Deployment "agent provider catalog records disagree on the Herdr kind of $agent"
        }
        if (@($records | ForEach-Object { $_.selection } | Select-Object -Unique).Count -ne 1) {
            Stop-Deployment "agent provider catalog records disagree on the selection of $agent"
        }
        $viable = @(Select-AgentRecords $catalog $agent)
        if ($viable.Count -eq 0) { Stop-Deployment "agent $agent has no provider that can serve windows" }
        if (@($viable | ForEach-Object { $_.order } | Select-Object -Unique).Count -ne $viable.Count) {
            Stop-Deployment "agent provider catalog records share an order for $agent"
        }
        if (@($records | Where-Object { $_.provider -in @('bun', 'native') }).Count -ne 1) {
            Stop-Deployment "agent $agent must declare exactly one deployment-owned provider"
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
    if ($ProfilePreset) {
        if ($ProfilePreset -notmatch '^windows-(workstation|remote-compute)$') { Stop-Deployment 'native PowerShell requires a windows profile' }
        if ($Class -and $ProfilePreset -ne 'windows-workstation') { Stop-Deployment 'conflicting profile and class selections' }
        $selectedPlatform = 'windows'; $selectedRole = $ProfilePreset.Substring(8)
    }
    if (($Class -or $ProfilePreset) -and (($Role -and $Role -ne $selectedRole) -or ($Platform -and $Platform -ne $selectedPlatform))) {
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
    $mirror = Get-Input 'DOTFILES_MIRROR' 'tuna'
    if ($mirror -notin @('tuna', 'upstream')) { Stop-Deployment 'invalid DOTFILES_MIRROR; use tuna or upstream' }
    return [ordered]@{ platform = 'windows'; role = $selectedRole; arch = 'x86_64'; profile = "windows-$selectedRole"; mirror = $mirror }
}
function Get-Agents {
    $selection = Get-Input 'DOTFILES_AGENTS' 'all'
    if ($script:EntryParameters.ContainsKey('Agents')) { $selection = $Agents }
    $catalog = @()
    foreach ($row in (Get-AgentCatalog)) {
        if ($row.selection -eq 'selectable') { $catalog += [string]$row.agent }
    }
    if ($selection -eq 'all') { return $catalog }
    if ($selection -eq 'none') { return @() }
    if (-not $selection -or $selection -match '(^,|,$|,,)') { Stop-Deployment 'invalid agent selection' }
    $aliases = @{ 'kimi-code' = 'kimi'; 'claude-code' = 'claude'; 'minimax-code' = 'minimax' }
    $requested = @()
    foreach ($name in $selection.Split(',')) {
        $canonical = if ($aliases.ContainsKey($name)) { $aliases[$name] } else { $name }
        if ($canonical -notin $catalog) { Stop-Deployment "unknown agent; choose $($catalog -join ', ')" }
        if ($canonical -notin $requested) { $requested += $canonical }
    }
    return @($catalog | Where-Object { $_ -in $requested })
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
    if ([string]::IsNullOrWhiteSpace($Source)) {
        $Source = $PSScriptRoot
        if ([string]::IsNullOrWhiteSpace($Source) -and $PSCommandPath) {
            $Source = Split-Path -Parent $PSCommandPath
        }
    }
    if ([string]::IsNullOrWhiteSpace($Source)) { Stop-Deployment 'Source must identify the dotfiles working tree' }
    $Source = [IO.Path]::GetFullPath($Source)
    if (-not [IO.File]::Exists((Join-Path $Source '.chezmoi.toml.tmpl'))) { Stop-Deployment 'Source must be the dotfiles working tree' }
    Test-AgentCatalog
    $selectedAgents = @(Get-Agents)
    $selectedBundles = @(Get-Bundles)
    $packages = @(Get-Packages)
    $bundlePackages = @(Get-BundlePackages)
    $rawExceptions = @([IO.File]::ReadAllText((Join-Path $Source 'deployment/windows-assets.json')) | ConvertFrom-Json)
    $exceptionRecords = New-Object System.Collections.ArrayList
    $pendingAssetRecords = New-Object System.Collections.Stack
    $pendingAssetRecords.Push($rawExceptions)
    while ($pendingAssetRecords.Count -gt 0) {
        $candidate = $pendingAssetRecords.Pop()
        if ($candidate -is [Array]) {
            foreach ($item in $candidate) { $pendingAssetRecords.Push($item) }
        } else { [void]$exceptionRecords.Add($candidate) }
    }
    $exceptions = @($exceptionRecords.ToArray())
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
    $agentCatalog = @(Get-AgentCatalog)
    foreach ($agent in @($agentCatalog | ForEach-Object { $_.agent } | Select-Object -Unique)) {
        $records = @($agentCatalog | Where-Object { $_.agent -eq $agent })
        if ($records[0].selection -ne 'always' -and $agent -notin $selectedAgents) { continue }
        $viable = @(Select-AgentRecords $agentCatalog $agent)
        if ($viable.Count -eq 0) { continue }
        $row = $viable[0]
        $ownedRecords = @($records | Where-Object { $_.provider -in @('bun', 'native') })
        $owned = $ownedRecords[0]
        $tools += $row.commands.Split(',')
        $entry = [ordered]@{
            name = $agent; provider = $row.provider; policy = $row.policy; version = $row.version
            commands = @($row.commands.Split(',')); herdr = $(if ($row.herdr -eq '-') { $null } else { $row.herdr })
        }
        if ($owned.provider -eq 'bun') {
            $entry['package'] = $owned.package; $entry['manager'] = 'bun'
            $entry['minimumNode'] = $owned.minimumNode; $entry['lock'] = $owned.lock
        } else {
            $entry['package'] = $null; $entry['manager'] = 'native'; $entry['manifest'] = $owned.lock
        }
        $agentPackages += $entry
    }
    $actions = @('install-managers', 'apply-source', 'install-common', 'install-agents', 'prepare-shell')
    if ($ApplyOnly) { $actions = @('apply-source') }
    if ($AgentsOnly) { $actions = @('apply-source', 'install-agents') }
    $result = [ordered]@{
        platform = $selection.platform; role = $selection.role; arch = $selection.arch; profile = $selection.profile
        mirror = $selection.mirror
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
