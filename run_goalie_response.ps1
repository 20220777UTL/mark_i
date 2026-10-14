[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$python = Join-Path $root 'PythonScripts\.venv\Scripts\python.exe'
$ini = Join-Path $root 'zss.ini'
$grsim = Join-Path $root 'grSim.exe'
$client = Join-Path $root 'Client.exe'

if (-not (Test-Path -LiteralPath $python)) { throw "Python 3.12 venv not found: $python" }
if (-not (Test-Path -LiteralPath $ini)) { throw "Runtime config not found: $ini" }
$version = & $python -c 'import sys; print(sys.version.split()[0]); sys.exit(0 if sys.version_info[:3] == (3,12,10) else 1)'
if ($LASTEXITCODE -ne 0) { throw "This experiment requires Python 3.12.10; found $version" }

$expectedPython = [IO.Path]::GetFullPath($python)
$runningStrategy = Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object {
    try { [IO.Path]::GetFullPath($_.Path) -ieq $expectedPython } catch { $false }
}
if ($runningStrategy) {
    throw "Stop the existing mark_i Python process first (PID $($runningStrategy.Id -join ', '))."
}

$runId = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
$output = Join-Path (Split-Path $root -Parent) "tmp\goalie_response_$runId"
$null = New-Item -ItemType Directory -Path $output -Force
$stdout = Join-Path $output 'stdout.log'
$stderr = Join-Path $output 'stderr.log'
$originalIni = [IO.File]::ReadAllBytes($ini)
$previousOutput = [Environment]::GetEnvironmentVariable('SRC_GOALIE_RESPONSE_OUT', 'Process')
$strategy = $null

try {
    if (-not (Get-Process grSim -ErrorAction SilentlyContinue)) {
        if (-not (Test-Path -LiteralPath $grsim)) { throw "Simulator not found: $grsim" }
        Start-Process -FilePath $grsim -WorkingDirectory $root
        Write-Host 'Started grSim. Confirm that the desired field division is loaded.'
        Start-Sleep -Seconds 3
    }
    if (-not (Get-Process Client -ErrorAction SilentlyContinue)) {
        if (-not (Test-Path -LiteralPath $client)) { throw "Client not found: $client" }
        Start-Process -FilePath $client -WorkingDirectory $root
        Write-Host 'Started Client; waiting for vision and referee connection.'
        Start-Sleep -Seconds 5
    }

    $env:SRC_GOALIE_RESPONSE_OUT = $output
    $launchArgs = @('-X', 'utf8', '-u', 'PythonScripts/run_goalie_response.py',
                    '--sim', '--team', 'yellow', '--side', 'right')
    $strategy = Start-Process -FilePath $python -ArgumentList $launchArgs -WorkingDirectory $root `
        -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    Write-Host "Running 60 GoalieOnly response trials (PID $($strategy.Id)); logs: $output"

    $deadline = (Get-Date).AddMinutes(12)
    $nextProgress = (Get-Date).AddSeconds(15)
    while (-not $strategy.HasExited -and (Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 2
        $strategy.Refresh()
        if (-not $strategy.HasExited -and (Get-Date) -ge $nextProgress) {
            $latest = Get-Content -LiteralPath $stdout -Tail 1 -ErrorAction SilentlyContinue
            if ($latest) { Write-Host $latest }
            $nextProgress = (Get-Date).AddSeconds(15)
        }
    }
    $strategy.Refresh()
    if (-not $strategy.HasExited) {
        Stop-Process -Id $strategy.Id -Force -ErrorAction SilentlyContinue
        throw "Goalie experiment timed out after 12 minutes. Partial telemetry remains in $output"
    }
    if ($strategy.ExitCode -ne 0) {
        Get-Content -LiteralPath $stderr -Tail 40 -ErrorAction SilentlyContinue
        throw "Goalie experiment exited with code $($strategy.ExitCode). Logs: $output"
    }

    Get-Content -LiteralPath $stdout -Tail 8
    Write-Host "Results: $(Join-Path $output 'results.json')"
} finally {
    # Terminate only the strategy process started here if this wrapper is stopped.
    if ($strategy -and -not $strategy.HasExited) {
        Stop-Process -Id $strategy.Id -Force -ErrorAction SilentlyContinue
        try { $strategy.WaitForExit() } catch { }
    }
    if ($null -eq $previousOutput) {
        Remove-Item Env:SRC_GOALIE_RESPONSE_OUT -ErrorAction SilentlyContinue
    } else {
        $env:SRC_GOALIE_RESPONSE_OUT = $previousOutput
    }
    # main.py writes team/side flags into zss.ini; restore the exact original bytes.
    [IO.File]::WriteAllBytes($ini, $originalIni)
}
