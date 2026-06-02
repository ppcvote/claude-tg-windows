# `settings.json.example` — what each hook does

The companion file `settings.json.example` is **strict JSON** — no
comments allowed (Claude Code's settings parser may reject unknown keys).
This README explains each hook entry.

Before pasting into your real `~/.claude/settings.json`, **replace every
`<HOME>` placeholder with your resolved home path** (Claude Code's hook
runner does not expand `~`):

- Windows: `C:/Users/<yourname>` (forward slashes are fine)
- macOS:   `/Users/<yourname>`
- Linux:   `/home/<yourname>`

If your real settings.json already has a `hooks` key, **merge** the entries
event-by-event — don't overwrite the whole block.

## The four hook entries

### `SessionStart`
Runs `tg-log.py inject`. Reads the rolling TG log and emits a
`{"hookSpecificOutput": {"additionalContext": "..."}}` envelope so Claude
Code injects the last ~20 TG messages into the new session's context.
Gives cross-session continuity without manual copy-paste.

### `UserPromptSubmit`
Runs `tg-log.py inbound`. On every prompt submission, scrapes any
`<channel source="plugin:telegram:telegram">` tags and appends them to
the rolling log. This is what gives the SessionStart inject something to
inject.

### `PostToolUse` (matcher: `mcp__plugin_telegram_telegram__reply`)
Runs `tg-log.py outbound`. Every time you call the Telegram reply tool,
logs the outbound text so the mirror-check hook can tell whether your
turn included a TG reply.

### `Stop`
Runs `tg-mirror-check.py`. After each assistant turn, checks whether the
last inbound TG message got a reply. If not (and the inbound was
substantive, not a one-word ack), alerts you back via the Telegram bot
API. Requires `TG_ALERT_BOT_TOKEN` + `TG_ALERT_CHAT_ID` env vars; without
them it logs to `~/.claude/tg-log/missed-mirrors.log`.
