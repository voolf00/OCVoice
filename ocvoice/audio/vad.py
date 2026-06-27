"""Voice Activity Detection using webrtcvad.

@contract: Detects speech segments in real-time audio streams
@desc: Filters silence and background noise from audio streams using
       WebRTC VAD as primary and Silero VAD (ONNX) as alternative.
       Tracks speech start/end edges for segment boundary detection.
@tags: audio, vad, streaming
"""

from typing import Optional

import numpy as np

try:
    import webrtcvad
    HAS_WEBRTCVAD = True
except ImportError:
    HAS_WEBRTCVAD = False


class VoiceActivityDetector:
    """Detects voice activity in audio frames.

    @contract: Reports speech/silence state with rising/falling edge detection
    @desc: Uses WebRTC VAD optimized for speech across languages.
           Configurable aggressiveness and silence frame count.
           Tracks speech start and end transitions for segment detection.
    @tags: vad, audio, streaming
    """

    # WebRTC VAD supports frame sizes: 10, 20, or 30 ms
    VALID_FRAME_MS = {10, 20, 30}

    def __init__(
        self,
        sample_rate: int = 16000,
        aggressiveness: int = 2,
        frame_ms: int = 30,
        speech_threshold: float = 0.5,
        silence_frames: int = 15,
    ):
        if not HAS_WEBRTCVAD:
            raise RuntimeError(
                "webrtcvad is required for voice activity detection. "
                "Install with: pip install webrtcvad"
            )

        if frame_ms not in self.VALID_FRAME_MS:
            raise ValueError(f"frame_ms must be one of {self.VALID_FRAME_MS}")

        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.frame_size = int(sample_rate * frame_ms / 1000)
        self.speech_threshold = speech_threshold
        self.silence_frames = silence_frames

        self._vad = webrtcvad.Vad(aggressiveness)

        # Internal state
        self._silence_count = 0
        self._speech_count = 0
        self._is_speaking = False
        self._speech_started = False

    def _float_to_pcm16(self, audio: np.ndarray) -> bytes:
        """Convert float32 [-1.0, 1.0] to 16-bit PCM bytes."""
        audio = np.clip(audio, -1.0, 1.0)
        pcm = (audio * 32767).astype(np.int16)
        return pcm.tobytes()

    def is_speech(self, audio_frame: np.ndarray) -> bool:
        """Check if an audio frame contains speech.

        @param audio_frame: float32 samples, should match frame_size
        @returns: True if WebRTC VAD detects speech
        @tags: vad, audio
        """
        if len(audio_frame) != self.frame_size:
            if len(audio_frame) < self.frame_size:
                return False
            audio_frame = audio_frame[:self.frame_size]

        pcm_bytes = self._float_to_pcm16(audio_frame)
        try:
            return self._vad.is_speech(pcm_bytes, self.sample_rate)
        except Exception:
            return False

    def process(self, audio_frame: np.ndarray) -> dict:
        """Process an audio frame and return VAD state.

        @contract: Returns edges only once per transition
        @param audio_frame: float32 samples
        @returns: dict with keys: is_speaking, speech_started, speech_ended
        @tags: vad, audio
        """
        speech = self.is_speech(audio_frame)

        result = {
            "is_speaking": self._is_speaking,
            "speech_started": False,
            "speech_ended": False,
        }

        if speech:
            self._silence_count = 0
            self._speech_count += 1
            if not self._is_speaking and self._speech_count >= 3:
                self._is_speaking = True
                result["speech_started"] = True
        else:
            self._speech_count = 0
            if self._is_speaking:
                self._silence_count += 1
                if self._silence_count >= self.silence_frames:
                    self._is_speaking = False
                    self._silence_count = 0
                    result["speech_ended"] = True

        result["is_speaking"] = self._is_speaking
        return result

    def reset(self):
        """Reset internal speech/silence counters.

        @tags: vad, audio
        """
        self._silence_count = 0
        self._speech_count = 0
        self._is_speaking = False


class SileroVAD:
    """Alternative VAD using Silero VAD model (via ONNX).

    @contract: Returns speech probability 0.0–1.0
    @desc: More accurate than WebRTC VAD. Requires torch + onnxruntime.
           Auto-downloads the model on first use. Returns 0.0 if unavailable.
    @tags: vad, audio, onnx
    @bug: Requires manual model download first time; no progress bar
    """

    def __init__(self, sample_rate: int = 16000, threshold: float = 0.5):
        self.sample_rate = sample_rate
        self.threshold = threshold
        self._model = None

    def _load_model(self):
        """Lazy-load the Silero VAD model."""
        if self._model is not None:
            return True
        try:
            import torch
            import onnxruntime as ort

            self._ort = ort
            self._torch = torch
            # Silero VAD expects specific operations
            model_path = self._get_model_path()
            self._model = ort.InferenceSession(model_path)
            return True
        except ImportError:
            return False
        except Exception:
            return False

    def _get_model_path(self) -> str:
        """Get path to Silero VAD ONNX model."""
        import os
        cache_dir = os.path.expanduser("~/.cache/ocvoice")
        model_path = os.path.join(cache_dir, "silero_vad.onnx")
        if os.path.exists(model_path):
            return model_path

        # Download on first use
        try:
            import urllib.request
            os.makedirs(cache_dir, exist_ok=True)
            url = "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"
            urllib.request.urlretrieve(url, model_path)
            return model_path
        except Exception:
            raise RuntimeError(
                "Could not download Silero VAD model. "
                "Install with: pip install silero-vad"
            )

    def is_speech(self, audio: np.ndarray) -> float:
        """Check speech probability.

        @param audio: float32 samples (must be ≥512 samples at 16kHz)
        @returns: Probability 0.0–1.0 (0.0 if model not loaded)
        @tags: vad, audio
        """
        if not self._load_model():
            return 0.0

        # Silero expects 512/1024/2048 samples at 16kHz
        if len(audio) < 512:
            return 0.0

        # Take last valid window
        for size in [2048, 1024, 512]:
            if len(audio) >= size:
                window = audio[-size:]
                break
        else:
            return 0.0

        window = window.astype(np.float32)
        ort_inputs = {
            "input": window.reshape(1, -1),
            "sr": np.array(self.sample_rate, dtype=np.int64),
        }
        output = self._model.run(["output"], ort_inputs)[0]
        return float(output[0, 0])

    @property
    def available(self) -> bool:
        return self._load_model()
