"""OCVoice entry point."""

import sys
from .config import Config


def _cmd_autostart(config: Config, action: str):
    """Manage macOS LaunchAgent for auto-start on login."""
    import os
    import platform

    if platform.system() != "Darwin":
        print("LaunchAgent autostart is only available on macOS")
        print("For Linux: use systemd --user service")
        print("For Windows: use Task Scheduler or Startup folder")
        return

    plist_dir = os.path.expanduser("~/Library/LaunchAgents")
    plist_path = os.path.join(plist_dir, "ai.ocvoice.plist")
    ocv_path = os.path.expanduser("~/.local/bin/ocv")
    python_path = sys.executable
    log_dir = os.path.expanduser("~/Library/Logs")

    if action == "install":
        os.makedirs(plist_dir, exist_ok=True)
        os.makedirs(log_dir, exist_ok=True)

        plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>ai.ocvoice</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>-m</string>
        <string>ocvoice</string>
        <string>start</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log_dir}/ocvoice.log</string>
    <key>StandardErrorPath</key>
    <string>{log_dir}/ocvoice.err</string>
        <key>EnvironmentVariables</key>
        <dict>
            <key>PATH</key>
            <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
            <key>OCVOICE_TRAY_ENABLED</key>
            <string>false</string>
            <key>OCVOICE_HEADLESS</key>
            <string>true</string>
        </dict>
</dict>
</plist>"""

        with open(plist_path, "w") as f:
            f.write(plist_content)

        os.system(f"launchctl load {plist_path} 2>/dev/null")
        print(f"[OCVoice] LaunchAgent installed at {plist_path}")
        print(f"  Logs: {log_dir}/ocvoice.log")
        print(f"  OCVoice will auto-start on next login")

    elif action == "uninstall":
        if os.path.exists(plist_path):
            os.system(f"launchctl unload {plist_path} 2>/dev/null")
            os.remove(plist_path)
            print(f"[OCVoice] LaunchAgent removed")
        else:
            print("LaunchAgent not installed")

    elif action == "status":
        if os.path.exists(plist_path):
            print(f"LaunchAgent: installed at {plist_path}")
            import subprocess
            r = subprocess.run(["launchctl", "list", "ai.ocvoice"],
                              capture_output=True, text=True)
            if r.returncode == 0 and "ai.ocvoice" in r.stdout:
                print("Status: loaded (running)")
            else:
                print("Status: installed but not loaded")
        else:
            print("LaunchAgent: not installed")
            print("Run: ocv autostart install")


def main():
    """Main entry point for OCVoice CLI."""
    # Python version check
    if sys.version_info < (3, 10):
        print(f"[OCVoice] ❌ Python 3.10+ required (you have {sys.version_info.major}.{sys.version_info.minor})")
        print("   Install Python 3.10+ and reinstall OCVoice:")
        print("   brew install python@3.12")
        print("   rm -rf ~/.local/share/ocvoice/venv")
        print("   ./install.sh")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("OCVoice — Voice control for OpenCode")
        print("Version: 0.1.0")
        print()
        print("Usage:")
        print("  ocvoice start           Start voice daemon")
        print("  ocvoice enroll          Enroll your voice for speaker verification")
        print("  ocvoice status          Show daemon status")
        print("  ocvoice stop            Stop voice daemon")
        print("  ocvoice ptt             Push-to-talk (single command, no wake word)")
        print("  ocvoice select session   Pick a session interactively")
        print("  ocvoice select project   Pick a project interactively")
        print("  ocvoice config          Print current configuration")
        print("  ocvoice test-wake       Test wake word detection (10s)")
        print("  ocvoice autostart install   Install LaunchAgent (macOS auto-start)")
        print("  ocvoice autostart uninstall Remove LaunchAgent")
        print("  ocvoice autostart status    Check LaunchAgent status")
        sys.exit(0)

    command = sys.argv[1]
    config = Config()

    match command:
        case "start":
            from .daemon import VoiceDaemon
            daemon = VoiceDaemon(config)
            daemon.run()
        case "enroll":
            from .speech.speaker import SpeakerVerifier
            verifier = SpeakerVerifier(config)
            verifier.enroll()
        case "status":
            from .daemon import VoiceDaemon
            VoiceDaemon.print_status()
        case "stop":
            from .daemon import VoiceDaemon
            VoiceDaemon.stop()
        case "config":
            import json
            print(json.dumps(config._data, indent=2, default=str, ensure_ascii=False))
        case "autostart":
            action = sys.argv[2] if len(sys.argv) > 2 else "status"
            _cmd_autostart(config, action)
        case "select":
            from .cli.select import main as select_main
            select_main(sys.argv[2:])
        case "ptt":
            from .cli.ipc import write_command
            write_command("ptt")
            print("🎤 Push-to-talk. Speak your command and say 'отправь'.")
            print("   После отправки микрофон отключится автоматически.")
        case "test-wake":
            from .cli.test_wake import test_wake
            test_wake()
        case _:
            print(f"Unknown command: {command}")
            sys.exit(1)


if __name__ == "__main__":
    main()
