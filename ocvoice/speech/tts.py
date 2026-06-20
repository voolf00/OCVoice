"""Text-to-Speech module.

Converts OpenCode text responses to spoken audio.
Supports:
- Edge TTS (Microsoft Edge TTS, free, high quality, many voices)
- Piper TTS (fully offline, lightweight)
"""

import asyncio
import io
import os
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np


class EdgeTTS:
    """Text-to-Speech using Microsoft Edge TTS (free, online)."""

    def __init__(
        self,
        voice: str = "en-US-JennyNeural",
        speed: float = 1.0,
    ):
        self.voice = voice
        self.speed = speed

    def speak(self, text: str, output_file: Optional[str] = None) -> Optional[bytes]:
        """Convert text to speech and play or return audio.

        Args:
            text: Text to speak.
            output_file: If provided, save to file. Otherwise play directly.

        Returns:
            Audio bytes if output_file is None and status is success.
        """
        try:
            import edge_tts

            communicate = edge_tts.Communicate(
                text,
                self.voice,
                rate=f"{'+' if self.speed >= 1 else ''}{int((self.speed - 1) * 100)}%",
            )

            if output_file:
                asyncio.run(self._save_to_file(communicate, output_file))
                return None
            else:
                return asyncio.run(self._collect_audio(communicate))
        except ImportError:
            print("[OCVoice] edge-tts not installed. Install with: pip install edge-tts")
            return None
        except Exception as e:
            print(f"[OCVoice] Edge TTS error: {e}")
            return None

    async def _save_to_file(self, communicate, output_file: str):
        """Save TTS audio to file."""
        await communicate.save(output_file)

    async def _collect_audio(self, communicate) -> bytes:
        """Collect TTS audio into bytes."""
        audio_chunks = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])
        return b"".join(audio_chunks)


class PiperTTS:
    """Text-to-Speech using Piper TTS (offline).

    Piper is a fast, local neural TTS system. Requires downloading
    voice models from https://github.com/rhasspy/piper.
    """

    def __init__(
        self,
        model_path: str = "",
        voice: str = "en_US-lessac-medium",
        speed: float = 1.0,
    ):
        self.model_path = model_path
        self.voice = voice
        self.speed = speed

    def speak(self, text: str) -> Optional[bytes]:
        """Convert text to speech using Piper.

        Returns audio as WAV bytes.
        """
        try:
            import subprocess
            import sys

            piper_path = self._find_piper()
            if not piper_path:
                print("[OCVoice] Piper not found. Install from https://github.com/rhasspy/piper")
                return None

            # Find voice model
            model_path = self._find_model()
            if not model_path:
                print(f"[OCVoice] Piper voice model not found: {self.voice}")
                return None

            # Run piper
            cmd = [
                piper_path,
                "--model", model_path,
                "--output-raw",
            ]
            if self.speed != 1.0:
                cmd.extend(["--length-scale", str(1.0 / self.speed)])

            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = process.communicate(input=text.encode("utf-8"))
            return stdout
        except Exception as e:
            print(f"[OCVoice] Piper TTS error: {e}")
            return None

    def _find_piper(self) -> Optional[str]:
        """Find piper executable."""
        # Check PATH
        import shutil
        piper = shutil.which("piper")
        if piper:
            return piper

        # Check common locations
        candidates = [
            Path.home() / ".local" / "bin" / "piper",
            Path("/usr/local/bin/piper"),
        ]
        for c in candidates:
            if c.exists():
                return str(c)
        return None

    def _find_model(self) -> Optional[str]:
        """Find voice model file."""
        if self.model_path and Path(self.model_path).exists():
            return self.model_path

        # Search in cache
        cache_dirs = [
            Path.home() / ".cache" / "piper",
            Path.home() / ".local" / "share" / "piper",
        ]
        for d in cache_dirs:
            if d.exists():
                onnx = d / f"{self.voice}.onnx"
                if onnx.exists():
                    return str(onnx)
        return None


class TextToSpeech:
    """Unified TTS interface with auto language detection."""

    def __init__(
        self,
        backend: str = "edge",
        voice_ru: str = "ru-RU-SvetlanaNeural",
        voice_en: str = "en-US-JennyNeural",
        speed: float = 1.0,
        read_code: bool = False,
        max_length: int = 500,
    ):
        self.backend = backend
        self.voice_ru = voice_ru
        self.voice_en = voice_en
        self.speed = speed
        self.read_code = read_code
        self.max_length = max_length

    def speak(self, text: str, language: str = "auto"):
        """Convert text to speech and play it."""
        if not text or not text.strip():
            return

        # Clean text for speech
        text = self._clean_text(text)

        # Truncate very long responses
        if len(text) > self.max_length:
            text = text[:self.max_length].rsplit('. ', 1)[0] + "."

        if not text.strip():
            return

        # Detect language
        if language == "auto":
            language = self._detect_language(text)

        # Choose voice
        if language == "ru":
            voice = self.voice_ru
        else:
            voice = self.voice_en

        # Speak
        if self.backend == "edge":
            tts = EdgeTTS(voice=voice, speed=self.speed)
            audio = tts.speak(text)
            if audio:
                self._play_audio(audio)
        elif self.backend == "piper":
            tts = PiperTTS(voice="ru_RU-ruslan-medium" if language == "ru" else "en_US-lessac-medium")
            audio = tts.speak(text)
            if audio:
                self._play_audio(audio)

    def _detect_language(self, text: str) -> str:
        """Simple language detection based on character set."""
        russian_chars = sum(1 for c in text if 'а' <= c.lower() <= 'я')
        if russian_chars > len(text) * 0.3:
            return "ru"
        return "en"

    def _clean_text(self, text: str) -> str:
        """Prepare text for speech: strip code, formatting, symbols."""
        import re

        # 1. Remove code blocks (```...```)
        if not self.read_code:
            text = re.sub(r'```[\s\S]*?```', '', text)
            text = re.sub(r'~~~[\s\S]*?~~~', '', text)

        # 1b. Remove indented code blocks (4+ spaces at line start, multi-line)
        if not self.read_code:
            text = re.sub(r'(?:^[ \t]{4,}.*\n?)+', '', text, flags=re.MULTILINE)

        # 2. Remove inline `code` (replace with its content)
        text = re.sub(r'`([^`]+)`', r'\1', text)

        # 3. Remove markdown links: [text](url) → text
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)

        # 4. Remove images: ![alt](url)
        text = re.sub(r'!\[([^\]]*)\]\([^)]+\)', '', text)

        # 5. Remove bold/italic: **text**, *text*, ~~text~~
        text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
        text = re.sub(r'~~([^~]+)~~', r'\1', text)

        # 6. Remove markdown headers
        text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)

        # 7. Remove horizontal rules
        text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)

        # 8. Remove diff markers (+ , -) at line starts
        text = re.sub(r'^[+\-]\s', '', text, flags=re.MULTILINE)

        # 9. Remove shell prompt markers
        text = re.sub(r'^\$\s', '', text, flags=re.MULTILINE)
        text = re.sub(r'^>\s', '', text, flags=re.MULTILINE)

        # 10. Remove ASCII arrows and special chars that TTS mangles
        text = re.sub(r'\s*→\s*', ' ', text)
        text = re.sub(r'\s*=>\s*', ' ', text)
        text = re.sub(r'\s*==>\s*', ' ', text)
        text = re.sub(r'\s*\|-\s*', '', text)

        # 11. Remove bullet points (-, *, + at line starts)
        text = re.sub(r'^[\s]*[-*+]\s+', '', text, flags=re.MULTILINE)

        # 12. Remove numbered list markers (1. 2. etc)
        text = re.sub(r'^\s*\d+[.)]\s+', '', text, flags=re.MULTILINE)

        # 13. Collapse multiple newlines
        text = re.sub(r'\n{3,}', '\n\n', text)

        # 14. Collapse multiple spaces
        text = re.sub(r'[ \t]+', ' ', text)

        # 15. Remove lines that are just symbols after cleaning
        lines = [l for l in text.split('\n') if l.strip()]
        text = '\n'.join(lines)

        return text.strip()

    def _play_audio(self, audio: bytes):
        """Play WAV audio bytes."""
        try:
            # Write to temp file and play
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio)
                tmp_path = f.name

            self._play_file(tmp_path)
            os.unlink(tmp_path)
        except Exception as e:
            print(f"[OCVoice] Audio playback error: {e}")

    @staticmethod
    def _play_file(path: str):
        """Play an audio file using the best available method."""
        # Try sounddevice first
        try:
            import soundfile as sf
            import sounddevice as sd
            data, sr = sf.read(path)
            sd.play(data, sr)
            sd.wait()
            return
        except ImportError:
            pass

        # Platform-specific fallbacks
        import platform
        system = platform.system()

        if system == "Darwin":
            os.system(f"afplay '{path}' &")
        elif system == "Linux":
            os.system(f"aplay '{path}' &" if os.path.exists("/usr/bin/aplay") else f"paplay '{path}' &")
        elif system == "Windows":
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME)
