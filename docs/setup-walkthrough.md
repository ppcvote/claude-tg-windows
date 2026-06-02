# Setup walkthrough — adding hooks + critic agent on top of the boot scripts

If you've already run `install.ps1`, you have the boot + zombie killer pieces.
This walkthrough adds the Phase 2 pieces:

- `hooks/tg-log.py` — rolling TG conversation log + SessionStart context inject
- `hooks/tg-mirror-check.py` — alerts you when Claude forgets to mirror to TG
- `agents/critic.md` — adversarial reviewer agent

Total time: 10-15 minutes.

---

## Prerequisites

You should already have:

- Claude Code installed
- The `telegram` MCP plugin enabled (`/telegram:configure` done, `/telegram:access` done with your `chat_id` allowlisted)
- The Phase 1 boot pieces installed (`install.ps1` ran cleanly)
- Python 3.9+ on PATH (`python --version` works in a fresh terminal)

---

## 1. Install the hooks

Copy both Python files into your Claude Code hooks directory:

```powershell
# PowerShell
$dst = Join-Path $env:USERPROFILE ".claude\hooks"
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Copy-Item -Force "hooks\tg-log.py" $dst
Copy-Item -Force "hooks\tg-mirror-check.py" $dst
```

```bash
# Bash / WSL / Git Bash
mkdir -p ~/.claude/hooks
cp hooks/tg-log.py hooks/tg-mirror-check.py ~/.claude/hooks/
```

## 2. Wire them into settings.json

Open `~/.claude/settings.json`. Merge the `hooks` block from
`examples/settings.json.example` into it. If your `settings.json` doesn't
have a `hooks` key yet, you can copy the whole block. If it does, merge
each event handler (don't overwrite existing entries).

A minimal settings.json with just the hooks looks like:

```json
{
  "hooks": {
    "SessionStart": [
      {"hooks": [{"type": "command",
                  "command": "python ~/.claude/hooks/tg-log.py inject"}]}
    ],
    "UserPromptSubmit": [
      {"hooks": [{"type": "command",
                  "command": "python ~/.claude/hooks/tg-log.py inbound"}]}
    ],
    "PostToolUse": [
      {"matcher": "mcp__plugin_telegram_telegram__reply",
       "hooks": [{"type": "command",
                  "command": "python ~/.claude/hooks/tg-log.py outbound"}]}
    ],
    "Stop": [
      {"hooks": [{"type": "command",
                  "command": "python ~/.claude/hooks/tg-mirror-check.py"}]}
    ]
  }
}
```

> Windows tip: if `python` isn't on PATH for the hook runner, use the
> absolute path (e.g. `C:/Users/<you>/AppData/Local/Programs/Python/Python311/python.exe`).

## 3. Set alert credentials (for tg-mirror-check.py)

The mirror-check hook pings you back via the Telegram bot API when Claude
forgets to mirror a reply. It needs two env vars:

- `TG_ALERT_BOT_TOKEN` — your bot's token (same one Claude's MCP uses; find
  it via `/telegram:configure` or in `~/.claude/channels/telegram/access.json`
  context if you exported it there)
- `TG_ALERT_CHAT_ID` — your Telegram numeric chat_id (the same one in
  `access.json` `allowFrom`)

Set them as **system env vars** (so they're inherited by Claude Code's hook
runner). On Windows:

```powershell
[Environment]::SetEnvironmentVariable("TG_ALERT_BOT_TOKEN", "123456:ABC...", "User")
[Environment]::SetEnvironmentVariable("TG_ALERT_CHAT_ID", "781284060", "User")
```

Restart your terminal / Claude Code so the env vars are picked up.

> If you skip this step, the hook still runs — it just logs missed mirrors
> to `~/.claude/tg-log/missed-mirrors.log` instead of alerting. Useful for
> debugging your hook config before you wire up alerts.

## 4. Install the critic agent

The critic agent file is a markdown file with frontmatter. Drop it into your
user-scoped agents directory:

```powershell
$dst = Join-Path $env:USERPROFILE ".claude\agents"
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Copy-Item -Force "agents\critic.md" $dst
```

```bash
mkdir -p ~/.claude/agents
cp agents/critic.md ~/.claude/agents/
```

After **restarting Claude Code**, you can invoke the critic with:

```
/agents critic
```

or by asking the main agent to "spawn the critic on <deliverable>".

The critic ships generic — see the "Customizing this critic for your
domain" section at the bottom of `agents/critic.md` for how to inject your
business-specific failure modes so the critic actually catches your
team's repeat mistakes.

## 5. Verify

After restarting Claude Code:

1. Send yourself a Telegram message ("test").
2. Open a Claude Code session, ask Claude to "echo back the last TG message".
3. Claude should reply via TG.
4. Check `~/.claude/tg-log/recent.jsonl` — should have `dir=in` for your
   "test" and `dir=out` for Claude's echo.
5. Check `~/.claude/tg-log/missed-mirrors.log` — should be empty (Claude
   didn't forget).

Then deliberately break it:

1. Send another Telegram message.
2. Open a Claude Code session, ask Claude to respond in terminal only ("just
   write your answer here, don't mirror to TG").
3. Wait for Claude to finish.
4. **You should receive a Telegram alert** that says Claude finished without
   mirroring. The hook caught it.

---

## Troubleshooting

**"Python not found" in hook output**:
Use the full path to `python.exe` in your settings.json commands, or add
Python to system PATH (not just user PATH — hooks run in a stripped env).

**No alerts when I expect them**:
Check `~/.claude/tg-log/missed-mirrors.log` first. If entries appear there
but no TG alert, your env vars aren't set in the hook runner's environment.
Restart Claude Code after setting env vars.

**Alerts on every short ack like "OK"**:
Open `hooks/tg-mirror-check.py` and tune `SUBSTANTIVE_MIN_CHARS` upward.
Default is 15; if you say "OK 收到" a lot, bump to 20 or add specific
ack-only strings to the `is_substantive` function.

**Hook runner timing out**:
The hooks are all written to exit fast and swallow errors. If you see
timeouts, check that your Python install isn't doing slow startup
(e.g. importing a giant `site.py` from a global venv). Use a minimal
Python install or a fast `pypy`.
