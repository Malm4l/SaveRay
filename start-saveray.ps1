param(
    [switch]$Reimport
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $here ".venv\Scripts\python.exe"
$url = "http://localhost:8501"

function Test-Up {
    try {
        (Invoke-WebRequest -UseBasicParsing "$url/_stcore/health" -TimeoutSec 3).Content -eq "ok"
    } catch { $false }
}

function Stop-Server {
    Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
}

if (Test-Up) {
    if (-not $Reimport) {
        Start-Process $url
        return
    }
    Stop-Server
}

$activeFile = Join-Path $here "active_snapshot.txt"
$snapDir = Join-Path $here "snapshots"
$needImport = $false
if ($Reimport) {
    $needImport = $true
} elseif (-not (Test-Path $activeFile) -and
          -not (Test-Path (Join-Path $here "players.db")) -and
          -not (Get-ChildItem $snapDir -Filter *.db -ErrorAction SilentlyContinue)) {
    $needImport = $true
}

if ($needImport) {
    $games = Join-Path $env:USERPROFILE "Documents\Sports Interactive\Football Manager 27\games"
    $latest = Get-ChildItem $games -Filter *.fm |
        Where-Object { $_.Name -notlike "last save overwrite*" } |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $latest) { throw "Tidak ada file .fm di $games" }
    New-Item -ItemType Directory -Force $snapDir | Out-Null
    $slug = ($latest.BaseName.ToLower() -replace '[^a-z0-9]+', '-').Trim('-')
    if (-not $slug) { $slug = "save" }
    $target = Join-Path $snapDir "$slug.db"
    & $python (Join-Path $here "import_save.py") $latest.FullName $target
    [System.IO.File]::WriteAllText($activeFile, $target)
}

Start-Process -FilePath $python `
    -ArgumentList '-m','streamlit','run','app.py','--server.port','8501','--server.headless','true','--browser.gatherUsageStats','false' `
    -WorkingDirectory $here `
    -RedirectStandardOutput (Join-Path $here "streamlit.log") `
    -RedirectStandardError (Join-Path $here "streamlit.err") `
    -WindowStyle Hidden

for ($i = 0; $i -lt 40; $i++) {
    if (Test-Up) { break }
    Start-Sleep -Seconds 1
}
Start-Process $url
