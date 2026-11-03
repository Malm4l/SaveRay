$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = [Environment]::GetFolderPath('Desktop')
$ps = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$icon = Join-Path $here ".venv\Scripts\python.exe"
$ws = New-Object -ComObject WScript.Shell

function New-SaveRayShortcut($name, $script, $extra) {
    $lnk = $ws.CreateShortcut((Join-Path $desktop $name))
    $lnk.TargetPath = $ps
    $lnk.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`" $extra"
    $lnk.WorkingDirectory = $here
    $lnk.IconLocation = "$icon,0"
    $lnk.Save()
    Write-Output "SHORTCUT: $name"
}

New-SaveRayShortcut "SaveRay.lnk" (Join-Path $here "start-saveray.ps1") ""
New-SaveRayShortcut "SaveRay - Stop.lnk" (Join-Path $here "stop-saveray.ps1") ""
