@echo off
REM Boot-time health check for the Telegram MCP plugin.
REM
REM Invoked by ..\startup\claude-telegram-startup.vbs (silently) on Windows logon.
REM Do NOT auto-start claude.exe here — a headless boot session would steal TG
REM polling from the real session you open later (see zombie-killer.ps1).

REM Wait 15 seconds for network to be ready
timeout /t 15 /nobreak > NUL

REM Ensure bun is in PATH
set "PATH=%USERPROFILE%\.bun\bin;%USERPROFILE%\AppData\Roaming\npm;%PATH%"

REM Run health check (kills orphaned processes from previous Windows session, cleans inbox)
start "" /MIN "C:\Program Files\Git\bin\bash.exe" -c "~/.claude/channels/telegram/health-check.sh"
