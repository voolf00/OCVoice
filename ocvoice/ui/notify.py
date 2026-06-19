"""Desktop notifications — zero external dependencies.

Uses osascript on macOS, notify-send on Linux, nothing on Windows (fallback to prints).
"""

import platform
import subprocess
import sys


SYSTEM = platform.system()


def notify(title: str, message: str, subtitle: str = "") -> bool:
    """Send a desktop notification.

    Args:
        title: Notification title.
        message: Notification body text.
        subtitle: Optional subtitle (macOS only).

    Returns:
        True if notification was sent, False if fell back to terminal.
    """
    if SYSTEM == "Darwin":
        return _notify_macos(title, message, subtitle)
    elif SYSTEM == "Linux":
        return _notify_linux(title, message)
    elif SYSTEM == "Windows":
        return _notify_windows(title, message)
    else:
        print(f"[{title}] {message}", file=sys.stderr, flush=True)
        return False


def _notify_macos(title: str, message: str, subtitle: str = "") -> bool:
    """Send notification via osascript."""
    try:
        script = f'display notification "{_escape(message)}" with title "{_escape(title)}"'
        if subtitle:
            script += f' subtitle "{_escape(subtitle)}"'
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            timeout=5,
        )
        return True
    except Exception:
        print(f"[{title}] {message}", file=sys.stderr, flush=True)
        return False


def _notify_linux(title: str, message: str) -> bool:
    """Send notification via notify-send."""
    try:
        subprocess.run(
            ["notify-send", title, message],
            capture_output=True,
            timeout=5,
        )
        return True
    except Exception:
        print(f"[{title}] {message}", file=sys.stderr, flush=True)
        return False


def _notify_windows(title: str, message: str) -> bool:
    """Send notification on Windows."""
    try:
        from win10toast import ToastNotifier
        toaster = ToastNotifier()
        toaster.show_toast(title, message, duration=5)
        return True
    except ImportError:
        pass
    # Fallback: use PowerShell
    try:
        subprocess.run(
            ["powershell", "-Command",
             f"New-BurntToastNotification -Text '{title}', '{message}'"],
            capture_output=True, timeout=5,
        )
        return True
    except Exception:
        pass
    print(f"[{title}] {message}", file=sys.stderr, flush=True)
    return False


def _escape(s: str) -> str:
    """Escape string for AppleScript double-quoted string."""
    return s.replace('"', '\\"').replace("\n", " ")[:200]
