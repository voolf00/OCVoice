"""Settings window for OCVoice.

Uses CustomTkinter for a modern native-looking settings dialog.
Launched as a subprocess to avoid main-thread conflicts with rumps/pystray.
"""

import json
import os
import sys
import time
from pathlib import Path

try:
    import customtkinter as ctk
except ImportError:
    print("customtkinter not installed. Install with: pip install customtkinter")
    sys.exit(1)


CONFIG_PATH = Path.home() / ".config" / "ocvoice" / "config.toml"
IPC_PATH = Path.home() / ".config" / "ocvoice" / "command.json"

LANGUAGE_CODES = [
    "ru", "cn", "en", "ca", "cs", "de", "eo", "es", "fa", "fr",
    "gu", "hi", "it", "ja", "ka", "ko", "ky", "kz", "nl", "pl",
    "pt", "sv", "te", "tg", "tr", "uk", "vn",
]

LANGUAGE_LABELS = {
    "ru": "🇷🇺 Русский", "cn": "🇨🇳 中文", "en": "🇬🇧 English",
    "de": "🇩🇪 Deutsch", "es": "🇪🇸 Español", "fr": "🇫🇷 Français",
    "it": "🇮🇹 Italiano", "ja": "🇯🇵 日本語", "ko": "🇰🇷 한국어",
    "nl": "🇳🇱 Nederlands", "pl": "🇵🇱 Polski", "pt": "🇧🇷 Português",
    "tr": "🇹🇷 Türkçe", "vn": "🇻🇳 Tiếng Việt", "hi": "🇮🇳 हिन्दी",
    "uk": "🇺🇦 Українська", "kz": "🇰🇿 Қазақша", "fa": "🇮🇷 فارسی",
    "cs": "🇨🇿 Čeština", "sv": "🇸🇪 Svenska", "eo": "🌐 Esperanto",
    "ca": "🏴 Català", "gu": "🇮🇳 ગુજરાતી", "ka": "🇬🇪 ქართული",
    "ky": "🇰🇿 Кыргызча", "tg": "🇹🇯 Тоҷикӣ", "te": "🇮🇳 తెలుగు",
}


def _load_config() -> dict:
    """Load config from file, return dict."""
    try:
        import tomllib
        return tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_config(cfg: dict):
    """Write config dict to file as TOML (handles nested sections)."""
    sections: dict[str, list] = {}

    def _flatten(d: dict, prefix: str):
        for key, val in d.items():
            if isinstance(val, dict):
                new_prefix = f"{prefix}.{key}" if prefix else key
                _flatten(val, new_prefix)
            else:
                sections.setdefault(prefix, []).append((key, val))

    _flatten(cfg, "")

    lines = []
    for section in sorted(sections.keys()):
        if section:
            lines.append(f"[{section}]")
        for key, val in sections[section]:
            if isinstance(val, str):
                lines.append(f'{key} = "{val}"')
            elif isinstance(val, bool):
                lines.append(f'{key} = {"true" if val else "false"}')
            elif isinstance(val, list):
                items = ", ".join(f'"{v}"' for v in val)
                lines.append(f'{key} = [{items}]')
            else:
                lines.append(f'{key} = {val}')
        lines.append("")
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text("\n".join(lines), encoding="utf-8")


def _send_reload_ipc():
    """Tell daemon to reload config via IPC."""
    try:
        IPC_PATH.parent.mkdir(parents=True, exist_ok=True)
        IPC_PATH.write_text(json.dumps({"cmd": "reload_config", "ts": time.time()}))
    except Exception:
        pass


def open_settings_window():
    """Launch the settings window (non-blocking, subprocess)."""
    import subprocess
    subprocess.Popen(
        [sys.executable, "-m", "ocvoice.ui.settings_window"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


class SettingsWindow:
    def __init__(self):
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.win = ctk.CTk()
        self.win.title("⚙️ OCVoice Settings")
        self.win.geometry("520x520")
        self.win.minsize(480, 400)
        self.win.resizable(True, True)

        self.cfg = _load_config()

        self._build_ui()
        self._load_values()

        self.win.protocol("WM_DELETE_WINDOW", self._cancel)
        self.win.mainloop()

    def _build_ui(self):
        # Scrollable frame for content
        scroll = ctk.CTkScrollableFrame(self.win, corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=10, pady=(10, 0))

        # Enable mousewheel scrolling on all platforms
        def _bind_mw(e):
            scroll._parent_canvas.bind_all("<MouseWheel>",
                lambda ev: scroll._parent_canvas.yview_scroll(int(-1*(ev.delta/120)), "units"))
        def _unbind_mw(e):
            scroll._parent_canvas.unbind_all("<MouseWheel>")
        scroll.bind("<Enter>", _bind_mw)
        scroll.bind("<Leave>", _unbind_mw)

        # Wake words
        ctk.CTkLabel(scroll, text="🎤 Wake Words", anchor="w",
                      font=ctk.CTkFont(size=14, weight="bold")).pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(scroll, text="Comma-separated. Say one of these to activate listening.",
                      anchor="w", font=ctk.CTkFont(size=11)).pack(fill="x")
        self.wake_entry = ctk.CTkEntry(scroll, height=35)
        self.wake_entry.pack(fill="x", pady=(4, 10))

        # Send phrases
        ctk.CTkLabel(scroll, text="✉️ Send Phrases", anchor="w",
                      font=ctk.CTkFont(size=14, weight="bold")).pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(scroll, text="Comma-separated. Say one of these to send the message.",
                      anchor="w", font=ctk.CTkFont(size=11)).pack(fill="x")
        self.send_entry = ctk.CTkEntry(scroll, height=35)
        self.send_entry.pack(fill="x", pady=(4, 10))

        # Language
        ctk.CTkLabel(scroll, text="🔤 Language", anchor="w",
                      font=ctk.CTkFont(size=14, weight="bold")).pack(fill="x", pady=(10, 0))
        lang_labels = [LANGUAGE_LABELS.get(c, c) for c in LANGUAGE_CODES]
        current_lang = self.cfg.get("voice", {}).get("language", "ru")
        try:
            lang_idx = LANGUAGE_CODES.index(current_lang)
        except ValueError:
            lang_idx = 0
        self.lang_menu = ctk.CTkOptionMenu(
            scroll, values=lang_labels, width=200,
            font=ctk.CTkFont(size=13),
        )
        self.lang_menu.pack(anchor="w", pady=(4, 10))
        self.lang_menu.set(lang_labels[lang_idx])
        self._lang_code = LANGUAGE_CODES[lang_idx]

        def on_lang_change(choice):
            for code, label in LANGUAGE_LABELS.items():
                if label == choice:
                    self._lang_code = code
                    break

        self.lang_menu.configure(command=on_lang_change)

        # Silence timeout
        ctk.CTkLabel(scroll, text="⏱ Silence Timeout (seconds)", anchor="w",
                      font=ctk.CTkFont(size=14, weight="bold")).pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(scroll, text="How long to wait after speech ends before auto-sending.",
                      anchor="w", font=ctk.CTkFont(size=11)).pack(fill="x")
        timeout_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        timeout_frame.pack(fill="x", pady=(4, 10))
        self.timeout_slider = ctk.CTkSlider(
            timeout_frame, from_=0.5, to=10.0, number_of_steps=20,
            command=self._on_timeout_change,
        )
        self.timeout_slider.pack(side="left", fill="x", expand=True)
        self.timeout_label = ctk.CTkLabel(timeout_frame, text="0.8s", width=40)
        self.timeout_label.pack(side="right", padx=(10, 0))

        # Wake sensitivity
        ctk.CTkLabel(scroll, text="🎤 Wake Sensitivity", anchor="w",
                      font=ctk.CTkFont(size=14, weight="bold")).pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(scroll, text="Higher = detects even quiet voice. Lower = fewer false positives.",
                      anchor="w", font=ctk.CTkFont(size=11)).pack(fill="x")
        sens_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        sens_frame.pack(fill="x", pady=(4, 10))
        ctk.CTkLabel(sens_frame, text="Low", font=ctk.CTkFont(size=11)).pack(side="left")
        self.sens_slider = ctk.CTkSlider(
            sens_frame, from_=0.1, to=1.0, number_of_steps=18,
            command=lambda v: self.sens_label.configure(text=f"{v:.1f}"),
        )
        self.sens_slider.pack(side="left", fill="x", expand=True, padx=5)
        ctk.CTkLabel(sens_frame, text="High", font=ctk.CTkFont(size=11)).pack(side="left")
        self.sens_label = ctk.CTkLabel(sens_frame, text="0.5", width=30)
        self.sens_label.pack(side="right", padx=(10, 0))

        # Speaker threshold
        ctk.CTkLabel(scroll, text="🔒 Speaker Threshold", anchor="w",
                      font=ctk.CTkFont(size=14, weight="bold")).pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(scroll, text="Lower = more permissive (accepts quieter/imperfect voice matches).",
                      anchor="w", font=ctk.CTkFont(size=11)).pack(fill="x")
        thresh_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        thresh_frame.pack(fill="x", pady=(4, 10))
        ctk.CTkLabel(thresh_frame, text="Permissive", font=ctk.CTkFont(size=11)).pack(side="left")
        self.thresh_slider = ctk.CTkSlider(
            thresh_frame, from_=0.1, to=1.0, number_of_steps=18,
            command=lambda v: self.thresh_label.configure(text=f"{v:.1f}"),
        )
        self.thresh_slider.pack(side="left", fill="x", expand=True, padx=5)
        ctk.CTkLabel(thresh_frame, text="Strict", font=ctk.CTkFont(size=11)).pack(side="left")
        self.thresh_label = ctk.CTkLabel(thresh_frame, text="0.5", width=30)
        self.thresh_label.pack(side="right", padx=(10, 0))

        # Voice mode
        ctk.CTkLabel(scroll, text="🎧 Voice Mode", anchor="w",
                      font=ctk.CTkFont(size=14, weight="bold")).pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(scroll, text="wake_word = say wake word first. always_on = always listening.",
                      anchor="w", font=ctk.CTkFont(size=11)).pack(fill="x")
        self.mode_var = ctk.StringVar(value="wake_word")
        self.mode_menu = ctk.CTkOptionMenu(
            scroll, values=["wake_word", "always_on", "push_to_talk"],
            variable=self.mode_var,
            width=200, font=ctk.CTkFont(size=13),
        )
        self.mode_menu.pack(anchor="w", pady=(4, 10))

        # Audio device
        ctk.CTkLabel(scroll, text="🎤 Audio Device", anchor="w",
                      font=ctk.CTkFont(size=14, weight="bold")).pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(scroll, text="Select microphone for voice input.",
                      anchor="w", font=ctk.CTkFont(size=11)).pack(fill="x")
        device_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        device_frame.pack(fill="x", pady=(4, 10))
        self._devices = self._get_audio_devices()
        device_labels = [d["label"] for d in self._devices]
        self.device_var = ctk.StringVar(value="")
        self.device_menu = ctk.CTkOptionMenu(
            device_frame, values=device_labels if device_labels else ["No devices found"],
            variable=self.device_var,
            width=350, font=ctk.CTkFont(size=12),
        )
        self.device_menu.pack(side="left", fill="x", expand=True)
        if not device_labels:
            self.device_menu.configure(state="disabled")

        # Speaker verification toggle
        ctk.CTkLabel(scroll, text="🔒 Speaker Verification", anchor="w",
                      font=ctk.CTkFont(size=14, weight="bold")).pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(scroll, text="Only your enrolled voice activates commands.",
                      anchor="w", font=ctk.CTkFont(size=11)).pack(fill="x")
        self.speaker_var = ctk.BooleanVar(value=True)
        self.speaker_switch = ctk.CTkSwitch(
            scroll, text="Enabled", variable=self.speaker_var,
            font=ctk.CTkFont(size=13),
        )
        self.speaker_switch.pack(anchor="w", pady=(4, 10))

        # TTS toggle
        ctk.CTkLabel(scroll, text="💬 Text-to-Speech", anchor="w",
                      font=ctk.CTkFont(size=14, weight="bold")).pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(scroll, text="Play AI responses aloud via speaker.",
                      anchor="w", font=ctk.CTkFont(size=11)).pack(fill="x")
        self.tts_var = ctk.BooleanVar(value=True)
        self.tts_switch = ctk.CTkSwitch(
            scroll, text="Enabled", variable=self.tts_var,
            font=ctk.CTkFont(size=13),
        )
        self.tts_switch.pack(anchor="w", pady=(4, 10))

        # Buttons
        btn_frame = ctk.CTkFrame(self.win, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkButton(
            btn_frame, text="💾 Save & Apply",
            command=self._save,
            fg_color="#2aa82a", hover_color="#228822",
            height=38, font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(side="right", padx=(5, 0))

        ctk.CTkButton(
            btn_frame, text="✖ Cancel",
            command=self._cancel,
            fg_color="#555555", hover_color="#444444",
            height=38,
        ).pack(side="right", padx=(5, 0))

    @staticmethod
    def _get_audio_devices() -> list[dict]:
        """Return list of input audio devices with id, name, label."""
        import sounddevice as sd
        devices = []
        try:
            for d in sd.query_devices():
                if d["max_input_channels"] > 0:
                    label = f'{d["index"]}: {d["name"]}'
                    devices.append({"id": d["index"], "name": d["name"], "label": label})
        except Exception:
            pass
        return devices

    def _on_timeout_change(self, val):
        self.timeout_label.configure(text=f"{val:.1f}s")

    def _load_values(self):
        voice = self.cfg.get("voice", {})
        self.wake_entry.insert(0, ", ".join(voice.get("wake_words", ["окей код", "hey code"])))
        self.send_entry.insert(0, ", ".join(voice.get("send_phrases", [
            "отправь", "отправляй", "отправить", "send", "go", "done",
        ])))
        timeout = voice.get("silence_timeout", 0.8)
        self.timeout_slider.set(timeout)
        self.timeout_label.configure(text=f"{timeout:.1f}s")

        sens = voice.get("wake_sensitivity", 0.5)
        self.sens_slider.set(sens)
        self.sens_label.configure(text=f"{sens:.1f}")

        thresh = self.cfg.get("speech", {}).get("speaker", {}).get("threshold", 0.5)
        self.thresh_slider.set(thresh)
        self.thresh_label.configure(text=f"{thresh:.1f}")

        mode = voice.get("mode", "wake_word")
        self.mode_var.set(mode)

        # Audio device
        device_id = self.cfg.get("audio", {}).get("device_id", 1)
        for d in self._devices:
            if d["id"] == device_id:
                self.device_var.set(d["label"])
                break
        else:
            self.device_var.set(f"{device_id}: (current device)")
            if self._devices:
                self.device_menu.configure(values=[f"{device_id}: (current device)"] + [d["label"] for d in self._devices])

        speaker = self.cfg.get("speech", {}).get("speaker", {}).get("enabled", True)
        self.speaker_var.set(speaker)

        tts = self.cfg.get("speech", {}).get("tts", {}).get("enabled", True)
        self.tts_var.set(tts)

    def _save(self):
        voice = self.cfg.setdefault("voice", {})
        voice["wake_words"] = [w.strip() for w in self.wake_entry.get().split(",") if w.strip()]
        voice["send_phrases"] = [w.strip() for w in self.send_entry.get().split(",") if w.strip()]
        voice["silence_timeout"] = round(self.timeout_slider.get(), 1)
        voice["language"] = self._lang_code
        voice["wake_sensitivity"] = round(self.sens_slider.get(), 1)
        voice["mode"] = self.mode_var.get()

        # Audio device: map label back to ID
        selected_label = self.device_var.get()
        for d in self._devices:
            if d["label"] == selected_label:
                self.cfg.setdefault("audio", {})["device_id"] = d["id"]
                break

        speech = self.cfg.setdefault("speech", {})
        sp = speech.setdefault("speaker", {})
        sp["enabled"] = self.speaker_var.get()
        sp["threshold"] = round(self.thresh_slider.get(), 1)
        tt = speech.setdefault("tts", {})
        tt["enabled"] = self.tts_var.get()

        _save_config(self.cfg)
        _send_reload_ipc()
        self.win.destroy()

    def _cancel(self):
        self.win.destroy()


if __name__ == "__main__":
    SettingsWindow()
