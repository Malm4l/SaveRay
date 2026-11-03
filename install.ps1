# SaveRay one-time installer.
# Creates a local virtual environment in .venv, installs the requirements,
# and creates the desktop shortcuts. Safe to run again after an update.

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

Write-Host "SaveRay installer"
Write-Host "-----------------"

# 1. Find Python 3.11 or newer (3.12 recommended).
$py = $null
foreach ($candidate in @("py", "python")) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if (-not $cmd) { continue }
    if ($candidate -eq "py") {
        $ver = & py -c "import sys; print(sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and $ver -match "\((\d+), (\d+)\)" -and
            (([int]$Matches[1] -gt 3) -or
             ([int]$Matches[1] -eq 3 -and [int]$Matches[2] -ge 11))) {
            $py = @("py")
            break
        }
    } else {
        $ver = & python -c "import sys; print(sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and $ver -match "\((\d+), (\d+)\)" -and
            (([int]$Matches[1] -gt 3) -or
             ([int]$Matches[1] -eq 3 -and [int]$Matches[2] -ge 11))) {
            $py = @("python")
            break
        }
    }
}
if (-not $py) {
    Write-Host ""
    Write-Host "Python 3.11 or newer was not found on this computer."
    Write-Host "Install Python from https://www.python.org/downloads/ and"
    Write-Host "tick 'Add python.exe to PATH' during setup, then run this"
    Write-Host "installer again."
    exit 1
}
Write-Host "Python found. Creating the virtual environment..."

# 2. Virtual environment and dependencies.
& $py -m venv (Join-Path $here ".venv")
$venvPy = Join-Path $here ".venv\Scripts\python.exe"
& $venvPy -m pip install --upgrade pip --quiet
Write-Host "Installing SaveRay requirements, this can take a few minutes..."
& $venvPy -m pip install -r (Join-Path $here "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    Write-Host "Requirement installation failed. Check your internet"
    Write-Host "connection and run this installer again."
    exit 1
}

# 3. Desktop shortcuts.
& (Join-Path $here "make-shortcuts.ps1")

Write-Host ""
Write-Host "Done. Use the 'SaveRay' shortcut on your desktop to start,"
Write-Host "and 'SaveRay - Stop' to stop it. Inside the app, open the"
Write-Host "Save menu in the left sidebar and import your FM27 save."
