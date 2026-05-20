# Installer for claude-tg-windows.
#
# Copies the boot scripts, silent launcher, health check, and zombie killer
# into the right places under %USERPROFILE%, and registers a scheduled task
# that runs the zombie killer every 2 minutes.
#
# Idempotent — re-running is safe.
#
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
#   powershell -ExecutionPolicy Bypass -File .\install.ps1 -Uninstall

param(
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'

$repoRoot     = $PSScriptRoot
$bootScripts  = Join-Path $env:USERPROFILE 'boot-scripts'
$startupDir   = [Environment]::GetFolderPath('Startup')
$tgStateDir   = Join-Path $env:USERPROFILE '.claude\channels\telegram'
$taskName     = 'TGZombieKiller'

function Remove-IfExists($path) {
    if (Test-Path $path) {
        Remove-Item $path -Force
        Write-Host "  removed $path"
    }
}

if ($Uninstall) {
    Write-Host "Uninstalling claude-tg-windows..."

    schtasks /Query /TN $taskName 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        schtasks /Delete /TN $taskName /F | Out-Null
        Write-Host "  removed scheduled task $taskName"
    }

    Remove-IfExists (Join-Path $startupDir 'claude-telegram-startup.vbs')
    Remove-IfExists (Join-Path $bootScripts 'claude-telegram-startup.bat')
    Remove-IfExists (Join-Path $tgStateDir 'zombie-killer.ps1')
    Remove-IfExists (Join-Path $tgStateDir 'health-check.sh')

    Write-Host "Done. Reboot to confirm nothing pops up."
    exit 0
}

Write-Host "Installing claude-tg-windows..."

New-Item -ItemType Directory -Force -Path $bootScripts | Out-Null
New-Item -ItemType Directory -Force -Path $tgStateDir  | Out-Null

Copy-Item (Join-Path $repoRoot 'boot-scripts\claude-telegram-startup.bat') $bootScripts -Force
Write-Host "  copied boot-scripts/claude-telegram-startup.bat → $bootScripts"

Copy-Item (Join-Path $repoRoot 'startup\claude-telegram-startup.vbs') $startupDir -Force
Write-Host "  copied startup/claude-telegram-startup.vbs → $startupDir"

Copy-Item (Join-Path $repoRoot 'scripts\health-check.sh') $tgStateDir -Force
Copy-Item (Join-Path $repoRoot 'scripts\zombie-killer.ps1') $tgStateDir -Force
Write-Host "  copied scripts/* → $tgStateDir"

schtasks /Query /TN $taskName 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    schtasks /Delete /TN $taskName /F | Out-Null
}
$killerScript = Join-Path $tgStateDir 'zombie-killer.ps1'
$tr = "powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$killerScript`""
schtasks /Create /TN $taskName /TR $tr /SC MINUTE /MO 2 /F | Out-Null
Write-Host "  registered scheduled task $taskName (runs every 2 min)"

Write-Host ""
Write-Host "Done."
Write-Host "  Next reboot: no CMD windows should pop for this toolkit."
Write-Host "  Verify zombie killer: schtasks /Query /TN $taskName"
Write-Host "  Killer log:    $tgStateDir\zombie-killer.log (empty = nothing to kill)"
