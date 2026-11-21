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
$runId = [Guid]::NewGuid().ToString('N')
$reportPath = Join-Path $ReportDirectory 'windows.json'
# Every file this run writes carries its own name, so a report, a fact file,
# or a test log left behind by an earlier run can never be read as this run's
# evidence. The assembled report is published under the shared name only
# after it has been checked.
$stagedReportPath = Join-Path $ReportDirectory ("windows-$runId.json")
$factsPath = Join-Path $ReportDirectory ("windows-facts-$runId.json")
$testLogPath = Join-Path $ReportDirectory ("windows-tests-$runId.log")
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

# The checkout the run verifies is established before any check runs, so the
# report names the source the scenarios actually exercised.
$identity = $null
$identityFailure = ''
if ($python) {
    $identityOutput = & $python (Join-Path $source 'tests/native_report.py') --identity --source $source 2>&1
    $identityExit = $LASTEXITCODE
    if ($identityExit -eq 0) {
        try { $identity = (($identityOutput | Out-String).Trim() | ConvertFrom-Json) }
        catch { $identityFailure = $_.Exception.Message }
    } else {
        $identityFailure = "the checkout identity could not be established (exit $identityExit)"
    }
} else {
    $identityFailure = 'no Python runtime is available to establish the checkout identity'
}
if ($identityFailure) {
    Add-Scenario -Name 'checkout identity' -Outcome 'failed' -Reason $identityFailure
} else {
    Add-Scenario -Name 'checkout identity' -Outcome 'passed'
}

# The scenarios a native Windows run has to establish. A scenario that did
# not pass withholds the acceptance instead of sitting beside it.
$requiredScenarios = @('checkout identity', 'native runtime and architecture',
                        'native renderer preparation', 'native windows deployment tests',
                        'native full-to-narrow agent state and status',
                        'native targeted repair and preservation')
if ($Bundles) { $requiredScenarios += 'native bundle exposure' }

# The scenarios the native fixture states for itself. The fixture reports the
# transition it reached for each of them, so the adapter reads what the
# fixture observed instead of inferring an outcome from an exit status.
$fixtureScenarios = @('native bundle exposure', 'native full-to-narrow agent state and status',
                      'native targeted repair and preservation')

# The outcome the native fixture reported for one scenario. The shared contract
# owns the marker vocabulary and the rule that a scenario the fixture started
# and never passed failed inside it, while a scenario it never started was
# never reached.
function Get-FixtureOutcome {
    param([string]$Scenario)
    if (-not $python) { return 'unknown' }
    $exit = 1
    $ErrorActionPreference = 'Continue'
    try {
        $output = & $python (Join-Path $source 'tests/native_report.py') --fixture-outcome --log $testLogPath --scenario $Scenario 2>&1
        $exit = $LASTEXITCODE
    } catch {
        return 'unknown'
    }
    if ($exit -ne 0) { return 'unknown' }
    return (($output | Out-String).Trim())
}

try {
    # The ordinary native-home discovery without the XDG startup boundary needs
    # a Windows host that starts without XDG, which the disposable-home
    # contract forbids. The scenario stays visible with that reason.
    $knownFolderReason = 'not exercised; explicit XDG startup boundary prevents writes to the CI user profile'
    $preflightReason = ''
    $preflightPassed = $false
    try {
        if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'this is a native Windows gate' }
        if ($env:PROCESSOR_ARCHITECTURE -ne 'AMD64' -and $env:PROCESSOR_ARCHITEW6432 -ne 'AMD64') { throw 'native Windows matrix requires x86_64' }
        if ($PSVersionTable.PSVersion -lt [version]'5.1') { throw 'Windows PowerShell 5.1 or newer is required' }
        $preflightPassed = $true
        Add-Scenario -Name 'native runtime and architecture' -Outcome 'passed'
    } catch {
        # A runner that cannot execute the native target establishes nothing
        # about it, so the preflight is unavailable rather than failed.
        $preflightReason = $_.Exception.Message
        Add-Scenario -Name 'native runtime and architecture' -Outcome 'unavailable' -Reason $preflightReason
    }
    $nativeExecution = $preflightPassed
    $fields.nativeExecution = $nativeExecution
    $renderer = $false
    $rendererReason = ''
    $testsPassed = $false
    if ($nativeExecution) {
        $env:DOTFILES_TEST_POWERSHELL = Join-Path $PSHOME 'powershell.exe'
        if (-not [IO.File]::Exists($env:DOTFILES_TEST_POWERSHELL)) { $env:DOTFILES_TEST_POWERSHELL = Join-Path $PSHOME 'pwsh.exe' }
        $env:DOTFILES_TEST_NATIVE_WINDOWS_INSTALL = '1'
        $env:DOTFILES_TEST_WINDOWS_ROLE = $Role
        if ($Bundles) { $env:DOTFILES_TEST_WINDOWS_BUNDLES = $Bundles } else { Remove-Item Env:\DOTFILES_TEST_WINDOWS_BUNDLES -ErrorAction SilentlyContinue }
        $env:PYTHONUTF8 = '1'
        $env:DOTFILES_TEST_WINDOWS_TEMP = [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($ReportDirectory))
        try {
            # A native ApplyOnly seed verifies stock PowerShell without Git Bash
            # and supplies the pinned renderer to every preservation test. It
            # applies the source without installing a package, so it cannot
            # establish that a selected bundle is exposed.
            $seed = @{ TargetHome = $managerHome; Role = $Role; ApplyOnly = $true }
            if ($Bundles) { $seed.Bundles = $Bundles }
            $global:LASTEXITCODE = 0
            & (Join-Path $source 'bootstrap.ps1') @seed
            if ($LASTEXITCODE) { throw 'native renderer preparation failed' }
            $renderer = $true
            Add-Scenario -Name 'native renderer preparation' -Outcome 'passed'
        } catch {
            $rendererReason = $_.Exception.Message
            Add-Scenario -Name 'native renderer preparation' -Outcome 'failed' -Reason $rendererReason
        }
        if ($renderer) {
            try {
                if (-not $python) { throw 'no Python runtime is available for the native Windows deployment tests' }
                Push-Location $source
                try {
                    $ErrorActionPreference = 'Continue' # unittest writes progress to stderr on PS5.1.
                    & $python -m unittest discover -s tests -p test_windows_deployment.py -v 2>&1 | Tee-Object -FilePath $testLogPath
                    $result = $LASTEXITCODE
                } finally { $ErrorActionPreference = 'Stop'; Pop-Location }
                if ($result) {
                    $diagnostics = @()
                    if (Test-Path -LiteralPath $testLogPath) {
                        $diagnostics = @(Get-Content -LiteralPath $testLogPath | ForEach-Object {
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
                    $testsPassed = $true
                    Add-Scenario -Name 'native windows deployment tests' -Outcome 'passed'
                }
            } catch {
                $reason = $_.Exception.Message
                Write-Output "::error title=Native Windows acceptance failed::$reason"
                Add-Scenario -Name 'native windows deployment tests' -Outcome 'failed' -Reason $reason
            }
        } else {
            Add-Scenario -Name 'native windows deployment tests' -Outcome 'skipped' -Reason "the renderer preparation failed: $rendererReason"
        }
        # The native fixture states which scenarios it established. A scenario
        # it started and never passed failed inside it; a scenario it never
        # started was never reached, which is not a failure of that scenario.
        foreach ($scenario in $fixtureScenarios) {
            if ($scenario -eq 'native bundle exposure' -and -not $Bundles) {
                Add-Scenario -Name $scenario -Outcome 'skipped' -Reason 'no bundle selection was requested'
                continue
            }
            $outcome = Get-FixtureOutcome -Scenario $scenario
            if ($outcome -eq 'passed') {
                Add-Scenario -Name $scenario -Outcome 'passed'
            } elseif ($outcome -eq 'failed') {
                Add-Scenario -Name $scenario -Outcome 'failed' -Reason 'the native fixture started this scenario and did not report it as passed'
            } elseif ($outcome -eq 'skipped') {
                if (-not $renderer) {
                    Add-Scenario -Name $scenario -Outcome 'skipped' -Reason "the renderer preparation failed: $rendererReason"
                } elseif (-not $testsPassed) {
                    Add-Scenario -Name $scenario -Outcome 'skipped' -Reason 'the native deployment tests never reached this scenario'
                } else {
                    Add-Scenario -Name $scenario -Outcome 'failed' -Reason 'the native deployment test did not report this scenario'
                }
            } else {
                Add-Scenario -Name $scenario -Outcome 'failed' -Reason 'the native fixture report could not be read'
            }
        }
    } else {
        $preflight = "the native runtime preflight did not pass: $preflightReason"
        Add-Scenario -Name 'native renderer preparation' -Outcome 'skipped' -Reason $preflight
        Add-Scenario -Name 'native windows deployment tests' -Outcome 'skipped' -Reason $preflight
        foreach ($scenario in $fixtureScenarios) {
            $reason = if ($scenario -eq 'native bundle exposure' -and -not $Bundles) {
                'no bundle selection was requested'
            } else {
                $preflight
            }
            Add-Scenario -Name $scenario -Outcome 'skipped' -Reason $reason
        }
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
            identity = $identity; required = @($requiredScenarios)
            # A generic list does not serialize; its array does.
            scenarios = @($scenarios.ToArray()); fields = $fields
        }
        [IO.File]::WriteAllText($factsPath, ($facts | ConvertTo-Json -Depth 8), (New-Object Text.UTF8Encoding($false)))
        if (-not $python) { throw 'no Python runtime is available for the shared report contract' }
        & $python (Join-Path $source 'tests/native_report.py') --source $source --facts $factsPath --output $stagedReportPath
        $assemblerExit = $LASTEXITCODE
        if ($assemblerExit -ne 0) { throw "the shared report contract failed (exit $assemblerExit)" }
        if (-not (Test-Path -LiteralPath $stagedReportPath)) { throw 'the shared report contract wrote no report' }
        $assembled = Get-Content -LiteralPath $stagedReportPath -Raw | ConvertFrom-Json
        # The published report has to be the one this run produced, naming the
        # checkout this run established before its checks.
        if ($identity) {
            if ($assembled.checkout.commit -ne $identity.commit -or
                $assembled.checkout.source_sha256 -ne $identity.source_sha256) {
                throw 'the assembled report does not name the checkout this run established'
            }
        }
        Move-Item -LiteralPath $stagedReportPath -Destination $reportPath -Force
    } catch {
        Write-Output "::warning title=Native Windows report::$($_.Exception.Message)"
        # The canonical report must never keep a verdict from another run, so
        # a contract that cannot assemble this report replaces it. A runner
        # that could not execute natively establishes nothing about the
        # target, so its report is unavailable; a native run whose contract
        # failed is failed.
        $fallbackStatus = if ([bool]$fields.nativeExecution) { 'failed' } else { 'unavailable' }
        $fallback = [ordered]@{
            platform = 'windows'; role = $Role; arch = 'x86_64'; started = $started
            nativeExecution = [bool]$fields.nativeExecution; status = $fallbackStatus; acceptance = $false
            checkout = $identity
            scenarios = @($scenarios.ToArray())
            reason = "the shared report contract could not assemble this report: $($_.Exception.Message)"
        }
        [IO.File]::WriteAllText($reportPath, ($fallback | ConvertTo-Json -Depth 8), (New-Object Text.UTF8Encoding($false)))
    } finally {
        # Never upload homes containing runtime authentication/history state.
        if (Test-Path -LiteralPath $managerHome) { Remove-Item -LiteralPath $managerHome -Recurse -Force }
    }
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
