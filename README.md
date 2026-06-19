# OCVoice

Voice control for **OpenCode** — the AI programming assistant.

Speak commands in Russian or English. OCVoice detects the wake word "окей код",
streams speech recognition in real time, and sends messages to your OpenCode IDE session.

## Features

- 🎤 Voice control for OpenCode — switch projects, sessions, agents, models
- 🧠 Speech recognition: **Vosk** (real-time, offline) + **Whisper** (high accuracy, offline)
- 🔒 **Speaker verification** (Resemblyzer) — only your voice gets through
- 🏃 **Streaming** — words appear as you speak, no 3-second windows
- 📁 **Project-aware** — select projects from your OpenCode Desktop list; sessions filter automatically
- 💬 **Session-aware** — pick sessions from any project via menubar, tray, or CLI
- ⏱ 10 seconds of silence → auto-send
- "отправь" → instant send
- 🟢🟡🔵🟣✅ state shown in session title
- macOS / Windows / Linux

## Quick Start

```bash
git clone https://github.com/voolf00/OCVoice.git
cd OCVoice

# macOS / Linux
./install.sh

# or Windows
install.bat
```

After install:

```bash
# Enroll voice print (10 seconds)
ocv enroll

# Start the daemon
ocv start
```

Start speaking: **"окей код, write a sorting function, отправь"**

## Voice Commands

| Command | Action |
|---------|--------|
| "окей код, [message], отправь" | Send message to IDE |
| "окей код, стоп" / "stop" | Pause listening |
| "окей код, новая сессия" | Create new session |
| "окей код, plan mode" | Switch to Plan agent |
| "окей код, build mode" | Switch to Build agent |
| "окей код, найди сервер" / "find server" | Rediscover IDE server |
| "окей код, список проектов" / "list projects" | List all projects |

Messages without "отправь" auto-send after 10 seconds of silence.

## Selecting Projects & Sessions

OCVoice integrates with OpenCode Desktop to let you choose which project and session to work with.

### Menu Bar (macOS)

Click the 🎤 icon in the menu bar:

- **📁 Projects** — lists all projects from your OpenCode Desktop config. Click to switch — sessions filter to that project automatically.
- **💬 Sessions** — shows sessions for the current project. Click to switch.
- **✚ New Session** — create a fresh session.

### System Tray (Linux/Windows)

Same functionality via the system tray icon.

### CLI

```bash
# Show current project and session
ocv select status

# Pick a session interactively
ocv select session

# Pick a project interactively
ocv select project
```

### How it works

Projects are read from OpenCode Desktop's `opencode.global.dat` config and the SQLite database at `~/.local/share/opencode/opencode.db`. Sessions are filtered by the selected project's worktree path using a SQLite `JOIN` on the `session` and `project` tables. No port scanning needed — OCVoice stays connected to the main Desktop server.

## Architecture

```
Microphone → Vosk (streaming) → "okay... code... test..."
                                    ↓
                          wake word "окей код" found?
                                    ↓
                     ⬇️ YES                   ⬇️ NO
                Speaker Verify           → keep listening
                     ⬇️
               score > 0.5? (your voice?)
          ⬇️ YES                 ⬇️ NO
     BEEP + CMD START          → ignore
          ⬇️
     speak your message
     "отправь" → ✅ sent to IDE
     silence 10s → ✅ auto-send
```

## State Indicators

The session title in OpenCode Desktop updates automatically:

| Icon | State | Description |
|------|-------|-------------|
| 🟢 | waiting | Waiting for "окей код" |
| 🔵 | command | Listening, building text |
| 🟣 | awaiting | Sent, waiting for AI |
| ✅ | ready | Message delivered |

Also visible in `~/.config/ocvoice/state.json` (macOS/Linux)
or `%USERPROFILE%\.config\ocvoice\state.json` (Windows).

## Configuration

Config file: `~/.config/ocvoice/config.toml`

Key options:

```toml
[audio]
device_id = 1  # 0 = iPhone, 1 = MacBook built-in

[speech.speaker]
enabled = true          # speaker verification
threshold = 0.5         # higher = stricter, lower = more permissive

[speech.stt]
local_model = "base"     # tiny/base/small/medium (whisper model size)

[voice]
mode = "wake_word"       # wake_word | always_on | push_to_talk
wake_words = ["окей код", "hey code"]
silence_timeout = 0.8    # seconds of silence to detect end of speech

[ui]
menubar = true           # macOS menu bar (default: true)
tray_enabled = false     # system tray (default: false on macOS)
```

## Re-enrolling Voice

```bash
rm -rf ~/.config/ocvoice/enrollments
ocv enroll
```

## Autostart

```bash
# macOS — LaunchAgent (starts on login)
ocv autostart install

# Remove
ocv autostart uninstall
```

## Project Structure

```
OCVoice/
├── bin/ocv               # CLI launcher
├── install.sh             # macOS/Linux installer
├── install.bat            # Windows installer
├── config.toml            # Default config
├── start.sh               # Quick daemon start
├── ocvoice/
│   ├── daemon.py          # Main daemon loop
│   ├── config.py          # Config loader
│   ├── cli/
│   │   ├── select.py      # Interactive project/session picker
│   │   └── ipc.py         # CLI↔daemon IPC via JSON file
│   ├── audio/
│   │   ├── capture.py     # Audio capture
│   │   ├── vad.py         # Voice Activity Detection
│   │   └── wake.py        # Wake word detection
│   ├── speech/
│   │   ├── stt.py         # Whisper STT
│   │   ├── vosk_stt.py    # Vosk streaming
│   │   ├── speaker.py     # Speaker verification
│   │   └── tts.py         # Text-to-Speech
│   ├── intent/
│   │   ├── parser.py      # Command parser
│   │   └── intents.py     # Intent definitions
│   ├── opencode/
│   │   ├── client.py      # OpenCode API client
│   │   ├── launcher.py    # opencode serve launcher
│   │   └── ide_discovery.py # IDE server discovery
│   └── ui/
│       ├── menubar.py     # macOS menu bar (rumps)
│       ├── tray.py        # System tray (pystray)
│       ├── overlay.py     # Floating overlay
│       └── notify.py      # Notifications
├── .opencode/
│   ├── commands/voice.md  # /voice command for OpenCode
│   └── plugins/ocvoice.js # OpenCode plugin
└── tests/
```

## Dependencies

| Package | Size | Purpose |
|---------|------|---------|
| `vosk` | 2MB | Real-time speech streaming |
| `faster-whisper` | 142MB | High-accuracy recognition (fallback) |
| `resemblyzer` | 15MB | Speaker verification |
| `sounddevice` | <1MB | Audio capture |
| `webrtcvad` | <1MB | Voice activity detection |
| `rumps` | <1MB | Menu bar (macOS) |
| `edge-tts` | <1MB | Text-to-speech responses |
| `pystray` | <1MB | System tray (Linux/Windows) |

## Troubleshooting

### "ocv: command not found"
```bash
export PATH="$HOME/.local/bin:$PATH"
# Add to ~/.zshrc or ~/.bashrc
```

### "ocvoice: command not found"
```bash
cd OCVoice
.venv/bin/python3 -m ocvoice [command]
```

### Microphone not working
```bash
ocvoice start --debug  # or check: tail -f /tmp/ocvoice-daemon.log
```

### Speaker verification rejecting you
```bash
ocv enroll  # re-record voice print
```

## License

MIT
