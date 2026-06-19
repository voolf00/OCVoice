"""Audio capture module using sounddevice.

Provides a ring-buffer audio stream with configurable sample rate,
channels, and device selection.
"""

import threading
import time
from collections import deque
from typing import Optional

import numpy as np

try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except ImportError:
    HAS_SOUNDDEVICE = False


class AudioCapture:
    """Captures audio from the default microphone into a ring buffer."""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        device_id: Optional[int] = None,
        chunk_size: int = 1024,
        buffer_duration: float = 30.0,
    ):
        if not HAS_SOUNDDEVICE:
            raise RuntimeError(
                "sounddevice is required for audio capture. "
                "Install with: pip install sounddevice"
            )

        self.sample_rate = sample_rate
        self.channels = channels
        self.device_id = device_id
        self.chunk_size = chunk_size

        self._stream: Optional[sd.InputStream] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Ring buffer: store buffer_duration seconds of audio
        buffer_frames = int(buffer_duration * sample_rate)
        self._buffer = deque(maxlen=buffer_frames)
        self._lock = threading.Lock()

        # Event for new audio data
        self._data_event = threading.Event()

        # Check device
        if device_id is not None:
            try:
                sd.check_input_settings(device=device_id, channels=channels, samplerate=sample_rate)
            except sd.PortAudioError as e:
                print(f"Warning: device {device_id} not suitable: {e}")
                print("Available devices:")
                for d in sd.query_devices():
                    if d["max_input_channels"] > 0:
                        print(f"  [{d['index']}] {d['name']}")

    def _callback(self, indata, frames, time_info, status):
        """Audio stream callback — pushes data to ring buffer."""
        if status:
            print(f"Audio callback status: {status}")
        with self._lock:
            # Store as float32 normalized samples
            self._buffer.extend(indata[:, 0].tolist())
        self._data_event.set()

    def start(self):
        """Start audio capture."""
        if self._running:
            return

        self._running = True
        self._stream = sd.InputStream(
            device=self.device_id,
            channels=self.channels,
            samplerate=self.sample_rate,
            callback=self._callback,
            blocksize=self.chunk_size,
            dtype=np.float32,
        )
        self._stream.start()
        print(f"[OCVoice] Audio capture started (SR={self.sample_rate}, CH={self.channels})")

    def stop(self):
        """Stop audio capture."""
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        print("[OCVoice] Audio capture stopped")

    def read(self, num_samples: int, timeout: float = 1.0) -> np.ndarray:
        """Read num_samples from the ring buffer.

        Blocks until enough data is available or timeout expires.
        Returns numpy array of float32 samples.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if len(self._buffer) >= num_samples:
                    data = [self._buffer.popleft() for _ in range(num_samples)]
                    return np.array(data, dtype=np.float32)
            self._data_event.wait(timeout=0.05)
            self._data_event.clear()

        # Timeout — return whatever we have
        with self._lock:
            available = min(num_samples, len(self._buffer))
            if available == 0:
                return np.array([], dtype=np.float32)
            data = [self._buffer.popleft() for _ in range(available)]
            return np.array(data, dtype=np.float32)

    def read_all(self) -> np.ndarray:
        """Read all available data from the ring buffer."""
        with self._lock:
            data = list(self._buffer)
            self._buffer.clear()
        return np.array(data, dtype=np.float32) if data else np.array([], dtype=np.float32)

    def wait_for_speech(self, min_samples: int, timeout: float = 10.0) -> bool:
        """Wait until at least min_samples are in the buffer."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if len(self._buffer) >= min_samples:
                    return True
            self._data_event.wait(timeout=0.1)
            self._data_event.clear()
        return False

    @property
    def is_running(self) -> bool:
        return self._running

    @staticmethod
    def list_devices():
        """List available audio input devices."""
        if not HAS_SOUNDDEVICE:
            print("sounddevice not available")
            return
        devices = sd.query_devices()
        for d in devices:
            if d["max_input_channels"] > 0:
                print(f"  [{d['index']}] {d['name']} "
                      f"(in: {d['max_input_channels']}, "
                      f"sr: {d['default_samplerate']:.0f})")

    @staticmethod
    def auto_detect_device() -> int:
        """Auto-detect best input device. Prefers built-in mic, avoids iPhone/Bluetooth."""
        if not HAS_SOUNDDEVICE:
            return 0
        devices = sd.query_devices()
        best = 0
        best_score = -1
        for d in devices:
            if d["max_input_channels"] == 0:
                continue
            name = d["name"].lower()
            score = 0
            # Penalize iPhone
            if "iphone" in name:
                score -= 10
            # Penalize Bluetooth
            if "bluetooth" in name:
                score -= 5
            # Prefer MacBook built-in
            if "macbook" in name or "built-in" in name:
                score += 5
            if "microphone" in name:
                score += 3
            # Prefer higher sample rate
            if d["default_samplerate"] >= 48000:
                score += 1
            if score > best_score:
                best_score = score
                best = d["index"]
        return best
