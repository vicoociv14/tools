# Turn the Live Meeting Agent ON:
#   - re-enable the logon autostart task
#   - start it now (single tray instance)
# Run: powershell -ExecutionPolicy Bypass -File scripts\agent-on.ps1
Enable-ScheduledTask -TaskName whisp-rec -ErrorAction SilentlyContinue | Out-Null
Start-ScheduledTask -TaskName whisp-rec
Write-Host "Live Meeting Agent is ON (autostart enabled, tray started)."
