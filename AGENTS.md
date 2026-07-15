# OCVoice — Documentation Convention (GRACE)

All code MUST have inline GRACE-style documentation in docstrings.

## GRACE tags

| Tag | Required? | Where | Description |
|-----|-----------|-------|-------------|
| `@contract` | **yes** | module, class, public method | What the unit guarantees (postcondition/invariant) |
| `@desc` | **yes** | module, class, public method | What it does in plain language |
| `@tags` | **yes** | module, class, public method | Comma-separated keywords for search/discovery |
| `@param` | when applicable | method | Typed parameter descriptions |
| `@returns` | when applicable | method | Return value contract |
| `@example` | optional | class, method | Usage example |
| `@bug` | optional | module, class, method | Known bugs or limitations |

## Rules

1. Every module, class, and public method MUST have `@contract` + `@desc` + `@tags`
2. Doc is embedded IN the code — no separate .md documentation files
3. Documentation changes WITH code (always in sync, never stale)
4. ALL agents MUST follow this convention in every session
5. `@tags` use a controlled vocabulary (see codebase for existing tags)
6. `@bug` must be added when a known limitation is discovered

## Controlled tag vocabulary

`config`, `daemon`, `audio`, `capture`, `vad`, `wake`,
`speech`, `stt`, `vosk`, `tts`, `speaker`,
`intent`, `parser`, `network`, `client`, `async`,
`session`, `project`, `message`, `cli`, `ipc`,
`ui`, `menubar`, `tray`, `settings`, `overlay`,
`notification`, `discovery`, `launcher`, `test`,
`macos`, `linux`, `windows`, `enrollment`, `verification`

## How to use

```bash
ocv start          # Start daemon (menubar/tray appears)
ocv stop           # Stop daemon
ocv enroll         # Record voice print for speaker verification
ocv select session # Pick session interactively
ocv select project # Pick project interactively
ocv ptt           # Push-to-talk (one command, no wake word)
```

Speak commands in **Russian** or **English**.

## Quick reference: voice commands

| Command | Action |
|---------|--------|
| `"дарвин, [message], отправь"` | Send message to IDE |
| `"дарвин, новая сессия"` | Create new session |
| `"дарвин, план мод"` / `"билд мод"` | Switch agent (Plan/Build) |
| `"дарвин, открой проект [name]"` | Switch project (fuzzy match) |
| `"дарвин, последняя сессия"` | Back to most recent |
| `"дарвин, стоп"` | Pause listening |
| `"дарвин, найди сервер"` | Rediscover IDE |

## Desktop port detection

OCVoice auto-detects the OpenCode Desktop server by:
1. Scanning listening ports via `lsof`
2. Checking which port serves HTML (Desktop web UI) at `/`
3. Preferring the Desktop port over standalone `opencode serve`

To override, set `desktop_port` in `~/.config/ocvoice/config.toml`:
```toml
[opencode]
desktop_port = 64398
```

Or via environment variable: `OCVOICE_OPENCODE_DESKTOP_PORT=64398`

If set to `0` (default), auto-detection is used.

## Project session sync

When you select a project (via tray, voice, or CLI), OCVoice finds the most recently
updated session for that specific project. Sessions from other projects are ignored.<｜end▁of▁thinking｜>

<｜｜DSML｜｜parameter name="description" string="true">Update AGENTS.md docs
