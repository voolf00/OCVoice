"""Speech-to-Text module.

Supports two backends:
1. Local: faster-whisper (CTranslate2-based Whisper) — offline, fast
2. API: OpenAI Whisper API — cloud, highest accuracy

Operates in "auto" mode by default: local first, API fallback.
"""

import io
import time
from pathlib import Path
from typing import Optional

import numpy as np

# ---- Local backend ----

try:
    from faster_whisper import WhisperModel
    HAS_FASTER_WHISPER = True
except ImportError:
    HAS_FASTER_WHISPER = False

# ---- API backend ----

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


MODEL_SIZES = {
    "tiny": "tiny",
    "base": "base",
    "small": "small",
    "medium": "medium",
    "large": "large-v3",
}


class LocalSTT:
    """Speech-to-text using faster-whisper (local inference)."""

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "default",
    ):
        if not HAS_FASTER_WHISPER:
            raise RuntimeError(
                "faster-whisper is required for local STT. "
                "Install with: pip install faster-whisper"
            )

        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type

        self._model: Optional[WhisperModel] = None
        self._model_name = MODEL_SIZES.get(model_size, model_size)

    def _ensure_model(self):
        """Lazy-load the Whisper model."""
        if self._model is not None:
            return

        print(f"[OCVoice] Loading faster-whisper model '{self._model_name}' "
              f"on {self.device}...")
        start = time.time()

        self._model = WhisperModel(
            self._model_name,
            device=self.device,
            compute_type=self.compute_type,
            download_root=str(Path.home() / ".cache" / "ocvoice" / "whisper"),
        )

        elapsed = time.time() - start
        print(f"[OCVoice] Model loaded in {elapsed:.1f}s")

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> dict:
        """Transcribe audio to text.

        Args:
            audio: float32 numpy array of audio samples.
            sample_rate: audio sample rate.

        Returns:
            dict with keys: text, language, confidence, backend
        """
        self._ensure_model()

        # faster-whisper expects float32
        audio = audio.astype(np.float32)

        segments, info = self._model.transcribe(
            audio,
            beam_size=5,
            language=None,  # auto-detect
            vad_filter=True,
            vad_parameters={"threshold": 0.5},
        )

        texts = []
        total_confidence = 0.0
        count = 0

        for segment in segments:
            texts.append(segment.text.strip())
            total_confidence += segment.avg_logprob
            count += 1

        text = " ".join(texts).strip()
        confidence = total_confidence / max(count, 1)
        # Convert logprob to a 0-1 scale approximation
        confidence = max(0.0, min(1.0, (confidence + 2.0) / 2.0))

        return {
            "text": text,
            "language": info.language,
            "confidence": confidence,
            "backend": "local",
        }

    @property
    def loaded(self) -> bool:
        return self._model is not None


class API_STT:
    """Speech-to-text using OpenAI Whisper API."""

    def __init__(self, api_key: str = ""):
        if not HAS_OPENAI:
            raise RuntimeError(
                "openai package is required for API STT. "
                "Install with: pip install openai"
            )

        self.api_key = api_key
        self._client: Optional[OpenAI] = None

    def _ensure_client(self):
        if self._client is not None:
            return
        key = self.api_key or ""
        if not key:
            raise ValueError("OpenAI API key is required for API STT")
        self._client = OpenAI(api_key=key)

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> dict:
        """Transcribe audio using OpenAI Whisper API.

        Args:
            audio: float32 numpy array.
            sample_rate: audio sample rate.

        Returns:
            dict with keys: text, language, confidence, backend
        """
        self._ensure_client()

        # Convert to 16-bit PCM WAV in memory
        audio = np.clip(audio, -1.0, 1.0)
        pcm = (audio * 32767).astype(np.int16)

        import struct
        import wave

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes(pcm.tobytes())

        buf.seek(0)
        buf.name = "audio.wav"

        transcript = self._client.audio.transcriptions.create(
            model="whisper-1",
            file=buf,
            response_format="verbose_json",
        )

        return {
            "text": transcript.text.strip(),
            "language": transcript.language,
            "confidence": getattr(transcript, "confidence", 0.95),
            "backend": "api",
        }


class SpeechToText:
    """Unified Speech-to-Text interface.

    Handles backend selection, fallback logic, and result normalization.
    """

    def __init__(
        self,
        backend: str = "auto",
        local_model: str = "base",
        local_device: str = "cpu",
        local_compute_type: str = "default",
        api_key: str = "",
        fallback_to_api: bool = True,
    ):
        self.backend = backend
        self.fallback_to_api = fallback_to_api

        # Initialize backends lazily
        self._local: Optional[LocalSTT] = None
        self._api: Optional[API_STT] = None

        self._local_config = {
            "model_size": local_model,
            "device": local_device,
            "compute_type": local_compute_type,
        }
        self._api_key = api_key

    def _get_local(self) -> LocalSTT:
        if self._local is None:
            self._local = LocalSTT(**self._local_config)
        return self._local

    def _get_api(self) -> API_STT:
        if self._api is None:
            self._api = API_STT(api_key=self._api_key)
        return self._api

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> dict:
        """Transcribe audio to text.

        Returns dict: {text, language, confidence, backend}
        """
        if len(audio) == 0:
            return {"text": "", "language": "", "confidence": 0.0, "backend": "none"}

        # Determine which backend to try
        if self.backend == "local":
            return self._transcribe_local(audio, sample_rate)
        elif self.backend == "api":
            return self._transcribe_api(audio, sample_rate)
        else:  # "auto"
            return self._transcribe_auto(audio, sample_rate)

    def _transcribe_local(self, audio: np.ndarray, sample_rate: int) -> dict:
        try:
            if not HAS_FASTER_WHISPER:
                raise RuntimeError("faster-whisper not installed")
            return self._get_local().transcribe(audio, sample_rate)
        except Exception as e:
            if self.fallback_to_api and self._api_key:
                print(f"[OCVoice] Local STT failed, trying API...")
                return self._transcribe_api(audio, sample_rate)
            return {"text": "", "language": "", "confidence": 0.0, "backend": "error"}

    def _transcribe_api(self, audio: np.ndarray, sample_rate: int) -> dict:
        try:
            if not HAS_OPENAI or not self._api_key:
                raise RuntimeError("OpenAI API key not configured")
            return self._get_api().transcribe(audio, sample_rate)
        except Exception as e:
            return {"text": "", "language": "", "confidence": 0.0, "backend": "error"}

    def _transcribe_auto(self, audio: np.ndarray, sample_rate: int) -> dict:
        """Try local first, fall back to API."""
        result = self._transcribe_local(audio, sample_rate)
        if result["text"]:
            return result
        if self.fallback_to_api:
            return self._transcribe_api(audio, sample_rate)
        return result
