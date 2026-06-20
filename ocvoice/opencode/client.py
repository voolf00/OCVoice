"""OpenCode REST API client.

Communicates with a running OpenCode server (opencode serve)
via its HTTP REST API. Handles session management, message
sending, configuration updates, and TUI control.
"""

from typing import Optional
import threading

import httpx


class OpenCodeError(Exception):
    """Raised when an OpenCode API call fails."""
    pass


class OpenCodeClient:
    """Async HTTP client for the OpenCode server REST API."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:4096",
        timeout: float = 120.0,
        auth: tuple = None,
        prefix: str = "/session",
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._auth = auth
        self._client: Optional[httpx.Client] = None
        self._session_id: Optional[str] = None
        self._prefix = prefix.rstrip("/")
        self._lock = threading.Lock()

    @property
    def client(self) -> httpx.Client:
        with self._lock:
            if self._client is None:
                self._client = httpx.Client(
                    base_url=self.base_url,
                    timeout=httpx.Timeout(self.timeout),
                    auth=self._auth,
                )
            return self._client

    def close(self):
        with self._lock:
            if self._client:
                self._client.close()
                self._client = None

    # ─── Health ───

    def health(self) -> dict:
        """Check server health.
        
        In OpenCode >= v1.0 this is /global/health.
        In earlier versions, we probe /session as a connectivity check.
        """
        try:
            # Try the modern endpoint first
            r = self.client.get("/global/health")
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError:
            # Fallback: check /session
            try:
                r = self.client.get("/session")
                if r.status_code == 200:
                    return {"healthy": True, "version": "pre-1.0"}
            except Exception:
                pass
            return {"healthy": False, "error": "health check failed"}
        except httpx.ConnectError:
            return {"healthy": False, "error": "connection refused"}
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    def is_connected(self) -> bool:
        """Check if OpenCode server is reachable."""
        h = self.health()
        return h.get("healthy", False)

    # ─── Projects ───

    def list_projects(self) -> list[dict]:
        """List all projects."""
        r = self.client.get("/project")
        r.raise_for_status()
        return r.json()

    def get_current_project(self) -> dict:
        """Get the current project."""
        r = self.client.get("/project/current")
        r.raise_for_status()
        return r.json()

    # ─── Sessions ───

    def list_sessions(self) -> list[dict]:
        """List all sessions."""
        r = self.client.get("/session")
        r.raise_for_status()
        return r.json()

    def create_session(self, title: str = "OCVoice session") -> dict:
        """Create a new session.

        Returns the session object with its ID.
        """
        r = self.client.post("/session", json={"title": title})
        r.raise_for_status()
        session = r.json()
        self._session_id = session.get("id")
        return session

    def get_session(self, session_id: str = None) -> dict:
        """Get session details."""
        sid = session_id or self._session_id
        if not sid:
            raise OpenCodeError("No session ID")
        r = self.client.get(f"{self._prefix}/{sid}")
        r.raise_for_status()
        return r.json()

    def delete_session(self, session_id: str = None) -> bool:
        """Delete a session."""
        sid = session_id or self._session_id
        if not sid:
            raise OpenCodeError("No session ID")
        r = self.client.delete(f"{self._prefix}/{sid}")
        r.raise_for_status()
        return True

    def update_session(self, title: str = None, session_id: str = None) -> dict:
        """Update session properties (e.g. title for state indication)."""
        sid = session_id or self._session_id
        if not sid:
            raise OpenCodeError("No session ID")
        body = {}
        if title:
            body["title"] = title
        if body:
            r = self.client.patch(f"{self._prefix}/{sid}", json=body)
            r.raise_for_status()
            return r.json()
        return {}

    def fork_session(self, session_id: str = None, message_id: str = None) -> dict:
        """Fork a session at a message."""
        sid = session_id or self._session_id
        if not sid:
            raise OpenCodeError("No session ID")
        body = {}
        if message_id:
            body["messageID"] = message_id
        r = self.client.post(f"{self._prefix}/{sid}/fork", json=body)
        r.raise_for_status()
        return r.json()

    def abort_session(self, session_id: str = None) -> bool:
        """Abort a running session."""
        sid = session_id or self._session_id
        if not sid:
            raise OpenCodeError("No session ID")
        r = self.client.post(f"{self._prefix}/{sid}/abort")
        r.raise_for_status()
        return True

    # ─── Messages ───

    def send_message(
        self,
        text: str,
        session_id: str = None,
        model: str = None,
        agent: str = None,
        no_reply: bool = False,
    ) -> dict:
        """Send a text message to a session and wait for response.

        Args:
            text: The message content.
            session_id: Target session (uses current if None).
            model: Model in provider/model format (e.g. "anthropic/claude-sonnet-4-5").
            agent: Agent name (e.g. "build", "plan").
            no_reply: If True, inject context without waiting for AI response.

        Returns:
            Response dict with info and parts.
        """
        sid = session_id or self._session_id
        if not sid:
            raise OpenCodeError("No session ID. Create a session first.")

        body = {
            "parts": [{"type": "text", "text": text}],
        }

        if model:
            parts = model.split("/", 1)
            body["model"] = {"providerID": parts[0], "modelID": parts[1] if len(parts) > 1 else parts[0]}

        if agent:
            body["agent"] = agent

        if no_reply:
            body["noReply"] = True

        r = self.client.post(f"{self._prefix}/{sid}/message", json=body)
        r.raise_for_status()
        return r.json()

    def send_prompt_async(self, text: str, session_id: str = None, model: str = None, agent: str = None) -> bool:
        """Send a message asynchronously (fire-and-forget)."""
        sid = session_id or self._session_id
        if not sid:
            raise OpenCodeError("No session ID")

        body = {
            "parts": [{"type": "text", "text": text}],
        }
        if model:
            parts = model.split("/", 1)
            body["model"] = {"providerID": parts[0], "modelID": parts[1] if len(parts) > 1 else parts[0]}
        if agent:
            body["agent"] = agent

        r = self.client.post(f"{self._prefix}/{sid}/prompt_async", json=body)
        r.raise_for_status()
        return True

    # ─── Commands ───

    def execute_command(self, command: str, session_id: str = None, agent: str = None) -> dict:
        """Execute a slash command (e.g. /undo, /thinking, /compact).

        Args:
            command: Command name without slash (e.g. "thinking", "undo").
            session_id: Target session.
            agent: Agent to use.

        Returns:
            Response dict.
        """
        sid = session_id or self._session_id
        if not sid:
            raise OpenCodeError("No session ID")

        body = {"command": command, "arguments": ""}
        if agent:
            body["agent"] = agent

        r = self.client.post(f"{self._prefix}/{sid}/command", json=body)
        r.raise_for_status()
        return r.json()

    def run_shell(self, command: str, session_id: str = None, agent: str = None) -> dict:
        """Run a shell command in the session."""
        sid = session_id or self._session_id
        if not sid:
            raise OpenCodeError("No session ID")

        body = {"command": command}
        if agent:
            body["agent"] = agent

        r = self.client.post(f"{self._prefix}/{sid}/shell", json=body)
        r.raise_for_status()
        return r.json()

    # ─── Config ───

    def get_config(self) -> dict:
        """Get current OpenCode configuration."""
        r = self.client.get("/config")
        r.raise_for_status()
        return r.json()

    def update_config(self, config: dict) -> dict:
        """Update OpenCode configuration.

        Note: PATCH /config is not available in all OpenCode versions.
        Falls back gracefully.

        Example:
            client.update_config({"model": "anthropic/claude-sonnet-4-5"})
        """
        try:
            r = self.client.patch("/config", json=config)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # PATCH not supported — config is read-only via API
                # Settings are applied per-message via send_message()
                return {"status": "config_patch_unsupported", "applied": False}
            raise

    def list_models(self) -> list[dict]:
        """List available models from configured providers."""
        r = self.client.get("/config/providers")
        r.raise_for_status()
        return r.json()

    # ─── TUI ───

    def tui_submit_prompt(self) -> bool:
        """Submit the current prompt in TUI."""
        r = self.client.post("/tui/submit-prompt")
        r.raise_for_status()
        return True

    def tui_execute_command(self, command: str) -> bool:
        """Execute a slash command in the TUI."""
        r = self.client.post("/tui/execute-command", json={"command": command})
        r.raise_for_status()
        return True

    def tui_append_prompt(self, text: str) -> bool:
        """Append text to the TUI prompt."""
        r = self.client.post("/tui/append-prompt", json={"text": text})
        r.raise_for_status()
        return True

    def tui_show_toast(self, message: str, variant: str = "info") -> bool:
        """Show a toast notification in the TUI."""
        r = self.client.post("/tui/show-toast", json={
            "message": message,
            "variant": variant,
        })
        r.raise_for_status()
        return True

    # ─── Agents ───

    def list_agents(self) -> list[dict]:
        """List available agents."""
        r = self.client.get("/agent")
        r.raise_for_status()
        return r.json()

    # ─── Session management helpers ───

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    @session_id.setter
    def session_id(self, value: str):
        self._session_id = value


class AsyncOpenCodeClient:
    """Async version of OpenCodeClient using httpx.AsyncClient."""

    def __init__(self, base_url: str = "http://127.0.0.1:4096", timeout: float = 120.0, prefix: str = "/session"):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._session_id: Optional[str] = None
        self._prefix = prefix.rstrip("/")

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def health(self) -> dict:
        try:
            client = await self._get_client()
            r = await client.get("/global/health")
            r.raise_for_status()
            return r.json()
        except httpx.ConnectError:
            return {"healthy": False, "error": "connection refused"}
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    async def is_connected(self) -> bool:
        h = await self.health()
        return h.get("healthy", False)

    async def send_message(self, text: str, session_id: str = None, model: str = None, agent: str = None) -> dict:
        sid = session_id or self._session_id
        if not sid:
            raise OpenCodeError("No session ID")

        body = {"parts": [{"type": "text", "text": text}]}
        if model:
            parts = model.split("/", 1)
            body["model"] = {"providerID": parts[0], "modelID": parts[1] if len(parts) > 1 else parts[0]}
        if agent:
            body["agent"] = agent

        client = await self._get_client()
        r = await client.post(f"{self._prefix}/{sid}/message", json=body)
        r.raise_for_status()
        return r.json()

    async def execute_command(self, command: str, session_id: str = None, agent: str = None) -> dict:
        sid = session_id or self._session_id
        if not sid:
            raise OpenCodeError("No session ID")

        body = {"command": command}
        if agent:
            body["agent"] = agent

        client = await self._get_client()
        r = await client.post(f"{self._prefix}/{sid}/command", json=body)
        r.raise_for_status()
        return r.json()

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    @session_id.setter
    def session_id(self, value: str):
        self._session_id = value
