"""IPC between CLI and daemon via JSON command file.

@contract: Provides reliable CLI↔daemon communication via file-based IPC
@desc: CLI writes commands to ~/.config/ocvoice/command.json, daemon polls
       and processes them. Commands expire after 10 seconds to prevent stale
       execution. Supports any JSON-serializable command payload.
@tags: ipc, cli, daemon
"""

import json
import time
from pathlib import Path
from typing import Optional

COMMAND_FILE = Path.home() / ".config" / "ocvoice" / "command.json"


def write_command(cmd: str, **kwargs):
    """Write a command to the IPC file for the daemon to pick up."""
    data = {"cmd": cmd, "ts": time.time(), **kwargs}
    COMMAND_FILE.parent.mkdir(parents=True, exist_ok=True)
    COMMAND_FILE.write_text(json.dumps(data, ensure_ascii=False))


def read_command() -> Optional[dict]:
    """Read a pending command from the IPC file. Returns None if none."""
    if not COMMAND_FILE.exists():
        return None
    try:
        data = json.loads(COMMAND_FILE.read_text())
        cmd = data.get('cmd')
        if cmd is None:
            return None
        ts = data.get('ts', 0)
        if time.time() - ts > 10:
            return None
        return data
    except Exception:
        return None


def clear_command():
    """Reset the command file to empty state."""
    try:
        COMMAND_FILE.parent.mkdir(parents=True, exist_ok=True)
        COMMAND_FILE.write_text(json.dumps({"cmd": None}))
    except Exception:
        pass
