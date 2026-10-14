[CmdletBinding()]
param(
    [string]$LogDirectory,
    [switch]$Wait
)

# Same documented Python entry point as blue / left-to-right simulation.
# Resolve paths from this script, never from the caller's current directory or PATH.
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot 'PythonScripts\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Project Python was not found: $pythonPath"
}
$version = & $pythonPath -c 'import sys,struct; print(sys.version.split()[0]); sys.exit(0 if sys.version_info[:2] == (3,12) and struct.calcsize("P")==8 else 1)'
if ($LASTEXITCODE -ne 0) {
    throw "CppPackage requires the project Python 3.12 x64 runtime. Found: $version"
}
$existing = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'python.exe' -and $_.CommandLine -match 'PythonScripts[\\/]main\.py' -and
    $_.CommandLine -match '(--team\s+blue|-t\s+blue)'
}
if ($existing) {
    throw "A blue strategy process is already running (PID: $($existing.ProcessId -join ', ')). Stop it before starting another."
}
if (-not $LogDirectory) {
    $LogDirectory = Join-Path $projectRoot ('LOG\left_to_right_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
}
$null = New-Item -ItemType Directory -Path $LogDirectory -Force
$LogDirectory = (Resolve-Path -LiteralPath $LogDirectory).Path
$stdoutPath = Join-Path $LogDirectory 'stdout.log'
$stderrPath = Join-Path $LogDirectory 'stderr.log'
$launchArgs = @('-X','utf8','-u','PythonScripts/main.py','--sim','--team','blue','--side','left')
$strategyProcess = Start-Process -FilePath $pythonPath -ArgumentList $launchArgs `
    -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
[pscustomobject]@{
    ProcessId = $strategyProcess.Id
    Python = $pythonPath
    Version = $version
    Stdout = $stdoutPath
    Stderr = $stderrPath
} | Format-List
if ($Wait) {
    $strategyProcess.WaitForExit()
    $strategyProcess.Refresh()
    exit $strategyProcess.ExitCode
}
