"""Rolling Telegram conversation log + SessionStart context injector.

A pair of Claude Code hooks that work together to give cross-session
continuity for Telegram-driven workflows:

  - `inbound`  hook (UserPromptSubmit): scrapes <channel source="plugin:telegram:telegram">
                tags from prompts and appends them to a rolling JSONL log.
  - `outbound` hook (PostToolUse on `mcp__plugin_telegram_telegram__reply`):
                appends each TG reply you send to the same log.
  - `inject`   hook (SessionStart): renders the last N entries from the log
                so they're injected into the new session's context. The result
                is that when your session disconnects + reconnects, the next
                Claude turn already knows the last ~20 messages of TG history.

Log path: ~/.claude/tg-log/recent.jsonl (capped at 60 entries by default)

## Installation

1. Drop this file at `<HOME>/.claude/hooks/tg-log.py`
   (where `<HOME>` is your real home directory — `C:/Users/you` on Windows,
   forward slashes recommended; or `/home/you` on Linux / `/Users/you` on macOS)

2. In `<HOME>/.claude/settings.json` add the three hook entries.
   **Important**: Claude Code's hook runner does NOT expand `~` in the
   `command` field — you must write the full resolved path. On Windows
   the `%USERPROFILE%` env var works inside cmd-style invocations:

```json
{
  "hooks": {
    "SessionStart": [
      {"hooks": [{"type": "command",
                  "command": "python <HOME>/.claude/hooks/tg-log.py inject"}]}
    ],
    "UserPromptSubmit": [
      {"hooks": [{"type": "command",
                  "command": "python <HOME>/.claude/hooks/tg-log.py inbound"}]}
    ],
    "PostToolUse": [
      {"matcher": "mcp__plugin_telegram_telegram__reply",
       "hooks": [{"type": "command",
                  "command": "python <HOME>/.claude/hooks/tg-log.py outbound"}]}
    ]
  }
}
```

Replace `<HOME>` with your resolved home path (forward slashes are fine on
all platforms when passing to `python`). On Windows you may use
`%USERPROFILE%` in its place if you prefer cmd-style env expansion.

Hooks never fail loudly: any error path swallows + exits 0, so a buggy log
file can't block Claude Code's normal session flow.
"""
from __future__ import annotations

import io
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Force UTF-8 on Windows so Chinese / emoji in TG messages survive stdin/stdout.
if hasattr(sys.stdin, "buffer"):
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

LOG = Path.home() / ".claude" / "tg-log" / "recent.jsonl"
CAP = 60       # rolling cap; older entries drop off
INJECT_N = 20  # how many recent entries to inject at session start
MAX_TEXT = 600 # truncate per-entry text body for log compactness

LOG.parent.mkdir(parents=True, exist_ok=True)

# Optional liveness heartbeat — if you also run a watchdog that checks whether
# inbound TG is still flowing, point it at this file. Touched whenever a real
# inbound is logged. Safe to ignore if you don't have a watchdog.
HEARTBEAT = Path.home() / ".claude" / "channels" / "telegram" / "last-inbound.heartbeat"


def load_entries() -> list[dict]:
    if not LOG.exists():
        return []
    out: list[dict] = []
    for line in LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def save_entries(entries: list[dict]) -> None:
    entries = entries[-CAP:]
    payload = "\n".join(json.dumps(e, ensure_ascii=False) for e in entries)
    if payload:
        payload += "\n"
    LOG.write_text(payload, encoding="utf-8")


def append(entry: dict) -> None:
    entries = load_entries()
    # dedupe inbounds by (dir, message_id) — UserPromptSubmit can fire multiple
    # times for the same prompt while you're typing
    key = (entry.get("dir"), entry.get("message_id"))
    if key[1]:
        entries = [e for e in entries if (e.get("dir"), e.get("message_id")) != key]
    entries.append(entry)
    save_entries(entries)


CHANNEL_RE = re.compile(
    r'<channel\s+source="plugin:telegram:telegram"(?P<attrs>[^>]*)>(?P<body>.*?)</channel>',
    re.DOTALL,
)
ATTR_RE = re.compile(r'(\w+)="([^"]*)"')


def parse_attrs(s: str) -> dict[str, str]:
    return dict(ATTR_RE.findall(s))


def touch_heartbeat() -> None:
    try:
        HEARTBEAT.parent.mkdir(parents=True, exist_ok=True)
        HEARTBEAT.touch()
    except Exception:
        pass


def cmd_inbound() -> None:
    """Read UserPromptSubmit hook JSON from stdin; extract any embedded TG channel tags."""
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    prompt = data.get("prompt") or ""
    if not prompt:
        return
    found = 0
    for m in CHANNEL_RE.finditer(prompt):
        attrs = parse_attrs(m.group("attrs"))
        body = m.group("body").strip()
        entry = {
            "dir": "in",
            "chat_id": attrs.get("chat_id", ""),
            "message_id": attrs.get("message_id", ""),
            "user": attrs.get("user", ""),
            "ts": attrs.get("ts", ""),
            "text": body[:MAX_TEXT],
        }
        if attrs.get("image_path"):
            entry["image_path"] = attrs["image_path"]
        if attrs.get("attachment_file_id"):
            entry["attachment_file_id"] = attrs["attachment_file_id"]
        append(entry)
        found += 1
    if found:
        touch_heartbeat()


def cmd_outbound() -> None:
    """Read PostToolUse hook JSON from stdin; log the outbound TG reply."""
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    tool = data.get("tool_name") or data.get("tool") or ""
    if "telegram" not in tool or "reply" not in tool:
        return
    inp = data.get("tool_input") or {}
    text = inp.get("text") or ""
    if not text:
        return
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    append({
        "dir": "out",
        "chat_id": str(inp.get("chat_id", "")),
        "ts": now,
        "text": text[:MAX_TEXT],
    })


def cmd_inject() -> None:
    """Render recent log entries via the SessionStart hook's `additionalContext` envelope.

    Claude Code's SessionStart hook expects JSON of the form
    `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "..."}}`
    on stdout. Raw text may show in the transcript but isn't guaranteed to be
    injected into the model's context — the envelope is the documented contract.
    """
    entries = load_entries()
    if not entries:
        return
    recent = entries[-INJECT_N:]
    lines = [
        "# Recent Telegram exchanges (auto-loaded from rolling log)",
        f"Last {len(recent)} messages, oldest -> newest.",
        "Use for cross-session continuity; if the user references 'earlier' or 'last time', check this first.",
        "",
    ]
    for e in recent:
        ts = e.get("ts", "")
        if e.get("dir") == "in":
            user = e.get("user") or "user"
            arrow = f"<- IN  ({user})"
        else:
            arrow = "-> OUT (me)"
        text = (e.get("text") or "").replace("\r", "").replace("\n", " | ")
        extras = []
        if e.get("image_path"):
            extras.append(f"image={e['image_path']}")
        if e.get("attachment_file_id"):
            extras.append(f"attachment={e['attachment_file_id']}")
        suffix = f" [{', '.join(extras)}]" if extras else ""
        lines.append(f"[{ts}] {arrow} {text}{suffix}")

    payload = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "\n".join(lines),
        }
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if mode == "inbound":
            cmd_inbound()
        elif mode == "outbound":
            cmd_outbound()
        elif mode == "inject":
            cmd_inject()
    except Exception as e:
        # Never fail the hook — write to stderr (gets captured by Claude Code's hook runner).
        sys.stderr.write(f"tg-log {mode} error: {e}\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
