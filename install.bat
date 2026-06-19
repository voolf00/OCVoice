@echo off
chcp 65001 >nul
title OCVoice Installer for Windows
echo =========================================
echo   OCVoice — Voice Control for OpenCode
echo   Windows Installer
echo =========================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.10+ from:
    echo   https://www.python.org/downloads/
    echo.
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

python -c "import sys; exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
    echo [ERROR] Python 3.10 or higher required.
    pause
    exit /b 1
)

echo [OK] Python detected
python --version

:: Check OpenCode
where opencode >nul 2>&1
if errorlevel 1 (
    echo [WARN] OpenCode not found in PATH.
    echo   Install with: npm install -g opencode-ai
    echo   Or: scoop install opencode
    echo.
) else (
    echo [OK] OpenCode found
)

:: Create virtual environment
set VENV_DIR=%LOCALAPPDATA%\ocvoice\venv
if not exist "%VENV_DIR%" (
    echo [*] Creating virtual environment...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created
)

:: Install package
echo [*] Installing dependencies...
"%VENV_DIR%\Scripts\pip.exe" install --upgrade pip -q
"%VENV_DIR%\Scripts\pip.exe" install vosk faster-whisper resemblyzer sounddevice webrtcvad edge-tts -q
"%VENV_DIR%\Scripts\pip.exe" install -e "%~dp0." -q

if errorlevel 1 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)
echo [OK] Dependencies installed

:: Create config directory
if not exist "%USERPROFILE%\.config\ocvoice" (
    mkdir "%USERPROFILE%\.config\ocvoice"
)
if not exist "%USERPROFILE%\.config\ocvoice\config.toml" (
    copy "%~dp0config.toml" "%USERPROFILE%\.config\ocvoice\config.toml" >nul
    echo [OK] Default config created
)

:: Create launcher
set LAUNCHER_DIR=%USERPROFILE%\.local\bin
if not exist "%LAUNCHER_DIR%" mkdir "%LAUNCHER_DIR%"

:: ocv.bat
(
echo @echo off
echo "%VENV_DIR%\Scripts\python.exe" -m ocvoice %%*
) > "%LAUNCHER_DIR%\ocv.bat"

:: Add to PATH if needed
echo %PATH% | findstr /C:"%LAUNCHER_DIR%" >nul
if errorlevel 1 (
    echo [WARN] Add %LAUNCHER_DIR% to your PATH
    echo   run: setx PATH "%%PATH%%;%LAUNCHER_DIR%"
)

:: Download Vosk model
echo [*] Downloading speech recognition model...
"%VENV_DIR%\Scripts\python.exe" -c "from ocvoice.speech.vosk_stt import VoskSTT; VoskSTT(lang='ru')" >nul 2>&1
if errorlevel 1 (
    echo [WARN] Vosk model download failed. Download manually:
    echo   https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip
    echo   Extract to: %USERPROFILE%\.cache\ocvoice\vosk\
) else (
    echo [OK] Speech model downloaded
)

:: Done
echo.
echo =========================================
echo   Installation complete!
echo =========================================
echo.
echo Quick start:
echo   ocv enroll     Enroll your voice (say the text aloud)
echo   ocv start      Start voice daemon
echo.
echo Voice commands:
echo   "okey kod, send message, otprav"
echo   "okey kod, new session"
echo   "okey kod, stop"
echo.
pause
