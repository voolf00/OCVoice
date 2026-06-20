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


# All Vosk small models (recommended for desktop) — ordered: ru, cn, en, then alphabetically
MODEL_URLS = {
    "ru": "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip",
    "cn": "https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip",
    "en": "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
    "de": "https://alphacephei.com/vosk/models/vosk-model-small-de-0.15.zip",
    "es": "https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip",
    "fr": "https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip",
    "it": "https://alphacephei.com/vosk/models/vosk-model-small-it-0.22.zip",
    "ja": "https://alphacephei.com/vosk/models/vosk-model-small-ja-0.22.zip",
    "ko": "https://alphacephei.com/vosk/models/vosk-model-small-ko-0.22.zip",
    "nl": "https://alphacephei.com/vosk/models/vosk-model-small-nl-0.22.zip",
    "pl": "https://alphacephei.com/vosk/models/vosk-model-small-pl-0.22.zip",
    "pt": "https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip",
    "tr": "https://alphacephei.com/vosk/models/vosk-model-small-tr-0.3.zip",
    "vn": "https://alphacephei.com/vosk/models/vosk-model-small-vn-0.4.zip",
    "hi": "https://alphacephei.com/vosk/models/vosk-model-small-hi-0.22.zip",
    "uk": "https://alphacephei.com/vosk/models/vosk-model-small-uk-v3-small.zip",
    "kz": "https://alphacephei.com/vosk/models/vosk-model-small-kz-0.42.zip",
    "fa": "https://alphacephei.com/vosk/models/vosk-model-small-fa-0.42.zip",
    "cs": "https://alphacephei.com/vosk/models/vosk-model-small-cs-0.4-rhasspy.zip",
    "sv": "https://alphacephei.com/vosk/models/vosk-model-small-sv-rhasspy-0.15.zip",
    "eo": "https://alphacephei.com/vosk/models/vosk-model-small-eo-0.42.zip",
    "ca": "https://alphacephei.com/vosk/models/vosk-model-small-ca-0.4.zip",
    "gu": "https://alphacephei.com/vosk/models/vosk-model-small-gu-0.42.zip",
    "ka": "https://alphacephei.com/vosk/models/vosk-model-small-ka-0.42.zip",
    "ky": "https://alphacephei.com/vosk/models/vosk-model-small-ky-0.42.zip",
    "tg": "https://alphacephei.com/vosk/models/vosk-model-small-tg-0.22.zip",
    "te": "https://alphacephei.com/vosk/models/vosk-model-small-te-0.42.zip",
}

MODEL_DIR_NAMES = {
    "ru": "vosk-model-small-ru-0.22",
    "cn": "vosk-model-small-cn-0.22",
    "en": "vosk-model-small-en-us-0.15",
    "de": "vosk-model-small-de-0.15",
    "es": "vosk-model-small-es-0.42",
    "fr": "vosk-model-small-fr-0.22",
    "it": "vosk-model-small-it-0.22",
    "ja": "vosk-model-small-ja-0.22",
    "ko": "vosk-model-small-ko-0.22",
    "nl": "vosk-model-small-nl-0.22",
    "pl": "vosk-model-small-pl-0.22",
    "pt": "vosk-model-small-pt-0.3",
    "tr": "vosk-model-small-tr-0.3",
    "vn": "vosk-model-small-vn-0.4",
    "hi": "vosk-model-small-hi-0.22",
    "uk": "vosk-model-small-uk-v3-small",
    "kz": "vosk-model-small-kz-0.42",
    "fa": "vosk-model-small-fa-0.42",
    "cs": "vosk-model-small-cs-0.4-rhasspy",
    "sv": "vosk-model-small-sv-rhasspy-0.15",
    "eo": "vosk-model-small-eo-0.42",
    "ca": "vosk-model-small-ca-0.4",
    "gu": "vosk-model-small-gu-0.42",
    "ka": "vosk-model-small-ka-0.42",
    "ky": "vosk-model-small-ky-0.42",
    "tg": "vosk-model-small-tg-0.22",
    "te": "vosk-model-small-te-0.42",
}


LANGUAGE_NAMES = {
    "ru": "🇷🇺 Русский",
    "cn": "🇨🇳 中文",
    "en": "🇬🇧 English",
    "de": "🇩🇪 Deutsch",
    "es": "🇪🇸 Español",
    "fr": "🇫🇷 Français",
    "it": "🇮🇹 Italiano",
    "ja": "🇯🇵 日本語",
    "ko": "🇰🇷 한국어",
    "nl": "🇳🇱 Nederlands",
    "pl": "🇵🇱 Polski",
    "pt": "🇧🇷 Português",
    "tr": "🇹🇷 Türkçe",
    "vn": "🇻🇳 Tiếng Việt",
    "hi": "🇮🇳 हिन्दी",
    "uk": "🇺🇦 Українська",
    "kz": "🇰🇿 Қазақша",
    "fa": "🇮🇷 فارسی",
    "cs": "🇨🇿 Čeština",
    "sv": "🇸🇪 Svenska",
    "eo": "🌐 Esperanto",
    "ca": "🏴 Català",
    "gu": "🇮🇳 ગુજરાતી",
    "ka": "🇬🇪 ქართული",
    "ky": "🇰🇿 Кыргызча",
    "tg": "🇹🇯 Тоҷикӣ",
    "te": "🇮🇳 తెలుగు",
}

# Ordered list for UI: ru, cn, en, then alphabetical
LANGUAGE_ORDER = ["ru", "cn", "en"] + sorted(
    [k for k in LANGUAGE_NAMES if k not in ("ru", "cn", "en")]
)


# ─── class VoskSTT ───────────────────────────────
# Streaming STT — each chunk → partial text in real-time

class VoskSTT:
    """Streaming speech recognition using Vosk."""

    def __init__(self, lang: str = "ru", sample_rate: int = 16000):
        if not HAS_VOSK:
            raise RuntimeError("Vosk is required. Install: pip install vosk")

        self.lang = lang
        self.sample_rate = sample_rate
        self._model = None
        self._rec = None
        self._load_model(lang)
        self._partial = ""
        self._final_parts: list[str] = []
        self._silence_frames = 0

    def _load_model(self, lang: str):
        """Load (or download and load) a Vosk model for the given language."""
        model_path = self._get_or_download_model(lang)
        self._model = Model(model_path)
        self._rec = KaldiRecognizer(self._model, self.sample_rate)
        self._rec.SetWords(True)

# ─── def set_lang ───────────────────────────────
# Switch Vosk model at runtime (download if needed)

    def set_lang(self, lang: str):
        """Switch to a different language model at runtime."""
        if lang == self.lang and self._model:
            return
        self.lang = lang
        self._partial = ""
        self._final_parts = []
        self._load_model(lang)

# ─── def _get_or_download_model ───────────────────────────────
# Download with progress bar via httpx streaming

    def _get_or_download_model(self, lang: str) -> str:
        """Get model path, download if needed with progress bar."""
        cache_dir = os.path.expanduser("~/.cache/ocvoice/vosk")
        model_dir_name = MODEL_DIR_NAMES.get(lang, MODEL_DIR_NAMES["ru"])
        model_path = os.path.join(cache_dir, model_dir_name)

        if os.path.exists(os.path.join(model_path, "am")):
            return model_path

        # Download with progress
        import io
        import zipfile

        url = MODEL_URLS.get(lang, MODEL_URLS["ru"])
        zip_path = os.path.join(cache_dir, f"{model_dir_name}.zip")
        os.makedirs(cache_dir, exist_ok=True)

        if not os.path.exists(zip_path):
            print(f"[OCVoice] 📥 Downloading Vosk model ({model_dir_name})...")
            import httpx
            try:
                response = httpx.get(url, follow_redirects=True, timeout=300)
                total = int(response.headers.get("content-length", 0))
                downloaded = 0
                with open(zip_path, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = downloaded * 100 // total
                            mb_dl = downloaded // (1024 * 1024)
                            mb_total = total // (1024 * 1024)
                            print(f"\r  📥 {pct}% ({mb_dl}MB / {mb_total}MB)", end="", file=sys.stderr)
                if total:
                    print(file=sys.stderr)
            except Exception as e:
                print(f"[OCVoice] ❌ Download failed: {e}", file=sys.stderr)
                if os.path.exists(zip_path):
                    os.remove(zip_path)
                # Fallback to urllib
                import urllib.request
                urllib.request.urlretrieve(url, zip_path)

        print(f"[OCVoice] 📦 Extracting model...", file=sys.stderr)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(cache_dir)
        print(f"[OCVoice] ✅ Model ready at {model_path}", file=sys.stderr)

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
