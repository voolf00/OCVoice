"""System tray icon for OCVoice (Linux/Windows).

On macOS, use menubar.py instead (rumps — native macOS menu bar).
Shows an icon in the system tray with status, session/project selection,
and quick actions. Menu is dynamic — rebuilt from poller data.
"""

import threading
import platform
from pathlib import Path
from typing import Optional

_HAS_PYSTRAY = True
try:
    import pystray
except ImportError:
    _HAS_PYSTRAY = False


class TrayIcon:
    """System tray icon — works on Linux/Windows with threading."""

    STATUS_COLORS = {
        "stopped": "#FF4444",
        "listening": "#FFAA00",
        "active": "#FFAA00",
        "processing": "#4488FF",
        "ready": "#44CC44",
        "error": "#FF4444",
        "waiting": "#44CC44",
        "cmd": "#4488FF",
        "awaiting": "#AA44FF",
    }

    def __init__(self, callbacks: dict):
        self._callbacks = callbacks
        self._icon: Optional[pystray.Icon] = None
        self._status = "stopped"
        self._running = False

        self._sessions: list[dict] = []
        self._projects: list[dict] = []
        self._current_session_id: str = ""
        self._current_project_name: str = ""
        self._server_url: str = ""
        self._all_projects: list[dict] = []
        self._language: str = "ru"

    def start(self):
        if not _HAS_PYSTRAY:
            return

        self._running = True
        icon_image = self._create_icon("stopped")
        menu = pystray.Menu(
            pystray.MenuItem("OCVoice", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("🎤 Start", self._action_start),
            pystray.MenuItem("🔇 Stop", self._action_stop),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("🔤 Language", self._build_language_menu()),
            pystray.MenuItem("⚙️ Settings", self._build_settings_menu()),
            pystray.MenuItem("❌ Exit", self._action_exit),
        )

        self._icon = pystray.Icon(
            "ocvoice",
            icon_image,
            "OCVoice — Voice Control for OpenCode",
            menu,
        )

        try:
            thread = threading.Thread(target=self._icon.run, daemon=True)
            thread.start()
        except Exception as e:
            print(f"[OCVoice] System tray error: {e}")
            print("[OCVoice] Tray disabled")

    def stop(self):
        self._running = False
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None

    def update_menu(self, sessions: list[dict], projects: list[dict],
                    current_session_id: str, current_project_name: str,
                    server_url: str, all_projects: list[dict] = None,
                    language: str = ""):
        if not self._icon:
            return
        self._sessions = sessions
        self._projects = projects
        self._current_session_id = current_session_id
        self._current_project_name = current_project_name
        self._server_url = server_url
        self._all_projects = all_projects or []
        if language:
            self._language = language
        try:
            self._icon.menu = self._build_menu()
            self._icon.update_menu()
        except Exception:
            pass

    def set_status(self, status: str):
        self._status = status
        if self._icon:
            try:
                self._icon.icon = self._create_icon(status)
            except Exception:
                pass

    def notify(self, title: str, message: str):
        if self._icon and hasattr(self._icon, 'notify'):
            try:
                self._icon.notify(message, title)
            except Exception:
                pass

    def _build_menu(self):
        current_title = "?"
        for s in self._sessions:
            if s.get('id') == self._current_session_id:
                current_title = s.get('title', 'untitled')[:45]
                break
        project = self._current_project_name or "?"
        server = self._server_url.replace("http://", "") if self._server_url else "?"

        return pystray.Menu(
            pystray.MenuItem(f"📁 {project}", None, enabled=False),
            pystray.MenuItem(f"💬 {current_title}", None, enabled=False),
            pystray.MenuItem(f"🔗 {server}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("💬 Sessions", self._build_sessions_menu()),
            pystray.MenuItem("📁 Projects", self._build_projects_menu()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("🎤 Start", self._action_start),
            pystray.MenuItem("🔇 Stop", self._action_stop),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("🔤 Language", self._build_language_menu()),
            pystray.MenuItem("⚙️ Settings", self._build_settings_menu()),
            pystray.MenuItem("❌ Exit", self._action_exit),
        )

    def _build_sessions_menu(self):
        items = []
        cb = self._callbacks.get('on_select_session')
        for s in self._sessions:
            sid = s.get('id', '')
            title = s.get('title', 'untitled')[:50]
            if '[OCVoice]' in title:
                continue
            is_current = sid == self._current_session_id
            display = f"✓ {title}" if is_current else f"  {title}"
            items.append(
                pystray.MenuItem(
                    display,
                    lambda _sid=sid, _cb=cb: _cb(_sid) if _cb else None,
                )
            )
        if not items:
            items.append(pystray.MenuItem("(no sessions)", None, enabled=False))
        items.append(pystray.Menu.SEPARATOR)
        new_cb = self._callbacks.get('on_new_session')
        items.append(pystray.MenuItem("✚ New Session", lambda: new_cb() if new_cb else None))
        items.append(pystray.MenuItem("🔄 Refresh", lambda: None))
        return pystray.Menu(*items)

    def _build_projects_menu(self):
        items = []
        select_cb = self._callbacks.get('on_select_project')
        if not select_cb:
            select_cb = self._callbacks.get('on_find_server')

        for p in self._all_projects:
            mark = "✓ " if p.get('current') else "  "
            name = p.get('name', '?')
            worktree = p.get('worktree', '')
            display = f"{mark}{name}"
            items.append(
                pystray.MenuItem(
                    display,
                    lambda _wt=worktree, _cb=select_cb: _cb(_wt) if _cb else None,
                )
            )

        if not self._all_projects:
            if self._current_project_name:
                items.append(
                    pystray.MenuItem(f"✓ {self._current_project_name}", None, enabled=False),
                )

        items.append(pystray.Menu.SEPARATOR)
        items.append(pystray.MenuItem("🔄 Find Server", lambda: find_cb(None) if find_cb else None))
        return pystray.Menu(*items)

    def _build_language_menu(self):
        from ..speech.vosk_stt import LANGUAGE_ORDER, LANGUAGE_NAMES
        items = []
        cb = self._callbacks.get('on_language_switch')
        for code in LANGUAGE_ORDER:
            label = LANGUAGE_NAMES.get(code, code)
            mark = "✓ " if code == self._language else "  "
            items.append(
                pystray.MenuItem(
                    f"{mark}{label}",
                    lambda _code=code, _cb=cb: _cb(_code) if _cb else None,
                )
            )
        return pystray.Menu(*items)

    @staticmethod
    def _open_config():
        """Open config file in system editor."""
        config_path = Path.home() / ".config" / "ocvoice" / "config.toml"
        if config_path.exists():
            import webbrowser
            webbrowser.open(str(config_path))

    def _build_settings_menu(self):
        """Build settings submenu with editable configs."""
        config_path = Path.home() / ".config" / "ocvoice" / "config.toml"
        exists = config_path.exists()
        import os as _os
        os_cfg = _os.path.expanduser("~/.config/ocvoice/config.toml")
        wake = "?"
        send = "?"
        try:
            with open(os_cfg) as f:
                for line in f:
                    if line.startswith("wake_words"):
                        wake = line.split("=")[1].strip().strip(",").strip("[]").replace('"', '').strip()
                    elif line.startswith("send_phrases"):
                        send = line.split("=")[1].strip().strip(",").strip("[]").replace('"', '').strip()
        except Exception:
            pass
        return pystray.Menu(
            pystray.MenuItem(
                f"🎤 Wake: {wake[:30]}" if exists else "🎤 Wake words",
                lambda *_: self._open_config(),
            ),
            pystray.MenuItem(
                f"✉️ Send: {send[:30]}" if exists else "✉️ Send phrases",
                lambda *_: self._open_config(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "📝 Edit config file" if exists else "📝 Create config",
                lambda *_: self._open_config(),
            ),
        )

    def _create_icon(self, status: str):
        try:
            from PIL import Image, ImageDraw
            color = self.STATUS_COLORS.get(status, "#888888")
            img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.ellipse((8, 8, 56, 56), fill=color, outline="#333333")
            draw.rectangle((28, 16, 36, 38), fill="white")
            draw.ellipse((24, 8, 40, 24), fill="white")
            draw.rectangle((28, 38, 36, 48), fill="white")
            draw.rectangle((24, 44, 40, 48), fill="white")
            return img
        except Exception:
            from PIL import Image
            return Image.new("RGBA", (64, 64), (100, 100, 100, 255))

    def _action_start(self, icon, item):
        cb = self._callbacks.get('on_toggle')
        if cb:
            cb(True)

    def _action_stop(self, icon, item):
        cb = self._callbacks.get('on_toggle')
        if cb:
            cb(False)

    def _action_settings(self, icon, item):
        config_path = Path.home() / ".config" / "ocvoice" / "config.toml"
        if config_path.exists():
            import webbrowser
            webbrowser.open(str(config_path))
        else:
            self.notify("Settings", "Config file not found")

    def _action_exit(self, icon, item):
        cb = self._callbacks.get('on_exit')
        if cb:
            cb()
        self.stop()

    @property
    def is_running(self) -> bool:
        return self._running


class TrayManager:
    """Manages the tray icon lifecycle and communicates with the daemon."""

    def __init__(self):
        self.tray: Optional[TrayIcon] = None

    def start(self, on_toggle=None, on_exit=None,
              on_select_session=None, on_select_project=None,
              on_language_switch=None,
              on_find_server=None,
              on_new_session=None):
        if not _HAS_PYSTRAY:
            return
        callbacks = {
            'on_toggle': on_toggle,
            'on_exit': on_exit,
            'on_select_session': on_select_session,
            'on_select_project': on_select_project,
            'on_language_switch': on_language_switch,
            'on_find_server': on_find_server,
            'on_new_session': on_new_session,
        }
        self.tray = TrayIcon(callbacks)
        self.tray.start()

    def update_menu(self, sessions=None, projects=None,
                    current_session_id="", current_project_name="",
                    server_url="", all_projects=None,
                    language=""):
        if self.tray:
            self.tray.update_menu(
                sessions or [],
                projects or [],
                current_session_id or "",
                current_project_name or "",
                server_url or "",
                all_projects or [],
                language or "",
            )

    def update(self, status: str):
        if self.tray:
            self.tray.set_status(status)

    def notify(self, title: str, message: str):
        if self.tray:
            self.tray.notify(title, message)

    def stop(self):
        if self.tray:
            self.tray.stop()
