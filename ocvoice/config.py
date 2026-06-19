"""Configuration management for OCVoice.

Loads config from multiple locations with precedence:
1. Default config (bundled with package)
2. ~/.config/ocvoice/config.toml (user overrides)
3. Environment variables (OCVOICE_*)
"""

import os
import sys
from pathlib import Path

_HAS_TOML = True
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        _HAS_TOML = False


DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config.toml"
USER_CONFIG_DIR = Path.home() / ".config" / "ocvoice"
USER_CONFIG_PATH = USER_CONFIG_DIR / "config.toml"

DEFAULT_CONFIG = """[audio]
device_id = 0
sample_rate = 16000
channels = 1
chunk_size = 1024

[voice]
mode = "wake_word"
wake_words = ["окей код", "hey code"]
wake_sensitivity = 0.5
silence_timeout = 2.0
max_duration = 10.0
language = "ru"
send_phrases = ["отправь", "отправляй", "отправить", "send", "go", "done"]

[speech.stt]
backend = "auto"
local_model = "base"
local_device = "cpu"
local_compute_type = "default"
api_key = ""
fallback_to_api = true

[speech.speaker]
enabled = true
threshold = 0.75
enrollments_dir = ""

[speech.tts]
enabled = true
backend = "edge"
voice_ru = "ru-RU-SvetlanaNeural"
voice_en = "en-US-JennyNeural"
speed = 1.0

[opencode]
host = "127.0.0.1"
port = 4096
auto_start = true
default_model = "anthropic/claude-sonnet-4-5"
default_agent = "build"
binary_path = ""

[intent]
parser = "regex"
confidence_threshold = 0.7

[ui.tray]
enabled = false
show_notifications = true
sound_feedback = true
"""


def _parse_toml(content: str) -> dict:
    """Parse TOML content, returns empty dict on failure."""
    if not _HAS_TOML:
        print("Warning: tomli/tomllib not available, using default config", file=sys.stderr)
        return {}
    try:
        return tomllib.loads(content)
    except Exception as e:
        print(f"Warning: failed to parse TOML config: {e}", file=sys.stderr)
        return {}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _env_overrides(config: dict) -> dict:
    """Apply environment variable overrides (OCVOICE_ prefix)."""
    env_map = {
        "OCVOICE_AUDIO_DEVICE": ("audio", "device_id", int),
        "OCVOICE_VOICE_MODE": ("voice", "mode", str),
        "OCVOICE_STT_BACKEND": ("speech", "stt", "backend", str),
        "OCVOICE_STT_LOCAL_MODEL": ("speech", "stt", "local_model", str),
        "OCVOICE_STT_API_KEY": ("speech", "stt", "api_key", str),
        "OCVOICE_SPEAKER_ENABLED": ("speech", "speaker", "enabled", lambda v: v.lower() in ("true", "1", "yes")),
        "OCVOICE_SPEAKER_THRESHOLD": ("speech", "speaker", "threshold", float),
        "OCVOICE_TTS_ENABLED": ("speech", "tts", "enabled", lambda v: v.lower() in ("true", "1", "yes")),
        "OCVOICE_OPENCODE_HOST": ("opencode", "host", str),
        "OCVOICE_OPENCODE_PORT": ("opencode", "port", int),
        "OCVOICE_OPENCODE_AUTO_START": ("opencode", "auto_start", lambda v: v.lower() in ("true", "1", "yes")),
        "OCVOICE_OPENCODE_MODEL": ("opencode", "default_model", str),
        "OCVOICE_OPENCODE_AGENT": ("opencode", "default_agent", str),
        "OCVOICE_HEADLESS": ("ui", "headless", lambda v: v.lower() in ("true", "1", "yes")),
    }

    for env_var, path in env_map.items():
        value = os.environ.get(env_var)
        if value is not None:
            try:
                # path is (section, key, converter) — converter is last
                # path[:-2] = sections to traverse, path[-2] = key to set
                converter = path[-1]
                key = path[-2]
                converted = converter(value) if callable(converter) else value
                d = config
                for section in path[:-2]:
                    if section not in d:
                        d[section] = {}
                    d = d[section]
                d[key] = converted
            except (ValueError, KeyError):
                pass

    return config


class Config:
    """OCVoice configuration with attribute-style access."""

    def __init__(self, config_path: str | None = None):
        self._data = self._load(config_path)

    def _load(self, config_path: str | None) -> dict:
        # 1. Start with defaults
        data = _parse_toml(DEFAULT_CONFIG)

        # 2. Bundled config (if exists)
        if DEFAULT_CONFIG_PATH.exists():
            bundled = _parse_toml(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
            data = _deep_merge(data, bundled)

        # 3. User config
        user_path = Path(config_path) if config_path else USER_CONFIG_PATH
        if user_path.exists():
            user = _parse_toml(user_path.read_text(encoding="utf-8"))
            data = _deep_merge(data, user)

        # 4. Environment overrides
        data = _env_overrides(data)

        return data

    def get(self, *keys: str, default=None):
        """Get a nested config value by key path."""
        d = self._data
        for key in keys:
            if isinstance(d, dict):
                d = d.get(key)
            else:
                return default
            if d is None:
                return default
        return d

    def set(self, *keys, value):
        """Set a nested config value and save to user config file."""
        d = self._data
        for key in keys[:-1]:
            if key not in d or not isinstance(d[key], dict):
                d[key] = {}
            d = d[key]
        d[keys[-1]] = value
        self._save()

    def _save(self):
        """Write current config to user config file."""
        USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        lines = []
        for section, values in self._data.items():
            if isinstance(values, dict):
                lines.append(f"[{section}]")
                for key, val in values.items():
                    if isinstance(val, dict):
                        continue
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
        USER_CONFIG_PATH.write_text("\n".join(lines))

    # Convenience properties
    @property
    def audio_device(self) -> int: return self.get("audio", "device_id", default=1)

    @property
    def audio_sample_rate(self) -> int: return self.get("audio", "sample_rate", default=16000)

    @property
    def audio_channels(self) -> int: return self.get("audio", "channels", default=1)

    @property
    def audio_chunk_size(self) -> int: return self.get("audio", "chunk_size", default=1024)

    @property
    def voice_mode(self) -> str: return self.get("voice", "mode", default="wake_word")

    @property
    def wake_words(self) -> list: return self.get("voice", "wake_words", default=["окей код", "hey code"])

    @property
    def wake_sensitivity(self) -> float: return self.get("voice", "wake_sensitivity", default=0.5)

    @property
    def silence_timeout(self) -> float: return self.get("voice", "silence_timeout", default=1.5)

    @property
    def max_duration(self) -> float: return self.get("voice", "max_duration", default=15.0)

    @property
    def language(self) -> str: return self.get("voice", "language", default="ru")

    @property
    def send_phrases(self) -> list: return self.get("voice", "send_phrases", default=["отправь", "отправляй", "отправить", "send", "go", "done"])

    @property
    def stt_backend(self) -> str: return self.get("speech", "stt", "backend", default="auto")

    @property
    def stt_local_model(self) -> str: return self.get("speech", "stt", "local_model", default="base")

    @property
    def stt_local_device(self) -> str: return self.get("speech", "stt", "local_device", default="cpu")

    @property
    def stt_local_compute_type(self) -> str: return self.get("speech", "stt", "local_compute_type", default="default")

    @property
    def stt_api_key(self) -> str: return self.get("speech", "stt", "api_key", default="") or os.environ.get("OPENAI_API_KEY", "")

    @property
    def stt_fallback_to_api(self) -> bool: return self.get("speech", "stt", "fallback_to_api", default=True)

    @property
    def speaker_enabled(self) -> bool: return self.get("speech", "speaker", "enabled", default=True)

    @property
    def speaker_threshold(self) -> float: return self.get("speech", "speaker", "threshold", default=0.5)

    @property
    def speaker_enrollments_dir(self) -> str:
        d = self.get("speech", "speaker", "enrollments_dir", default="")
        return d if d else str(USER_CONFIG_DIR / "enrollments")

    @property
    def tts_enabled(self) -> bool: return self.get("speech", "tts", "enabled", default=True)

    @property
    def tts_backend(self) -> str: return self.get("speech", "tts", "backend", default="edge")

    @property
    def tts_voice_ru(self) -> str: return self.get("speech", "tts", "voice_ru", default="ru-RU-SvetlanaNeural")

    @property
    def tts_voice_en(self) -> str: return self.get("speech", "tts", "voice_en", default="en-US-JennyNeural")

    @property
    def tts_speed(self) -> float: return self.get("speech", "tts", "speed", default=1.0)

    @property
    def opencode_host(self) -> str: return self.get("opencode", "host", default="127.0.0.1")

    @property
    def opencode_port(self) -> int: return self.get("opencode", "port", default=4096)

    @property
    def opencode_auto_start(self) -> bool: return self.get("opencode", "auto_start", default=True)

    @property
    def opencode_default_model(self) -> str: return self.get("opencode", "default_model", default="anthropic/claude-sonnet-4-5")

    @property
    def opencode_default_agent(self) -> str: return self.get("opencode", "default_agent", default="build")

    @property
    def opencode_binary_path(self) -> str: return self.get("opencode", "binary_path", default="") or "opencode"

    @property
    def intent_parser(self) -> str: return self.get("intent", "parser", default="regex")

    @property
    def intent_confidence_threshold(self) -> float: return self.get("intent", "confidence_threshold", default=0.7)

    @property
    def tray_enabled(self) -> bool: return self.get("ui", "tray", "enabled", default=True)

    @property
    def tray_notifications(self) -> bool: return self.get("ui", "tray", "show_notifications", default=True)

    @property
    def tray_sound_feedback(self) -> bool: return self.get("ui", "tray", "sound_feedback", default=True)

    @property
    def headless(self) -> bool: return self.get("ui", "headless", default=False)

    @property
    def opencode_base_url(self) -> str:
        return f"http://{self.opencode_host}:{self.opencode_port}"
