# Telegram MCP zombie killer.
#
# Run every 2 minutes by the TGZombieKiller scheduled task.
# Detects multiple Telegram-plugin bun wrappers (which only happens if
# you've accidentally opened more than one Claude Code session) and
# kills the older ones plus their server.ts children.
#
# Logs only when something is killed.

$ErrorActionPreference = 'SilentlyContinue'
$logFile = "$env:USERPROFILE\.claude\channels\telegram\zombie-killer.log"

$wrappers = @(Get-CimInstance Win32_Process -Filter "Name='bun.exe'" | Where-Object {
    $_.CommandLine -match 'claude-plugins-official[\\/]telegram'
})

if ($wrappers.Count -le 1) { exit 0 }

$sorted = $wrappers | Sort-Object CreationDate -Descending
$keep = $sorted[0]
$kill = $sorted[1..($sorted.Count - 1)]

$ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
"[$ts] Found $($wrappers.Count) telegram wrappers; keeping newest PID=$($keep.ProcessId) (started $($keep.CreationDate))" | Add-Content -Path $logFile

foreach ($w in $kill) {
    $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$($w.ProcessId)")
    foreach ($c in $children) {
        Stop-Process -Id $c.ProcessId -Force
        "[$ts]   killed child PID=$($c.ProcessId) name=$($c.Name)" | Add-Content -Path $logFile
    }
    Stop-Process -Id $w.ProcessId -Force
    "[$ts]   killed wrapper PID=$($w.ProcessId) (started $($w.CreationDate))" | Add-Content -Path $logFile
}
