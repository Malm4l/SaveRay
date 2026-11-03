$ErrorActionPreference = "SilentlyContinue"
Get-NetTCPConnection -LocalPort 8501 -State Listen |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*streamlit*app.py*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Write-Output "SaveRay stopped."
