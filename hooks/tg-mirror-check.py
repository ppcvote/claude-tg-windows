"""TG-mirror failure detector — Claude Code Stop hook.

Solves a real-world failure mode: you ask Claude something via Telegram,
Claude responds in the local terminal (transcript) but forgets to mirror the
answer back to TG. You see nothing on your phone and silently lose the
deliverable.

This hook fires after each assistant turn. It reads the rolling TG log
maintained by `tg-log.py` (see sibling file in this directory) and detects:

  > The most recent inbound TG message was substantive (>= 15 chars OR
  > contains '?' / '？'), and the assistant turn did NOT call
  > mcp__plugin_telegram_telegram__reply.

When detected, it pings you back via the Telegram bot API directly, using
credentials from environment variables. Configure with:

  TG_ALERT_BOT_TOKEN  — Telegram bot token (same one Claude's MCP uses)
  TG_ALERT_CHAT_ID    — your chat_id (where the alert is delivered)

If either env var is unset, the hook **logs the missed-mirror to a local
file** instead of alerting — useful for debugging your config without
spamming. Log: ~/.claude/tg-log/missed-mirrors.log

## Installation

1. Drop this file at `~/.claude/hooks/tg-mirror-check.py`
2. Set env vars (system env, .env, or whatever your shell uses):
       TG_ALERT_BOT_TOKEN=123456:ABC...
       TG_ALERT_CHAT_ID=781284060
3. Add the Stop hook to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {"hooks": [{"type": "command",
                  "command": "python ~/.claude/hooks/tg-mirror-check.py"}]}
    ]
  }
}
```

Hook never fails: every error path swallows + exits 0, so a buggy hook
can't block Claude Code's normal Stop event.

## Tuning

`SUBSTANTIVE_MIN_CHARS` controls the noise floor. Default 15: short single-
word acks like "OK" / "好" / "1" don't trigger. Anything longer, or
containing a question mark, does.

If you keep getting false positives, raise the floor or add specific
ack-only strings to the skip list inside `is_substantive`.
"""
from __future__ import annotations

import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# UTF-8 stdout/stderr on Windows.
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

LOG = Path.home() / ".claude" / "tg-log" / "recent.jsonl"
MISSED_LOG = Path.home() / ".claude" / "tg-log" / "missed-mirrors.log"

SUBSTANTIVE_MIN_CHARS = 15
QUESTION_CHARS = ("?", "？")


def is_substantive(text: str) -> bool:
    """Whether an inbound TG message needs a reply (vs being a short ack)."""
    t = (text or "").strip()
    if not t:
        return False
    if any(q in t for q in QUESTION_CHARS):
        return True
    return len(t) >= SUBSTANTIVE_MIN_CHARS


def load_entries() -> list[dict]:
    if not LOG.exists():
        return []
    out: list[dict] = []
    for line in LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def find_last_inbound_idx(entries: list[dict]) -> int | None:
    for i in range(len(entries) - 1, -1, -1):
        if entries[i].get("dir") == "in":
            return i
    return None


def has_outbound_after(entries: list[dict], idx: int) -> bool:
    for i in range(idx + 1, len(entries)):
        if entries[i].get("dir") == "out":
            return True
    return False


def send_alert(inbound_text: str) -> None:
    """Push an alert to the user via Telegram bot API (or log to file if no creds)."""
    snippet = (inbound_text or "").strip().replace("\n", " ")
    if len(snippet) > 120:
        snippet = snippet[:117] + "..."
    msg = (
        "⚠️ Claude finished a turn responding to your last TG message, "
        "but did NOT mirror the answer back to Telegram. "
        "Check the terminal transcript or ask Claude to resend."
        f"\n\nLast inbound: \"{snippet}\""
    )

    token = os.environ.get("TG_ALERT_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TG_ALERT_CHAT_ID", "").strip()

    if not token or not chat_id:
        # No credentials — fall back to local file log so the user can debug.
        try:
            MISSED_LOG.parent.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).isoformat()
            with MISSED_LOG.open("a", encoding="utf-8") as f:
                f.write(f"[{ts}] missed mirror — inbound: {snippet}\n")
        except Exception:
            pass
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": msg}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        # Telegram unreachable — fall back to file log so the signal isn't lost.
        try:
            MISSED_LOG.parent.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).isoformat()
            with MISSED_LOG.open("a", encoding="utf-8") as f:
                f.write(f"[{ts}] missed mirror + TG alert failed ({e}) — inbound: {snippet}\n")
        except Exception:
            pass


def main() -> None:
    # Stop hook supplies JSON on stdin (session_id, transcript_path, ...) — we don't need it.
    try:
        sys.stdin.read()  # drain (some hook runtimes block if stdin is unread)
    except Exception:
        pass

    entries = load_entries()
    if not entries:
        return

    last_in = find_last_inbound_idx(entries)
    if last_in is None:
        return

    inbound = entries[last_in]
    text = inbound.get("text") or ""
    if not is_substantive(text):
        return

    if has_outbound_after(entries, last_in):
        return  # mirror was sent — all good

    send_alert(text)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        sys.stderr.write(f"tg-mirror-check error: {e}\n")
    sys.exit(0)
