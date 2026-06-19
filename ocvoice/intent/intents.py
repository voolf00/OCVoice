"""Intent definitions for OCVoice.

Maps recognized voice commands to intents that drive OpenCode API calls.
Support for both Russian and English commands.
"""

from enum import Enum
from typing import Optional


class Intent(str, Enum):
    """Known voice command intents."""

    # Session management
    NEW_SESSION = "new_session"
    CONTINUE_SESSION = "continue_session"
    LIST_SESSIONS = "list_sessions"
    SWITCH_SESSION = "switch_session"
    SELECT_LAST_SESSION = "select_last_session"

    # Project management
    SWITCH_PROJECT = "switch_project"
    CURRENT_PROJECT = "current_project"
    LIST_PROJECTS = "list_projects"

    # Session info
    CURRENT_SESSION = "current_session"

    # Discovery
    REDISCOVER = "rediscover"

    # Model & agent configuration
    SWITCH_MODEL = "switch_model"
    SWITCH_AGENT = "switch_agent"
    TOGGLE_THINKING = "toggle_thinking"
    SWITCH_MODE = "switch_mode"  # plan / build

    # Communication
    SEND_MESSAGE = "send_message"
    EXECUTE_COMMAND = "execute_command"
    RUN_SHELL = "run_shell"

    # Voice control
    STOP_LISTENING = "stop_listening"
    START_LISTENING = "start_listening"
    TOGGLE_VOICE = "toggle_voice"

    # OpenCode actions
    UNDO = "undo"
    REDO = "redo"
    COMPACT = "compact"
    SHARE = "share"

    # Unknown
    UNKNOWN = "unknown"


# ─── Intent patterns (regex + keywords) ───

INTENT_PATTERNS_RU = [
    # Session management
    (Intent.NEW_SESSION, [
        r"новая\s+сессия",
        r"создай\s+сессию",
        r"начни\s+(новую\s+)?сессию",
        r"открой\s+сессию",
        r"новая\s+задача",
        r"новый\s+чат",
        r"чистая\s+сессия",
        r"сбрось\s+сессию",
    ]),
    (Intent.CONTINUE_SESSION, [
        r"продолжи\s+сессию",
        r"вернись\s+к\s+сессии",
        r"открой\s+прошлую\s+сессию",
        r"предыдущая\s+сессия",
    ]),
    (Intent.LIST_SESSIONS, [
        r"покажи\s+сессии",
        r"список\s+сессий",
        r"какие\s+сессии",
        r"все\s+сессии",
        r"мои\s+сессии",
    ]),
    (Intent.SWITCH_SESSION, [
        r"(?:работай|переключись)\s+(?:с|на|со)\s+сесси(?:ей|ю|и)\s+(.+)",
        r"используй\s+сессию\s+(.+)",
        r"выбери\s+сессию\s+(.+)",
        r"открой\s+сессию\s+(.+)",
    ]),
    (Intent.SELECT_LAST_SESSION, [
        r"последняя\s+сессия",
        r"свежая\s+сессия",
        r"вернись\s+(?:к\s+)?последней",
        r"вернись\s+назад",
        r"последний\s+чат",
    ]),
    (Intent.CURRENT_SESSION, [
        r"какая\s+сессия",
        r"текущая\s+сессия",
        r"что\s+за\s+сессия",
        r"где\s+я\s+сейчас",
        r"покажи\s+сессию",
    ]),

    # Project
    (Intent.CURRENT_PROJECT, [
        r"какой\s+проект",
        r"текущий\s+проект",
        r"что\s+за\s+проект",
        r"где\s+я",
        r"покажи\s+проект",
    ]),
    (Intent.LIST_PROJECTS, [
        r"список\s+проектов",
        r"какие\s+проекты",
        r"все\s+проекты",
        r"мои\s+проекты",
    ]),
    (Intent.SWITCH_PROJECT, [
        r"переключи(?:сь)?\s+(?:на\s+)?проект\s+(.+)",
        r"переключи(?:сь)?\s+(?:на\s+)?проекта\s+(.+)",
        r"открой\s+проект\s+(.+)",
        r"смени\s+проект\s+(?:на\s+)?(.+)",
        r"работай\s+(?:в|с|над)\s+проект(?:ом|е)?\s+(.+)",
        r"перейди\s+(?:в|на)\s+проект\s+(.+)",
    ]),
    (Intent.REDISCOVER, [
        r"найди\s+сервер",
        r"найдите\s+сервер",
        r"переподключись",
        r"обнови\s+соединение",
        r"пересканируй",
        r"найди\s+проекты",
        r"найдите\s+проекты",
    ]),

    # Model
    (Intent.SWITCH_MODEL, [
        r"смени\s+модель\s+(?:на\s+)?(.+)",
        r"переключи\s+модель\s+(?:на\s+)?(.+)",
        r"используй\s+модель\s+(.+)",
        r"поставь\s+модель\s+(.+)",
        r"модель\s+(.+)",
        r"работай\s+(?:с|через)\s+(?:моделью?|модель)\s+(.+)",
    ]),

    # Agent / Mode
    (Intent.SWITCH_AGENT, [
        r"смени\s+агента\s+(?:на\s+)?(.+)",
        r"переключи\s+агента\s+(?:на\s+)?(.+)",
        r"используй\s+агента\s+(.+)",
        r"агент\s+(.+)",
    ]),
    (Intent.SWITCH_MODE, [
        r"(?:включи|переключи|поставь)\s+(?:режим\s+)?(plan|build|план|код|билд)",
        r"(plan|build|план|билд)\s+mode",
        r"режим\s+(plan|build|план|билд)",
        r"mode\s+(plan|build)",
    ]),

    # Thinking
    (Intent.TOGGLE_THINKING, [
        r"включи\s+(?:режим\s+)?thinking",
        r"отключи\s+(?:режим\s+)?thinking",
        r"включи\s+(?:режим\s+)?думанья",
        r"отключи\s+(?:режим\s+)?думанья",
        r"toggle\s+thinking",
        r"покажи\s+размышления",
        r"скрой\s+размышления",
    ]),

    # Voice control
    (Intent.STOP_LISTENING, [
        r"остановись",
        r"замолчи",
        r"стоп",
        r"хватит",
        r"перестань\s+слушать",
        r"выключи\s+микрофон",
        r"отдохни",
        r"пауза",
    ]),
    (Intent.START_LISTENING, [
        r"продолжи\s+слушать",
        r"начинай\s+слушать",
        r"включи\s+микрофон",
        r"проснись",
        r"слушай",
    ]),
    (Intent.TOGGLE_VOICE, [
        r"включи\s+(?:голосовое\s+)?управление",
        r"отключи\s+(?:голосовое\s+)?управление",
    ]),

    # OpenCode actions
    (Intent.UNDO, [
        r"отмени",
        r"отмена",
        r"undo",
        r"верни\s+(?:как\s+было|назад)",
        r"откати",
    ]),
    (Intent.REDO, [
        r"повтори",
        r"верни\s+отмену",
        r"redo",
        r"вперёд",
    ]),
    (Intent.COMPACT, [
        r"сожми\s+контекст",
        r"суммаризируй",
        r"compact",
        r"очисти\s+контекст",
    ]),
    (Intent.SHARE, [
        r"поделись\s+сессией",
        r"расшарь\s+сессию",
        r"share",
        r"отправь\s+ссылку",
    ]),

    # Execute command
    (Intent.EXECUTE_COMMAND, [
        r"выполни\s+команду\s+(.+)",
        r"запусти\s+команду\s+(.+)",
        r"команда\s+(.+)",
    ]),
    (Intent.RUN_SHELL, [
        r"запусти\s+(?:в\s+терминале\s+)?(.+)",
        r"выполни\s+(?:в\s+терминале\s+)?(.+)",
        r"shell\s+(.+)",
        r"терминал\s+(.+)",
    ]),
]

# Additional patterns matching "спроси / напиши / ask"
# These are handled separately as SEND_MESSAGE intent with the query as content

INTENT_PATTERNS_EN = [
    (Intent.NEW_SESSION, [
        r"new\s+session",
        r"create\s+(?:a\s+)?(?:new\s+)?session",
        r"start\s+(?:a\s+)?(?:new\s+)?session",
        r"fresh\s+session",
        r"clear\s+session",
        r"new\s+chat",
    ]),
    (Intent.CONTINUE_SESSION, [
        r"continue\s+session",
        r"resume\s+session",
        r"open\s+(?:previous|last)\s+session",
        r"go\s+back\s+to\s+session",
    ]),
    (Intent.LIST_SESSIONS, [
        r"list\s+sessions",
        r"show\s+sessions",
        r"what\s+sessions",
        r"all\s+sessions",
        r"my\s+sessions",
    ]),
    (Intent.SWITCH_SESSION, [
        r"(?:switch|change)\s+(?:to\s+)?session\s+(.+)",
        r"work\s+(?:with|on)\s+session\s+(.+)",
        r"use\s+session\s+(.+)",
        r"open\s+session\s+(.+)",
    ]),
    (Intent.SELECT_LAST_SESSION, [
        r"last\s+session",
        r"latest\s+session",
        r"most\s+recent",
        r"go\s+back",
        r"go\s+back\s+to\s+last",
    ]),
    (Intent.CURRENT_SESSION, [
        r"what\s+session",
        r"current\s+session",
        r"show\s+session",
        r"where\s+am\s+i",
    ]),
    (Intent.CURRENT_PROJECT, [
        r"what\s+project",
        r"current\s+project",
        r"where\s+am\s+i",
        r"show\s+project",
    ]),
    (Intent.LIST_PROJECTS, [
        r"list\s+projects",
        r"all\s+projects",
        r"my\s+projects",
    ]),
    (Intent.SWITCH_PROJECT, [
        r"switch\s+(?:to\s+)?project\s+(.+)",
        r"open\s+project\s+(.+)",
        r"change\s+project\s+(?:to\s+)?(.+)",
        r"work\s+(?:on|in)\s+project\s+(.+)",
    ]),
    (Intent.REDISCOVER, [
        r"find\s+server",
        r"rediscover",
        r"rescan",
        r"reconnect",
        r"find\s+projects",
    ]),
    (Intent.SWITCH_MODEL, [
        r"(?:switch|change|use)\s+(?:to\s+)?(?:the\s+)?model\s+(.+)",
        r"set\s+model\s+(?:to\s+)?(.+)",
        r"model\s+(.+)",
    ]),
    (Intent.SWITCH_AGENT, [
        r"(?:switch|change|use)\s+(?:to\s+)?(?:the\s+)?agent\s+(.+)",
        r"set\s+agent\s+(?:to\s+)?(.+)",
        r"agent\s+(.+)",
    ]),
    (Intent.SWITCH_MODE, [
        r"(?:switch\s+to|set|enable|use)\s+(plan|build)\s+mode",
        r"(plan|build)\s+mode",
        r"mode\s+(plan|build)",
    ]),
    (Intent.TOGGLE_THINKING, [
        r"(?:enable|disable|toggle)\s+thinking",
        r"show\s+thinking",
        r"hide\s+thinking",
        r"toggle\s+thoughts",
    ]),
    (Intent.STOP_LISTENING, [
        r"stop\s+listening",
        r"stop",
        r"shut\s+up",
        r"pause",
        r"mute",
        r"go\s+to\s+sleep",
    ]),
    (Intent.START_LISTENING, [
        r"start\s+listening",
        r"wake\s+up",
        r"resume\s+listening",
        r"unmute",
        r"listen",
    ]),
    (Intent.TOGGLE_VOICE, [
        r"enable\s+voice\s+control",
        r"disable\s+voice\s+control",
    ]),
    (Intent.UNDO, [
        r"undo",
        r"revert",
        r"go\s+back",
        r"rollback",
    ]),
    (Intent.REDO, [
        r"redo",
        r"restore",
        r"go\s+forward",
    ]),
    (Intent.COMPACT, [
        r"compact",
        r"summarize",
        r"compress\s+context",
    ]),
    (Intent.SHARE, [
        r"share\s+session",
        r"share",
        r"get\s+link",
    ]),
    (Intent.EXECUTE_COMMAND, [
        r"execute\s+command\s+(.+)",
        r"run\s+command\s+(.+)",
        r"command\s+(.+)",
    ]),
    (Intent.RUN_SHELL, [
        r"run\s+(?:in\s+terminal\s+)?(.+)",
        r"shell\s+(.+)",
        r"terminal\s+(.+)",
    ]),
]

# Trigger phrases for SEND_MESSAGE (anything after these is the message)
MESSAGE_TRIGGERS_RU = [
    "спроси", "напиши", "скажи", "попроси",
    "запроси", "сделай", "найди", "объясни",
    "покажи", "расскажи", "помоги", "исправь",
    "добавь", "удали", "измени", "создай",
    "проверь", "протестируй", "отрефактори",
    "оптимизируй", "почини", "настрой",
    "как", "что", "почему", "где", "когда",
]

MESSAGE_TRIGGERS_EN = [
    "ask", "tell", "say", "write", "explain",
    "show", "find", "search", "create", "make",
    "build", "fix", "add", "remove", "delete",
    "change", "update", "refactor", "optimize",
    "test", "check", "review", "debug",
    "how", "what", "why", "where", "when",
    "can you", "could you", "would you",
    "please", "help", "implement",
]

# End phrases — user says this to trigger sending the message
# Everything before the end phrase is the command
END_PHRASES_RU = [
    "отправь", "отправляй", "отправить",
]

END_PHRASES_EN = [
    "send", "go", "done",
]
