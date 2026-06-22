#!/usr/bin/env bash
# OCVoice — быстрый запуск голосового демона
# Запускать из директории OCVoice: ./start.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON="${SCRIPT_DIR}/.venv/bin/python3"

if [ ! -f "$PYTHON" ]; then
    echo "❌ Виртуальное окружение не найдено. Запусти сначала: ./install.sh"
    exit 1
fi

echo "🎤 OCVoice — запуск голосового демона..."
echo ""

# Kill any existing daemon
pkill -f "ocvoice.*start" 2>/dev/null || true
sleep 0.5

# Start daemon in background
OCVOICE_TRAY_ENABLED=false OCVOICE_OPENCODE_AUTO_START=false PYTHONUNBUFFERED=1 \
nohup "$PYTHON" -m ocvoice start > /tmp/ocvoice-daemon.log 2>&1 &

DAEMON_PID=$!
echo "PID: $DAEMON_PID"
sleep 4

# Check it's running
if kill -0 $DAEMON_PID 2>/dev/null; then
    echo ""
    echo "✅ Демон запущен!"
    echo ""
    grep -E "(Found|Wake|Audio|Daemon running)" /tmp/ocvoice-daemon.log 2>/dev/null | tail -5
    echo ""
    echo "Говори громко: 'дарвин, напиши функцию, отправь'"
    echo ""
    echo "Смотри логи:       tail -f /tmp/ocvoice-daemon.log"
    echo "Остановить:        pkill -f 'ocvoice.*start'"
    echo "Статус:            grep -E '(Wake|Recognized|Ответ)' /tmp/ocvoice-daemon.log"
else
    echo "❌ Демон не запустился. Лог:"
    cat /tmp/ocvoice-daemon.log
    exit 1
fi
