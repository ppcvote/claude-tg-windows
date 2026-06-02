# Why this setup survives 2+ months of daily use

This doc explains the *architecture* behind the boot scripts + hooks + agents
in this repo. The mechanical pieces are simple; the design choices behind
them are what make a personal AI control surface actually reliable.

The author has been running this configuration for ~2 months across a Windows
desktop + WSL2 + Telegram (mobile + travel) without a single day of forced
downtime. That isn't normal for personal AI tooling. Below is the recipe.

---

## The four design choices that matter

### 1. Telegram is the control tower, not just an output channel

Most people use Claude Code as a terminal-bound tool. You sit at the desk,
open VS Code, type in a Claude chat panel, read the response in the panel.
The moment you leave the desk, you lose the agent.

This setup inverts that: **Telegram is the primary interface**. Claude reads
incoming TG messages (via the official `telegram` MCP plugin), responds via
TG replies, and the desktop terminal is just one of many possible session
runners. You can:

- type from your phone on the bus
- type from a hotel room across timezones
- type from a tablet while cooking
- type from the terminal when you're at the desk anyway

All four paths flow through the same channel. There's only one
artifact-of-record (the TG chat history), not a fragmented set of
"sessions I had with the AI today across different surfaces."

The downstream consequence: every substantive deliverable Claude produces
**must be mirrored to TG**, not just printed to the terminal. Forgetting
this rule is the #1 failure mode (see `hooks/tg-mirror-check.py` for the
automated catch).

### 2. Reliability is layered, not single-point

Telegram on Windows fails in *many* specific ways. None of them are deadly
on their own, but any one of them ends your "control tower" for the day.
This setup stacks four defenses, each targeting a different failure class:

| Layer | Failure it defends against |
|---|---|
| `boot-scripts/` + `startup/` silent launcher | Windows reboot leaves Claude offline forever (Startup folder usually pops a console window per `.bat`; this hides it) |
| `scripts/zombie-killer.ps1` | Two `bun.exe` processes both polling `getUpdates` causes inbound messages to drop randomly into the older zombie process — silent partial outage |
| Liveness watchdog (optional, project-specific) | Single `bun.exe` is "alive" but its websocket hung — Telegram getWebhookInfo says inactive |
| `hooks/tg-mirror-check.py` | Claude responds to your TG question via terminal-only — your phone shows nothing back |

No single layer covers all four. The point is **layers covering distinct
failure classes**, not "best-effort reliability."

### 3. Two stateless workarounds for an inherently stateless LLM

LLM sessions are stateless. Every new Claude Code session starts from zero —
no memory of what you talked about yesterday, no context about which
projects you're juggling.

Two pieces in this repo (combined with Claude Code's built-in memory file
system) work around this:

| Piece | What it preserves |
|---|---|
| `hooks/tg-log.py inject` (SessionStart hook) | Last ~20 Telegram messages — auto-injected at the top of every new session, so the assistant picks up the conversation cold without you having to recap |
| Your own `~/.claude/projects/<project>/memory/` markdown files | Long-lived facts: user identity, feedback corrections, project state, external system pointers. Curated, not auto-generated. |

Together, your new sessions start with: short-term TG history (from the
inject hook) + long-term curated memory (from your memory dir). The net
effect is the assistant feels stateful, even though it isn't.

### 4. Lock down the channel before you trust it

Telegram bots are open by default — anyone who knows the bot username can
DM it. With Claude Code on the receiving end, that's a prompt-injection
attack waiting to happen.

The official `telegram` MCP plugin already supports an allowlist
(`access.json` with `allowFrom`) plus a `dmPolicy: pairing` setting that
requires you to manually approve each new chat. Set both before you put
anything important behind the bot. This repo's `scripts/health-check.sh`
verifies these are present on boot.

---

## What this repo does NOT solve

Be honest about the gaps so you don't get blindsided:

- **Cost / token usage monitoring**: there's nothing in this setup that
  tells you when you're burning through Claude API tokens. Build your own
  cost dashboard if your usage is heavy.
- **Multi-device redundancy**: if your phone TG sync breaks while
  travelling, the control tower is offline until you can reach a browser
  or restart the app. Some users solve this by mirroring critical outbound
  messages to a second channel (email, Discord, secondary TG group).
- **Output correctness**: this setup makes Claude *reachable*, not *right*.
  See `agents/critic.md` for an adversarial-review pattern that helps
  catch fabricated claims before they go out.

---

## A real failure log

The author has tracked every Telegram-related incident across 2 months.
Top failure modes by frequency, after the layered defenses were in place:

1. **TG-forget (6 incidents)**: Claude answered the user in terminal but
   didn't mirror to TG. Solved by `hooks/tg-mirror-check.py`.
2. **Phone TG sync glitch (2 incidents)**: Telegram on the phone stopped
   syncing for a few hours. Solved by manually force-closing + restarting
   the TG app. No tooling can fix this from the server side.
3. **Zombie bun process (~weekly, automated catch)**: Caught + killed by
   `scripts/zombie-killer.ps1` every 2 minutes via Task Scheduler. Never
   reached the user as a visible incident.
4. **Windows reboot (planned + unplanned)**: Boot scripts auto-resume.
   Zero manual action.

That's it. Two months. Everything else is noise.
