"""Streaming Speech-to-Text using Vosk.

Real-time transcription with word-by-word output.
Vosk runs locally, no internet needed.
"""

import json
import os
import time
from pathlib import Path
from typing import Optional

import numpy as np

try:
    from vosk import Model, KaldiRecognizer
    HAS_VOSK = True
except ImportError:
    HAS_VOSK = False


MODEL_URLS = {
    "ru": "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip",
    "en": "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
}

MODEL_DIR_NAMES = {
    "ru": "vosk-model-small-ru-0.22",
    "en": "vosk-model-small-en-us-0.15",
}


class VoskSTT:
    """Streaming speech recognition using Vosk."""

    def __init__(self, lang: str = "ru", sample_rate: int = 16000):
        if not HAS_VOSK:
            raise RuntimeError("Vosk is required. Install: pip install vosk")

        self.lang = lang
        self.sample_rate = sample_rate
        self.model_path = self._get_or_download_model(lang)
        self._model = Model(self.model_path)
        self._rec = KaldiRecognizer(self._model, sample_rate)
        self._rec.SetWords(True)
        self._partial = ""
        self._final_parts: list[str] = []
        self._silence_frames = 0

    def _get_or_download_model(self, lang: str) -> str:
        """Get model path, download if needed."""
        cache_dir = os.path.expanduser("~/.cache/ocvoice/vosk")
        model_dir_name = MODEL_DIR_NAMES.get(lang, MODEL_DIR_NAMES["ru"])
        model_path = os.path.join(cache_dir, model_dir_name)

        if os.path.exists(os.path.join(model_path, "am")):
            return model_path

        # Download
        import urllib.request
        import zipfile

        url = MODEL_URLS.get(lang, MODEL_URLS["ru"])
        zip_path = os.path.join(cache_dir, f"{model_dir_name}.zip")

        os.makedirs(cache_dir, exist_ok=True)

        if not os.path.exists(zip_path):
            print(f"[OCVoice] Downloading Vosk model ({model_dir_name})...")
            print(f"[OCVoice] URL: {url}")
            urllib.request.urlretrieve(url, zip_path)
            print(f"[OCVoice] Downloaded")

        print(f"[OCVoice] Extracting model...")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(cache_dir)
        print(f"[OCVoice] Model ready at {model_path}")

        return model_path

    def process(self, audio_chunk: np.ndarray) -> str:
        """Process an audio chunk and return new partial text.

        Args:
            audio_chunk: float32 numpy array of audio (e.g. 1024 samples)

        Returns:
            Latest partial transcription (e.g. "окей код прив...")
        """
        # Vosk expects int16 PCM
        chunk = np.clip(audio_chunk, -1.0, 1.0)
        pcm = (chunk * 32767).astype(np.int16)

        if self._rec.AcceptWaveform(pcm.tobytes()):
            # Final result for this utterance chunk
            result = json.loads(self._rec.Result())
            text = result.get("text", "").strip()
            if text:
                self._final_parts.append(text)
            self._partial = ""
        else:
            # Partial result (mid-utterance)
            partial = json.loads(self._rec.PartialResult())
            self._partial = partial.get("partial", "").strip()

        return self._partial

    def get_partial(self) -> str:
        """Get current partial transcription."""
        return self._partial

    def get_final_since_last_check(self) -> list[str]:
        """Get finalized utterance parts since last check.

        Returns:
            List of finalized text segments.
        """
        parts = list(self._final_parts)
        self._final_parts = []
        return parts

    def get_all_text(self) -> str:
        """Get all accumulated finalized text."""
        result = json.loads(self._rec.FinalResult())
        final = result.get("text", "").strip()
        all_text = " ".join(self._final_parts + [final])
        self._final_parts = []
        self._partial = ""
        return all_text

    def reset(self):
        """Reset the recognizer for a new utterance."""
        self._rec = KaldiRecognizer(self._model, self.sample_rate)
        self._rec.SetWords(True)
        self._partial = ""
        self._final_parts = []

    @property
    def is_partial(self) -> bool:
        return bool(self._partial)
