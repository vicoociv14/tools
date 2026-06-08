# Turn the Live Meeting Agent fully OFF:
#   - stop + disable the logon autostart task (won't come back at next sign-in)
#   - kill the running tray + any live UI window
# Run: powershell -ExecutionPolicy Bypass -File scripts\agent-off.ps1
Stop-ScheduledTask -TaskName whisp-rec -ErrorAction SilentlyContinue
Disable-ScheduledTask -TaskName whisp-rec -ErrorAction SilentlyContinue | Out-Null
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
  Where-Object { $_.CommandLine -match 'run\.pyw|lma\.ui' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Remove-Item "$PSScriptRoot\..\lma\capture\.whisp-rec.lock" -Force -ErrorAction SilentlyContinue
Write-Host "Live Meeting Agent is OFF (autostart disabled, tray stopped)."
