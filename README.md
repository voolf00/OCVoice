# OpenCode Voice (OCVoice)

**Voice control for OpenCode** — the AI programming assistant.
**Голосовое управление для OpenCode** — AI-ассистента для программирования.

---

## English

### Features

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

### Quick Start

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

### Voice Commands

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

### Selecting Projects & Sessions

OCVoice integrates with OpenCode Desktop to let you choose which project and session to work with.

**Menu Bar (macOS):** Click the 🎤 icon in the menu bar.

- **📁 Projects** — lists all projects from your OpenCode Desktop config. Click to switch — sessions filter to that project automatically.
- **💬 Sessions** — shows sessions for the current project. Click to switch.
- **✚ New Session** — create a fresh session.

**System Tray (Linux/Windows):** Same functionality via the system tray icon.

**CLI:**
```bash
ocv select status      # Show current project and session
ocv select session     # Pick a session interactively
ocv select project     # Pick a project interactively
```

**How it works:** Projects are read from OpenCode Desktop's `opencode.global.dat` config and the SQLite database at `~/.local/share/opencode/opencode.db`. Sessions are filtered by the selected project's worktree path using a SQLite `JOIN` on the `session` and `project` tables. No port scanning — OCVoice stays connected to the main Desktop server.

### Architecture

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

### State Indicators

Session title in OpenCode Desktop updates automatically:

| Icon | State | Description |
|------|-------|-------------|
| 🟢 | waiting | Waiting for "окей код" |
| 🔵 | command | Listening, building text |
| 🟣 | awaiting | Sent, waiting for AI |
| ✅ | ready | Message delivered |

Also visible in `~/.config/ocvoice/state.json` (macOS/Linux)
or `%USERPROFILE%\.config\ocvoice\state.json` (Windows).

### Configuration

Config file: `~/.config/ocvoice/config.toml`

```toml
[audio]
device_id = 1

[speech.speaker]
enabled = true
threshold = 0.5

[speech.stt]
local_model = "base"

[voice]
mode = "wake_word"
wake_words = ["окей код", "hey code"]
silence_timeout = 0.8

[ui]
menubar = true
tray_enabled = false
```

### Troubleshooting

| Problem | Solution |
|---------|----------|
| `ocv: command not found` | `export PATH="$HOME/.local/bin:$PATH"` |
| `ocvoice: command not found` | `cd OCVoice && .venv/bin/python3 -m ocvoice [command]` |
| Microphone not working | `ocvoice start --debug` |
| Speaker verification rejects | `ocv enroll` |

---

## Русский

### Возможности

- 🎤 Голосовое управление OpenCode — переключение проектов, сессий, агентов, моделей
- 🧠 Распознавание речи: **Vosk** (реальное время, офлайн) + **Whisper** (точность, офлайн)
- 🔒 **Верификация голоса** (Resemblyzer) — только ваш голос, посторонние игнорируются
- 🏃 **Стриминг** — слова по мере говорения, без окон по 3 секунды
- 📁 **Проекты** — выберите проект из списка OpenCode Desktop; сессии фильтруются автоматически
- 💬 **Сессии** — переключайтесь между сессиями через меню, трей или CLI
- ⏱ 10 секунд тишины → авто-отправка
- "отправь" → мгновенная отправка
- 🟢🟡🔵🟣✅ индикация состояния в названии сессии
- macOS / Windows / Linux

### Быстрый старт

```bash
git clone https://github.com/voolf00/OCVoice.git
cd OCVoice

# macOS / Linux
./install.sh

# Windows
install.bat
```

После установки:

```bash
# Записать отпечаток голоса (10 секунд)
ocv enroll

# Запустить демон
ocv start
```

Говорите: **"окей код, напиши функцию сортировки, отправь"**

### Голосовые команды

| Команда | Действие |
|---------|----------|
| "окей код, [сообщение], отправь" | Отправить сообщение в IDE |
| "окей код, стоп" | Пауза прослушивания |
| "окей код, новая сессия" | Создать новую сессию |
| "окей код, plan mode" | Переключить в режим Plan |
| "окей код, build mode" | Переключить в режим Build |
| "окей код, найди сервер" | Пересканировать серверы |
| "окей код, список проектов" | Показать все проекты |

Сообщения без "отправь" отправляются автоматически через 10 секунд тишины.

### Выбор проектов и сессий

**Меню-бар (macOS):** Иконка 🎤 в строке меню.

- **📁 Проекты** — все проекты из OpenCode Desktop. При выборе сессии фильтруются по проекту.
- **💬 Сессии** — сессии текущего проекта. Клик для переключения.
- **✚ Новая сессия** — создать свежую сессию.

**Системный трей (Linux/Windows):** Та же функциональность через иконку в трее.

**CLI:**
```bash
ocv select status      # Текущий проект и сессия
ocv select session     # Выбрать сессию интерактивно
ocv select project     # Выбрать проект интерактивно
```

**Как это работает:** Проекты читаются из `opencode.global.dat` и SQLite базы `~/.local/share/opencode/opencode.db`. Сессии фильтруются через SQLite `JOIN` таблиц `session` и `project`. Сканирование портов не требуется — OCVoice остаётся на главном сервере Desktop.

### Архитектура

```
Микрофон → Vosk (стриминг) → "окей... код... тест..."
                                    ↓
                          wake word "окей код" найден?
                                    ↓
                     ⬇️ ДА                    ⬇️ НЕТ
                Speaker Verify          → ждём дальше
                     ⬇️
               score > 0.5? (твой голос?)
          ⬇️ ДА                 ⬇️ НЕТ
     BEEP + CMD START          → игнор
          ⬇️
     говоришь сообщение
     "отправь" → ✅ отправлено в IDE
     тишина 10с → ✅ авто-отправка
```

### Индикация состояния

Название сессии в OpenCode Desktop меняется автоматически:

| Иконка | Состояние | Описание |
|--------|-----------|----------|
| 🟢 | ожидает | Ждёт "окей код" |
| 🔵 | команда | Слушает, набирает текст |
| 🟣 | ответ... | Отправлено, ждёт AI |
| ✅ | готов | Сообщение доставлено |

Также можно смотреть `~/.config/ocvoice/state.json` (macOS/Linux)
или `%USERPROFILE%\.config\ocvoice\state.json` (Windows).

### Настройка

Конфиг: `~/.config/ocvoice/config.toml`

```toml
[audio]
device_id = 1

[speech.speaker]
enabled = true
threshold = 0.5

[speech.stt]
local_model = "base"

[voice]
mode = "wake_word"
wake_words = ["окей код", "hey code"]
silence_timeout = 0.8

[ui]
menubar = true
tray_enabled = false
```

### Решение проблем

| Проблема | Решение |
|----------|---------|
| `ocv: command not found` | `export PATH="$HOME/.local/bin:$PATH"` |
| `ocvoice: command not found` | `cd OCVoice && .venv/bin/python3 -m ocvoice [команда]` |
| Не слышит микрофон | `ocvoice start --debug` |
| Speaker verification не пропускает | `ocv enroll` (перезаписать голос) |

---

## Project Structure / Структура проекта

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

## Dependencies / Зависимости

| Package | Size | Purpose / Назначение |
|---------|------|----------------------|
| `vosk` | 2MB | Real-time speech streaming / Стриминг речи |
| `faster-whisper` | 142MB | High-accuracy recognition / Точное распознавание |
| `resemblyzer` | 15MB | Speaker verification / Верификация голоса |
| `sounddevice` | <1MB | Audio capture / Захват аудио |
| `webrtcvad` | <1MB | Voice activity detection / Детекция речи |
| `rumps` | <1MB | Menu bar (macOS) / Меню-бар |
| `edge-tts` | <1MB | Text-to-speech / Озвучивание |
| `pystray` | <1MB | System tray (Linux/Windows) / Системный трей |

## License / Лицензия

MIT
