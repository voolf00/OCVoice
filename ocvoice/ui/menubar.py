"""macOS Menu Bar app for OCVoice.

Uses rumps for native macOS menu bar integration.
Runs on the main thread — safe from PyObjC threading issues.
Provides dynamic session/project selection via rumps timer refresh.
"""

import sys
import threading
from typing import Optional

try:
    import rumps
    HAS_RUMPS = True
except ImportError:
    HAS_RUMPS = False


class OCVoiceMenuBar(rumps.App if HAS_RUMPS else object):
    """Menu bar icon for OCVoice with session/project selection."""

    def __init__(self, callbacks: dict):
        self._callbacks = callbacks
        self._pending = None

        self._sessions: list[dict] = []
        self._projects: list[dict] = []
        self._current_session_id: str = ""
        self._current_project_name: str = ""
        self._server_url: str = ""
        self._all_projects: list[dict] = []
        self._language: str = "ru"

        if not HAS_RUMPS:
            self._running = False
            return

        self._running = True

        super().__init__(
            name="OCVoice",
            title="🎤",
            quit_button=None,
        )

        self._build_menu()

    def _build_menu(self):
        self.menu.clear()

        project = self._current_project_name or "?"
        current_title = "?"
        for s in self._sessions:
            if s.get('id') == self._current_session_id:
                current_title = s.get('title', 'untitled')[:40]

        self.menu.add(rumps.MenuItem(f"📁 {project}", callback=None))
        self.menu.add(rumps.MenuItem(f"💬 {current_title}", callback=None))
        self.menu.add(None)

        sessions_menu = rumps.MenuItem("💬 Sessions")
        has_user = False
        for s in self._sessions:
            sid = s.get('id', '')
            title = s.get('title', 'untitled')[:50]
            if '[OCVoice]' in title:
                continue
            has_user = True
            is_current = sid == self._current_session_id
            display = f"✓ {title}" if is_current else f"  {title}"
            item = rumps.MenuItem(display, callback=self._make_session_cb(sid))
            sessions_menu.add(item)

        if not has_user:
            sessions_menu.add(rumps.MenuItem("(no sessions)", callback=None))

        sessions_menu.add(None)
        new_cb = self._callbacks.get('on_new_session')
        sessions_menu.add(
            rumps.MenuItem("✚ New Session", callback=lambda _: new_cb() if new_cb else None)
        )
        sessions_menu.add(rumps.MenuItem("🔄 Refresh", callback=None))
        self.menu.add(sessions_menu)

        projects_menu = rumps.MenuItem("📁 Projects")

        for p in self._all_projects:
            mark = "✓ " if p.get('current') else "  "
            name = p.get('name', '?')
            worktree = p.get('worktree', '')
            display = f"{mark}{name}"
            projects_menu.add(
                rumps.MenuItem(display, callback=self._make_project_cb(worktree))
            )

        if not self._all_projects:
            if self._current_project_name:
                projects_menu.add(rumps.MenuItem(f"✓ {self._current_project_name}", callback=None))
            else:
                projects_menu.add(rumps.MenuItem("(no projects)", callback=None))

        projects_menu.add(None)
        find_cb = self._callbacks.get('on_find_server')
        projects_menu.add(
            rumps.MenuItem("🔄 Find Server", callback=lambda _: find_cb() if find_cb else None)
        )
        self.menu.add(projects_menu)

        self.menu.add(None)
        self.menu.add(rumps.MenuItem("🎤 Start", callback=self._action_start))
        self.menu.add(rumps.MenuItem("🔇 Stop", callback=self._action_stop))

        # Language submenu
        from ..speech.vosk_stt import LANGUAGE_ORDER, LANGUAGE_NAMES
        lang_menu = rumps.MenuItem("🔤 Language")
        for code in LANGUAGE_ORDER:
            label = LANGUAGE_NAMES.get(code, code)
            mark = "✓ " if code == self._language else "  "
            item = rumps.MenuItem(
                f"{mark}{label}",
                callback=self._make_language_cb(code),
            )
            lang_menu.add(item)
        self.menu.add(lang_menu)

        self.menu.add(None)
        self.menu.add(rumps.MenuItem("⚙️ Settings", callback=self._action_settings))
        self.menu.add(None)
        self.menu.add(rumps.MenuItem("📋 Status", callback=self._action_status))
        self.menu.add(rumps.MenuItem("❌ Quit", callback=self._action_quit))

    def _make_session_cb(self, session_id):
        def _cb(sender):
            cb = self._callbacks.get('on_select_session')
            if cb:
                cb(session_id)
        return _cb

    def _make_project_cb(self, worktree):
        def _cb(sender):
            cb = self._callbacks.get('on_select_project')
            if not cb:
                cb = self._callbacks.get('on_find_server')
            if cb:
                cb(worktree)
        return _cb

    def _make_language_cb(self, code):
        def _cb(sender):
            cb = self._callbacks.get('on_language_switch')
            if cb:
                cb(code)
        return _cb

    def update_menu(self, sessions=None, projects=None,
                    current_session_id="", current_project_name="",
                    server_url="", all_projects=None,
                    language=""):
        self._pending = (
            sessions or [],
            projects or [],
            current_session_id or "",
            current_project_name or "",
            server_url or "",
            all_projects or [],
            language or "",
        )

    @rumps.timer(2) if HAS_RUMPS else (lambda f: f)
    def _timer_check(self, sender=None):
        if self._pending:
            s, p, sid, pn, url, ap, lang = self._pending
            self._pending = None
            self._sessions = s
            self._projects = p
            self._current_session_id = sid
            self._current_project_name = pn
            self._server_url = url
            self._all_projects = ap
            self._language = lang or self._language
            self._build_menu()

    def _action_start(self, sender):
        cb = self._callbacks.get('on_toggle')
        if cb:
            cb(True)
        self.title = "🟢"

    def _action_stop(self, sender):
        cb = self._callbacks.get('on_toggle')
        if cb:
            cb(False)
        self.title = "🔴"

    def _action_settings(self, sender):
        config_path = __import__('pathlib').Path.home() / ".config" / "ocvoice" / "config.toml"
        if config_path.exists():
            __import__('webbrowser').open(str(config_path))
        else:
            rumps.notification("OCVoice", "Settings", "Config file not found")

    def _action_status(self, sender):
        rumps.notification(
            "OCVoice",
            "Status",
            f"Project: {self._current_project_name or '?'}\n"
            f"Server: {self._server_url or '?'}",
        )

    def _action_quit(self, sender):
        cb = self._callbacks.get('on_quit')
        if cb:
            cb()
        rumps.quit_application()

    STATE_ICONS = {
        "waiting": "🟢",
        "cmd": "🔵",
        "awaiting": "🟣",
        "stopped": "🔴",
    }

    def set_state_indicator(self, state: str):
        icon = self.STATE_ICONS.get(state, "🎤")
        self.title = icon

    def set_listening(self, active: bool):
        self.title = "🟢" if active else "🔴"

    def set_processing(self):
        self.title = "🟡"

    def set_ready(self):
        self.title = "🟢"

    def set_error(self):
        self.title = "🔴"

    def show_notification(self, title: str, message: str):
        try:
            rumps.notification(title, "", message)
        except Exception:
            pass

    def run(self):
        if not HAS_RUMPS:
            return
        super().run()

    @property
    def is_running(self) -> bool:
        return self._running


class MenuBarManager:
    """Manages the menu bar app lifecycle."""

    def __init__(self):
        self._app: Optional[OCVoiceMenuBar] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self, on_toggle=None, on_quit=None,
              on_select_session=None, on_select_project=None,
              on_language_switch=None,
              on_find_server=None,
              on_new_session=None):
        if sys.platform != "darwin":
            print("[OCVoice] Menu bar only available on macOS")
            return
        if not HAS_RUMPS:
            print("[OCVoice] rumps not installed. pip install rumps")
            return

        self._running = True
        callbacks = {
            'on_toggle': on_toggle,
            'on_quit': on_quit,
            'on_select_session': on_select_session,
            'on_select_project': on_select_project,
            'on_language_switch': on_language_switch,
            'on_find_server': on_find_server,
            'on_new_session': on_new_session,
        }
        self._app = OCVoiceMenuBar(callbacks)
        # App runs on main thread via VoiceDaemon._run_menu_bar()

    def update_menu(self, sessions=None, projects=None,
                    current_session_id="", current_project_name="",
                    server_url="", all_projects=None,
                    language=""):
        if self._app:
            self._app.update_menu(
                sessions or [],
                projects or [],
                current_session_id or "",
                current_project_name or "",
                server_url or "",
                all_projects or [],
                language or "",
            )

    def update_status(self, status: str):
        if self._app:
            match status:
                case "listening":
                    self._app.set_listening(True)
                case "stopped":
                    self._app.set_listening(False)
                case "processing":
                    self._app.set_processing()
                case "ready":
                    self._app.set_ready()
                case "error":
                    self._app.set_error()
                case _:
                    self._app.set_state_indicator(status)

    def notify(self, title: str, message: str):
        if self._app:
            self._app.show_notification(title, message)

    def stop(self):
        self._running = False
        if self._app:
            try:
                rumps.quit_application()
            except Exception:
                pass

    @property
    def is_running(self) -> bool:
        return self._running
