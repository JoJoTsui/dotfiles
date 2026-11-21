# Native Windows acceptance; report files contain no homes, keys or history DBs.
[CmdletBinding()]
param([ValidateSet('workstation', 'remote-compute')][string]$Role = 'workstation',
      [string]$Bundles, [string]$ReportDirectory)
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$source = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
if (-not $env:TEMP) { $env:TEMP = [IO.Path]::GetTempPath() }
if (-not $ReportDirectory) { $ReportDirectory = Join-Path $env:TEMP ('dotfiles-windows-report-' + [Guid]::NewGuid().ToString('N')) }
[IO.Directory]::CreateDirectory($ReportDirectory) | Out-Null
$reportPath = Join-Path $ReportDirectory 'windows.json'
$factsPath = Join-Path $ReportDirectory 'windows-facts.json'
$managerHome = Join-Path ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($ReportDirectory))) ('dotfiles-windows-manager-' + [Guid]::NewGuid().ToString('N'))
$started = [DateTime]::UtcNow.ToString('o')
$scenarios = New-Object 'System.Collections.Generic.List[object]'

# Every scenario the run attempted, with the outcome it reached. A scenario
# that did not pass states why, so a skipped check never reads as a pass.
function Add-Scenario {
    param([string]$Name, [string]$Outcome, [string]$Reason = '', [double]$Seconds = -1)
    $record = [ordered]@{ name = $Name; outcome = $Outcome }
    if ($Reason) { $record['reason'] = $Reason }
    if ($Seconds -ge 0) { $record['seconds'] = [math]::Round($Seconds, 3) }
    $script:scenarios.Add($record)
}

# The report's verdict belongs to the shared contract, so the script hands
# over what it observed instead of deciding the outcome on its own.
function Resolve-Python {
    foreach ($candidate in @($env:DOTFILES_TEST_PYTHON, 'python', 'python3')) {
        if (-not $candidate) { continue }
        $command = Get-Command -Name $candidate -CommandType Application -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($command) { return $command.Path }
    }
    return $null
}

$python = Resolve-Python
$fields = [ordered]@{
    platform = 'windows'; role = $Role; arch = 'x86_64'; started = $started
    os = [Environment]::OSVersion.VersionString; powershell = $PSVersionTable.PSVersion.ToString()
    image = $env:ImageVersion; run = "https://github.com/$($env:GITHUB_REPOSITORY)/actions/runs/$($env:GITHUB_RUN_ID)"
    nativeExecution = $false
}
if ($Bundles) { $fields.bundles = @($Bundles.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ }) }
try {
    # The ordinary native-home discovery without the XDG startup boundary needs
    # a Windows host that starts without XDG, which the disposable-home
    # contract forbids. The scenario stays visible with that reason.
    $knownFolderReason = 'not exercised; explicit XDG startup boundary prevents writes to the CI user profile'
    $preflightReason = ''
    try {
        if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'this is a native Windows gate' }
        if ($env:PROCESSOR_ARCHITECTURE -ne 'AMD64' -and $env:PROCESSOR_ARCHITEW6432 -ne 'AMD64') { throw 'native Windows matrix requires x86_64' }
        if ($PSVersionTable.PSVersion -lt [version]'5.1') { throw 'Windows PowerShell 5.1 or newer is required' }
        Add-Scenario -Name 'native runtime and architecture' -Outcome 'passed'
    } catch {
        # A runner that cannot execute the native target establishes nothing
        # about it, so the preflight is unavailable rather than failed.
        $preflightReason = $_.Exception.Message
        Add-Scenario -Name 'native runtime and architecture' -Outcome 'unavailable' -Reason $preflightReason
    }
    $nativeExecution = ($scenarios[0].outcome -eq 'passed')
    $fields.nativeExecution = $nativeExecution
    if ($nativeExecution) {
        $env:DOTFILES_TEST_POWERSHELL = Join-Path $PSHOME 'powershell.exe'
        if (-not [IO.File]::Exists($env:DOTFILES_TEST_POWERSHELL)) { $env:DOTFILES_TEST_POWERSHELL = Join-Path $PSHOME 'pwsh.exe' }
        $env:DOTFILES_TEST_NATIVE_WINDOWS_INSTALL = '1'
        $env:DOTFILES_TEST_WINDOWS_ROLE = $Role
        if ($Bundles) { $env:DOTFILES_TEST_WINDOWS_BUNDLES = $Bundles } else { Remove-Item Env:\DOTFILES_TEST_WINDOWS_BUNDLES -ErrorAction SilentlyContinue }
        $env:PYTHONUTF8 = '1'
        $env:DOTFILES_TEST_WINDOWS_TEMP = [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($ReportDirectory))
        $renderer = $true
        try {
            # A native ApplyOnly seed verifies stock PowerShell without Git Bash
            # and supplies the pinned renderer to every preservation test.
            $seed = @{ TargetHome = $managerHome; Role = $Role; ApplyOnly = $true }
            if ($Bundles) { $seed.Bundles = $Bundles }
            $global:LASTEXITCODE = 0
            & (Join-Path $source 'bootstrap.ps1') @seed
            if ($LASTEXITCODE) { throw 'native renderer preparation failed' }
            Add-Scenario -Name 'native renderer preparation' -Outcome 'passed'
            if ($Bundles) {
                Add-Scenario -Name 'selected bundle exposure' -Outcome 'passed'
            } else {
                Add-Scenario -Name 'selected bundle exposure' -Outcome 'skipped' -Reason 'no bundle selection was requested'
            }
        } catch {
            $renderer = $false
            $reason = $_.Exception.Message
            Add-Scenario -Name 'native renderer preparation' -Outcome 'failed' -Reason $reason
            Add-Scenario -Name 'selected bundle exposure' -Outcome 'skipped' -Reason "the renderer preparation failed: $reason"
            Add-Scenario -Name 'native windows deployment tests' -Outcome 'skipped' -Reason "the renderer preparation failed: $reason"
        }
        if ($renderer) {
            try {
                if (-not $python) { throw 'no Python runtime is available for the native Windows deployment tests' }
                Push-Location $source
                try {
                    $ErrorActionPreference = 'Continue' # unittest writes progress to stderr on PS5.1.
                    & $python -m unittest discover -s tests -p test_windows_deployment.py -v 2>&1 | Tee-Object -FilePath (Join-Path $ReportDirectory 'windows-tests.log')
                    $result = $LASTEXITCODE
                } finally { $ErrorActionPreference = 'Stop'; Pop-Location }
                if ($result) {
                    $testLog = Join-Path $ReportDirectory 'windows-tests.log'
                    $diagnostics = @()
                    if (Test-Path -LiteralPath $testLog) {
                        $diagnostics = @(Get-Content -LiteralPath $testLog | ForEach-Object {
                            if ($_ -match '^(FAIL|ERROR): (test_[A-Za-z0-9_]+)\b') {
                                "$($Matches[1]): $($Matches[2])"
                            } elseif ($_ -match '^Ran ([0-9]+) tests? in ') {
                                "Ran $($Matches[1]) tests"
                            } elseif ($_ -match '^FAILED') {
                                'FAILED'
                            }
                        } | Select-Object -First 8)
                    }
                    if ($diagnostics.Count -gt 0) {
                        $message = $diagnostics -join '; '
                        Write-Output "::error title=Native Windows acceptance failed::$message"
                        Add-Scenario -Name 'native windows deployment tests' -Outcome 'failed' -Reason $message
                    } else {
                        Write-Output '::error title=Native Windows acceptance failed::the native Windows deployment tests failed'
                        Add-Scenario -Name 'native windows deployment tests' -Outcome 'failed' -Reason 'the native Windows deployment tests failed'
                    }
                } else {
                    Add-Scenario -Name 'native windows deployment tests' -Outcome 'passed'
                }
            } catch {
                $reason = $_.Exception.Message
                Write-Output "::error title=Native Windows acceptance failed::$reason"
                Add-Scenario -Name 'native windows deployment tests' -Outcome 'failed' -Reason $reason
            }
        }
    } else {
        $preflight = "the native runtime preflight did not pass: $preflightReason"
        Add-Scenario -Name 'native renderer preparation' -Outcome 'skipped' -Reason $preflight
        Add-Scenario -Name 'selected bundle exposure' -Outcome 'skipped' -Reason $preflight
        Add-Scenario -Name 'native windows deployment tests' -Outcome 'skipped' -Reason $preflight
    }
    Add-Scenario -Name 'known folder fallback' -Outcome 'skipped' -Reason $knownFolderReason
} catch {
    $reason = $_.Exception.Message
    Write-Output "::error title=Native Windows acceptance failed::$reason"
    Add-Scenario -Name 'native acceptance run' -Outcome 'failed' -Reason $reason
} finally {
    try {
        $facts = [ordered]@{
            source = $source; native_execution = [bool]$fields.nativeExecution
            # A generic list does not serialize; its array does.
            scenarios = @($scenarios.ToArray()); fields = $fields
        }
        [IO.File]::WriteAllText($factsPath, ($facts | ConvertTo-Json -Depth 6), (New-Object Text.UTF8Encoding($false)))
        if ($python) {
            & $python (Join-Path $source 'tests/native_report.py') --source $source --facts $factsPath --output $reportPath
        } else {
            Write-Output '::warning title=Native Windows report::no Python runtime is available for the shared report contract'
        }
    } catch {
        Write-Output "::warning title=Native Windows report::$($_.Exception.Message)"
    } finally {
        # Never upload homes containing runtime authentication/history state.
        if (Test-Path -LiteralPath $managerHome) { Remove-Item -LiteralPath $managerHome -Recurse -Force }
    }
}
if (-not (Test-Path -LiteralPath $reportPath)) {
    # The shared contract could not apply its verdict, so the run fails closed.
    $fallback = [ordered]@{
        platform = 'windows'; role = $Role; arch = 'x86_64'; started = $started
        nativeExecution = [bool]$fields.nativeExecution; status = 'failed'; acceptance = $false
        scenarios = @($scenarios.ToArray())
        reason = 'the shared report contract could not assemble this report'
    }
    [IO.File]::WriteAllText($reportPath, ($fallback | ConvertTo-Json -Depth 6), (New-Object Text.UTF8Encoding($false)))
}
$established = $false
try {
    $written = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
    $established = [bool]$written.acceptance
} catch { }
if (-not $established) {
    Write-Output '::error title=Native Windows acceptance failed::the native run established no acceptance'
    exit 1
}
exit 0
