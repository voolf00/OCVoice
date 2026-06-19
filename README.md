# OCVoice

Голосовое управление для **OpenCode** — AI-ассистента для программирования.

Говорите команды голосом, OCVoice распознаёт речь, находит wake word "окей код", отправляет сообщения в вашу IDE-сессию OpenCode.

## Возможности

- 🎤 Управление OpenCode голосом
- 🧠 Распознавание речи: **Vosk** (реальное время, офлайн) + **Whisper** (точность, офлайн)
- 🔒 **Speaker Verification** — только ваш голос, радио/TV/другие люди игнорируются
- 🏃 **Стриминг** — слова появляются по мере говорения, без окон по 3 секунды
- 🔄 Работает во **всех проектах и сессиях** OpenCode Desktop IDE
- 10 секунд тишины → авто-отправка
- "отправь" → мгновенная отправка
- 🟢🟡🔵🟣✅ индикация состояния в названии сессии
- macOS / Windows / Linux

## Быстрый старт

```bash
git clone https://github.com/ваш-репозиторий/OCVoice.git
cd OCVoice

# macOS / Linux
./install.sh

# или Windows
install.bat
```

После установки:

```bash
# Записать отпечаток голоса (10 секунд)
ocv enroll

# Запустить демон
ocv start
```

Готово. Говорите: **"окей код, напиши функцию сортировки, отправь"**

## Как это работает

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
     BEEP + CMD START      → игнор
          ⬇️
     говоришь сообщение
     "отправь" → ✅ отправлено в IDE
     тишина 10с → ✅ авто-отправка
```

## Установка на macOS

```bash
# 1. Клонировать
git clone https://github.com/ваш-репозиторий/OCVoice.git
cd OCVoice

# 2. Установить
./install.sh

# 3. Записать голос
ocv enroll

# 4. Запустить
ocv start

# 5. Использовать
Говорите: "окей код, тестовое сообщение, отправь"
```

## Установка на Windows

```cmd
:: Запустить от имени пользователя (не администратор)
install.bat

:: Записать голос
ocv enroll

:: Запустить
ocv start
```

## Установка на Linux

```bash
./install.sh
```

Требуется: Python 3.10+, pip, PortAudio (`apt install portaudio19-dev` на Ubuntu).

## Голосовые команды

| Команда | Действие |
|---------|----------|
| "окей код, [сообщение], отправь" | Отправить сообщение в IDE |
| "окей код, стоп" | Пауза прослушивания |
| "окей код, новая сессия" | Создать новую сессию |
| "окей код, plan mode" | Переключить в режим Plan |
| "окей код, build mode" | Переключить в режим Build |

Любое сообщение без "отправь" отправится автоматически через 10 секунд тишины.

## Индикация состояния

Название сессии в OpenCode Desktop меняется автоматически:

| Иконка | Состояние | Описание |
|--------|-----------|----------|
| 🟢 | ожидает | Ждёт "окей код" |
| 🔵 | команда | Слушает, набирает текст |
| 🟣 | ответ... | Отправлено, ждёт AI |
| ✅ | готов | Сообщение доставлено |

Также можно смотреть `~/.config/ocvoice/state.json` (macOS/Linux)
или `%USERPROFILE%\.config\ocvoice\state.json` (Windows).

## Настройка

Конфиг: `~/.config/ocvoice/config.toml`

Основные параметры:

```toml
[audio]
device_id = 1  # 0 = iPhone, 1 = MacBook встроенный

[speech.speaker]
enabled = true          # верификация голоса
threshold = 0.5          # порог: выше = строже, ниже = лояльнее

[speech.stt]
local_model = "base"     # tiny/base/small/medium (размер whisper)

[voice]
mode = "wake_word"       # wake_word | always_on | push_to_talk
wake_words = ["окей код", "hey code"]
silence_timeout = 0.8    # секунд тишины для детекции конца речи
```

## Переустановка голосового отпечатка

```bash
rm -rf ~/.config/ocvoice/enrollments
ocv enroll
```

## Автозапуск

```bash
# macOS — LaunchAgent (автостарт при входе)
ocv autostart install

# Отключить
ocv autostart uninstall
```

## Структура проекта

```
OCVoice/
├── bin/ocv               # CLI-лаунчер (основная команда)
├── install.sh             # Установщик macOS/Linux
├── install.bat            # Установщик Windows
├── install.ps1            # Установщик Windows PowerShell
├── config.toml            # Конфигурация по умолчанию
├── start.sh               # Быстрый запуск демона
├── README.md              # Этот файл
├── ocvoice/
│   ├── daemon.py          # Основной цикл
│   ├── config.py          # Загрузка конфига
│   └── audio/
│       ├── capture.py     # Захват аудио
│       ├── vad.py         # Voice Activity Detection
│       └── wake.py        # Wake word детектор
│   ├── speech/
│       ├── stt.py         # Whisper STT
│       ├── vosk_stt.py    # Vosk стриминг
│       ├── speaker.py     # Speaker verification
│       └── tts.py         # Text-to-Speech
│   ├── intent/
│       ├── parser.py      # Парсер команд
│       └── intents.py     # Определения команд
│   └── opencode/
│       ├── client.py      # API клиент OpenCode
│       ├── launcher.py    # Запуск opencode serve
│       └── ide_discovery.py # Поиск IDE сервера
│   └── ui/
│       ├── notify.py      # Уведомления
│       ├── overlay.py     # Плавающее окно
│       └── tray.py        # System tray
├── .opencode/
│   ├── commands/voice.md  # /voice команда для OpenCode
│   └── plugins/ocvoice.js # Плагин для OpenCode
└── tests/
```

## Зависимости

| Пакет | Размер | Назначение |
|-------|--------|------------|
| `vosk` | 2MB | Стриминг речи (реальное время) |
| `faster-whisper` | 142MB | Точное распознавание (fallback) |
| `resemblyzer` | 15MB | Верификация голоса |
| `sounddevice` | <1MB | Захват аудио |
| `webrtcvad` | <1MB | Детекция активности речи |
| `rumps` | <1MB | Menu bar (macOS) |
| `edge-tts` | <1MB | Озвучивание ответов |

## Устранение проблем

### "ocv: command not found"
```bash
export PATH="$HOME/.local/bin:$PATH"
# Добавьте в ~/.zshrc или ~/.bashrc
```

### "ocvoice: command not found"
```bash
cd OCVoice
.venv/bin/python3 -m ocvoice [команда]
```

### Не слышит микрофон
```bash
ocvoice start --debug  # или смотри: tail -f /tmp/ocvoice-daemon.log
```

### Speaker verification не пропускает
```bash
ocv enroll  # перезаписать отпечаток голоса
```

## Лицензия

MIT
