param([switch]$SwapRobots, [switch]$KeepScene)

# Start grSim + Client first; grSim must use Division B (9 x 6 m).
$ErrorActionPreference = 'Stop'
if ($KeepScene -and $SwapRobots) {
    throw 'KeepScene preserves current positions; do not combine it with SwapRobots.'
}
$passPython = Join-Path $PSScriptRoot 'PythonScripts\.venv\Scripts\python.exe'
$passPrevious = @{}
foreach ($name in @('SRC_PRELIM', 'SRC_KICK_CALIBRATION', 'SRC_SIMPLE_PASS', 'PYTHONIOENCODING')) {
    $passPrevious[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
Push-Location $PSScriptRoot
try {
    $env:SRC_PRELIM = '0'
    $env:SRC_KICK_CALIBRATION = '0'
    $env:SRC_SIMPLE_PASS = '1'
    $env:PYTHONIOENCODING = 'utf-8'
    if (-not $KeepScene) {
        $sceneOptions = @()
        if ($SwapRobots) { $sceneOptions += '--swap-robots' }
        & $passPython PythonScripts/tools/preliminary_scene.py @sceneOptions
        if ($LASTEXITCODE -ne 0) { throw 'Scene reset failed' }
    } else {
        Write-Host 'Keeping current ball and robot positions. Starting a fresh strategy round.'
    }
    Start-Sleep -Milliseconds 700
    & $passPython -X faulthandler -u PythonScripts/main.py --sim --team blue --side left
    if ($LASTEXITCODE -ne 0) { throw "Strategy exited with code $LASTEXITCODE; keep its error output for diagnosis" }
} finally {
    foreach ($name in $passPrevious.Keys) {
        [Environment]::SetEnvironmentVariable($name, $passPrevious[$name], 'Process')
    }
    Pop-Location
}
