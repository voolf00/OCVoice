# OCVoice — Voice Control for OpenCode

OCVoice is a voice assistant for OpenCode. It runs as a background daemon
and connects to your OpenCode IDE via its API.

## How to use with this project

The project is configured for voice control. When you work on it:

1. Make sure OCVoice is running: `ocv start`
2. Speak commands in Russian or English
3. Messages appear in your IDE session

## Voice commands

- `"окей код, [any message], отправь"` — send a message
- `"окей код, новая сессия"` — create new session
- `"окей код, plan mode"` / `"build mode"` — switch agents
- `"окей код, стоп"` — pause listening

## Architecture

- Daemon runs in background, auto-discovers IDE server
- Vosk streams speech in real-time (no 3s windows)
- Speaker verification (Resemblyzer) filters non-user voices
- Messages sent async to IDE via `/session/:id/prompt_async`
- State shown in session title: 🟢 ожидает → 🔵 команда → ✅ ответ
