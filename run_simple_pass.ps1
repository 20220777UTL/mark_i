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
    $nativeCrashCodes = @(-1073741819, -1073740940) # access violation, heap corruption
    $maxAttempts = 4
    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        if (-not $KeepScene) {
            $sceneOptions = @()
            if ($SwapRobots) { $sceneOptions += '--swap-robots' }
            & $passPython PythonScripts/tools/preliminary_scene.py @sceneOptions
            if ($LASTEXITCODE -ne 0) { throw 'Scene reset failed' }
        } else {
            Write-Host 'Keeping current ball and robot positions. Starting a fresh strategy round.'
        }
        # Let grSim publish a few complete vision cycles after replacing the scene.
        Start-Sleep -Seconds 2
        Write-Host "Starting strategy attempt $attempt/$maxAttempts"
        & $passPython -X faulthandler -u PythonScripts/main.py --sim --team blue --side left
        $exitCode = $LASTEXITCODE
        if ($exitCode -eq 0) { break }
        if ($nativeCrashCodes -contains $exitCode -and $attempt -lt $maxAttempts) {
            Write-Warning "Native C++ module exited with code $exitCode; retrying after 2 seconds"
            Start-Sleep -Seconds 2
            continue
        }
        throw "Strategy exited with code $exitCode after $attempt attempt(s); keep its error output for diagnosis"
    }
} finally {
    foreach ($name in $passPrevious.Keys) {
        [Environment]::SetEnvironmentVariable($name, $passPrevious[$name], 'Process')
    }
    Pop-Location
}
