"""Intent parser — converts transcribed speech to structured commands.

@contract: Parses text → structured ParsedCommand with intent, args, confidence
@desc: Two parsing strategies — regex (fast, offline, rule-based) as default,
       and LLM (via OpenCode) for complex/ambiguous phrases (stub).
       Strips wake words, matches command patterns and message triggers.
@tags: intent, parser, session, project, message, cli
"""

import re
from typing import Optional

from .intents import (
    Intent,
    INTENT_PATTERNS_RU,
    INTENT_PATTERNS_EN,
    MESSAGE_TRIGGERS_RU,
    MESSAGE_TRIGGERS_EN,
)


class ParsedCommand:
    """Result of intent parsing with structured metadata.

    @contract: Always has intent, text, confidence — never partial state
    @desc: Carries the parsed intent enum, cleaned text, extracted arguments,
           confidence score, and original raw text for debugging.
    @tags: intent, parser
    """

    def __init__(
        self,
        intent: Intent,
        text: str = "",
        arguments: dict = None,
        confidence: float = 0.0,
        raw_text: str = "",
    ):
        self.intent = intent
        self.text = text  # Cleaned text / message content
        self.arguments = arguments or {}
        self.confidence = confidence
        self.raw_text = raw_text

    def __repr__(self):
        return (f"ParsedCommand(intent={self.intent.value}, "
                f"text='{self.text[:50]}', confidence={self.confidence:.2f})")


# ─── class RegexIntentParser ───────────────────────────────
# Regex intent parser — RU + EN patterns

class RegexIntentParser:
    """Rule-based intent parser using regex patterns.

    @contract: Always returns a ParsedCommand (defaults to SEND_MESSAGE)
    @desc: Compiles RU/EN regex patterns for known commands, strips wake words,
           falls back to message trigger detection, then defaults to SEND_MESSAGE
           with lower confidence.
    @tags: intent, parser, regex
    """

    def __init__(self, confidence_threshold: float = 0.7, language: str = "auto",
                 wake_words: list[str] | None = None):
        self.threshold = confidence_threshold
        self._language = language
        self._wake_words = wake_words or ["окей код", "hey code"]

        # Compile all patterns
        self._patterns_ru = self._compile(INTENT_PATTERNS_RU)
        self._patterns_en = self._compile(INTENT_PATTERNS_EN)

    def set_language(self, lang: str):
        """Set language for pattern matching: ru, en, or auto."""
        self._language = lang

    def _compile(self, patterns: list) -> list:
        """Compile regex patterns."""
        compiled = []
        for intent, pats in patterns:
            for pat in pats:
                try:
                    compiled.append((intent, re.compile(pat, re.IGNORECASE)))
                except re.error:
                    pass
        return compiled

    def parse(self, text: str) -> ParsedCommand:
        """Parse text into a command.

        @contract: Never raises; returns UNKNOWN intent on empty text
        @param text: Transcribed speech (Russian or English)
        @returns: ParsedCommand with best-guess intent and arguments
        @tags: intent, parser
        """
        text = text.strip().lower()
        if not text:
            return ParsedCommand(Intent.UNKNOWN, raw_text=text)

        # Strip wake words from text
        cleaned = self._strip_wake_words(text)

        # 1. Check explicit command patterns
        command = self._match_patterns(cleaned)
        if command and command.confidence >= self.threshold:
            return command

        # 2. Check message trigger phrases
        command = self._match_message_triggers(cleaned)
        if command:
            return command

        # 3. Default: treat as SEND_MESSAGE
        return ParsedCommand(
            intent=Intent.SEND_MESSAGE,
            text=cleaned,
            raw_text=text,
            confidence=0.5,
        )

# ─── def _strip_wake_words ───────────────────────────────
# Remove дарвин/darwin/okey code from text

    def _strip_wake_words(self, text: str) -> str:
        """Remove known wake words from the text."""
        # Build variants from configured wake words
        wake_phrases = list(self._wake_words)
        for w in self._wake_words:
            wl = w.lower()
            if wl == "дарвин":
                wake_phrases.extend(["дарвин", "darwin", "darvin", "darvine", "dарвин"])
            elif wl == "darwin":
                wake_phrases.extend(["darwin", "дарвин", "darvin", "darvine"])
            elif wl == "окей код":
                wake_phrases.extend(["окей code", "okay code", "эй код", "хей код", "окей", "okay"])
            elif wl == "hey code":
                wake_phrases.extend(["hey code", "эй код", "хей код"])
        wake_phrases = sorted(set(wake_phrases), key=len, reverse=True)
        cleaned = text
        for phrase in wake_phrases:
            cleaned = cleaned.replace(phrase, "").strip()
            cleaned = re.sub(r'\s+', ' ', cleaned)
        return cleaned

    def _match_patterns(self, text: str) -> Optional[ParsedCommand]:
        """Try to match text against known command patterns."""
        best_match = None
        best_length = 0

        patterns = []
        if self._language in ("auto", "ru"):
            patterns += self._patterns_ru
        if self._language in ("auto", "en"):
            patterns += self._patterns_en

        for intent, pattern in patterns:
            match = pattern.search(text)
            if match:
                match_length = len(match.group(0))
                if match_length > best_length:
                    best_length = match_length
                    args = self._extract_args(intent, match)
                    best_match = ParsedCommand(
                        intent=intent,
                        text=args.pop("_text", ""),
                        arguments=args,
                        confidence=0.9,
                        raw_text=text,
                    )

        return best_match

    def _match_message_triggers(self, text: str) -> Optional[ParsedCommand]:
        """Check if text starts with a message trigger phrase."""
        all_triggers = []
        if self._language in ("auto", "ru"):
            all_triggers += MESSAGE_TRIGGERS_RU
        if self._language in ("auto", "en"):
            all_triggers += MESSAGE_TRIGGERS_EN

        # Sort by length (longest first) to match more specific triggers
        for trigger in sorted(all_triggers, key=len, reverse=True):
            if text.startswith(trigger + " ") or text.startswith(trigger + ":"):
                message = text[len(trigger):].strip().lstrip(": ")
                if message:
                    return ParsedCommand(
                        intent=Intent.SEND_MESSAGE,
                        text=message,
                        raw_text=text,
                        confidence=0.85,
                    )

        # Also check if trigger word is in the middle
        for trigger in all_triggers:
            idx = text.find(" " + trigger + " ")
            if idx > 0:
                message = text[idx + len(trigger) + 1:].strip()
                if message:
                    return ParsedCommand(
                        intent=Intent.SEND_MESSAGE,
                        text=message,
                        raw_text=text,
                        confidence=0.7,
                    )

        return None

    def _extract_args(self, intent: Intent, match: re.Match) -> dict:
        """Extract named arguments from regex match."""
        args = match.groupdict().copy()

        # Try to get captured groups
        groups = match.groups()
        group_map = IntentParser.ARGUMENT_NAMES.get(intent, [])

        for i, group in enumerate(groups):
            if group:
                if i < len(group_map):
                    args[group_map[i]] = group.strip()
                else:
                    args["_text"] = group.strip()

        # For SEND_MESSAGE-like intents, extract the text
        if intent in (Intent.SWITCH_PROJECT, Intent.SWITCH_MODEL,
                       Intent.SWITCH_AGENT, Intent.SWITCH_SESSION,
                       Intent.EXECUTE_COMMAND, Intent.RUN_SHELL):
            for i, group in enumerate(groups):
                if group and i == 0:
                    args["_text"] = group.strip()

        return args


# ─── class IntentParser ───────────────────────────────
# Master parser with model/mode alias resolution

class IntentParser:
    """Main intent parser with configurable strategy and alias resolution.

    @contract: Returns normalized ParsedCommand with resolved model/mode aliases
    @desc: Wraps RegexIntentParser, applies normalization (model name aliases,
           mode name resolution, thinking toggle detection). Supports "regex"
           and "llm" parser types.
    @tags: intent, parser, model, agent
    """

    # Maps intents to expected argument names
    ARGUMENT_NAMES = {
        Intent.SWITCH_PROJECT: ["project"],
        Intent.SWITCH_MODEL: ["model"],
        Intent.SWITCH_AGENT: ["agent"],
        Intent.SWITCH_SESSION: ["session"],
        Intent.EXECUTE_COMMAND: ["command"],
        Intent.RUN_SHELL: ["command"],
        Intent.SELECT_LAST_SESSION: [],
    }

    KNOWN_MODELS = {
        # Russian aliases
        "клод": "anthropic/claude-sonnet-4-5",
        "клод сонет": "anthropic/claude-sonnet-4-5",
        "клод опус": "anthropic/claude-opus-4-5",
        "клод хайку": "anthropic/claude-haiku-4-5",
        "джипити": "openai/gpt-5",
        "chatgpt": "openai/gpt-5",
        "гпт": "openai/gpt-5",
        "гемини": "google/gemini-2.5-pro",
        "джемини": "google/gemini-2.5-pro",
        # English aliases
        "claude": "anthropic/claude-sonnet-4-5",
        "sonnet": "anthropic/claude-sonnet-4-5",
        "claude sonnet": "anthropic/claude-sonnet-4-5",
        "opus": "anthropic/claude-opus-4-5",
        "claude opus": "anthropic/claude-opus-4-5",
        "haiku": "anthropic/claude-haiku-4-5",
        "claude haiku": "anthropic/claude-haiku-4-5",
        "gpt": "openai/gpt-5",
        "gpt5": "openai/gpt-5",
        "openai": "openai/gpt-5",
        "gemini": "google/gemini-2.5-pro",
        "deepseek": "deepseek/deepseek-chat",
    }

    def __init__(self, parser_type: str = "regex", confidence_threshold: float = 0.7,
                 language: str = "auto", wake_words: list[str] | None = None):
        self.parser_type = parser_type
        self.regex_parser = RegexIntentParser(confidence_threshold, language=language,
                                              wake_words=wake_words)

    def set_language(self, lang: str):
        """Set language for intent parsing."""
        self.regex_parser.set_language(lang)

    def set_wake_words(self, wake_words: list[str]):
        """Update wake words for stripping."""
        self.regex_parser._wake_words = wake_words

    def parse(self, text: str) -> ParsedCommand:
        """Parse transcribed text into a command."""
        if self.parser_type == "regex":
            command = self.regex_parser.parse(text)
            command = self._normalize(command)
            return command
        else:
            # LLM-based parsing — delegates to OpenCode itself
            return ParsedCommand(
                intent=Intent.SEND_MESSAGE,
                text=text,
                raw_text=text,
                confidence=0.6,
            )

    def _normalize(self, command: ParsedCommand) -> ParsedCommand:
        """Normalize and enhance parsed command.

        - Resolve model aliases to full model IDs
        - Normalize mode names
        """
        if command.intent == Intent.SWITCH_MODEL:
            name = command.text.lower().strip()
            if name in self.KNOWN_MODELS:
                command.arguments["model"] = self.KNOWN_MODELS[name]
            else:
                command.arguments["model"] = command.text.strip()

        elif command.intent == Intent.SWITCH_MODE:
            mode = command.text.lower().strip()
            if mode in ("план", "plan"):
                command.arguments["agent"] = "plan"
            elif mode in ("билд", "build", "код"):
                command.arguments["agent"] = "build"
            else:
                command.arguments["agent"] = mode

        elif command.intent == Intent.TOGGLE_THINKING:
            # Determine enable/disable from raw text
            raw = command.raw_text.lower()
            if any(w in raw for w in ("отключи", "скрой", "disable", "hide", "выключи")):
                command.arguments["enable"] = False
            else:
                command.arguments["enable"] = True

        return command
