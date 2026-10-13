# Native Windows acceptance; report files contain no homes, keys or history DBs.
[CmdletBinding()]
param([ValidateSet('workstation', 'remote-compute')][string]$Role = 'workstation', [string]$ReportDirectory)
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$source = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'this is a native Windows gate' }
if ($env:PROCESSOR_ARCHITECTURE -ne 'AMD64' -and $env:PROCESSOR_ARCHITEW6432 -ne 'AMD64') { throw 'native Windows matrix requires x86_64' }
if ($PSVersionTable.PSVersion -lt [version]'5.1') { throw 'Windows PowerShell 5.1 or newer is required' }
if (-not $ReportDirectory) { $ReportDirectory = Join-Path $env:TEMP ('dotfiles-windows-report-' + [Guid]::NewGuid().ToString('N')) }
[IO.Directory]::CreateDirectory($ReportDirectory) | Out-Null
$env:DOTFILES_TEST_POWERSHELL = Join-Path $PSHOME 'powershell.exe'
if (-not [IO.File]::Exists($env:DOTFILES_TEST_POWERSHELL)) { $env:DOTFILES_TEST_POWERSHELL = Join-Path $PSHOME 'pwsh.exe' }
$env:DOTFILES_TEST_NATIVE_WINDOWS_INSTALL = '1'
$env:DOTFILES_TEST_WINDOWS_ROLE = $Role
$env:PYTHONUTF8 = '1'
$managerHome = Join-Path ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($ReportDirectory))) ('dotfiles-windows-manager-' + [Guid]::NewGuid().ToString('N'))
$started = [DateTime]::UtcNow.ToString('o')
$report = [ordered]@{
    platform = 'windows'; role = $Role; arch = 'x86_64'; started = $started
    os = [Environment]::OSVersion.VersionString; powershell = $PSVersionTable.PSVersion.ToString()
    image = $env:ImageVersion; run = "https://github.com/$($env:GITHUB_REPOSITORY)/actions/runs/$($env:GITHUB_RUN_ID)"
    nativeExecution = $true; status = 'failed'
    knownFolderFallback = 'not exercised; explicit XDG startup boundary prevents writes to the CI user profile'
}
try {
    # A native ApplyOnly seed verifies stock PowerShell without Git Bash and
    # supplies the pinned renderer to every preservation test.
    & (Join-Path $source 'bootstrap.ps1') -TargetHome $managerHome -Role $Role -ApplyOnly
    if ($LASTEXITCODE) { throw 'native renderer preparation failed' }
    $env:DOTFILES_TEST_CHEZMOI = Join-Path $managerHome '.local/bin/chezmoi.exe'
    Push-Location $source
    try {
        $ErrorActionPreference = 'Continue' # unittest writes progress to stderr on PS5.1.
        & python -m unittest discover -s tests -p test_windows_deployment.py -v 2>&1 | Tee-Object -FilePath (Join-Path $ReportDirectory 'windows-tests.log')
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
                $report.failure = $diagnostics
                $message = $diagnostics -join '; '
                Write-Output "::error title=Native Windows acceptance failed::$message"
            }
            throw 'native Windows deployment tests failed'
        }
    $report.status = 'passed'
} finally {
    $report.finished = [DateTime]::UtcNow.ToString('o')
    [IO.File]::WriteAllText((Join-Path $ReportDirectory 'windows.json'), ($report | ConvertTo-Json -Depth 6), (New-Object Text.UTF8Encoding($false)))
    # Never upload homes containing runtime authentication/history state.
    if (Test-Path -LiteralPath $managerHome) { Remove-Item -LiteralPath $managerHome -Recurse -Force }
}
