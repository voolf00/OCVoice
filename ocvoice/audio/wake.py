"""Wake word detection using openwakeword.

@contract: Detects configured wake words in real-time audio streams
@desc: Uses openwakeword (ONNX) for ML-based wake word detection with
       energy-based fallback (SimpleWakeWordDetector). Supports multiple
       simultaneous wake words with cooldown to prevent re-triggering.
@tags: wake, audio, streaming, onnx
"""

import time
from collections import deque
from typing import Optional

import numpy as np

try:
    from openwakeword.model import Model as OpenWakeWordModel
    HAS_OPENWAKEWORD = True
except ImportError:
    HAS_OPENWAKEWORD = False


class WakeWordDetector:
    """Detects wake words using openwakeword models.

    @contract: Returns matching wake word string or None
    @desc: Loads openwakeword ONNX models per configured wake word.
           Maps custom phrases (e.g. "окей код") to the closest built-in model.
           Cooldown prevents rapid re-triggering of the same phrase.
    @tags: wake, audio, onnx
    """

    # Built-in wake word models available in openwakeword
    BUILTIN_MODELS = {
        "hey code": "hey_mycroft",  # closest match
        "alexa": "alexa",
        "hey mycroft": "hey_mycroft",
    }

    def __init__(
        self,
        wake_words: list[str] = None,
        sample_rate: int = 16000,
        sensitivity: float = 0.5,
        chunk_size: int = 1280,  # 80ms at 16kHz
    ):
        if not HAS_OPENWAKEWORD:
            raise RuntimeError(
                "openwakeword is required for wake word detection. "
                "Install with: pip install openwakeword"
            )

        self.sample_rate = sample_rate
        self.sensitivity = sensitivity
        self.chunk_size = chunk_size
        self.wake_words = wake_words or ["hey code"]

        # Initialize openwakeword model (use onnx since tflite not always available)
        model_names = self._get_models()
        self._model = OpenWakeWordModel(
            wakeword_models=model_names,
            inference_framework="onnx",
        )

        # Keep a small history of detections to avoid false positives
        self._detection_history: deque[tuple[str, float, float]] = deque(maxlen=10)
        self._last_detection_time: dict[str, float] = {}
        self._cooldown = 2.0  # seconds between same wake word

    def _get_models(self) -> list:
        """Get the models to load based on configured wake words.

        Maps wake words to available openwakeword models.
        For Russian "окей код", uses a custom or closest model.
        """
        models = []
        for word in self.wake_words:
            word_lower = word.lower().strip()
            if word_lower in self.BUILTIN_MODELS:
                models.append(self.BUILTIN_MODELS[word_lower])
            elif "окей" in word_lower or "код" in word_lower:
                # Russian wake word — use hey_mycroft as closest match
                # In production, train a custom model
                if "hey_mycroft" not in models:
                    models.append("hey_mycroft")
            else:
                # Try the word directly as model name
                models.append(word_lower)
        return models if models else ["hey_mycroft"]

    def process(self, audio_chunk: np.ndarray) -> Optional[str]:
        """Process an audio chunk and detect wake words.

        @contract: Returns None if no wake word or within cooldown period
        @param audio_chunk: float32 samples, must match chunk_size (1280)
        @returns: Wake word model name if detected, None otherwise
        @tags: wake, audio
        """
        if len(audio_chunk) < self.chunk_size:
            return None

        # openwakeword expects int16 PCM
        audio_chunk = np.clip(audio_chunk[:self.chunk_size], -1.0, 1.0)
        pcm = (audio_chunk * 32767).astype(np.int16)

        predictions = self._model.predict(pcm)

        now = time.time()
        for model_name, score in predictions.items():
            if score > self.sensitivity:
                # Check cooldown
                last = self._last_detection_time.get(model_name, 0)
                if now - last < self._cooldown:
                    continue

                self._last_detection_time[model_name] = now
                self._detection_history.append((model_name, score, now))
                return model_name

        return None

    def reset(self):
        """Reset predictor state and detection cooldowns.

        @tags: wake, audio
        """
        self._model.reset()
        self._last_detection_time.clear()


class SimpleWakeWordDetector:
    """Lightweight wake word detector using audio energy + pattern matching.

    @contract: Detects loud audio spikes as potential wake words
    @desc: Fallback when openwakeword is not available. Uses RMS energy
           spike detection. Less accurate but zero dependencies beyond numpy.
    @tags: wake, audio, fallback
    @bug: Only detects loud sounds, not specific words — high false positive rate
    """

    def __init__(
        self,
        wake_words: list[str] = None,
        sample_rate: int = 16000,
        sensitivity: float = 0.5,
        energy_threshold: float = 0.005,
    ):
        self.sample_rate = sample_rate
        self.sensitivity = sensitivity
        self.energy_threshold = energy_threshold
        self.wake_words = wake_words or ["hey code"]

        # State
        self._energy_history = deque(maxlen=100)
        self._last_detection_time = 0.0
        self._cooldown = 8.0  # seconds between detections  # seconds between detections

    def process(self, audio_chunk: np.ndarray) -> Optional[str]:
        """Simple energy-based wake word detection.

        @contract: May return false positives on any loud sound
        @param audio_chunk: float32 samples
        @returns: "energy_spike" if energy exceeds threshold, None otherwise
        @tags: wake, audio, fallback
        """
        if len(audio_chunk) == 0:
            return None

        energy = np.sqrt(np.mean(audio_chunk ** 2))
        self._energy_history.append(energy)

        if len(self._energy_history) < 3:
            return None

        # Check if recent energy spike exceeds threshold
        recent = list(self._energy_history)[-5:]
        avg_energy = np.mean(recent)
        max_energy = np.max(recent)

        if max_energy > self.energy_threshold * 2.5 and max_energy > avg_energy * 3:
            now = time.time()
            if now - self._last_detection_time > self._cooldown:
                self._last_detection_time = now
                return "energy_spike"

        return None
