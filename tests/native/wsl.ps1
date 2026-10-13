# Disposable CI provisioning only. Product bootstrap never changes Windows or
# imports distributions. -Plan is read-only and is not native execution proof.
[CmdletBinding()]
param(
    [switch] $Plan,
    [switch] $Provision,
    [Parameter(Mandatory = $true)] [string] $RunnerTemp,
    [Parameter(Mandatory = $true)] [string] $Source,
    [ValidateSet('workstation', 'remote-compute')] [string] $Role = 'workstation',
    [ValidateSet('x86_64', 'aarch64')] [string] $Architecture = 'x86_64'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$rootfs = if ($Architecture -eq 'x86_64') {
    @{
        url = 'https://releases.ubuntu.com/24.04.5/ubuntu-24.04.5-wsl-amd64.wsl'
        sha256 = 'bb415d824822c4b878125729af451a5d18fb13d1cf5cbed9a7393ad64ac6039e'
    }
} else {
    @{
        url = 'https://cdimage.ubuntu.com/releases/24.04.5/release/ubuntu-24.04.5-wsl-arm64.wsl'
        sha256 = '74478b5024d9047397ba79d17c27f73caf85ada4988f88cffc2892d65e6a806b'
    }
}
$coverage = if ($Architecture -eq 'x86_64') { 'hosted Windows2025 WSL2 execution required' }
            else { 'opt-in self-hosted Windows ARM64 WSL2 execution required; pending until run' }
if ($Plan) {
    @{
        platform = 'wsl'; role = $Role; architecture = $Architecture
        wslGeneration = 2; rootfs = $rootfs; nativePass = $false
        coverage = $coverage; sourceTransport = 'git archive HEAD preserves bytes and modes'
        deploymentHome = '/home/dotfilesci/validation-home'
    } | ConvertTo-Json -Depth 5 -Compress
    exit 0
}
if (-not $Provision) { throw 'Native WSL provisioning requires the explicit -Provision mode.' }
if (-not [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
    [System.Runtime.InteropServices.OSPlatform]::Windows)) {
    throw 'WSL provisioning requires a native Windows runtime; Linux planning is not a native pass.'
}

# Always check native exit codes. A committed workflow is not proof that the
# hosted VM can import/start a WSL2 kernel or execute this product's packages.
$PSNativeCommandUseErrorActionPreference = $false
function Invoke-CICommand {
    param([string] $Executable, [string[]] $ArgumentList, [string] $Description)
    $output = @(& $Executable @ArgumentList 2>&1)
    $status = $LASTEXITCODE
    if ($status -ne 0) {
        $output | ForEach-Object { Write-Host $_ }
        throw "$Description failed (exit $status)"
    }
    return @($output | ForEach-Object { "$($_)".Replace("`0", '') })
}
function Quote-BashLiteral {
    param([string] $Value)
    return "'" + $Value.Replace("'", "'\''") + "'"
}

$ciId = [Guid]::NewGuid().ToString('N')
$ciDistro = "DotfilesCI-$ciId"
$ciRoot = Join-Path ([IO.Path]::GetFullPath($RunnerTemp)) "dotfiles-wsl-$ciId"
$ciReports = Join-Path $ciRoot 'reports'
$ciArchive = Join-Path $ciRoot 'ubuntu-24.04.5-rootfs.tar.gz'
$ciSourceArchive = Join-Path $ciRoot 'source.tar'
$ciInstall = Join-Path $ciRoot 'distro'
$ciLinuxSource = '/home/dotfilesci/source'
$ciLinuxReport = '/home/dotfilesci/report/native-wsl.json'
$ciInterop = Join-Path $ciRoot 'interop space'
$ciFixture = Join-Path $ciInterop 'fixture.txt'
$ciToken = "dotfiles-wsl-$ciId"
$attemptedImport = $false
$imported = $false
$failure = $null
$wslExe = 'wsl.exe'
$report = [ordered]@{
    platform = 'wsl'; role = $Role; architecture = $Architecture
    wslGeneration = 2; nativePass = $false; phase = 'windows-preflight'
    coverage = $coverage; rootfs = $rootfs; cleanup = 'not required'
    runtime = [ordered]@{
        windowsVersion = [Environment]::OSVersion.VersionString
        windowsArchitecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
        runnerImage = $env:ImageOS; runnerImageVersion = $env:ImageVersion
    }
}
New-Item -ItemType Directory -Path $ciReports -Force | Out-Null
try {
    $expectedWindowsArch = if ($Architecture -eq 'x86_64') { 'X64' } else { 'Arm64' }
    if ($report.runtime.windowsArchitecture -ne $expectedWindowsArch) {
        throw 'Windows runtime architecture does not match the requested WSL target'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Source 'tests/native/wsl.py') -PathType Leaf)) {
        throw 'Source must be the committed dotfiles checkout containing the WSL verification entry point'
    }
    $report.runtime.wslVersion = (Invoke-CICommand $wslExe @('--version') 'WSL prerequisite probe') -join "`n"
    $commit = (Invoke-CICommand 'git' @('-C', $Source, 'rev-parse', '--verify', 'HEAD') 'Source commit probe') -join ''
    if ($commit -notmatch '^[0-9a-f]{40}$') { throw 'Source commit probe did not return an exact revision' }
    $report.commit = $commit
    # Git archive reads committed blobs and modes, avoiding CRLF/NTFS mode loss.
    # Product bootstrap still applies the working tree; this is CI transport.
    Invoke-CICommand 'git' @('-C', $Source, 'archive', '--format=tar', "--output=$ciSourceArchive", 'HEAD') 'Committed source archive' | Out-Null

    $report.phase = 'rootfs-download-and-integrity'
    Invoke-WebRequest -Uri $rootfs.url -OutFile $ciArchive
    $actualHash = (Get-FileHash -LiteralPath $ciArchive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $rootfs.sha256) { throw 'Pinned Ubuntu WSL rootfs SHA256 mismatch' }
    $report.rootfsVerified = $true
    New-Item -ItemType Directory -Path $ciInstall, $ciInterop | Out-Null
    [IO.File]::WriteAllText($ciFixture, $ciToken, [Text.UTF8Encoding]::new($false))

    $report.phase = 'wsl2-import'
    $attemptedImport = $true
    Invoke-CICommand $wslExe @('--import', $ciDistro, $ciInstall, $ciArchive, '--version', '2') 'Disposable WSL2 import' | Out-Null
    $imported = $true
    $distributionLines = Invoke-CICommand $wslExe @('--list', '--verbose') 'WSL generation probe'
    $ownedDistribution = @($distributionLines | Where-Object {
        $_ -match ('^\s*\*?\s*' + [Regex]::Escape($ciDistro) + '\s+.*\s+2\s*$')
    })
    if ($ownedDistribution.Count -ne 1) {
        throw 'Imported distro did not report WSL generation 2'
    }
    $report.runtime.distribution = $ownedDistribution[0]
    $report.runtime.linuxKernel = (Invoke-CICommand $wslExe @('-d', $ciDistro, '-u', 'root', '--exec', 'uname', '-r') 'WSL kernel startup') -join ''
    if ($report.runtime.linuxKernel -notmatch '(?i)microsoft.*wsl2') {
        throw 'Imported distro did not start a Microsoft WSL2 kernel'
    }
    $report.runtime.linuxArchitecture = (Invoke-CICommand $wslExe @('-d', $ciDistro, '-u', 'root', '--exec', 'uname', '-m') 'WSL CPU architecture') -join ''
    if ($report.runtime.linuxArchitecture -ne $Architecture) { throw 'Imported distro CPU architecture mismatch' }

    $report.phase = 'disposable-linux-prerequisites'
    $setup = @'
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends bash ca-certificates curl tar gzip xz-utils coreutils git unzip python3 libgcc-s1 libstdc++6
useradd --create-home --shell /bin/bash dotfilesci
install -d -o dotfilesci -g dotfilesci /home/dotfilesci/source /home/dotfilesci/report
'@
    Invoke-CICommand $wslExe @('-d', $ciDistro, '-u', 'root', '--exec', 'bash', '-lc', $setup) 'Disposable Linux prerequisites and nonroot user' | ForEach-Object { Write-Host $_ }
    $sourceArchiveLinux = (Invoke-CICommand $wslExe @('-d', $ciDistro, '-u', 'root', '--exec', 'wslpath', '-a', '-u', $ciSourceArchive) 'Source transport path') -join ''
    $copySource = 'set -euo pipefail; tar -xf ' + (Quote-BashLiteral $sourceArchiveLinux) +
                  ' -C ' + (Quote-BashLiteral $ciLinuxSource) + '; chown -R dotfilesci:dotfilesci ' + (Quote-BashLiteral $ciLinuxSource)
    Invoke-CICommand $wslExe @('-d', $ciDistro, '-u', 'root', '--exec', 'bash', '-lc', $copySource) 'Source extraction on Linux filesystem' | Out-Null

    $report.phase = 'native-product-verification'
    $runUrl = if ($env:GITHUB_SERVER_URL -and $env:GITHUB_REPOSITORY -and $env:GITHUB_RUN_ID) {
        "$env:GITHUB_SERVER_URL/$env:GITHUB_REPOSITORY/actions/runs/$env:GITHUB_RUN_ID"
    } else { '' }
    $windowsCommand = Join-Path $env:SystemRoot 'System32/cmd.exe'
    $verifyArguments = @('-d', $ciDistro, '-u', 'dotfilesci', '--exec', 'python3', "$ciLinuxSource/tests/native/wsl.py",
        '--verify', '--role', $Role, '--arch', $Architecture, '--home', '/home/dotfilesci/validation-home',
        '--report', $ciLinuxReport, '--windows-file', $ciFixture, '--windows-command', $windowsCommand,
        '--interop-token', $ciToken, '--commit', $commit)
    if ($runUrl) { $verifyArguments += @('--run-url', $runUrl) }
    Invoke-CICommand $wslExe $verifyArguments 'Unprivileged WSL deployment and interoperability gate' | ForEach-Object { Write-Host $_ }
    $nativeJson = (Invoke-CICommand $wslExe @('-d', $ciDistro, '-u', 'root', '--exec', 'cat', $ciLinuxReport) 'Native result collection') -join "`n"
    if (-not ($nativeJson | ConvertFrom-Json).nativePass) { throw 'Native verification did not establish a WSL pass' }
    $report.nativePass = $true
    $report.phase = 'complete'
} catch {
    $failure = $_.Exception.Message
    $report.failure = $failure
    Write-Host "native-wsl: $($report.phase) failed: $failure"
} finally {
    if ($imported) {
        $collected = @(& $wslExe '-d' $ciDistro '-u' 'root' '--exec' 'cat' $ciLinuxReport 2>$null)
        if ($LASTEXITCODE -eq 0) {
            [IO.File]::WriteAllText((Join-Path $ciReports 'native-wsl.json'), ($collected -join "`n"), [Text.UTF8Encoding]::new($false))
        }
    }
    if ($attemptedImport) {
        # Clean even when kernel startup, apt, bootstrap, or acceptance fails.
        # Only the fresh random-name distro owned by this invocation is touched.
        $null = & $wslExe '--terminate' $ciDistro 2>$null
        $null = & $wslExe '--unregister' $ciDistro 2>$null
        $unregisterStatus = $LASTEXITCODE
        $remaining = @(& $wslExe '--list' '--quiet' 2>$null)
        $listStatus = $LASTEXITCODE
        $names = @($remaining | ForEach-Object { "$($_)".Replace("`0", '').Trim() })
        if ($listStatus -ne 0 -or $names -contains $ciDistro -or ($imported -and $unregisterStatus -ne 0)) {
            $report.cleanup = 'failed: disposable distro cleanup must be investigated'
            $report.nativePass = $false
            $failure = if ($failure) { "$failure; disposable distro cleanup failed" } else { 'Disposable distro cleanup failed' }
        } else {
            $report.cleanup = 'disposable distro unregistered'
        }
    }
    Remove-Item -LiteralPath $ciArchive, $ciSourceArchive -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $ciInterop) {
        Remove-Item -LiteralPath $ciInterop -Recurse -Force -ErrorAction SilentlyContinue
    }
    [IO.File]::WriteAllText((Join-Path $ciReports 'controller.json'), ($report | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
}
if ($failure) { throw "Native WSL gate failed: $failure" }
Write-Host "native-wsl: passed $Architecture $Role; disposable distro cleaned"
