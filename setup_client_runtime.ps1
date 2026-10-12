$ErrorActionPreference = 'Stop'
$repo = $PSScriptRoot
$venvConfig = Join-Path $repo 'PythonScripts\.venv\pyvenv.cfg'
if (-not (Test-Path -LiteralPath $venvConfig)) {
    throw 'Create the Windows PythonScripts\.venv with uv sync --locked first.'
}
$homeLine = Get-Content -LiteralPath $venvConfig | Where-Object { $_ -match '^home\s*=' } | Select-Object -First 1
if (-not $homeLine) { throw 'Python runtime home is missing from pyvenv.cfg.' }
$runtime = ($homeLine -split '=', 2)[1].Trim()
if (-not (Test-Path -LiteralPath (Join-Path $runtime 'python312.dll'))) {
    throw "Expected a Python 3.12 runtime at $runtime"
}

foreach ($name in @('python312.dll', 'python3.dll')) {
    $source = Join-Path $runtime $name
    $destination = Join-Path $repo $name
    if (Test-Path -LiteralPath $destination) {
        $sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
        $destinationHash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash
        if ($sourceHash -eq $destinationHash) { continue }
    }
    Copy-Item -LiteralPath $source -Destination $destination -Force
}
foreach ($name in @('Lib', 'DLLs')) {
    $link = Join-Path $repo $name
    $target = Join-Path $runtime $name
    if (Test-Path -LiteralPath $link) {
        $existing = Get-Item -LiteralPath $link -Force
        $actualTarget = $existing.Target
        if ($existing.LinkType -eq 'Junction') {
            $parent = Get-Item -LiteralPath (Split-Path $actualTarget -Parent)
            if ($parent.LinkType -eq 'Junction') {
                $actualTarget = Join-Path $parent.Target (Split-Path $actualTarget -Leaf)
            }
        }
        if ($existing.LinkType -eq 'Junction' -and $actualTarget -eq $target) { continue }
        throw "An unrelated $link already exists; leave it untouched."
    }
    New-Item -ItemType Junction -Path $link -Target $target | Out-Null
}
New-Item -ItemType File -Path (Join-Path $repo '.client_practice_enabled') -Force | Out-Null
Write-Host 'Medusa.exe can now use this Windows Python 3.12 runtime.'
