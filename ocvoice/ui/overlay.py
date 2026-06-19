"""Floating overlay window for OCVoice.

Shows live voice recognition status as a semi-transparent window
that floats above other applications.
"""

import sys
import threading
import time
from typing import Optional

try:
    import tkinter as tk
    HAS_TKINTER = True
except ImportError:
    HAS_TKINTER = False


class VoiceOverlay:
    """Semi-transparent floating window showing voice status."""

    def __init__(self):
        if not HAS_TKINTER:
            print("[OCVoice] tkinter not available. Overlay disabled.")
            self._root = None
            return

        self._root = None
        self._label = None
        self._visible = False
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def _create_window(self):
        """Create the tkinter window in the main thread."""
        if not HAS_TKINTER:
            return
        if self._root:
            return

        try:
            import tkinter as tk_local
        except ImportError:
            return

        self._root = tk_local.Tk()
        self._root.title("OCVoice")
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        self._root.attributes("-alpha", 0.85)
        self._root.configure(bg="#1e1e1e")

        screen_w = self._root.winfo_screenwidth()
        win_w = 400
        win_h = 80
        x = (screen_w - win_w) // 2
        y = 50
        self._root.geometry(f"{win_w}x{win_h}+{x}+{y}")

        frame = tk_local.Frame(self._root, bg="#1e1e1e", padx=12, pady=8)
        frame.pack(fill=tk_local.BOTH, expand=True)

        self._status_icon = tk_local.Label(
            frame, text="🎤", font=("Helvetica", 18),
            bg="#1e1e1e", fg="#44CC44",
        )
        self._status_icon.pack(side=tk_local.LEFT, padx=(0, 10))

        self._label = tk_local.Label(
            frame, text="Listening...",
            font=("Helvetica", 14),
            bg="#1e1e1e", fg="#ffffff",
            wraplength=340, justify=tk_local.LEFT,
        )
        self._label.pack(side=tk_local.LEFT, fill=tk_local.BOTH, expand=True)

        self._last_update = time.time()
        self._root.withdraw()
        self._running = True
        self._check_auto_hide()

    def _check_auto_hide(self):
        """Auto-hide overlay after 5 seconds of inactivity."""
        if self._root and self._visible:
            if time.time() - self._last_update > 5:
                self.hide()
        if self._root and self._running:
            self._root.after(1000, self._check_auto_hide)

    def show(self):
        """Show the overlay."""
        if not self._root:
            self._create_window()
            if not self._root:
                return
        self._visible = True
        self._root.deiconify()
        self._root.lift()

    def hide(self):
        """Hide the overlay."""
        if self._root:
            self._visible = False
            self._root.withdraw()

    def show_recognition(self, text: str, intent: str = ""):
        """Show recognized speech."""
        self._last_update = time.time()
        if not self._root:
            self._create_window()
            if not self._root:
                print(f"[OCVoice] {text}")
                return
        self.show()

        lang = "🇷🇺" if any('а' <= c <= 'я' for c in text.lower()) else "🇬🇧"
        display = f"{lang} {text}"
        if intent:
            display += f"\n{'─'*30}\n🎯 {intent}"

        self._label.configure(text=display, fg="#FFCC00")
        self._status_icon.configure(text="🎤", fg="#FFCC00")

    def show_response(self, text: str):
        """Show AI response."""
        self._last_update = time.time()
        if not self._root:
            self._create_window()
            if not self._root:
                print(f"[OCVoice] {text[:200]}")
                return
        self.show()

        short = text[:300] + ("..." if len(text) > 300 else "")
        self._label.configure(text=f"✅ {short}", fg="#44CC44")
        self._status_icon.configure(text="✅", fg="#44CC44")

    def show_listening(self):
        """Show that we're listening."""
        self._last_update = time.time()
        if not self._root:
            self._create_window()
            if not self._root:
                return
        self.show()
        self._label.configure(text="Слушаю...", fg="#44CC44")
        self._status_icon.configure(text="🎤", fg="#44CC44")

    def show_error(self, text: str):
        """Show an error."""
        self._last_update = time.time()
        if not self._root:
            self._create_window()
            if not self._root:
                return
        self.show()
        self._label.configure(text=f"❌ {text}", fg="#FF4444")
        self._status_icon.configure(text="❌", fg="#FF4444")

    def toggle(self):
        """Toggle overlay visibility."""
        if self._visible:
            self.hide()
        else:
            self.show_listening()

    def start(self):
        """Start the overlay tkinter main loop in a thread."""
        if not HAS_TKINTER:
            return
        self._create_window()
        if self._root:
            self._root.mainloop()

    def stop(self):
        """Stop the overlay."""
        self._running = False
        if self._root:
            try:
                self._root.quit()
                self._root.destroy()
            except Exception:
                pass
            self._root = None


class OverlayManager:
    """Manages the overlay window lifecycle."""

    def __init__(self):
        self._overlay = VoiceOverlay()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._thread = threading.Thread(target=self._overlay.start, daemon=True)
        self._thread.start()
        time.sleep(0.5)  # Wait for tkinter to initialize

    def show_recognition(self, text: str, intent: str = ""):
        self._overlay.show_recognition(text, intent)

    def show_response(self, text: str):
        self._overlay.show_response(text)

    def show_listening(self):
        self._overlay.show_listening()

    def show_error(self, text: str):
        self._overlay.show_error(text)

    def toggle(self):
        self._overlay.toggle()

    def stop(self):
        self._overlay.stop()
