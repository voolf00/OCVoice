@echo off
chcp 65001 >nul
title OpenCode Voice Installer for Windows
echo =========================================
echo   OpenCode Voice — Windows Installer
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

:: Language selection
echo.
echo Select your language / Выберите язык:
echo  1) Russian / Русский        (ru)
echo  2) Chinese / 中文            (cn)
echo  3) English / English         (en)
echo  4) German / Deutsch          (de)
echo  5) French / Français         (fr)
echo  6) Spanish / Español         (es)
echo  7) Italian / Italiano        (it)
echo  8) Japanese / 日本語          (ja)
echo  9) Korean / 한국어           (ko)
echo  10) Dutch / Nederlands       (nl)
echo  11) Polish / Polski          (pl)
echo  12) Portuguese / Português   (pt)
echo  13) Turkish / Türkçe         (tr)
echo  14) Vietnamese / Tiếng Việt  (vn)
echo  15) Hindi / हिन्दी           (hi)
echo  16) Ukrainian / Українська   (uk)
echo  17) Kazakh / Қазақша         (kz)
echo  18) Auto / Whisper           (auto)
set /p LANG_CHOICE="  > "
if "%LANG_CHOICE%"=="" set LANG_CHOICE=1
if "%LANG_CHOICE%"=="1" set LANG_CODE=ru
if "%LANG_CHOICE%"=="2" set LANG_CODE=cn
if "%LANG_CHOICE%"=="3" set LANG_CODE=en
if "%LANG_CHOICE%"=="4" set LANG_CODE=de
if "%LANG_CHOICE%"=="5" set LANG_CODE=fr
if "%LANG_CHOICE%"=="6" set LANG_CODE=es
if "%LANG_CHOICE%"=="7" set LANG_CODE=it
if "%LANG_CHOICE%"=="8" set LANG_CODE=ja
if "%LANG_CHOICE%"=="9" set LANG_CODE=ko
if "%LANG_CHOICE%"=="10" set LANG_CODE=nl
if "%LANG_CHOICE%"=="11" set LANG_CODE=pl
if "%LANG_CHOICE%"=="12" set LANG_CODE=pt
if "%LANG_CHOICE%"=="13" set LANG_CODE=tr
if "%LANG_CHOICE%"=="14" set LANG_CODE=vn
if "%LANG_CHOICE%"=="15" set LANG_CODE=hi
if "%LANG_CHOICE%"=="16" set LANG_CODE=uk
if "%LANG_CHOICE%"=="17" set LANG_CODE=kz
if "%LANG_CHOICE%"=="18" set LANG_CODE=auto
if not defined LANG_CODE set LANG_CODE=ru

:: Write language to config
powershell -Command "(Get-Content '%USERPROFILE%\.config\ocvoice\config.toml') -replace 'language = \"ru\"', 'language = \"%LANG_CODE%\"' | Set-Content '%USERPROFILE%\.config\ocvoice\config.toml'"
echo [OK] Language set to: %LANG_CODE%

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
if not "%LANG_CODE%"=="auto" (
    "%VENV_DIR%\Scripts\python.exe" -c "from ocvoice.speech.vosk_stt import VoskSTT; VoskSTT(lang='%LANG_CODE%')" >nul 2>&1
    if errorlevel 1 (
        echo [WARN] Vosk model download failed. It will download on first start.
    ) else (
        echo [OK] Speech model downloaded
    )
) else (
    echo [OK] Auto mode — no Vosk model needed (Whisper only)
)

:: Done
echo.
echo =========================================
echo   Installation complete!
echo =========================================
echo.
echo Quick start:
echo   ocv enroll           Record your voice
echo   ocv start            Start voice daemon
echo   ocv select project   Pick a project
echo   ocv select session   Pick a session
echo   Settings via ⚙️ in menu bar
echo.
echo Voice commands:
echo   "окей код, напиши функцию, отправь"
echo   "окей код, открой проект [name]"
echo   "окей код, переключись на сессию [title]"
echo   "окей код, последняя сессия"
echo   "okey kod, send, otprav"
echo.
pause
