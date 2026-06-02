# claude-tg-windows

A small toolkit for running the official Telegram MCP plugin with [Claude Code](https://claude.com/claude-code) on **Windows** without the usual papercuts.

If you use Claude Code + Telegram MCP on Windows long enough, you'll hit three things:

1. **CMD windows flash open on every login** (any boot `.bat` you add to Startup pops a console).
2. **The Telegram poll loop dies after a while** — usually because an orphaned `bun.exe` from a previous Claude session is still polling `getUpdates` and stealing inbound messages.
3. **You accidentally open two Claude Code sessions** (one in VS Code, one in a terminal) and one of them silently zombies the other's Telegram channel.

This repo collects what we landed on after several months of running this setup in production. None of it is technically deep — it's ~200 lines of glue across PowerShell / Bash / VBScript — but it's the missing piece that keeps the plugin reliable on Windows.

> Battle-tested by [Ultra Lab](https://ultralab.tw)'s solo founder, who lives in Telegram and reboots a lot.

---

## What's inside

### Phase 1 — boot + process management (the original release)

| File | Purpose |
| ---- | ------- |
| `scripts/health-check.sh` | Runs once on every boot. Verifies bun + token + access.json, cleans stale inbox files, kills orphaned Telegram bun processes from previous Windows sessions. |
| `scripts/zombie-killer.ps1` | Runs every 2 minutes via Task Scheduler. If more than one Telegram MCP `bun.exe` wrapper is alive, keeps the newest and kills the older ones plus their `server.ts` children. |
| `boot-scripts/claude-telegram-startup.bat` | Wakes the network (15s delay), puts `bun` on PATH, then invokes `health-check.sh`. Lives outside the Startup folder so Windows never opens a console window for it. |
| `startup/claude-telegram-startup.vbs` | Silent launcher placed in the Startup folder. Calls the `.bat` with `windowstyle=0`. This is the *only* file Windows actually executes at logon. |
| `install.ps1` | One-shot installer: copies files into `%USERPROFILE%`, creates the `TGZombieKiller` scheduled task, registers the silent launcher in the Startup folder. |

### Phase 2 — hooks + adversarial reviewer (added after 2 months of production use)

Phase 1 keeps the Telegram channel *alive*. Phase 2 makes the *workflow* on
top of it reliable: cross-session continuity, never-forget-to-mirror-back,
and a built-in critic for catching your own hallucinated claims.

| File | Purpose |
| ---- | ------- |
| `hooks/tg-log.py` | Rolling log of all Telegram in/out + a SessionStart inject hook that gives every new Claude session context of the last ~20 TG messages. Cross-session memory without copy-pasting. |
| `hooks/tg-mirror-check.py` | After each assistant turn, checks whether the last inbound TG message got a reply. If it didn't (e.g. Claude answered in the terminal but forgot to mirror back), pings you via the Telegram bot API. Solves the #1 failure mode of the TG-as-control-tower workflow. |
| `agents/critic.md` | A user-scoped Claude Code agent that does adversarial review on deliverables produced by the main agent. Built around a "verify with tools or shut up" rule. Use it when you'd otherwise feel "this draft is fine" and want a second opinion that can grep / curl / WebFetch its claims. |
| `examples/settings.json.example` | Pre-wired hook entries you can merge into your `~/.claude/settings.json`. |
| `docs/workflow-architecture.md` | The "why" behind the four design choices that make this setup survive 2+ months of daily use. Read this before customizing. |
| `docs/setup-walkthrough.md` | Step-by-step installation guide for the Phase 2 pieces (10-15 minutes). |

---

## How the pieces fit together

```
Windows logon
    │
    ▼
Startup folder  ─────────────►  claude-telegram-startup.vbs   (silent, no window)
                                       │
                                       ▼
                                cmd /c  claude-telegram-startup.bat  (hidden)
                                       │
                                       ▼
                                bash    health-check.sh   (one-shot cleanup)


Every 2 minutes
    │
    ▼
Task Scheduler  ─────────────►  zombie-killer.ps1   (silent, no window)
                                       │
                                       ▼
                                detect >1 Telegram bun wrapper → kill older
```

You only ever run **one** Claude Code session at a time. That assumption is baked into the zombie killer — if it sees more than one Telegram wrapper, the older ones are by definition stale.

---

## Install

Requires:

- Windows 10 or 11
- [Claude Code](https://claude.com/claude-code) installed and the official Telegram MCP plugin already configured (`/telegram:configure` and `/telegram:access` are skills that ship with the plugin)
- [Git for Windows](https://git-scm.com/download/win) (provides `bash.exe` at the standard `C:\Program Files\Git\bin\` path)
- [Bun](https://bun.sh/) on PATH (the Telegram plugin runtime)

Then:

```powershell
git clone https://github.com/ppcvote/claude-tg-windows.git
cd claude-tg-windows
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

The installer is idempotent — running it twice is harmless.

To verify:

```powershell
schtasks /Query /TN TGZombieKiller
Get-ChildItem "$env:USERPROFILE\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup" -Filter "claude-telegram-*"
Get-Content "$env:USERPROFILE\.claude\channels\telegram\zombie-killer.log" -Tail 20  # empty = clean
```

---

## Uninstall

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Uninstall
```

---

## What this is *not*

- Not a fork of the Telegram MCP plugin. The plugin itself is Anthropic's; this repo only fixes the host-side rough edges on Windows.
- Not a cross-platform solution. macOS and Linux don't have these particular pain points — their process / autostart models work differently.
- Not a substitute for `/telegram:configure` or `/telegram:access`. You still set those up the normal way before installing this.

---

## License

MIT.

---

## 中文說明

在 Windows 上長期跑 Claude Code + 官方 Telegram MCP plugin 容易碰到三件事：

1. 每次開機都會有 CMD 視窗閃出來（任何放到 Startup 的 `.bat` 都會）。
2. Telegram polling 跑一陣子會掛，通常是上個 Claude session 留下的 zombie `bun.exe` 還在 poll getUpdates，把訊息搶走。
3. 不小心同時開兩個 Claude（一個在 VS Code、一個在 terminal），其中一個會默默把另一個的 TG 通道吃掉。

這個 repo 是我們實測幾個月後的解法，不是什麼高深技術 — 加總約 200 行 PowerShell / Bash / VBScript — 但這套就是讓 plugin 在 Windows 穩定下來的關鍵。

安裝方式跟上面英文段一樣。前置要 Claude Code、Git for Windows、Bun。`install.ps1` 跑一次就完事。

### Phase 2 — hooks + critic agent

Phase 1 解決「TG 通道掛掉」。Phase 2 解決「workflow 不夠穩」：

- **`hooks/tg-log.py`** — 滾動式記錄所有 TG 對話 + SessionStart hook 把最近 20 則訊息注入新 session，等於跨 session 記憶。
- **`hooks/tg-mirror-check.py`** — 每次 Claude 答覆結束自動檢查：上一則 TG inbound 有沒有被 reply 到？如果只在 terminal 答（忘了 mirror 回 TG），主動推 ⚠️ 警告。解決 TG-as-control-tower 模式最常見的失誤。
- **`agents/critic.md`** — 對抗式 reviewer agent，專門找 deliverable 漏洞。規則：「沒實際用 tool verify 就不算 finding」。寫完 draft 自我感覺良好時叫他出來潑冷水。

完整背景看 `docs/workflow-architecture.md`，逐步安裝看 `docs/setup-walkthrough.md`。
