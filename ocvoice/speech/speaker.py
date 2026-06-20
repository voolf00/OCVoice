"""Speaker verification using SpeechBrain ECAPA-TDNN.

Enrolls a user's voice and verifies that subsequent utterances
come from the same speaker. Prevents background radio, other people,
etc. from triggering commands.
"""

import json
import os
import time
from pathlib import Path
from typing import Optional

import numpy as np

# We'll try importing speechbrain, but provide a fallback

try:
    import speechbrain  # noqa: F401
    HAS_SPEECHBRAIN = True
except ImportError:
    HAS_SPEECHBRAIN = False

try:
    from resemblyzer import VoiceEncoder, preprocess_wav  # noqa: F401
    HAS_RESEMBLYZER = True
except ImportError:
    HAS_RESEMBLYZER = False


class SpeakerVerifier:
    """Speaker verification system.

    Uses SpeechBrain's ECAPA-TDNN model to create voice embeddings
    and compare them via cosine similarity.

    If SpeechBrain is not available, falls back to Resemblyzer.
    """

    def __init__(
        self,
        threshold: float = 0.75,
        enrollments_dir: str = "",
        sample_rate: int = 16000,
    ):
        self.threshold = threshold
        self.enrollments_dir = Path(enrollments_dir) if enrollments_dir else Path.home() / ".config" / "ocvoice" / "enrollments"
        self.sample_rate = sample_rate

        self._model = None
        self._backend = None
        self._embeddings: dict[str, np.ndarray] = {}
        self._loaded = False

    def _load_model(self):
        """Load the speaker verification model (lazy)."""
        if self._loaded:
            return

        # Try Resemblyzer first (лучше работает с короткими чанками)
        if HAS_RESEMBLYZER:
            try:
                self._model = VoiceEncoder()
                self._backend = "resemblyzer"
                print("[OCVoice] Speaker verification: Resemblyzer loaded")
                self._loaded = True
                return
            except Exception as e:
                print(f"[OCVoice] Resemblyzer load failed: {e}")

        # Fall back to SpeechBrain (требует длинного аудио)
        if HAS_SPEECHBRAIN:
            try:
                from speechbrain.inference.speaker import SpeakerRecognition
                self._model = SpeakerRecognition.from_hparams(
                    source="speechbrain/spkrec-ecapa-voxceleb",
                    savedir=str(Path.home() / ".cache" / "ocvoice" / "speechbrain"),
                )
                self._backend = "speechbrain"
                print("[OCVoice] Speaker verification: SpeechBrain ECAPA-TDNN loaded")
                self._loaded = True
                return
            except Exception as e:
                print(f"[OCVoice] SpeechBrain load failed: {e}")

        # No backend available
        print("[OCVoice] WARNING: No speaker verification backend available. "
              "Install speechbrain or resemblyzer.")
        self._loaded = True
        self._backend = "none"

    def enroll(self, name: str = "default", duration: float = 10.0):
        """Enroll a speaker's voice.

        Records audio from the microphone and saves the voice embedding.

        Args:
            name: Speaker name (for multiple profiles).
            duration: Recording duration in seconds.
        """
        self._load_model()

        if self._backend == "none":
            print("Speaker verification not available — skipping enrollment")
            return False

        print(f"\n{'='*50}")
        print(f"OCVoice — энролмент голоса: '{name}'")
        print(f"Пожалуйста, прочитайте этот текст вслух своим обычным голосом:")
        print()
        print('"Привет, это мой голос для управления OpenCode через голос.')
        print('Я буду использовать этот голос, чтобы отдавать команды.')
        print('OpenCode, узнай мой голос, пожалуйста."')
        print()
        print(f"Запись {duration} секунд...")

        audio = self._record_audio(duration)

        if len(audio) == 0:
            print("No audio recorded. Check your microphone.")
            return False

        embedding = self._create_embedding(audio)

        if embedding is None:
            print("Failed to create voice embedding.")
            return False

        self._save_embedding(name, embedding)
        print(f"Voice enrollment for '{name}' complete!")
        print(f"{'='*50}\n")
        return True

    def enroll_from_audio(self, audio: np.ndarray, sample_rate: int, name: str = "default") -> bool:
        """Enroll a speaker from already-recorded audio.

        Args:
            audio: float32 numpy array of audio samples.
            sample_rate: Sample rate of audio.
            name: Speaker name.

        Returns:
            True on success.
        """
        self._load_model()
        if self._backend == "none":
            return False
        if len(audio) == 0:
            return False
        # Resample if needed
        if sample_rate != self.sample_rate:
            from scipy import signal
            ratio = self.sample_rate / sample_rate
            new_len = int(len(audio) * ratio)
            audio = signal.resample(audio, new_len)
        embedding = self._create_embedding(audio)
        if embedding is None:
            return False
        self._save_embedding(name, embedding)
        return True

    def verify(self, audio: np.ndarray, name: str = "default") -> dict:
        """Verify that audio matches the enrolled speaker.

        Args:
            audio: float32 numpy array of audio samples.
            name: Speaker name to verify against.

        Returns:
            dict with keys: match (bool), score (float), backend (str)
        """
        self._load_model()

        if self._backend == "none":
            # No verification available — allow everything
            return {"match": True, "score": 0.0, "backend": "none"}

        if len(audio) < self.sample_rate * 0.5:
            return {"match": False, "score": 0.0, "backend": self._backend}

        # Load stored embedding
        stored = self._load_embedding(name)
        if stored is None:
            print(f"[OCVoice] No enrollment found for '{name}', you should run 'ocvoice enroll'")
            return {"match": True, "score": 0.0, "backend": self._backend}

        # Create embedding for the utterance
        utterance_emb = self._create_embedding(audio)
        if utterance_emb is None:
            return {"match": False, "score": 0.0, "backend": self._backend}

        # Cosine similarity
        similarity = self._cosine_similarity(stored, utterance_emb)
        match = similarity >= self.threshold

        return {
            "match": match,
            "score": float(similarity),
            "backend": self._backend,
        }

    def _create_embedding(self, audio: np.ndarray) -> Optional[np.ndarray]:
        """Create voice embedding from audio."""
        if self._backend == "speechbrain":
            try:
                # SpeechBrain expects a file path, we'll use temp file
                import tempfile
                import soundfile as sf

                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    sf.write(f.name, audio, self.sample_rate)
                    embedding = self._model.encode_batch(
                        self._model.load_audio(f.name)
                    ).squeeze().cpu().numpy()
                os.unlink(f.name)
                return embedding
            except ImportError:
                # Fallback: try wave module
                import tempfile
                import wave
                import struct

                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    with wave.open(f, "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(self.sample_rate)
                        audio_pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
                        wf.writeframes(audio_pcm.tobytes())
                    embedding = self._model.encode_batch(
                        self._model.load_audio(f.name)
                    ).squeeze().cpu().numpy()
                os.unlink(f.name)
                return embedding
            except Exception as e:
                print(f"[OCVoice] SpeechBrain embedding failed: {e}")
                return None

        elif self._backend == "resemblyzer":
            try:
                # Resemblyzer expects raw audio at 16kHz
                if self.sample_rate != 16000:
                    import scipy.signal
                    audio = scipy.signal.resample(
                        audio, int(len(audio) * 16000 / self.sample_rate)
                    )
                wav = preprocess_wav(audio, source_sr=16000)
                embedding = self._model.embed_utterance(wav)
                return embedding
            except Exception as e:
                print(f"[OCVoice] Resemblyzer embedding failed: {e}")
                return None

        return None

    def _record_audio(self, duration: float) -> np.ndarray:
        """Record audio from microphone for enrollment."""
        try:
            import sounddevice as sd
            audio = sd.rec(
                int(duration * self.sample_rate),
                samplerate=self.sample_rate,
                channels=1,
                dtype=np.float32,
            )
            sd.wait()
            return audio.flatten()
        except ImportError:
            print("sounddevice not available for enrollment recording")
            return np.array([], dtype=np.float32)
        except Exception as e:
            print(f"Recording failed: {e}")
            return np.array([], dtype=np.float32)

    def _save_embedding(self, name: str, embedding: np.ndarray):
        """Save speaker embedding to disk."""
        self.enrollments_dir.mkdir(parents=True, exist_ok=True)
        path = self.enrollments_dir / f"{name}.npy"
        np.save(path, embedding)

        # Also save metadata
        meta_path = self.enrollments_dir / f"{name}.json"
        meta = {
            "name": name,
            "backend": self._backend,
            "enrolled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "sample_rate": self.sample_rate,
        }
        meta_path.write_text(json.dumps(meta, indent=2))

    def _load_embedding(self, name: str) -> Optional[np.ndarray]:
        """Load speaker embedding from disk."""
        if name in self._embeddings:
            return self._embeddings[name]

        path = self.enrollments_dir / f"{name}.npy"
        if not path.exists():
            return None

        try:
            embedding = np.load(path)
            self._embeddings[name] = embedding
            return embedding
        except Exception:
            return None

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        a_norm = np.linalg.norm(a)
        b_norm = np.linalg.norm(b)
        if a_norm == 0 or b_norm == 0:
            return 0.0
        return float(np.dot(a, b) / (a_norm * b_norm))

    def is_enrolled(self, name: str = "default") -> bool:
        """Check if a speaker profile exists."""
        return (self.enrollments_dir / f"{name}.npy").exists()

    def list_enrollments(self) -> list[str]:
        """List all enrolled speaker names."""
        if not self.enrollments_dir.exists():
            return []
        return [
            p.stem for p in self.enrollments_dir.glob("*.npy")
        ]
