# OpenCode Voice (OCVoice)

Voice assistant for OpenCode. Background daemon with speech recognition,
speaker verification, and full project/session management via voice or UI.

## How to use with this project

```bash
ocv start          # Start daemon (menubar/tray appears)
ocv stop           # Stop daemon
ocv enroll         # Record voice print for speaker verification
ocv select session # Pick session interactively
ocv select project # Pick project interactively
```

Speak commands in **Russian** or **English**.

## Voice commands

| Command | Action |
|---------|--------|
| `"окей код, [message], отправь"` | Send message to IDE |
| `"окей код, новая сессия"` | Create new session |
| `"окей код, plan mode"` / `"build mode"` | Switch agent |
| `"окей код, открой проект [name]"` | Switch project (fuzzy match) |
| `"окей код, переключись на сессию [title]"` | Switch session |
| `"окей код, последняя сессия"` | Back to most recent |
| `"окей код, стоп"` | Pause listening |
| `"окей код, найди сервер"` | Rediscover IDE |

## Architecture

- **Daemon** runs in background, auto-discovers IDE server
- **Vosk** streams speech in real-time (Vosk model per language)
- **faster-whisper** fallback for accuracy
- **Speaker verification** (Resemblyzer/SpeechBrain) filters non-user voices
- **Projects** read from `opencode.global.dat` + SQLite `project` table
- **Sessions** filtered per project via SQLite JOIN (`session` + `project`)
- **Fuzzy matching** (difflib) + Russian→Latin transliteration for names
- **Messages** sent async to IDE via `/session/:id/prompt_async`
- **Settings** stored in `~/.config/ocvoice/config.toml` (or GUI via CustomTkinter)

## UI

- **macOS:** Menu bar (rumps) — 🎤 icon with project/session menus
- **Linux/Windows:** System tray (pystray) — same functionality
- **CLI:** `ocv select [session|project|status]` — interactive picker
- **Settings:** CustomTkinter window — wake/send phrases, language, sensitivity, toggles

## State indicators

Session title and menubar/tray icon update automatically:

```
🟢 ожидает → 🔵 команда → 🟣 ответ... → 🟢 ожидает
```

Also in `~/.config/ocvoice/state.json`.

## Config

Key file: `~/.config/ocvoice/config.toml`

```toml
[audio]
device_id = 1

[voice]
language = "ru"
wake_words = ["окей код", "hey code"]
send_phrases = ["отправь", "отправляй", "отправить", "send", "go", "done"]
wake_sensitivity = 0.5
silence_timeout = 0.8

[speech.speaker]
enabled = true
threshold = 0.5

[speech.stt]
backend = "auto"

[ui]
menubar = true
tray_enabled = false
```

## Key files

- `ocvoice/daemon.py` — main loop, state management, voice command processing
- `ocvoice/opencode/client.py` — OpenCode HTTP API client
- `ocvoice/opencode/ide_discovery.py` — server port scanning
- `ocvoice/speech/vosk_stt.py` — Vosk streaming (all language models)
- `ocvoice/speech/speaker.py` — Resemblyzer/SpeechBrain verification
- `ocvoice/intent/parser.py` — regex intent parser (RU/EN patterns)
- `ocvoice/intent/intents.py` — intent definitions and patterns
- `ocvoice/ui/menubar.py` — macOS menu bar
- `ocvoice/ui/tray.py` — system tray
- `ocvoice/ui/settings_window.py` — CustomTkinter settings GUI
- `ocvoice/cli/select.py` — interactive project/session picker
- `ocvoice/cli/ipc.py` — CLI↔daemon IPC via JSON file
- `ocvoice/config.py` — config loader with save support
