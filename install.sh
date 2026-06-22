#!/usr/bin/env bash
# OCVoice installer for macOS / Linux
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}   OpenCode Voice — Installer${NC}"
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

# Language selection
echo ""
echo -e "${YELLOW}Select your language / Выберите язык:${NC}"
echo "  1) 🇷🇺 Русский        (ru)"
echo "  2) 🇨🇳 中文            (cn)"
echo "  3) 🇬🇧 English         (en)"
echo "  4) 🇩🇪 Deutsch         (de)"
echo "  5) 🇫🇷 Français        (fr)"
echo "  6) 🇪🇸 Español         (es)"
echo "  7) 🇮🇹 Italiano        (it)"
echo "  8) 🇯🇵 日本語          (ja)"
echo "  9) 🇰🇷 한국어          (ko)"
echo "  10) 🇳🇱 Nederlands     (nl)"
echo "  11) 🇵🇱 Polski         (pl)"
echo "  12) 🇧🇷 Português      (pt)"
echo "  13) 🇹🇷 Türkçe         (tr)"
echo "  14) 🇻🇳 Tiếng Việt     (vn)"
echo "  15) 🇮🇳 हिन्दी         (hi)"
echo "  16) 🇺🇦 Українська     (uk)"
echo "  17) 🇰🇿 Қазақша        (kz)"
echo "  18) 🌐 Auto (Whisper)  (auto)"
read -p "  > " LANG_CHOICE
case "$LANG_CHOICE" in
  1|"") LANG_CODE="ru" ;;  2) LANG_CODE="cn" ;;  3) LANG_CODE="en" ;;
  4) LANG_CODE="de" ;;  5) LANG_CODE="fr" ;;  6) LANG_CODE="es" ;;
  7) LANG_CODE="it" ;;  8) LANG_CODE="ja" ;;  9) LANG_CODE="ko" ;;
  10) LANG_CODE="nl" ;;  11) LANG_CODE="pl" ;;  12) LANG_CODE="pt" ;;
  13) LANG_CODE="tr" ;;  14) LANG_CODE="vn" ;;  15) LANG_CODE="hi" ;;
  16) LANG_CODE="uk" ;;  17) LANG_CODE="kz" ;;  *) LANG_CODE="ru" ;;
esac

# Update config with language
if [[ "$(uname)" == "Darwin" ]]; then
    sed -i '' "s/language = \"ru\"/language = \"$LANG_CODE\"/" "$HOME/.config/ocvoice/config.toml"
else
    sed -i "s/language = \"ru\"/language = \"$LANG_CODE\"/" "$HOME/.config/ocvoice/config.toml"
fi
echo -e "${GREEN}[✓]${NC} Language set to: $LANG_CODE"

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
echo "  ocv start           # Start voice daemon (menu bar icon appears)"
echo "  ocv status          # Check current status"
echo "  ocv stop            # Stop daemon"
echo "  ocv enroll          # Record your voice print"
echo "  ocv select project  # Pick a project interactively"
echo "  ocv select session  # Pick a session interactively"
echo "  ⚙️ Settings         # Click 🎤 → Settings in menu bar"
echo ""
echo "Voice commands:"
echo '  "окей код, напиши функцию, отправь"'
echo '  "окей код, открой проект [name]"'
echo '  "окей код, переключись на сессию [title]"'
echo '  "окей код, последняя сессия"'
echo '  "дарвин, план мод" / "билд мод"'
echo '  "дарвин, стоп"'
echo ""
