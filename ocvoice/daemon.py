"""Voice Daemon — the core loop of OCVoice.

@contract: Orchestrates the full audio→action pipeline in a continuous loop
@desc: Manages the complete voice control pipeline:
       Audio → VAD → Wake Word → STT → Speaker Verify → Intent → OpenCode API.
       Runs as a singleton daemon with macOS menu bar / system tray integration.
       Recovers automatically from audio device failures.
@tags: daemon, audio, capture, vad, wake, speech, stt, intent, client, session, project, ui, menubar, tray
@bug: Vosk fuzzy matching has false positives on short utterances
"""

import difflib
import json
import os
import signal
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Optional

import numpy as np

from .config import Config
from .audio.capture import AudioCapture
from .audio.vad import VoiceActivityDetector
from .audio.wake import WakeWordDetector, SimpleWakeWordDetector
from .speech.stt import SpeechToText
from .speech.speaker import SpeakerVerifier
from .intent.parser import IntentParser, ParsedCommand
from .intent.intents import Intent
from .opencode.client import OpenCodeClient
from .opencode.launcher import OpenCodeLauncher
from .opencode.ide_discovery import IDEDiscovery
from .ui.tray import TrayManager
from .cli.ipc import read_command, clear_command
from .ui.menubar import MenuBarManager
from .ui.overlay import OverlayManager
from .ui.notify import notify


class VoiceDaemon:
    """Main voice control daemon.

    @contract: Maintains the audio→action pipeline in a single process
    @desc: Manages all OCVoice components: audio capture, VAD, wake word,
           speech-to-text (Vosk streaming), speaker verification, intent
           parsing, and OpenCode API communication. Runs the macOS menu bar
           on the main thread and audio processing in a background thread.
    @tags: daemon, audio, capture, vad, wake, speech, stt, intent, client, session, project, ui, menubar, tray
    """

    def __init__(self, config: Config):
        self.config = config
        self._running = False
        self._listening = True  # Can be toggled by voice commands
        self._start_time = time.time()

        # Components (initialized in setup)
        self.capture: Optional[AudioCapture] = None
        self.vad: Optional[VoiceActivityDetector] = None
        self.wake: Optional[WakeWordDetector | SimpleWakeWordDetector] = None
        self.stt: Optional[SpeechToText] = None
        self.speaker: Optional[SpeakerVerifier] = None
        self.parser: Optional[IntentParser] = None
        self.client: Optional[OpenCodeClient] = None
        self.launcher: Optional[OpenCodeLauncher] = None
        self.tray: Optional[TrayManager] = None
        self.menubar: Optional[MenuBarManager] = None
        self.overlay: Optional[OverlayManager] = None

        # State
        self._audio_buffer: list[np.ndarray] = []
        self._speaking = False
        self._wake_detected = False
        self._current_model = config.opencode_default_model
        self._current_agent = config.opencode_default_agent
        self._headless = config.headless
        self._quiet_until = time.time()
        self._cmd_mode = False
        self._cmd_text = ""
        self._cmd_start = time.time()
        self._vosk = None
        self._verify_buffer: list[np.ndarray] = []
        self._cmd_longest = ""
        self._cmd_paused = False
        self._cmd_paused_at = 0.0
        self._cmd_last_partial = ""
        self._cmd_silence_since = time.time()
        self._vad_cmd_buffer = np.array([], dtype=np.float32)
        self._state = ""
        self._state_since = 0
        self._state_session_id: Optional[str] = None
        self._session_timestamps: dict[str, float] = {}
        self._manual_session_until = 0.0
        self._selected_project_worktree: str = ""
        self._language: str = config.language
        self._audio_lock = threading.Lock()
        self._client_lock = threading.Lock()
        self._ptt_mode = False

    def _notify(self, title: str, text: str):
        """Send desktop notification + always print to stderr for logs."""
        notify(title, text)
        print(f"[{title}] {text}", file=sys.stderr, flush=True)

    @staticmethod
    def _debug_log(msg: str, exc=None):
        """Log a debug message with optional traceback."""
        if exc:
            tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            print(f"[OCVoice] ⚠️ {msg}: {exc}\n{tb}", file=sys.stderr, flush=True)
        else:
            print(f"[OCVoice] ⚠️ {msg}", file=sys.stderr, flush=True)

    # ─── State Machine ───────────────────────────────────────────────
    # Manages 🟢 ожидает → 🔵 команда → 🟣 ответ... → 🟢 cycle.
    # Updates: session title in OpenCode, dock badge, state file, menubar icon.

    def _set_state(self, state: str):
        """Update all state indicators: session title, dock badge, state file.

        States: waiting, cmd, awaiting, stopped
        """
        self._state = state
        self._state_since = time.time()

        # When awaiting AI response, save current session timestamp
        if state == "awaiting" and self.client and self.client.session_id:
            try:
                s = self.client.get_session(self.client.session_id)
                self._session_timestamps[self.client.session_id] = s.get('time', {}).get('updated', 0)
            except Exception as e:
                self._debug_log("Failed to save session timestamp", e)

        state_map = {
            "waiting":   ("🟢", "ожидает"),
            "cmd":       ("🔵", "команда"),
            "awaiting":  ("🟣", "ответ..."),
            "stopped":   ("🔴", "выкл"),
        }
        icon, label = state_map.get(state, ("⚪", "?"))
        dock_label = icon

        # 1. Обновить сессию-индикатор (видна во всех проектах)
        if self.client and self._state_session_id:
            try:
                title = f"{icon} [OCVoice] {label}"
                self.client.update_session(title=title, session_id=self._state_session_id)
            except Exception as e:
                self._debug_log("Failed to update session title", e)

        # 2. Dock badge (macOS)
        if dock_label:
            try:
                import subprocess
                subprocess.run(
                    ["osascript", "-e",
                     f'tell application "System Events" to set badge of (first process whose name is "OpenCode") to "{dock_label}"'],
                    capture_output=True, timeout=2,
                )
            except Exception as e:
                self._debug_log("Failed to set dock badge", e)

        # 3. State file
        try:
            import json
            from pathlib import Path
            state_path = Path.home() / ".config" / "ocvoice" / "state.json"
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps({
                "state": state,
                "icon": icon,
                "label": label,
                "listening": self._listening,
                "since": self._state_since,
                "model": self._current_model,
                "agent": self._current_agent,
            }, ensure_ascii=False))
        except Exception:
            pass

        # 4. UI indicator (menubar / tray)
        if self.menubar:
            self.menubar.update_status(state)
        if self.tray:
            self.tray.update(state)

    def setup(self) -> bool:
        """Initialize all components.

        @contract: Returns False on critical failure (no audio device)
        @desc: Discovers OpenCode server, starts audio capture, initializes
               VAD, wake word, STT, Vosk, speaker verifier, intent parser,
               and UI components (menu bar/tray/overlay).
        @returns: False if audio capture initialization fails
        @tags: daemon, setup
        """
        print("[OCVoice] Initializing voice daemon...")

        # ── Step 0: Discover OpenCode IDE/CLI server ──
        self.launcher = OpenCodeLauncher(
            binary_path=self.config.opencode_binary_path,
            host=self.config.opencode_host,
            port=self.config.opencode_port,
        )

        ide = IDEDiscovery()
        ide_found = ide.discover()
        
        if ide_found:
            print(f"[OCVoice] Found OpenCode server at {ide.base_url}")
            self.client = OpenCodeClient(base_url=ide.base_url, auth=ide.auth)
            # Verify we can actually use it
            try:
                self.client.list_sessions()
                print(f"[OCVoice] API connection OK")
            except Exception:
                print(f"[OCVoice] IDE requires auth — starting own server on port 4096")
                ide_found = False

        if not ide_found:
            print("[OCVoice] Starting OpenCode server on port 4096...")
            if self.launcher.start(timeout=30.0):
                self.client = OpenCodeClient(base_url=self.config.opencode_base_url)
            else:
                print("[OCVoice] WARNING: Could not start OpenCode server")
                self.client = OpenCodeClient(base_url=self.config.opencode_base_url)

        # Detect correct path prefix for this server
        print(f"[OCVoice] 📡 Сервер: {str(self.client.client.base_url)}", flush=True)

        # ── Audio capture (auto-detect mic) ──
        device_id = self.config.audio_device
        if device_id < 1:
            try:
                from .audio.capture import AudioCapture as _AC
                device_id = _AC.auto_detect_device()
                print(f"[OCVoice] Auto-detected mic device: {device_id}")
            except Exception:
                pass
        else:
            try:
                from .audio.capture import AudioCapture as _AC
                recommended = _AC.auto_detect_device()
                if device_id != recommended and device_id == 0:
                    print(f"[OCVoice] Config has device_id=0 (iPhone?), using auto-detected {recommended}")
                    device_id = recommended
                elif device_id != recommended:
                    print(f"[OCVoice] Using mic device {device_id} from config (auto would pick {recommended})")
            except Exception:
                pass

        try:
            self.capture = AudioCapture(
                sample_rate=self.config.audio_sample_rate,
                channels=self.config.audio_channels,
                device_id=device_id,
                chunk_size=self.config.audio_chunk_size,
            )
        except RuntimeError as e:
            print(f"[OCVoice] Audio capture error: {e}")
            return False

        # ── VAD ──
        try:
            self.vad = VoiceActivityDetector(
                sample_rate=self.config.audio_sample_rate,
                silence_frames=int(self.config.silence_timeout * 1000 / 30),
            )
        except RuntimeError:
            print("[OCVoice] WARNING: VAD not available, continuous mode")
            self.vad = None

        # ── Wake word ──
        if self.config.voice_mode == "wake_word":
            # Check if wake words match ONNX models; otherwise use energy
            onnx_words = [w for w in self.config.wake_words
                         if w.lower() in ("alexa", "hey mycroft", "hey jarvis", "hey rhasspy")]
            if onnx_words:
                try:
                    self.wake = WakeWordDetector(
                        wake_words=self.config.wake_words,
                        sample_rate=self.config.audio_sample_rate,
                        sensitivity=self.config.wake_sensitivity,
                    )
                    print(f"[OCVoice] Wake word detector: openwakeword (onnx) — {onnx_words}")
                except Exception as e:
                    print(f"[OCVoice] openwakeword failed ({e}), using energy detector")
                    self.wake = SimpleWakeWordDetector(
                        wake_words=self.config.wake_words,
                        sample_rate=self.config.audio_sample_rate,
                        sensitivity=self.config.wake_sensitivity,
                    )
                    print("[OCVoice] Wake word detector: energy-based (STT-verified)")
            else:
                self.wake = SimpleWakeWordDetector(
                    wake_words=self.config.wake_words,
                    sample_rate=self.config.audio_sample_rate,
                    sensitivity=self.config.wake_sensitivity,
                )
                print(f"[OCVoice] Wake word: energy-based, words: {', '.join(self.config.wake_words)}")

        # ── Speech-to-Text ──
        try:
            self.stt = SpeechToText(
                backend=self.config.stt_backend,
                local_model=self.config.stt_local_model,
                local_device=self.config.stt_local_device,
                local_compute_type=self.config.stt_local_compute_type,
                api_key=self.config.stt_api_key,
                fallback_to_api=self.config.stt_fallback_to_api,
            )
        except Exception as e:
            print(f"[OCVoice] STT initialization error: {e}")
            print("[OCVoice] Voice-to-text will not be available")
            self.stt = None

        # ── Vosk streaming STT ──
        try:
            from .speech.vosk_stt import VoskSTT
            self._vosk = VoskSTT(lang=self._language)
            print(f"[OCVoice] Vosk STT ready (lang={self._language})")
        except Exception as e:
            print(f"[OCVoice] Vosk init error: {e}")
            self._vosk = None

        # ── Speaker verification ──
        self.speaker = SpeakerVerifier(
            threshold=self.config.speaker_threshold,
            enrollments_dir=self.config.speaker_enrollments_dir,
            sample_rate=self.config.audio_sample_rate,
        )
        if self.config.speaker_enabled:
            if self.speaker.is_enrolled():
                print(f"[OCVoice] Speaker verification: ON (enrolled: {', '.join(self.speaker.list_enrollments())})")
            else:
                print("[OCVoice] Speaker verification: pending enrollment")
                print("[OCVoice] Run 'ocvoice enroll' to register your voice")
        else:
            print("[OCVoice] Speaker verification: OFF")

        # ── Intent parser ──
        self.parser = IntentParser(
            parser_type=self.config.intent_parser,
            confidence_threshold=self.config.intent_confidence_threshold,
            language=self._language,
            wake_words=self.config.wake_words,
        )

        # ── UI: macOS → menu bar, Linux/Windows → system tray ──
        import platform as _platform
        if _platform.system() == "Darwin":
            self.tray = None
            if self.config.get("ui", "menubar", default=True):
                self.menubar = MenuBarManager()
                self.menubar.start(
                    on_toggle=self._on_menubar_toggle,
                    on_quit=self._on_menubar_quit,
                    on_select_session=self._on_tray_select_session,
                    on_select_project=self._on_tray_select_project,
                    on_language_switch=self._on_language_switch,
                    on_agent_switch=self._on_tray_agent_switch,
                    on_find_server=self._on_tray_find_server,
                    on_new_session=self._on_tray_new_session,
                )
                print("[OCVoice] Menu bar: 🎤 в строке меню")
            else:
                self.menubar = None
        else:
            self.menubar = None
            if self.config.tray_enabled:
                self.tray = TrayManager()
                self.tray.start(
                    on_toggle=self._on_tray_toggle,
                    on_exit=self._on_tray_exit,
                    on_select_session=self._on_tray_select_session,
                    on_select_project=self._on_tray_select_project,
                    on_language_switch=self._on_language_switch,
                    on_agent_switch=self._on_tray_agent_switch,
                    on_find_server=self._on_tray_find_server,
                    on_new_session=self._on_tray_new_session,
                )

        # ── Floating overlay (disabled on macOS — requires main thread) ──
        import platform
        if platform.system() != "Darwin":
            try:
                self.overlay = OverlayManager()
                self.overlay.start()
            except Exception as e:
                print(f"[OCVoice] Overlay unavailable: {e}")
        else:
            print("[OCVoice] Overlay: disabled on macOS (use menu bar instead)")
            self.overlay = None

        print("[OCVoice] Daemon initialized")
        return True

    def run(self):
        """Main entry — menu bar on main thread, audio loop in background.

        @contract: Blocks until daemon shutdown (Ctrl+C or menubar quit)
        @desc: Acquires daemon lock, runs setup, starts audio polling thread,
               session poller thread, and blocks on the menu bar main loop.
        @tags: daemon, lifecycle
        """
        if not self._acquire_daemon_lock():
            return
        if not self.setup():
            print("[OCVoice] Failed to initialize. Exiting.")
            return

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        self._running = True
        self._listening = True  # Ensure fresh start, ignore stale state
        self._init_state_session()
        self._select_user_session()
        self._set_state("waiting")

        # Start audio in background thread
        self._start_time = time.time()
        audio_thread = threading.Thread(target=self._audio_loop, daemon=True)
        audio_thread.start()

        # Start session poller in background thread
        poller_thread = threading.Thread(target=self._session_poller, daemon=True)
        poller_thread.start()

        # Run menu bar on MAIN thread (required by macOS/rumps)
        self._run_menu_bar()

    def _audio_loop(self):
        """Audio capture loop — runs in background thread, auto-recovers indefinitely."""
        print("[OCVoice] Daemon running. Speak your commands.")
        if self.config.voice_mode == "wake_word":
            print(f"[OCVoice] Wake words: {', '.join(self.config.wake_words)}")

        while self._running:
            try:
                try:
                    self.capture.stop()
                except Exception:
                    pass
                self.capture = AudioCapture(
                    sample_rate=self.config.audio_sample_rate,
                    channels=self.config.audio_channels,
                    device_id=self.config.audio_device,
                    chunk_size=self.config.audio_chunk_size,
                )
                self.capture.start()
                self._main_loop()
            except Exception as e:
                import traceback
                print(f"[OCVoice] Audio loop error: {e}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                # Log crash to file for diagnosis
                try:
                    with open("/tmp/ocvoice-crash.log", "a") as f:
                        f.write(f"\n=== Crash at {time.ctime()} ===\n")
                        traceback.print_exc(file=f)
                        f.write(f"State: {self._state}, listing={self._listening}\n")
                except Exception:
                    pass
                if self._running:
                    print("[OCVoice] Restarting audio capture in 3s...", file=sys.stderr)
                    time.sleep(3)

        print("[OCVoice] Audio loop ended", file=sys.stderr)

    def _run_menu_bar(self):
        """Run the menu bar on the main thread (macOS requirement)."""
        if self.menubar and self.menubar._app:
            try:
                self.menubar._app.run()
            except Exception as e:
                print(f"[OCVoice] Menu bar error: {e}")
        else:
            # No menu bar — just wait for Ctrl+C
            try:
                while self._running:
                    time.sleep(0.5)
            except KeyboardInterrupt:
                pass

        self.shutdown()

    def _main_loop(self):
        """Core audio processing loop — resilient to per-iteration errors."""
        mode = self.config.voice_mode
        chunk_size = self.config.audio_chunk_size
        last_heartbeat = time.time()

        while self._running:
            try:
                # Check if capture is alive — if not, break for recovery
                if not getattr(self, 'capture', None):
                    print("[OCVoice] Audio capture lost — restarting...", file=sys.stderr)
                    break

                # Read audio chunk
                chunk = self.capture.read(chunk_size, timeout=0.1)
                if len(chunk) == 0:
                    continue

                if not self._listening:
                    continue

                # Safety: сброс зависших состояний (проверка каждый чанк)
                if self._state == "cmd" and time.time() - self._state_since > 180:
                    print(f"[OCVoice] ⏰ Safety reset: cmd 180s timeout", flush=True)
                    self._cmd_mode = False
                    if self._vosk:
                        self._vosk.reset()
                    self._set_state("waiting")
                if self._state == "awaiting" and time.time() - self._state_since > 25:
                    self._set_state("waiting")

                # Heartbeat
                if time.time() - last_heartbeat > 60:
                    self._set_state(self._state)
                    print(f"[OCVoice] Heartbeat: listening={self._listening}, "
                          f"model={self._current_model.split('/')[-1]}, agent={self._current_agent}",
                          file=sys.stderr, flush=True)
                    last_heartbeat = time.time()

                # ── Mode: wake_word ──
                if mode == "wake_word":
                    self._process_wake_word_mode(chunk)

                # ── Mode: always_on ──
                elif mode == "always_on":
                    self._process_always_on_mode(chunk)

                # ── Mode: push_to_talk ──
                elif mode == "push_to_talk":
                    time.sleep(0.05)

            except Exception as e:
                print(f"[OCVoice] Loop iteration error: {e}", file=sys.stderr, flush=True)
                time.sleep(0.5)  # Don't spin on repeated failures

    def _process_wake_word_mode(self, chunk: np.ndarray):
        """Vosk stream mode: каждый чанк → Vosk → проверка в реальном времени."""
        if not self._vosk:
            return

        # Накапливаем аудио для speaker verification (последние 3с)
        self._verify_buffer.append(chunk)
        max_verify = int(3.0 * self.config.audio_sample_rate)
        verify_len = sum(len(c) for c in self._verify_buffer)
        while verify_len > max_verify * 3:  # trim if too big
            self._verify_buffer.pop(0)
            verify_len = sum(len(c) for c in self._verify_buffer)

        self._vosk.process(chunk)
        partial = self._vosk.get_partial()

        import re
        partial_clean = re.sub(r'[^\w\s]', '', partial.lower())

        # Vosk-специфичные fuzzy варианты (small model часто путает)
        vosk_fuzzy = {
            "дарвин": "дарвин", "дарви": "дарвин", "darwin": "дарвин",
            "окей кот": "окей код", "окей код": "окей код",
            "оке": "окей", "кейкот": "окей код", "кей код": "окей код",
            "окикот": "окей код", "окейкут": "окей код",
            "окей ко": "окей код", "окейкат": "окей код",
            "о кей": "окей", "окей": "окей",
        }

        if not self._cmd_mode:
            # ── IDLE: ищем wake word в partial ──
            wake_match = None
            for ww in self.config.wake_words:
                ww_c = re.sub(r'[^\w\s]', '', ww.lower())
                # 1. Прямое совпадение
                if ww_c in partial_clean:
                    wake_match = ww_c
                    break
                # 2. Fuzzy match
                if self._fuzzy_wake_match(partial_clean, ww_c):
                    wake_match = ww_c
                    break
                # 3. Vosk fuzzy variants
                for vosk_w, real_w in vosk_fuzzy.items():
                    if vosk_w in partial_clean and real_w == ww_c:
                        wake_match = vosk_w
                        break
                if wake_match:
                    break
                # 4. Быстрая проверка: "ок" + любое слово на "к" в пределах 3 слов
                words = partial_clean.split()
                for i, w in enumerate(words):
                    if w.startswith("ок") or w.startswith("ok"):
                        for j in range(i+1, min(i+4, len(words))):
                            if words[j].startswith("к"):
                                wake_match = f"{w} {words[j]}"
                                break
                    if wake_match:
                        break
                if wake_match:
                    break

            if wake_match:
                # Используем накопленный буфер для verification
                if len(self._verify_buffer) > 0:
                    verify_audio = np.concatenate(self._verify_buffer)
                    # Берём только последние 0.5с (8000 samples)
                    if len(verify_audio) > max_verify:
                        verify_audio = verify_audio[-max_verify:]
                else:
                    verify_audio = chunk

                if self.speaker and self.config.speaker_enabled:
                    v = self.speaker.verify(verify_audio)
                    score = v.get("score", 0)
                    if score < 0.1:
                        print(f"[OCVoice] 🔍 Wake '{wake_match}' score={score:.2f} — skip verify (model issue)", flush=True)
                    elif not v.get("match", False):
                        if score >= 0.25:
                            print(f"[OCVoice] 🔍 Wake '{wake_match}' partial={score:.2f} — accepted (low threshold)", flush=True)
                        else:
                            print(f"[OCVoice] 🔍 Wake '{wake_match}' too low ({score:.2f}) — ignored", flush=True)
                            return
                # ✅ Wake word + speaker verified
                self._beep(1000, 0.2)
                if self._vosk:
                    self._vosk.reset()  # Чистый Vosk — старый текст не попадёт
                self._cmd_mode = True
                self._cmd_text = ""
                self._cmd_longest = ""
                self._cmd_paused = False
                self._cmd_paused_at = 0
                self._vad_cmd_buffer = np.array([], dtype=np.float32)
                self._cmd_last_partial = ""
                self._cmd_silence_since = time.time()
                self._cmd_start = time.time()
                self._set_state("cmd")
                print(f"[OCVoice] 🟡 CMD START (vosk): partial=\"{partial}\"", flush=True)
                return
            return

        # ── CMD: используем partial (вся речь целиком) + finals ──
        # Safety: если Vosk молчит >15с — возможно пользователь ушёл
        if time.time() - getattr(self, '_cmd_silence_since', time.time()) > 120:
            print(f"[OCVoice] ⏰ CMD timeout — 120с без речи", flush=True)
            self._cmd_mode = False
            self._cmd_text = ""
            if self._vosk:
                self._vosk.reset()
            self._set_state("waiting")
            return

        finals = self._vosk.get_final_since_last_check()
        for f in finals:
            self._cmd_text += " " + f
        self._cmd_text = re.sub(r'\s+', ' ', self._cmd_text).strip()

        # Полный текст = накопленные finals + текущий partial
        full_text = self._cmd_text
        if partial:
            full_text = (full_text + " " + partial).strip()
        full_clean = re.sub(r'[^\w\s]', '', full_text.lower())

        # Сохраняем самую длинную версию (Vosk partial может "съёживаться")
        if len(full_text) > len(getattr(self, '_cmd_longest', '')):
            self._cmd_longest = full_text

        # Ищем end phrase в полном тексте (из конфига + Vosk-специфичные)
        all_eps = list(self.config.send_phrases) + ["отправь", "отправ", "отправи"]
        for ep in sorted(all_eps, key=len, reverse=True):
            ep_c = re.sub(r'[^\w\s]', '', ep.lower())
            if f" {ep_c} " in f" {full_clean} " or full_clean.endswith(f" {ep_c}"):
                # Используем самую длинную версию текста
                longest = getattr(self, '_cmd_longest', full_text)
                longest_clean = re.sub(r'[^\w\s]', '', longest.lower())
                if f" {ep_c} " in f" {longest_clean} " or longest_clean.endswith(f" {ep_c}"):
                    cmd = longest_clean.rsplit(ep_c, 1)[0].strip()
                    print(f"[OCVoice] 🔍 EP match: '{ep}' in '{longest_clean[:100]}...'", flush=True)
                else:
                    cmd = full_clean.rsplit(ep_c, 1)[0].strip()
                print(f"[OCVoice] 🏁 End phrase '{ep}' FOUND! Sending: \"{cmd}\"", flush=True)
                self._cmd_mode = False
                self._cmd_text = ""
                if self._vosk:
                    self._vosk.reset()
                if cmd:
                    self._set_state("awaiting")
                    self._beep(800, 0.1)
                    print(f"[OCVoice] ✅ Sending: \"{cmd}\"", flush=True)
                    threading.Thread(target=self._execute_command_from_text, args=(cmd,), daemon=True).start()
                # PTT mode: single command then stop listening
                if self._ptt_mode:
                    self._ptt_mode = False
                    self._listening = False
                    self._set_state("stopped")
                    print(f"[OCVoice] 🔴 Push-to-talk: ожидание следующего F6", flush=True)
                return

        # Показываем partial + отслеживаем тишину через VAD
        if partial:
            if partial != self._cmd_last_partial:
                self._cmd_silence_since = time.time()
                self._cmd_last_partial = partial
            print(f"[OCVoice] 📝 CMD partial: \"{full_text[:80]}...\"", flush=True)

        # VAD: детектим конец речи (только для таймера, не отправляем)
        self._vad_cmd_buffer = np.concatenate([self._vad_cmd_buffer, chunk])
        while self.vad and len(self._vad_cmd_buffer) >= self.vad.frame_size:
            frame = self._vad_cmd_buffer[:self.vad.frame_size]
            self._vad_cmd_buffer = self._vad_cmd_buffer[self.vad.frame_size:]
            result = self.vad.process(frame)
            if result.get("speech_ended"):
                if not getattr(self, '_cmd_paused', False):
                    self._cmd_paused = True
                    self._cmd_paused_at = time.time()
            elif result.get("speech_started"):
                self._cmd_paused = False

        # Таймер: 10 секунд тишины → авто-отправка
        if getattr(self, '_cmd_paused', False) and time.time() - self._cmd_paused_at > 10:
            print(f"[OCVoice] ⏰ 10s silence — auto-send: \"{full_text[:60]}...\"", flush=True)
            self._cmd_mode = False
            self._cmd_text = ""
            self._vosk.reset()
            if full_clean.strip():
                self._set_state("awaiting")
                self._beep(800, 0.1)
                threading.Thread(target=self._execute_command_from_text, args=(full_clean,), daemon=True).start()
            else:
                self._set_state("waiting")

    def _fuzzy_wake_match(self, text: str, wake: str) -> bool:
        """Fuzzy wake word matching — check if wake word is near in text."""
        parts = wake.split()
        if len(parts) < 2:
            return wake in text
        words = text.split()
        for i, w in enumerate(words):
            if w.startswith(parts[0][:2]) or w.startswith("кей"):
                for j in range(i+1, min(i+4, len(words))):
                    if words[j].startswith(parts[1][:2]) or words[j].startswith("ко") or words[j].startswith("ка"):
                        return True
        return False

    def _execute_command_from_text(self, text: str):
        """Execute a command from transcribed text (CMD path).

        @contract: Routes all intents through _execute_command for unified handling
        @desc: Parses text and delegates to _execute_command for execution.
               All intent types (including SEND_MESSAGE) go through the same
               path to ensure consistent connection checks and logging.
        @tags: daemon, intent, message
        """
        from .intent.parser import IntentParser
        parser = IntentParser(parser_type=self.config.intent_parser,
                              wake_words=self.config.wake_words)
        cmd = parser.parse(text)
        print(f"[OCVoice] 🔍 Parser ({self.config.intent_parser}): \"{text}\" → {cmd.intent.name} conf={cmd.confidence}", flush=True)
        self._show_in_tui(text, cmd)
        self._execute_command(cmd)

    def _process_always_on_mode(self, chunk: np.ndarray):
        """Always-on mode: continuously listen and detect speech segments."""
        if not self.vad:
            return

        result = self.vad.process(chunk)

        if result.get("speech_started"):
            self._speaking = True
            self._audio_buffer = []

        if self._speaking:
            self._audio_buffer.append(chunk)

            if result.get("speech_ended"):
                self._process_speech_buffer()
                self._speaking = False
                self._audio_buffer = []

            # Safety limit
            buf_len = len(self._audio_buffer)
            max_frames = int(self.config.max_duration * self.config.audio_sample_rate / self.config.audio_chunk_size)
            if buf_len > max_frames:
                self._process_speech_buffer()
                self._speaking = False
                self._audio_buffer = []

    def _process_speech_buffer(self):
        """Process collected speech audio: STT → Verify → Parse → Execute."""
        if not self._audio_buffer:
            return

        audio = np.concatenate(self._audio_buffer)
        self._audio_buffer = []

        # Minimum speech length (1.0 seconds) — skip short clicks/pops
        min_samples = int(1.0 * self.config.audio_sample_rate)
        if len(audio) < min_samples:
            return

        print(f"[OCVoice] Processing {len(audio) / self.config.audio_sample_rate:.1f}s of audio...")
        if self.tray:
            self.tray.update("processing")

        # ── Step 1: Speech-to-Text ──
        if not self.stt:
            print("[OCVoice] STT not available")
            return

        result = self.stt.transcribe(audio, self.config.audio_sample_rate)
        text = result.get("text", "").strip()

        if not text:
            print("[OCVoice] No speech recognized")
            return

        print(f"[OCVoice] Recognized [{result.get('language', '?')}]: \"{text}\"")
        print(f"[OCVoice] Backend: {result.get('backend', '?')}, "
              f"Confidence: {result.get('confidence', 0):.2f}")

        # ── Step 1.5: Wake word verification (for wake_word mode) ──
        if self.config.voice_mode == "wake_word":
            import re
            # Normalize: lowercase, remove punctuation
            text_clean = re.sub(r'[^\w\s]', '', text.lower())
            text_clean = re.sub(r'\s+', ' ', text_clean).strip()

            wake_found = False
            for ww in self.config.wake_words:
                ww_clean = re.sub(r'[^\w\s]', '', ww.lower()).strip()
                # Check anywhere in text
                if ww_clean in text_clean:
                    wake_found = True
                    idx = text_clean.find(ww_clean)
                    text = text_clean[:idx] + text_clean[idx + len(ww_clean):]
                    text = text.strip()
                    break
                # Also check if individual words of wake word appear near each other
                ww_parts = ww_clean.split()
                if len(ww_parts) == 2:
                    # "окей" followed by "код" within 3 words
                    words = text_clean.split()
                    for j in range(len(words) - 1):
                        if words[j].startswith(ww_parts[0][:3]) and len(words) > j + 1:
                            # Check next 3 words for the second part
                            for k in range(j+1, min(j+4, len(words))):
                                if words[k].startswith(ww_parts[1][:2]):
                                    wake_found = True
                                    text = ' '.join(words[:j] + words[k+1:]).strip()
                                    print(f"[OCVoice] Wake word spread match: '{' '.join(words[j:k+1])}'")
                                    break
                        if wake_found:
                            break

            # Fuzzy fallback: check common misrecognitions
            if not wake_found:
                fuzzy_map = {
                    "окей кот": "окей код", "окей code": "hey code",
                    "okay code": "hey code", "эй код": "окей код",
                    "хей код": "окей код", "окейкот": "окей код",
                    "кейкот": "окей код", "окейкод": "окей код",
                    "окей кат": "окей код", "окей ко": "окей код",
                    "окикут": "окей код", "окейкут": "окей код",
                    "окейкот": "окей код", "окейкод": "окей код",
                    "hey code": "hey code", "окей кот": "окей код",
                }
                for fuzzy, real in fuzzy_map.items():
                    if fuzzy in text_clean:
                        wake_found = True
                        idx = text_clean.find(fuzzy)
                        text = text_clean[:idx] + text_clean[idx + len(fuzzy):]
                        text = text.strip()
                        print(f"[OCVoice] Wake word fuzzy match: '{fuzzy}' → '{real}'")
                        break
            
            # Additional: check if "оке" or "okay" + "код/кот/код" appear nearby
            if not wake_found:
                words = text_clean.split()
                for j, w in enumerate(words):
                    if w.startswith("ок") or w.startswith("ok") or w.startswith("кей") or w.startswith("oke") or w.startswith("оки") or w.startswith("ки"):
                        # Look for "код", "кот", "кад", "code" in next 4 words
                        for k in range(j+1, min(j+6, len(words))):
                            wk = words[k]
                            if wk.startswith("ко") or wk.startswith("ка") or wk.startswith("cad") or wk == "code" or wk.startswith("код"):
                                wake_found = True
                                text = ' '.join(words[:j] + words[k+1:]).strip()
                                print(f"[OCVoice] Wake word nearby match: '{' '.join(words[j:k+1])}'")
                                break
                    if wake_found:
                        break

            if not wake_found:
                print("[OCVoice] No wake word in transcript — ignoring")
                self._quiet_until = time.time() + 3.0
                return

            # ── End phrase check ──

            # Quick pre-check: if it's a direct command (not a message), allow immediately
            quick_intent = self.parser.parse(text)
            if quick_intent.intent in (Intent.STOP_LISTENING, Intent.START_LISTENING,
                                        Intent.NEW_SESSION, Intent.SWITCH_MODEL,
                                        Intent.SWITCH_MODE, Intent.TOGGLE_THINKING,
                                        Intent.UNDO, Intent.REDO, Intent.SHARE,
                                        Intent.COMPACT, Intent.LIST_SESSIONS):
                pass  # Commands execute immediately, no end phrase needed
            else:
                # For send_message: require end phrase
                all_end_phrases = self.config.send_phrases
                end_found = False

                # Phase 1: Exact match (preferred)
                for ep in sorted(all_end_phrases, key=len, reverse=True):
                    ep_clean = re.sub(r'[^\w\s]', '', ep.lower()).strip()
                    if f" {ep_clean} " in f" {text} " or text.endswith(f" {ep_clean}"):
                        parts = text.rsplit(f" {ep_clean}", 1)
                        text = parts[0].strip()
                        end_found = True
                        print(f"[OCVoice] End phrase detected: '{ep}' → sending")
                        break

                # Phase 2: Fuzzy match (fallback, only if no exact match)
                if not end_found:
                    text_words = text.split()
                    for ep in sorted(all_end_phrases, key=len, reverse=True):
                        ep_clean = re.sub(r'[^\w\s]', '', ep.lower()).strip()
                        # Only check last 3 words — end phrase should be at the end
                        for j in range(max(0, len(text_words)-3), len(text_words)):
                            tw = text_words[j]
                            if len(tw) >= 4 and len(ep_clean) >= 4:
                                if tw.startswith(ep_clean[:5]):
                                    before = ' '.join(text_words[:j]).strip()
                                    after = ' '.join(text_words[j+1:]).strip()
                                    text = f"{before} {after}".strip() if before and after else (before or after)
                                    end_found = True
                                    print(f"[OCVoice] End phrase fuzzy: '{tw}' → '{ep_clean}' → sending")
                                    break
                        if end_found:
                            break

                if not end_found and text.strip():
                    # Shortcut: if text is very short and clearly a command, allow it
                    if len(text.split()) <= 3:
                        print(f"[OCVoice] Short command, auto-sending: \"{text}\"")
                    else:
                        print(f"[OCVoice] Say end phrase to send ('отправь'/'я закончил'/'done')")
                        print(f"[OCVoice] Heard: \"{text}\"")
                        return

        # ── Step 2: Speaker Verification ──
        # ✅ BEEP #2: end phrase confirmed
        time.sleep(0.3)
        self._beep(1200, 0.08)
        self._set_state("awaiting")
        
        if self.speaker and self.config.speaker_enabled:
            if self.speaker.is_enrolled():
                verify = self.speaker.verify(audio)
                if not verify["match"]:
                    print(f"[OCVoice] Speaker verification FAILED (score: {verify['score']:.2f}, "
                          f"threshold: {self.config.speaker_threshold})")
                    print("[OCVoice] Ignoring — voice does not match enrolled speaker")
                    return
                print(f"[OCVoice] Speaker verified (score: {verify['score']:.2f})")
            else:
                print("[OCVoice] Run 'ocvoice enroll' to verify only your voice")

        # ── Step 3: Intent Parsing ──
        command = self.parser.parse(text)
        print(f"[OCVoice] Intent: {command.intent.value} (confidence: {command.confidence:.2f})", flush=True)

        # ── Step 3.5: Show recognition in OpenCode TUI ──
        self._show_in_tui(text, command)

        # ── Step 4: Execute in background thread (non-blocking) ──
        threading.Thread(
            target=self._execute_command,
            args=(command,),
            daemon=True,
        ).start()

    def _show_in_tui(self, text: str, command: ParsedCommand):
        """Show recognized voice command via menu bar notification."""
        lang_icon = "🇷🇺" if any('а' <= c <= 'я' for c in text.lower()) else "🇬🇧"
        print(f"\n{'─'*50}")
        print(f"  {lang_icon} Распознано: \"{text}\"")
        print(f"  🎯 Команда: {command.intent.value}")
        print(f"{'─'*50}")
        sys.stdout.flush()

        if self.menubar:
            self.menubar.notify(f"OCVoice {lang_icon}", text)

    def _show_response(self, text: str):
        """Show AI response via menu bar notification."""
        if self.menubar:
            short = text[:200] + ("..." if len(text) > 200 else "")
            self.menubar.notify("OCVoice ✅", short)

    def _execute_command(self, command: ParsedCommand):
        """Execute the parsed command against OpenCode."""
        try:
            match command.intent:
                case Intent.STOP_LISTENING:
                    self._listening = False
                    self._set_state("stopped")
                    print("[OCVoice] Listening paused. Say wake word to resume.")
                    if self.tray:
                        self.tray.update("stopped")
                    if self.menubar:
                        self.menubar.update_status("stopped")

                case Intent.START_LISTENING:
                    self._listening = True
                    print("[OCVoice] Listening resumed.")
                    if self.tray:
                        self.tray.update("listening")

                case Intent.NEW_SESSION:
                    self._ensure_connected()
                    session = self.client.create_session("🎤 Новая сессия")
                    self.client.session_id = session.get('id')
                    self._manual_session_until = time.time() + 30
                    print(f"  ✅ Новая сессия: {session.get('id', '?')[:16]}...", flush=True)
                    print(f"  💡 Переключитесь на неё в OpenCode (Ctrl+X L)", flush=True)

                case Intent.CURRENT_PROJECT:
                    self._ensure_connected()
                    try:
                        proj = self.client.get_current_project()
                        name = proj.get('worktree', '?').split('/')[-1] or proj.get('id', '?')
                        print(f"  📁 Проект: {name} ({proj.get('worktree', '?')})", flush=True)
                        self._notify("OCVoice 📁", f"Проект: {name}")
                    except Exception as e:
                        print(f"[OCVoice] ❌ Не удалось получить проект: {e}", flush=True)

                case Intent.CURRENT_SESSION:
                    self._ensure_connected()
                    sid = self.client.session_id
                    if not sid:
                        print("  ❌ Нет активной сессии", flush=True)
                    else:
                        try:
                            s = self.client.get_session(sid)
                            title = s.get('title', 'untitled')
                            print(f"  💬 Сессия: {title} ({sid[:16]}...)", flush=True)
                            self._notify("OCVoice 💬", f"Сессия: {title}")
                        except Exception:
                            print(f"  ❌ Сессия {sid[:16]}... недоступна", flush=True)
                    try:
                        proj = self.client.get_current_project()
                        pname = proj.get('worktree', '?').split('/')[-1] or proj.get('id', '?')
                        print(f"  📁 Проект: {pname}", flush=True)
                    except Exception:
                        pass
                    print(f"  🔗 {self.client.client.base_url}", flush=True)

                case Intent.LIST_PROJECTS:
                    self._ensure_connected()
                    try:
                        projects = self.client.list_projects()
                        print(f"[OCVoice] Проекты ({len(projects)}):", flush=True)
                        for i, p in enumerate(projects, 1):
                            name = p.get('worktree', '?').split('/')[-1] or p.get('id', '?')
                            print(f"  {i}. {name} ({p.get('worktree', '?')})", flush=True)
                        print("  💡 Выбрать проект мышкой в IDE", flush=True)
                    except Exception as e:
                        print(f"[OCVoice] ❌ Ошибка: {e}", flush=True)

                case Intent.SWITCH_PROJECT:
                    self._ensure_connected()
                    query = command.arguments.get("project", command.text).strip().lower()
                    all_projects = self._read_opencode_db_projects()
                    candidates = {}
                    for p in all_projects:
                        name = p.get('name', '').lower()
                        if name:
                            candidates[name] = p['worktree']
                            candidates[name.lower()] = p['worktree']
                        folder = p.get('worktree', '').rsplit('/', 1)[-1].lower()
                        if folder and folder != name:
                            candidates[folder] = p['worktree']
                    if not candidates:
                        print(f"[OCVoice] ❌ Нет проектов в БД", flush=True)
                    else:
                        # Try direct match
                        match = difflib.get_close_matches(query, list(candidates.keys()), n=1, cutoff=0.4)
                        # Try with Russian → Latin transliteration
                        if not match:
                            _ru_chars = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
                            _en_chars = "abvgdeejziyklmnoprstufhccssyy'euya"
                            _ru_to_en = dict(zip(_ru_chars, _en_chars))
                            _ru_to_en['ё'] = 'yo'
                            translit = ''.join(_ru_to_en.get(c, c) for c in query)
                            if translit != query:
                                match = difflib.get_close_matches(translit, list(candidates.keys()), n=1, cutoff=0.4)
                        if match:
                            wt = candidates[match[0]]
                            proj_name = wt.rsplit('/', 1)[-1]
                            print(f"[OCVoice] 📁 Проект: {proj_name}", flush=True)
                            self._on_tray_select_project(wt)
                        else:
                            print(f"[OCVoice] ❌ Проект \"{query}\" не найден", flush=True)
                            print(f"  Доступные проекты: {', '.join(sorted(candidates.keys()))}", flush=True)

                case Intent.REDISCOVER:
                    print(f"[OCVoice] 🔍 Поиск сервера...", flush=True)
                    if self._recheck_ide_server():
                        self._select_user_session()
                        print(f"  ✅ Сервер обновлён", flush=True)
                        try:
                            proj = self.client.get_current_project()
                            name = self._extract_project_name(proj)
                            print(f"  📁 Проект: {name}", flush=True)
                        except Exception as e:
                            self._debug_log("Failed to write state file", e)
                        sid = self.client.session_id
                        if sid:
                            try:
                                s = self.client.get_session(sid)
                                print(f"  💬 Сессия: {s.get('title', 'untitled')}", flush=True)
                            except Exception:
                                pass
                    else:
                        print(f"  ❌ Сервер не найден", flush=True)

                case Intent.SWITCH_MODEL:
                    model_name = command.arguments.get("model", command.text)
                    self._current_model = model_name
                    self._ensure_connected()
                    self.client.update_config({"model": model_name})
                    msg = f"Модель: {model_name}"
                    print(f"  ✅ {msg}", flush=True)
                    if self._headless:
                        self._notify("OCVoice 🤖", msg)

                case Intent.SWITCH_MODE:
                    agent = command.arguments.get("agent", "build")
                    self._current_agent = agent
                    self._ensure_connected()
                    self.client.update_config({"default_agent": agent})
                    msg = f"Режим: {agent}"
                    print(f"  ✅ {msg}", flush=True)
                    if self._headless:
                        self._notify("OCVoice 🔄", msg)
                    self._update_ui_menu()

                case Intent.TOGGLE_THINKING:
                    self._ensure_connected()
                    enable = command.arguments.get("enable", True)
                    action = "включен" if enable else "отключен"
                    try:
                        self.client.execute_command("thinking")
                    except Exception:
                        pass
                    print(f"  ✅ Thinking {action}", flush=True)

                case Intent.SWITCH_AGENT:
                    agent = command.arguments.get("agent", command.text)
                    self._current_agent = agent
                    self._ensure_connected()
                    self.client.update_config({"default_agent": agent})
                    print(f"  ✅ Агент: {agent}", flush=True)
                    self._update_ui_menu()

                case Intent.SEND_MESSAGE:
                    self._ensure_connected()
                    self._send_message(command.text)

                case Intent.UNDO:
                    self._ensure_connected()
                    self.client.execute_command("undo")
                    print("[OCVoice] Undo executed")

                case Intent.REDO:
                    self._ensure_connected()
                    self.client.execute_command("redo")
                    print("[OCVoice] Redo executed")

                case Intent.COMPACT:
                    self._ensure_connected()
                    self.client.execute_command("compact")
                    print("[OCVoice] Context compacted")

                case Intent.SHARE:
                    self._ensure_connected()
                    result = self.client.execute_command("share")
                    print("[OCVoice] Session shared")

                case Intent.LIST_SESSIONS:
                    self._ensure_connected()
                    sessions = self.client.list_sessions()
                    user_sessions = [s for s in sessions
                                     if 'OCVoice' not in s.get('title', '')]
                    print(f"[OCVoice] Сессии ({len(user_sessions)}):", flush=True)
                    for i, s in enumerate(user_sessions, 1):
                        marker = " ◄" if s.get('id') == self.client.session_id else ""
                        print(f"  {i}. {s.get('title', 'untitled')} ({s['id'][:8]}...){marker}", flush=True)

                case Intent.SWITCH_SESSION:
                    self._ensure_connected()
                    query = command.arguments.get("session", command.text).strip().lower()
                    sessions = self.client.list_sessions()
                    user_sessions = [s for s in sessions
                                     if 'OCVoice' not in s.get('title', '')]
                    titles = {s.get('title', '').lower()[:60]: s for s in user_sessions if s.get('title')}
                    # Fuzzy match
                    match = difflib.get_close_matches(query, list(titles.keys()), n=1, cutoff=0.4)
                    if match:
                        s = titles[match[0]]
                        self.client.session_id = s['id']
                        self._manual_session_until = time.time() + 30
                        self._beep(880, 0.08)
                        print(f"  ✅ Сессия: {s['title']} ({s['id'][:16]}...)", flush=True)
                    else:
                        # Fallback: substring match
                        matches = [s for s in user_sessions if query in s.get('title', '').lower()]
                        if len(matches) == 1:
                            s = matches[0]
                            self.client.session_id = s['id']
                            self._manual_session_until = time.time() + 30
                            self._beep(880, 0.08)
                            print(f"  ✅ Сессия: {s['title']} ({s['id'][:16]}...)", flush=True)
                        elif len(matches) > 1:
                            print(f"[OCVoice] Найдено несколько сессий:", flush=True)
                            for i, s in enumerate(matches, 1):
                                print(f"  {i}. {s['title']} ({s['id'][:8]}...)", flush=True)
                            print("  Уточни название", flush=True)
                        else:
                            print(f"[OCVoice] ❌ Сессия \"{query}\" не найдена", flush=True)
                            print("  Доступные: " + ", ".join(sorted(titles.keys())[:5]) + "...", flush=True)

                case Intent.SELECT_LAST_SESSION:
                    self._ensure_connected()
                    self._manual_session_until = 0
                    self._select_user_session()
                    print(f"[OCVoice] ✅ Возврат к последней сессии", flush=True)

                case Intent.EXECUTE_COMMAND:
                    self._ensure_connected()
                    cmd = command.arguments.get("command", command.text)
                    self.client.execute_command(cmd)
                    print(f"[OCVoice] Command executed: {cmd}")

                case Intent.RUN_SHELL:
                    self._ensure_connected()
                    cmd = command.arguments.get("command", command.text)
                    self.client.run_shell(cmd)
                    print(f"[OCVoice] Shell command: {cmd}")

                case Intent.UNKNOWN:
                    print(f"[OCVoice] Unknown command: \"{command.text}\"")

                case _:
                    print(f"[OCVoice] Unhandled intent: {command.intent}")

        except Exception as e:
            print(f"[OCVoice] Command execution error: {e}")
            if self.tray:
                self.tray.update("error")
        if command.intent not in (Intent.STOP_LISTENING, Intent.START_LISTENING):
            # Always reset state after command (even on error)
            self._set_state("waiting")

    def _init_state_session(self):
        """Create the status indicator session and clean up old ones."""
        import httpx
        try:
            base = str(self.client.client.base_url)
            auth = self.client.client._auth
            r = httpx.post(
                f"{base}/session",
                auth=auth,
                json={"title": "🎤 OCVoice"},
                timeout=5,
            )
            if r.status_code == 200:
                self._state_session_id = r.json().get("id")
                print(f"[OCVoice] 📊 Status session: {self._state_session_id[:16]}...")
        except Exception as e:
            print(f"[OCVoice] Status session create: {e}")

        if self._state_session_id:
            try:
                for s in self.client.list_sessions():
                    title = s.get('title', '')
                    sid = s.get('id')
                    if 'OCVoice' in title and sid != self._state_session_id:
                        self.client.delete_session(sid)
                        print(f"[OCVoice] 🗑 Deleted old status session: {sid[:16]}...")
            except Exception as e:
                print(f"[OCVoice] Cleanup old sessions: {e}")

    def _recheck_ide_server(self, target_port=None):
        """Rediscover OpenCode server when the current one is unreachable.

        If target_port is given, connect to that specific port directly
        (used by CLI 'ocv select project'). Otherwise scan all ports.
        """
        from .opencode.ide_discovery import IDEDiscovery

        if target_port:
            new_url = f"http://127.0.0.1:{target_port}"
            import httpx
            pw = os.environ.get("OPENCODE_SERVER_PASSWORD", "")
            auth = ("opencode", pw) if pw else None
            try:
                r = httpx.get(f"{new_url}/session", auth=auth, timeout=2)
                if r.status_code != 200:
                    print(f"[OCVoice] ❌ Проект на порту {target_port} недоступен", flush=True)
                    return False
            except Exception:
                print(f"[OCVoice] ❌ Нет соединения с портом {target_port}", flush=True)
                return False
        else:
            ide = IDEDiscovery()
            if not ide.discover():
                return False
            new_url = ide.base_url.rstrip("/")
            auth = ide.auth

        current_url = str(self.client.client.base_url).rstrip("/") if self.client else ""
        if new_url == current_url:
            return True

        print(f"[OCVoice] 🔄 Переключение на сервер: {new_url}", flush=True)
        self._beep(500, 0.12)
        time.sleep(0.08)
        self._beep(800, 0.15)
        if self.client:
            self.client.close()
        self.client = OpenCodeClient(base_url=new_url, auth=auth)
        self._state_session_id = None
        self._init_state_session()
        self._select_user_session()
        return True

    def _select_user_session(self):
        """Select the most recently updated user session and fill timestamp cache."""
        if not self.client:
            return
        try:
            sessions = self.client.list_sessions()
            user_sessions = [s for s in sessions
                             if 'OCVoice' not in s.get('title', '')
                             and s.get('id') != self._state_session_id]
            # Fill timestamp cache for all user sessions
            for s in sessions:
                self._session_timestamps[s['id']] = s.get('time', {}).get('updated', 0)
            if user_sessions:
                latest = max(user_sessions, key=lambda s: s.get('time', {}).get('updated', 0))
                self.client.session_id = latest['id']
                title = latest.get('title', 'untitled')
                print(f"  📋 Сессия: {title} ({latest['id'][:16]}...)", flush=True)
            else:
                s = self.client.create_session("Новый проект")
                self.client.session_id = s.get('id')
                print(f"  📋 Новая сессия: {s.get('id', '?')[:16]}...", flush=True)
        except Exception:
            pass

    def _session_poller(self):
        """Background thread: track session + server updates, IPC commands, tray menu."""
        poll_count = 0
        while self._running:
            # ── IPC: read CLI commands ──
            try:
                cmd = read_command()
                if cmd:
                    self._handle_ipc_command(cmd)
                    clear_command()
            except Exception as e:
                self._debug_log("IPC command error", e)

            # ── Session tracking ──
            try:
                self._check_session_changes()
            except Exception as e:
                self._debug_log("Session check error", e)

            # ── UI menu update (tray or menubar) ──
            try:
                self._update_ui_menu()
            except Exception as e:
                self._debug_log("UI menu update error", e)

            poll_count += 1
            if poll_count % 5 == 0:
                try:
                    self._recheck_ide_server()
                except Exception as e:
                    self._debug_log("Server recheck error", e)
            time.sleep(2.0)

    def _handle_ipc_command(self, cmd: dict):
        """Handle a command received from CLI via IPC file."""
        c = cmd.get('cmd')
        if c == 'select_session':
            session_id = cmd.get('session_id')
            if session_id and self.client:
                self.client.session_id = session_id
                self._manual_session_until = time.time() + 30
                self._beep(880, 0.1)
                print(f"[OCVoice] 📋 IPC: переключено на сессию {session_id[:16]}...", flush=True)
        elif c == 'select_project':
            worktree = cmd.get('worktree')
            if worktree:
                self._on_tray_select_project(worktree)
            port = cmd.get('port')
            if port:
                name = cmd.get('project_name', f'port:{port}')
                print(f"[OCVoice] 📁 IPC: переключено на проект '{name}'", flush=True)
        elif c == 'find_server':
            self._recheck_ide_server()
        elif c == 'new_session':
            self._on_tray_new_session()
        elif c == 'reload_config':
            print(f"[OCVoice] 🔄 Перезагрузка конфига...", flush=True)
            self.config = __import__('ocvoice.config', fromlist=['Config']).Config()
            self._language = self.config.language
            self.parser.set_language(self._language)
            self.parser.set_wake_words(self.config.wake_words)
            if self._vosk:
                self._vosk.set_lang(self._language)
            if self.stt:
                self.stt.set_language(self._language)
            # Restart audio capture with new device
            self._restart_audio_capture()
            # Reset voice mode etc.
            self._cmd_mode = False
            if self._vosk:
                self._vosk.reset()
            self._set_state("waiting")
            print(f"[OCVoice] ✅ Конфиг перезагружен", flush=True)
        elif c == 'ptt':
            print(f"[OCVoice] 🎤 Push-to-talk активирован", flush=True)
            self._ptt_mode = True
            if not self._listening:
                self._listening = True
            self._cmd_mode = False  # Allow new wake word / cmd mode
            if self._vosk:
                self._vosk.reset()
            self._set_state("cmd")

    def _update_ui_menu(self):
        """Fetch current data and push to tray or menubar."""
        if not self.client:
            return
        sessions = self._get_db_sessions_for_selected_project()
        projects = self.client.list_projects()
        current_project = {}
        try:
            current_project = self.client.get_current_project()
        except Exception:
            pass
        all_projects = self._read_opencode_db_projects()

        # Mark current — find which project matches the selected one
        selected = self._selected_project_worktree
        display_project = self._extract_project_name(current_project)
        for p in all_projects:
            p['current'] = bool(p.get('worktree')) and p['worktree'] == selected
            if selected and p.get('worktree') == selected:
                display_project = p.get('name', '') or selected.rsplit('/', 1)[-1]

        kwargs = dict(
            sessions=sessions,
            projects=projects,
            current_session_id=self.client.session_id or "",
            current_project_name=display_project,
            server_url=str(self.client.client.base_url) if self.client else "",
            all_projects=all_projects,
            language=self._language,
            current_agent=self._current_agent,
        )
        if self.menubar:
            self.menubar.update_menu(**kwargs)
        if self.tray:
            self.tray.update_menu(**kwargs)

    def _read_opencode_db_sessions(self, project_worktree: str = "") -> list[dict]:
        """Read sessions from SQLite DB, optionally filtered by project worktree.

        Returns list of {id, title, directory, time}.
        Falls back to API if DB unavailable.
        """
        import os as _os
        import sqlite3

        db_path = _os.path.expanduser("~/.local/share/opencode/opencode.db")
        if not _os.path.isfile(db_path):
            return []

        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            if project_worktree:
                cur = conn.execute(
                    "SELECT s.id, s.title, p.worktree, s.time_updated "
                    "FROM session s "
                    "LEFT JOIN project p ON s.project_id = p.id "
                    "WHERE p.worktree = ? AND s.title NOT LIKE '%[OCVoice]%' "
                    "ORDER BY s.time_updated DESC",
                    (project_worktree,)
                )
            else:
                cur = conn.execute(
                    "SELECT s.id, s.title, p.worktree, s.time_updated "
                    "FROM session s "
                    "LEFT JOIN project p ON s.project_id = p.id "
                    "WHERE s.title NOT LIKE '%[OCVoice]%' "
                    "ORDER BY s.time_updated DESC"
                )
            result = []
            for row in cur.fetchall():
                sid, title, wt, t_updated = row
                result.append({
                    "id": sid,
                    "title": title or "untitled",
                    "directory": wt or "",
                    "time": {"updated": t_updated or 0},
                })
            conn.close()
            return result
        except Exception:
            return []

    def _get_db_sessions_for_selected_project(self) -> list[dict]:
        """Get sessions for the currently selected project. Falls back to API."""
        wt = self._selected_project_worktree
        if not wt:
            return self.client.list_sessions() if self.client else []
        result = self._read_opencode_db_sessions(wt)
        if result:
            return result
        # Fallback: filter API sessions by directory
        if self.client:
            home = os.path.expanduser("~")
            return [
                s for s in self.client.list_sessions()
                if s.get('directory', '').startswith(wt) or s.get('directory', '') == home
            ]
        return []

    @staticmethod
    def _extract_project_name(project: dict) -> str:
        """Get a human-readable project name from API response."""
        name = project.get('name', '') if project else ''
        if name:
            return name
        worktree = project.get('worktree', '') if project else ''
        if worktree and worktree != '/':
            import os as _os
            return _os.path.basename(worktree.rstrip('/'))
        return project.get('id', 'Desktop')[:20] if project else 'Desktop'

    def _read_opencode_db_projects(self) -> list[dict]:
        """Read all projects from OpenCode Desktop storage.

        Sources (combined):
        1. opencode.global.dat — Electron config (all user-added projects)
        2. opencode.db — SQLite DB (additional project info)

        Returns list of {name, worktree, id, current}.
        """
        import os as _os

        seen_worktrees = set()
        result = []

        # 1) opencode.global.dat — primary source for project list
        global_dat_paths = [
            _os.path.expanduser(
                "~/Library/Application Support/ai.opencode.desktop/opencode.global.dat"
            ),
            _os.path.expanduser(
                "~/.config/ai.opencode.desktop/opencode.global.dat"
            ),
        ]
        for gd_path in global_dat_paths:
            if _os.path.isfile(gd_path):
                try:
                    with open(gd_path) as f:
                        gd_data = json.load(f)
                    raw_server = gd_data.get('server', {})
                    if isinstance(raw_server, str):
                        raw_server = json.loads(raw_server)
                    local = raw_server.get('projects', {}).get('local', [])
                    for p in local:
                        worktree = p.get('worktree', '')
                        if worktree and worktree not in seen_worktrees:
                            seen_worktrees.add(worktree)
                            name = _os.path.basename(worktree.rstrip('/'))
                            result.append({
                                "name": name,
                                "worktree": worktree,
                                "id": "",
                                "current": False,
                            })
                except Exception:
                    pass
                break

        # 2) SQLite DB — supplement with IDs, names, VCS info
        db_path = _os.path.expanduser("~/.local/share/opencode/opencode.db")
        if _os.path.isfile(db_path):
            try:
                import sqlite3
                conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
                cur = conn.execute(
                    "SELECT id, worktree, name, vcs FROM project "
                    "WHERE id != 'global' AND worktree != '/'"
                )
                db_projects = {}
                for row in cur.fetchall():
                    pid, worktree, pname, vcs = row
                    db_projects[worktree] = (pid, pname, vcs)
                conn.close()

                for p in result:
                    wt = p['worktree']
                    if wt in db_projects:
                        pid, pname, vcs = db_projects[wt]
                        p['id'] = pid
                        if pname:
                            p['name'] = pname
            except Exception:
                pass

        # 3) If global.dat unavailable, fallback to API
        if not result:
            return self._discover_projects_from_api()

        return result

    def _discover_projects_from_api(self) -> list[dict]:
        """Fallback: get projects from current server's API."""
        if not self.client:
            return []
        try:
            result = []
            for p in self.client.list_projects():
                pid = p.get('id', '')
                worktree = p.get('worktree', '')
                if pid == 'global' or worktree == '/':
                    continue
                import os as _os
                name = _os.path.basename(worktree.rstrip('/')) if worktree else pid[:40]
                result.append({
                    "name": name,
                    "worktree": worktree,
                    "id": pid,
                    "current": False,
                })
            return result
        except Exception:
            return []

    def _find_port_for_worktree(self, worktree: str) -> int | None:
        """Scan known ports to find one serving this worktree. Returns port or None."""
        import httpx
        from .opencode.ide_discovery import IDEDiscovery

        ide = IDEDiscovery()
        scan_ports = sorted(set(
            IDEDiscovery.KNOWN_PORTS + ide._scan_running_ports()
        ))
        pw = os.environ.get("OPENCODE_SERVER_PASSWORD", "")
        auth = ("opencode", pw) if pw else None

        for port in scan_ports:
            try:
                r = httpx.get(f"http://127.0.0.1:{port}/project", auth=auth, timeout=1.5)
                if r.status_code != 200:
                    continue
                for p in r.json():
                    if p.get('worktree') == worktree:
                        return port
            except Exception:
                pass
        return None

    def _extract_port(self) -> int:
        """Extract port number from current client URL."""
        if not self.client:
            return 0
        try:
            url = str(self.client.client.base_url)
            return int(url.rsplit(':', 1)[-1])
        except Exception:
            return 0

    def _check_session_changes(self):
        """List sessions; if awaiting AI response, detect completion and reset."""
        if not self.client:
            return
        try:
            sessions = self.client.list_sessions()
            if not sessions:
                return

            current_id = self.client.session_id

            # If awaiting AI response, check if current session updated
            if self._state == "awaiting" and current_id:
                for s in sessions:
                    if s['id'] == current_id:
                        updated = s.get('time', {}).get('updated', 0)
                        if updated > self._session_timestamps.get(current_id, 0):
                            self._session_timestamps[current_id] = updated
                            print(f"  ✅ AI ответил", flush=True)
                            self._set_state("waiting")
                        break
                return

            if time.time() < self._manual_session_until:
                return

            user_sessions = [s for s in sessions
                             if 'OCVoice' not in s.get('title', '')
                             and s.get('id') != self._state_session_id]
            if not user_sessions:
                return

            latest = max(user_sessions, key=lambda s: s.get('time', {}).get('updated', 0))
            latest_updated = latest.get('time', {}).get('updated', 0)

            if latest['id'] != current_id:
                current_updated = 0
                for s in user_sessions:
                    if s['id'] == current_id:
                        current_updated = s.get('time', {}).get('updated', 0)
                        break
                if latest_updated > current_updated:
                    # Only auto-switch if no project is selected, or session belongs to selected project
                    selected = self._selected_project_worktree
                    if not selected:
                        # No project selected — switch freely
                        pass
                    else:
                        # Project selected — only switch if newer session is in the same project
                        # Check directory field: starts with selected worktree
                        latest_dir = latest.get('directory', '')
                        current_dir = ''
                        for s in user_sessions:
                            if s['id'] == current_id:
                                current_dir = s.get('directory', '')
                                break
                        if not (latest_dir.startswith(selected) or latest_dir == os.path.expanduser("~")):
                            # Newer session is NOT in the selected project — don't switch
                            latest_updated = 0  # Prevent switch
                    if latest_updated > current_updated:
                        title = latest.get('title', 'untitled')
                        self._beep(660, 0.1)
                        print(f"  📋 Переключение на сессию: {title} ({latest['id'][:16]}...)", flush=True)
                        self.client.session_id = latest['id']
        except Exception:
            pass

    def _send_message(self, text: str):
        """Send a message to the active user session (sync, waits for response)."""
        if not text:
            return

        print(f"\n{'─'*50}", flush=True)
        print(f"  🤖 Отправляю в OpenCode [{self._current_agent}]...", flush=True)

        if not self.client or not self.client.session_id:
            print(f"[OCVoice] ❌ Нет сессии для отправки", flush=True)
            return

        # Validate session_id is a user session, not the state session
        if self._state_session_id and self.client.session_id == self._state_session_id:
            print(f"[OCVoice] ❌ session_id указывает на статусную сессию! "
                  f"id={self.client.session_id[:16]}...", flush=True)
            return

        sid = self.client.session_id
        print(f"  📋 Сессия: {sid[:16]}...", flush=True)

        for attempt in range(2):
            try:
                self._set_state("awaiting")
                response = self.client.send_message(
                    text=text,
                    agent=self._current_agent,
                )
                response_text = self._extract_response_text(response)
                if response_text:
                    print(f"  ✅ Ответ:", flush=True)
                    for line in response_text[:600].split('\n'):
                        print(f"  │ {line}", flush=True)
                    self._show_response(response_text)
                else:
                    print(f"  ⚠️ Пустой ответ от модели", flush=True)

                if response_text and self.config.tts_enabled:
                    self._speak_response(response_text)
                self._set_state("waiting")
                break
            except Exception as e:
                err_str = str(e)
                if attempt == 0 and ("ENOENT" in err_str or "no such file" in err_str.lower()):
                    print(f"  ⚠️ Сессия устарела ({sid[:16]}...), обновляю...", flush=True)
                    self._select_user_session()
                    sid = self.client.session_id
                    if sid:
                        print(f"  📋 Новая сессия: {sid[:16]}...", flush=True)
                        continue
                print(f"  ❌ Ошибка отправки: {e}", flush=True)
                self._set_state("waiting")
                break

        print(f"{'─'*50}\n", flush=True)

    def _extract_response_text(self, response: dict) -> str:
        """Extract readable text from OpenCode response."""
        try:
            parts = response.get("parts", [])
            texts = []
            for part in parts:
                if part.get("type") == "text":
                    texts.append(part.get("text", ""))
            return "\n".join(texts)
        except Exception:
            return ""

    def _speak_response(self, text: str):
        """Convert text to speech and play it."""
        try:
            from .speech.tts import TextToSpeech
            tts = TextToSpeech(
                backend=self.config.tts_backend,
                voice_ru=self.config.tts_voice_ru,
                voice_en=self.config.tts_voice_en,
                speed=self.config.tts_speed,
                read_code=self.config.tts_read_code,
                max_length=self.config.tts_max_length,
            )
            tts.speak(text)
        except Exception as e:
            print(f"[OCVoice] TTS error: {e}")

    def _ensure_connected(self):
        """Make sure OpenCode server is reachable. Start if auto_start is on."""
        if self.client.is_connected():
            return

        if self.config.opencode_auto_start:
            print("[OCVoice] OpenCode server not reachable, starting...")
            if self.launcher:
                self.launcher.start(timeout=30.0)

        # Give it a moment
        for _ in range(10):
            if self.client.is_connected():
                return
            time.sleep(0.5)

        print("[OCVoice] WARNING: Could not connect to OpenCode server")

    def _reset_wake_state(self):
        """Reset state."""
        self._cmd_mode = False
        self._cmd_text = ""
        self._audio_buffer = []
        self._verify_buffer = []
        self._cmd_longest = ""
        if self._vosk:
            self._vosk.reset()
        self._quiet_until = time.time() + 3.0
        self._cmd_last_partial = ""
        self._cmd_silence_since = time.time()
        self._vad_cmd_buffer = np.array([], dtype=np.float32)

    def _play_wake_sound(self):
        """Play a short sound to indicate wake word detection."""
        self._beep(800, 0.1)

    def _play_stop_sound(self):
        """Play a short sound to indicate listening stopped."""
        self._beep(400, 0.15)

    def _beep(self, frequency: float, duration: float):
        """Generate a short beep — thread-safe."""
        if not self._audio_lock.acquire(blocking=False):
            return  # Skip if another beep is playing
        try:
            import sounddevice as sd
            sample_rate = 44100
            t = np.linspace(0, duration, int(sample_rate * duration), False)
            tone = 0.7 * np.sin(2 * np.pi * frequency * t)
            fade = int(0.01 * sample_rate)
            tone[:fade] *= np.linspace(0, 1, fade)
            tone[-fade:] *= np.linspace(1, 0, fade)
            sd.play(tone.astype(np.float32), sample_rate, blocking=False)
        except Exception as e:
            print(f"[OCVoice] ⚠️ Beep error: {e}", file=sys.stderr, flush=True)
        finally:
            self._audio_lock.release()

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        print("\n[OCVoice] Shutting down...")
        self._running = False
        self._release_daemon_lock()

    def shutdown(self):
        """Clean shutdown of all components."""
        self._running = False
        # Reset state before stopping
        self._state = "stopped"
        self._state_since = time.time()

        if self.client and self._state_session_id:
            try:
                self.client.update_session(title="🔴 [OCVoice] выключен", session_id=self._state_session_id)
            except Exception:
                pass

        # Reset dock badge
        try:
            import subprocess
            subprocess.run(["osascript", "-e",
                'tell application "System Events" to set badge of (first process whose name is "OpenCode") to ""'],
                capture_output=True, timeout=2)
        except Exception:
            pass

        # Write final state file
        try:
            import json
            from pathlib import Path
            state_path = Path.home() / ".config" / "ocvoice" / "state.json"
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps({
                "state": "stopped",
                "icon": "🔴",
                "label": "выключен",
                "listening": False,
                "since": time.time(),
                "model": self._current_model,
                "agent": self._current_agent,
            }, ensure_ascii=False))
        except Exception:
            pass

        if self.overlay:
            self.overlay.stop()
        if self.menubar:
            self.menubar.stop()
        if self.tray:
            self.tray.stop()
        if self.capture:
            self.capture.stop()
        if self.client:
            self.client.close()
        if self.launcher:
            self.launcher.stop()
        self._release_daemon_lock()
        print("[OCVoice] Daemon stopped.")

    def _on_menubar_toggle(self, enabled: bool):
        """Handle menu bar toggle callback."""
        self._listening = enabled
        if self.menubar:
            self.menubar.update_status("listening" if enabled else "stopped")
        if self.tray:
            self.tray.update("listening" if enabled else "stopped")
        print(f"[OCVoice] Listening {'enabled' if enabled else 'disabled'} via menu bar")

    def _on_overlay_toggle(self):
        if self.overlay:
            self.overlay.toggle()

    def _on_enroll(self):
        print("[OCVoice] Starting voice enrollment via menu bar...")
        from .speech.speaker import SpeakerVerifier
        verifier = SpeakerVerifier(
            threshold=self.config.speaker_threshold,
            enrollments_dir=self.config.speaker_enrollments_dir,
            sample_rate=self.config.audio_sample_rate,
        )
        verifier.enroll()

    def _on_menubar_quit(self):
        self._running = False

    def _on_tray_toggle(self, enabled: bool):
        """Handle tray toggle callback."""
        self._listening = enabled
        if self.tray:
            self.tray.update("listening" if enabled else "stopped")
        if self.menubar:
            self.menubar.update_status("listening" if enabled else "stopped")
        print(f"[OCVoice] Listening {'enabled' if enabled else 'disabled'} via tray")

    def _on_tray_exit(self):
        """Handle tray exit callback."""
        self._running = False

    def _on_tray_select_session(self, session_id: str):
        """Handle session selection from tray menu."""
        if not self.client:
            return
        self.client.session_id = session_id
        self._manual_session_until = time.time() + 30
        self._beep(880, 0.1)
        title = "?"
        try:
            s = self.client.get_session(session_id)
            title = s.get('title', '?')[:40]
        except Exception:
            pass
        print(f"[OCVoice] 📋 Tray: переключено на сессию '{title}'", flush=True)

    def _on_tray_find_server(self, target_port=None):
        """Handle 'Find Server' from tray/menubar menu."""
        self._selected_project_worktree = ""
        if target_port:
            print(f"[OCVoice] 🔄 Подключение к проекту на порту :{target_port}", flush=True)
        self._recheck_ide_server(target_port=target_port)

    def _on_tray_new_session(self):
        """Handle 'New Session' from tray menu."""
        if not self.client:
            return
        self._selected_project_worktree = ""
        try:
            s = self.client.create_session("🎤 Новая сессия")
            self.client.session_id = s['id']
            self._manual_session_until = time.time() + 30
            self._beep(880, 0.1)
            print(f"[OCVoice] ✚ Tray: создана новая сессия {s['id'][:16]}...", flush=True)
        except Exception as e:
            print(f"[OCVoice] ✚ Tray: ошибка создания сессии — {e}", flush=True)

    def _on_tray_agent_switch(self, agent_id: str):
        """Handle agent switch from tray/menubar menu."""
        if agent_id not in ("plan", "build"):
            return
        self._current_agent = agent_id
        icon = "🤖" if agent_id == "plan" else "🔧"
        print(f"[OCVoice] {icon} Агент: {agent_id}", flush=True)
        self._update_ui_menu()
        self._beep(660, 0.1)

    def _on_tray_select_project(self, worktree: str):
        """Handle project selection from tray/menubar menu."""
        if not worktree:
            return
        name = worktree.rsplit('/', 1)[-1]
        print(f"[OCVoice] 📁 Выбран проект: {name} ({worktree})", flush=True)
        self._selected_project_worktree = worktree
        self._manual_session_until = float('inf')

        if not self.client:
            print(f"  ❌ Нет соединения с OpenCode", flush=True)
            self._update_ui_menu()
            return

        # Pick the most recent session for this project from DB
        sessions = self._read_opencode_db_sessions(worktree)
        if sessions:
            latest = max(sessions, key=lambda s: s.get('time', {}).get('updated', 0))
            session_id = latest['id']
            self.client.session_id = session_id
            print(f"  📋 Сессия: {latest.get('title', 'untitled')[:40]} ({session_id[:20]}...)", flush=True)
        else:
            # Fallback: create a new session for this project
            print(f"  ⚠️ Нет сессий для {name}, создаю новую...", flush=True)
            try:
                s = self.client.create_session(f"🎤 {name}")
                if s and s.get('id'):
                    self.client.session_id = s['id']
                    print(f"  📋 Создана новая сессия ({s['id'][:20]}...)", flush=True)
            except Exception as e:
                print(f"  ❌ Не удалось создать сессию: {e}", flush=True)

        self._set_state("waiting")
        self._update_ui_menu()
        self._beep(660, 0.1)

    def _restart_audio_capture(self):
        """Restart audio capture with current config device."""
        was_running = self.capture is not None and self.capture._running
        try:
            if self.capture:
                self.capture.stop()
        except Exception:
            pass
        try:
            from .audio.capture import AudioCapture
            device_id = self.config.audio_device
            if device_id < 1:
                device_id = AudioCapture.auto_detect_device()
            self.capture = AudioCapture(
                sample_rate=self.config.audio_sample_rate,
                channels=self.config.audio_channels,
                device_id=device_id,
                chunk_size=self.config.audio_chunk_size,
            )
            if was_running:
                self.capture.start()
            print(f"[OCVoice] 🎤 Аудиоустройство: device_id={device_id}", flush=True)
        except Exception as e:
            print(f"[OCVoice] ❌ Ошибка перезапуска аудио: {e}", flush=True)

    def _on_language_switch(self, lang: str):
        """Handle language switch from tray/menubar menu."""
        if lang == self._language:
            return
        from .speech.vosk_stt import LANGUAGE_NAMES
        name = LANGUAGE_NAMES.get(lang, lang)
        print(f"[OCVoice] 🔤 Язык: {name}", flush=True)
        self._language = lang

        # Save to config
        try:
            self.config.set("voice", "language", value=lang)
        except Exception:
            pass

        # Update Vosk model
        if self._vosk:
            try:
                self._vosk.set_lang(lang)
            except Exception as e:
                print(f"[OCVoice] Vosk model switch failed: {e}", flush=True)

        # Update parser
        self.parser.set_language(lang)

        # Update STT
        if self.stt:
            self.stt.set_language(lang)

        self._update_ui_menu()
        self._beep(660, 0.1)

    def _get_language_code(self) -> str:
        """Return current language code for UI."""
        return self._language

    DAEMON_PID = Path.home() / ".config" / "ocvoice" / "daemon.pid"

    @staticmethod
    def _acquire_daemon_lock() -> bool:
        """Ensure only one daemon runs. Auto-kill stale or old instances."""
        pid_file = VoiceDaemon.DAEMON_PID
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                os.kill(pid, 0)
                print(f"[OCVoice] 🔄 Останавливаю старый демон (PID {pid})...")
                os.kill(pid, signal.SIGTERM)
                for _ in range(50):
                    try:
                        os.kill(pid, 0)
                        time.sleep(0.1)
                    except ProcessLookupError:
                        break
                else:
                    print(f"[OCVoice] SIGTERM timeout, sending SIGKILL...")
                    try:
                        os.kill(pid, signal.SIGKILL)
                        time.sleep(0.2)
                    except ProcessLookupError:
                        pass
                pid_file.unlink(missing_ok=True)
                print(f"[OCVoice] ✅ Старый демон остановлен")
            except (ProcessLookupError, ValueError, OSError):
                pid_file.unlink(missing_ok=True)
        try:
            pid_file.parent.mkdir(parents=True, exist_ok=True)
            pid_file.write_text(str(os.getpid()))
        except Exception as e:
            print(f"[OCVoice] ❌ Не удалось записать PID: {e}")
            return False
        return True

    @staticmethod
    def _release_daemon_lock():
        """Remove the daemon PID file."""
        try:
            VoiceDaemon.DAEMON_PID.unlink(missing_ok=True)
        except Exception:
            pass

    @staticmethod
    def print_status():
        """Print daemon status."""
        print("OCVoice Status:")
        pid_file = VoiceDaemon.DAEMON_PID
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                print(f"  Daemon PID: {pid}")
            except ValueError:
                print("  Daemon PID: unknown")
        else:
            print("  Daemon PID: not running")

        opencode_pid = Path.home() / ".config" / "ocvoice" / "opencode.pid"
        if opencode_pid.exists():
            try:
                pid = int(opencode_pid.read_text().strip())
                print(f"  OpenCode PID: {pid}")
            except ValueError:
                print("  OpenCode PID: unknown")
        else:
            print("  OpenCode PID: not running")

        enroll_dir = Path.home() / ".config" / "ocvoice" / "enrollments"
        if enroll_dir.exists():
            enrollments = list(enroll_dir.glob("*.npy"))
            print(f"  Voice enrollments: {len(enrollments)}")
            for e in enrollments:
                print(f"    - {e.stem}")
        else:
            print("  Voice enrollments: none")

    @staticmethod
    def stop():
        """Stop a running daemon. SIGKILL if SIGTERM fails after 3s."""
        pid_file = VoiceDaemon.DAEMON_PID
        if not pid_file.exists():
            print("[OCVoice] No daemon PID file found.")
            return
        try:
            pid = int(pid_file.read_text().strip())
            import signal
            print(f"[OCVoice] Останавливаю демон (PID {pid})...")
            os.kill(pid, signal.SIGTERM)
            for _ in range(30):
                try:
                    os.kill(pid, 0)
                    time.sleep(0.1)
                except ProcessLookupError:
                    break
            else:
                print(f"[OCVoice] SIGTERM не сработал, применяю SIGKILL...")
                os.kill(pid, signal.SIGKILL)
                time.sleep(0.2)
            print(f"[OCVoice] Демон остановлен")
        except (ProcessLookupError, ValueError):
            print("[OCVoice] Daemon not running. Cleaning up.")
        finally:
            pid_file.unlink(missing_ok=True)
