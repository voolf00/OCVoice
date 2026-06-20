# OpenCode Voice (OCVoice)

**Voice control for OpenCode Desktop** — the AI programming assistant.
**Голосовое управление для OpenCode Desktop** — AI-ассистента для программирования.

> ⚠️ Tested on macOS M1 (Apple Silicon). Linux and Windows may work
> but are not yet validated. Contributions welcome!
>
> ⚠️ Проверено на macOS M1. Linux и Windows могут работать,
> но пока не протестированы. Контрибуции приветствуются!

---

## English

### Features

- 🎤 Voice control — switch projects, sessions, agents, models by voice
- 🧠 Speech recognition: **Vosk** (real-time, offline) + **faster-whisper** (high accuracy, fallback)
- 🔒 **Speaker verification** (Resemblyzer / SpeechBrain) — only your voice gets through; low threshold (score ≥ 0.25) for reliable detection
- 🏃 **Streaming** — words appear as you speak, no 3-second windows
- 📁 **Project-aware** — select projects from your OpenCode Desktop; sessions filter automatically
- 🔍 **Fuzzy matching** — say project names in any language ("дипстрим" → DeepStream3, "mayak" → Maiak)
- 💬 **Voice session switching** — "последняя сессия", "переключись на сессию...", "открой проект..."
- 🤖 **Agent switching** — "план мод" / "билд мод" — switch between Plan and Build agents
- 🧪 **Wake word test** — inline in Settings: checks Vosk detection + speaker verification score
- 🎙 **Voice enrollment** — inline in Settings window with progress bar and countdown
- ⚙️ **Settings GUI** — CustomTkinter window: wake words, send phrases, language, sensitivity, TTS voice, device
- 🗣️ **Smart TTS** — skips code blocks, arrows, formatting — reads only natural text (no crackling)
- 🔵 **State indicators** — icon in menubar/tray changes: 🟢 → 🔵 → 🟣 → 🟢
- 🎤 **Live audio device switching** — change microphone in Settings, applies immediately without restart
- 🔒 **Singleton lock** — prevents multiple daemon instances (PID file)
- ⏱ 10s silence → auto-send; "отправь" → instant send
- macOS / Windows / Linux

### Quick Start

```bash
git clone https://github.com/voolf00/OCVoice.git
cd OCVoice
./install.sh   # macOS/Linux
# or: install.bat  # Windows
ocv enroll      # enroll your voice (10s)
ocv start       # start the daemon
```

Speak: **"дарвин, напиши функцию сортировки, отправь"**

### Voice Commands

| Command / Команда | Action / Действие |
|-------------------|-------------------|
| "дарвин, [message], отправь" | Send message to IDE |
| "дарвин, стоп" / "stop" | Pause listening |
| "дарвин, новая сессия" | Create new session |
| "дарвин, план мод" / "билд мод" | Switch agent (Plan/Build) |
| "дарвин, открой проект [name]" | Switch project (fuzzy match) |
| "дарвин, последняя сессия" | Back to most recent session |
| "окей код, последняя сессия" | Back to most recent session |
| "окей код, найди сервер" / "find server" | Rediscover IDE server |
| "окей код, список проектов" | List all projects |

### Project & Session Selection

```
"дарвин, открой проект маяк"
  → fuzzy match "маяк" → "mayak" → Maiak
  → auto-selects most recent session for Maiak (by time_updated)

"дарвин, дипстрим, отправь"
  → translit "дипстрим" → "dipstrim" → DeepStream3

"дарвин, последняя сессия"
  → releases manual lock
  → poller picks most recently updated session

"дарвин, переключись на сессию тест"
  → fuzzy match against session titles

"дарвин, план мод, отправь"
  → switches to Plan agent
```

**Via menubar/tray:** Click 🎤 icon → 📁 Projects / 💬 Sessions / 🤖 Agent
**Via CLI:** `ocv select project` / `ocv select session`
**Via settings:** Click ⚙️ Settings in menubar/tray → CustomTkinter GUI

### Architecture

```
Microphone → Vosk (streaming) → "okay... code... test..."
                    ↓
          wake word "окей код" found?
                    ↓
           ⬇️ YES          ⬇️ NO
      Speaker Verify    keep listening
           ⬇️
     score > threshold? (your voice?)
   ⬇️ YES           ⬇️ NO
BEEP + CMD MODE    → ignore
   ⬇️
speak message
"отправь" → ✅ sent to IDE
silence 10s → ✅ auto-send
```

### State Indicators

Session title updates automatically. Icon in menubar/tray changes:

| Icon | State | Description |
|------|-------|-------------|
| 🟢 | waiting / ожидает | Waiting for "окей код" |
| 🔵 | command / команда | Listening, building text |
| 🟣 | awaiting / ответ... | Sent, waiting for AI |
| 🔴 | stopped / выкл | Listening paused |

Also in `~/.config/ocvoice/state.json`.

### Configuration

**GUI:** ⚙️ Settings in menubar/tray → CustomTkinter window
**File:** `~/.config/ocvoice/config.toml`

```toml
[audio]
device_id = 1

[voice]
language = "ru"
wake_words = ["окей код", "hey code"]
send_phrases = ["отправь", "отправляй", "отправить", "send", "go", "done"]
wake_sensitivity = 0.5
mode = "wake_word"

[speech.speaker]
enabled = true
threshold = 0.5

[speech.stt]
backend = "auto"
local_model = "base"

[speech.tts]
backend = "edge"
voice_ru = "ru-RU-SvetlanaNeural"
voice_en = "en-US-JennyNeural"
```

---

## Русский

### Возможности

- 🎤 Голосовое управление — переключение проектов, сессий, агентов, моделей голосом
- 🧠 Распознавание: **Vosk** (стриминг, реальное время) + **faster-whisper** (точность, фолбек)
- 🔒 **Верификация голоса** (Resemblyzer / SpeechBrain) — только ваш голос; низкий порог (score ≥ 0.25)
- 🏃 **Стриминг** — слова по мере говорения, без окон по 3 секунды
- 📁 **Проекты** — выбор проекта из OpenCode Desktop; сессии фильтруются автоматически
- 🔍 **Fuzzy поиск** — называй проекты на любом языке ("дипстрим" → DeepStream3, "mayak" → Maiak)
- 💬 **Голосовое переключение** — "последняя сессия", "переключись на сессию...", "открой проект..."
- 🤖 **Агенты** — "план мод" / "билд мод" — переключение Plan/Build
- 🧪 **Тест wake word** — в настройках: проверка Vosk + speaker verification
- 🎙 **Запись голоса** — прямо в окне настроек с прогрессом и отсчётом
- ⚙️ **Окно настроек** — CustomTkinter: wake words, send phrases, язык, TTS голос, устройство
- 🗣️ **Умный TTS** — пропускает код и форматирование, читает только текст (без треска)
- 🔵 **Индикация** в меню-баре/трее: 🟢 → 🔵 → 🟣 → 🟢
- 🎤 **Переключение девайса** — смени микрофон в настройках, работает без перезапуска
- 🔒 **Один экземпляр** — защита от запуска двух демонов
- ⏱ 10с тишины → авто-отправка; "отправь" → мгновенная отправка
- macOS / Windows / Linux

### Быстрый старт

```bash
git clone https://github.com/voolf00/OCVoice.git
cd OCVoice
./install.sh   # macOS/Linux
# или: install.bat  # Windows
ocv enroll      # записать голос (10с)
ocv start       # запустить демон
```

Говори: **"дарвин, напиши функцию сортировки, отправь"**

### Голосовые команды

| Команда | Действие |
|---------|----------|
| "дарвин, [сообщение], отправь" | Отправить сообщение в IDE |
| "дарвин, стоп" | Пауза прослушивания |
| "дарвин, новая сессия" | Создать новую сессию |
| "дарвин, план мод" / "билд мод" | Переключить агента |
| "дарвин, открой проект [название]" | Выбрать проект (fuzzy match) |
| "дарвин, последняя сессия" | Вернуться к последней сессии |

### Выбор проектов и сессий

```
"окей код, открой проект маяк"
  → fuzzy match "маяк" → "mayak" → Maiak
  → авто-выбор последней сессии для Maiak

"окей код, дипстрим, отправь"
  → транслит "дипстрим" → "dipstrim" → DeepStream3

"окей код, последняя сессия"
  → снимает блокировку
  → поллер выбирает самую свежую сессию

"окей код, переключись на сессию тест"
  → fuzzy match по названиям сессий
```

**Через меню-бар/трей:** Иконка 🎤 → 📁 Проекты / 💬 Сессии
**Через CLI:** `ocv select project` / `ocv select session`
**Через настройки:** ⚙️ Settings в меню-баре/трее → окно CustomTkinter

### Архитектура

```
Микрофон → Vosk (стриминг) → "окей... код... тест..."
                    ↓
          wake word "окей код" найден?
                    ↓
           ⬇️ ДА           ⬇️ НЕТ
      Speaker Verify     ждём дальше
           ⬇️
      score > threshold?
   ⬇️ ДА           ⬇️ НЕТ
BEEP + CMD MODE  → игнор
   ⬇️
говоришь сообщение
"отправь" → ✅ отправлено в IDE
тишина 10с → ✅ авто-отправка
```

### Индикация состояния

Заголовок сессии и иконка в меню-баре/трее:

| Иконка | Состояние | Описание |
|--------|-----------|----------|
| 🟢 | ожидает | Ждёт "окей код" |
| 🔵 | команда | Слушает, набирает текст |
| 🟣 | ответ... | Отправлено, ждёт AI |
| 🔴 | выкл | Прослушивание остановлено |

### Настройки

**GUI:** ⚙️ Settings в меню-баре/трее → окно CustomTkinter
**Файл:** `~/.config/ocvoice/config.toml`

```toml
[audio]
device_id = 1

[voice]
language = "ru"
wake_words = ["окей код", "hey code"]
send_phrases = ["отправь", "отправляй", "отправить", "send", "go", "done"]
wake_sensitivity = 0.5
mode = "wake_word"

[speech.speaker]
enabled = true
threshold = 0.5

[speech.stt]
backend = "auto"
local_model = "base"

[speech.tts]
backend = "edge"
voice_ru = "ru-RU-SvetlanaNeural"
voice_en = "en-US-JennyNeural"
```

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
│   │   └── ipc.py         # CLI↔daemon IPC
│   ├── audio/
│   │   ├── capture.py     # Audio capture
│   │   ├── vad.py         # Voice Activity Detection
│   │   └── wake.py        # Wake word detection
│   ├── speech/
│   │   ├── stt.py         # faster-whisper STT
│   │   ├── vosk_stt.py    # Vosk streaming STT
│   │   ├── speaker.py     # Speaker verification
│   │   └── tts.py         # Text-to-Speech
│   ├── intent/
│   │   ├── parser.py      # Intent parser
│   │   └── intents.py     # Intent definitions
│   ├── opencode/
│   │   ├── client.py      # OpenCode API client
│   │   ├── launcher.py    # opencode serve launcher
│   │   └── ide_discovery.py # IDE server discovery
│   └── ui/
│       ├── menubar.py     # macOS menu bar
│       ├── tray.py        # System tray
│       ├── settings_window.py # CustomTkinter GUI
│       ├── overlay.py     # Floating overlay
│       └── notify.py      # Notifications
└── tests/
```

## Dependencies / Зависимости

| Package | Size | Purpose / Назначение |
|---------|------|---------------------|
| `vosk` | 2MB | Streaming speech recognition / Стриминг речи |
| `faster-whisper` | 142MB | High-accuracy STT / Точное распознавание |
| `sounddevice` | <1MB | Audio capture / Захват аудио |
| `webrtcvad` | <1MB | Voice activity detection / Детекция речи |
| `resemblyzer` | 15MB | Speaker verification (primary) / Верификация голоса |
| `speechbrain` | 1GB+ | Speaker verification (fallback) / Верификация (запасной) |
| `edge-tts` | <1MB | Text-to-speech / Озвучивание ответов |
| `numpy` | — | Audio processing / Обработка аудио |
| `httpx` | — | HTTP client for OpenCode API |
| `rumps` | <1MB | Menu bar (macOS) / Меню-бар |
| `pystray` | <1MB | System tray (Linux/Windows) / Системный трей |
| `Pillow` | — | Tray icon generation / Иконка трея |
| `customtkinter` | — | Settings GUI / Окно настроек |
| `openwakeword` | — | Wake word detection (ONNX) / Детекция wake word |
| `soundfile` | — | Audio file I/O / Чтение/запись аудиофайлов |
| `difflib` | stdlib | Fuzzy matching for projects/sessions / Нечёткий поиск |
| `sqlite3` | stdlib | OpenCode DB reader / Чтение БД проектов/сессий |
