#!/bin/bash
# Telegram Plugin Health Check
# Run on Windows logon to clean up state left over from a previous session.
# Fixes: stale polling, orphan processes, missing dirs, corrupted state.

set -euo pipefail

STATE_DIR="$HOME/.claude/channels/telegram"
PLUGIN_DIR="$HOME/.claude/plugins/cache/claude-plugins-official/telegram/0.0.4"
ENV_FILE="$STATE_DIR/.env"
ACCESS_FILE="$STATE_DIR/access.json"
INBOX_DIR="$STATE_DIR/inbox"

echo "[telegram-health] Starting health check..."

# 1. Check bun is available
if ! command -v bun &>/dev/null; then
  echo "[telegram-health] ERROR: bun not found in PATH"
  echo "[telegram-health] Expected at: $HOME/.bun/bin/bun"
  if [ -x "$HOME/.bun/bin/bun" ]; then
    export PATH="$HOME/.bun/bin:$PATH"
    echo "[telegram-health] Fixed: added ~/.bun/bin to PATH"
  else
    echo "[telegram-health] FATAL: bun not installed. Run: curl -fsSL https://bun.sh/install | bash"
    exit 1
  fi
fi
echo "[telegram-health] OK: bun found at $(which bun)"

# 2. Check .env exists with token
if [ ! -f "$ENV_FILE" ]; then
  echo "[telegram-health] FATAL: $ENV_FILE missing (bot token)"
  exit 1
fi
if ! grep -q "^TELEGRAM_BOT_TOKEN=" "$ENV_FILE"; then
  echo "[telegram-health] FATAL: TELEGRAM_BOT_TOKEN not set in $ENV_FILE"
  exit 1
fi
echo "[telegram-health] OK: bot token present"

# 3. Check access.json is valid JSON
if [ -f "$ACCESS_FILE" ]; then
  WIN_ACCESS=$(cygpath -w "$ACCESS_FILE" 2>/dev/null || echo "$ACCESS_FILE")
  if ! node -e "JSON.parse(require('fs').readFileSync(String.raw\`$WIN_ACCESS\`,'utf8'))" 2>/dev/null; then
    echo "[telegram-health] WARN: access.json corrupted, backing up"
    cp "$ACCESS_FILE" "$ACCESS_FILE.bak.$(date +%s)"
    echo "[telegram-health] Restore manually or re-run /telegram:configure"
    exit 1
  fi
fi
echo "[telegram-health] OK: access.json valid"

# 4. Clean stale inbox files (older than 1 hour)
if [ -d "$INBOX_DIR" ]; then
  stale_count=$(find "$INBOX_DIR" -type f -mmin +60 2>/dev/null | wc -l)
  if [ "$stale_count" -gt 0 ]; then
    find "$INBOX_DIR" -type f -mmin +60 -delete 2>/dev/null
    echo "[telegram-health] Cleaned $stale_count stale inbox files"
  fi
fi
echo "[telegram-health] OK: inbox clean"

# 5. Kill orphaned bun/telegram processes from previous Windows sessions
orphans=$(ps aux 2>/dev/null | grep -i "[t]elegram.*server" | grep -i "bun" | awk '{print $2}' || true)
if [ -n "$orphans" ]; then
  echo "[telegram-health] Killing orphaned telegram processes: $orphans"
  echo "$orphans" | xargs kill -9 2>/dev/null || true
  sleep 2
  echo "[telegram-health] Fixed: orphaned processes killed"
else
  echo "[telegram-health] OK: no orphaned processes"
fi

# 6. Ensure plugin directory exists
if [ ! -d "$PLUGIN_DIR" ]; then
  echo "[telegram-health] WARN: plugin cache missing at $PLUGIN_DIR"
  echo "[telegram-health] Claude Code should re-download on next start"
fi

# 7. Ensure required dirs exist
mkdir -p "$INBOX_DIR" "$STATE_DIR/approved" 2>/dev/null || true

echo "[telegram-health] All checks passed."
