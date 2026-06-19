#!/usr/bin/env bash
# OCVoice installer for macOS / Linux
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}   OCVoice — Voice Control for OpenCode${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}Python 3.10+ is required. Install with: brew install python3${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "${GREEN}[✓]${NC} Python $PYTHON_VERSION detected"

# Check OpenCode
if ! command -v opencode &>/dev/null; then
    echo -e "${YELLOW}[!] OpenCode not found in PATH${NC}"
    echo "    Install with: curl -fsSL https://opencode.ai/install | bash"
    echo "    OCVoice will work once OpenCode is installed."
else
    echo -e "${GREEN}[✓]${NC} OpenCode found: $(opencode --version 2>/dev/null || echo 'installed')"
fi

# Create virtual environment
VENV_DIR="$HOME/.local/share/ocvoice/venv"
if [ ! -d "$VENV_DIR" ]; then
    echo -e "\n${YELLOW}[*] Creating virtual environment...${NC}"
    python3 -m venv "$VENV_DIR"
    echo -e "${GREEN}[✓]${NC} Virtual environment created at $VENV_DIR"
fi

# Activate and install
echo -e "\n${YELLOW}[*] Installing dependencies...${NC}"
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -e "$(dirname "$0")/.." -q

echo -e "${GREEN}[✓]${NC} Dependencies installed"

# Install STT model
echo -e "\n${YELLOW}[*] Downloading faster-whisper base model (~142MB)...${NC}"
"$VENV_DIR/bin/python3" -c "
from faster_whisper import WhisperModel
model = WhisperModel('base', device='cpu', compute_type='default',
                      download_root='$HOME/.cache/ocvoice/whisper')
print('Model ready')
" 2>/dev/null && echo -e "${GREEN}[✓]${NC} Whisper model downloaded" || \
    echo -e "${YELLOW}[!] Model download failed. Will download on first use.${NC}"

# Create config directory
mkdir -p "$HOME/.config/ocvoice"
if [ ! -f "$HOME/.config/ocvoice/config.toml" ]; then
    cp "$(dirname "$0")/../config.toml" "$HOME/.config/ocvoice/config.toml"
    echo -e "${GREEN}[✓]${NC} Default config created at ~/.config/ocvoice/config.toml"
fi

# Create launcher script
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/ocvoice" << 'LAUNCHER'
#!/usr/bin/env bash
exec "$HOME/.local/share/ocvoice/venv/bin/python3" -m ocvoice "$@"
LAUNCHER
chmod +x "$HOME/.local/bin/ocvoice"

echo -e "${GREEN}[✓]${NC} Launcher created at ~/.local/bin/ocvoice"

# Install ocv wrapper
cp "$(dirname "$0")/bin/ocv" "$HOME/.local/bin/ocv"
chmod +x "$HOME/.local/bin/ocv"
echo -e "${GREEN}[✓]${NC} OCV wrapper installed at ~/.local/bin/ocv"

# Add to PATH if needed
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo ''
    echo -e "${YELLOW}[!] Add ~/.local/bin to your PATH:${NC}"
    echo '    export PATH="$HOME/.local/bin:$PATH"'
    echo '    # Add this line to ~/.zshrc or ~/.bashrc'

    # Offer to add automatically
    read -p "    Add to ~/.zshrc automatically? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zshrc"
        echo -e "${GREEN}[✓]${NC} Added to ~/.zshrc"
    fi
fi

# Done
echo ""
echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}   Installation complete!${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""
echo "Quick start:"
echo "  ocv start           # Start voice daemon (menu bar + overlay)"
echo "  ocv status          # Check status"
echo "  ocv stop            # Stop everything"
echo ""
echo "What you get:"
echo "  🎤  Menu bar icon   — start/stop/status"
echo "  📊  Floating overlay — see recognized speech"
echo "  💬  IDE integration — messages in your session"
echo ""
echo "Voice commands:"
echo '  "окей код, привет как дела, отправь"'
echo '  "окей код, plan mode"'
echo '  "окей код, новая сессия"'
echo '  "окей код, стоп"'
echo ""
