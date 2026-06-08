# install.ps1 - setup for the Live Meeting Agent capture core.
#
# Creates the repo venv, installs dependencies, and registers a Task Scheduler
# entry that launches the capture core silently at user logon via run.pyw.
#
# Usage (normal PowerShell - admin not required):
#   .\install.ps1                # venv + deps + register auto-start
#   .\install.ps1 -SkipAutoStart # venv + deps only
#   .\install.ps1 -Uninstall     # remove the Task Scheduler entry + venv

param(
    [switch]$SkipAutoStart,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $ScriptDir ".venv"
$Pythonw = Join-Path $VenvDir "Scripts\pythonw.exe"
$Entry = Join-Path $ScriptDir "run.pyw"
$TaskName = "whisp-rec"

function Find-SystemPython {
    $candidates = @(
        "C:\Users\$env:USERNAME\AppData\Local\Programs\Python\Python311\python.exe",
        "C:\Users\$env:USERNAME\AppData\Local\Programs\Python\Python312\python.exe",
        "C:\Users\$env:USERNAME\AppData\Local\Programs\Python\Python313\python.exe",
        "C:\Program Files\Python311\python.exe",
        "C:\Program Files\Python312\python.exe"
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "no Python 3.11+ found. Install from https://python.org first."
}

if ($Uninstall) {
    Write-Host "uninstalling Live Meeting Agent auto-start..."
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "  removed scheduled task '$TaskName'"
    }
    if (Test-Path $VenvDir) { Remove-Item -Recurse -Force $VenvDir; Write-Host "  removed venv" }
    Write-Host "uninstall done. Recordings under C:\recordings are kept."
    exit 0
}

Write-Host "Live Meeting Agent install starting..."

if (-not (Test-Path $VenvDir)) {
    $sysPython = Find-SystemPython
    Write-Host "  creating venv with $sysPython"
    & $sysPython -m venv $VenvDir
} else {
    Write-Host "  venv already exists at $VenvDir"
}

$Python = Join-Path $VenvDir "Scripts\python.exe"
Write-Host "  upgrading pip (non-fatal)..."
& $Python -m pip install --upgrade pip --quiet 2>$null

Write-Host "  installing requirements..."
& $Python -m pip install -r (Join-Path $ScriptDir "requirements.txt") --quiet
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

if (-not (Test-Path $Pythonw)) { throw "pythonw.exe not found at $Pythonw" }
if (-not (Test-Path $Entry)) { throw "run.pyw not found at $Entry" }

if (-not $SkipAutoStart) {
    Write-Host "  registering scheduled task '$TaskName' to run at logon..."
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }
    $action = New-ScheduledTaskAction -Execute $Pythonw -Argument "`"$Entry`"" -WorkingDirectory $ScriptDir
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero)
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal | Out-Null
    Write-Host "  scheduled task registered -> $Pythonw $Entry"
}

Write-Host ""
Write-Host "install complete. Start now without rebooting:"
Write-Host "  & `"$Pythonw`" `"$Entry`""
Write-Host "config: $ScriptDir\lma\capture\config.json"
Write-Host "log:    $ScriptDir\lma\capture\whisp-rec.log"
