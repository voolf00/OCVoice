"""OpenCode IDE auto-discovery.

@contract: Finds running OpenCode server via port scanning with prefix detection
@desc: Scans known ports and running process list to discover OpenCode Desktop
       IDE or CLI server. Provides base_url, auth credentials, and API path prefix
       for the client. Probes multiple API paths (/session, /api/session, /) to
       handle Desktop vs TUI server layout differences.
@tags: discovery, network, client
"""

import os
from typing import Optional


class IDEDiscovery:
    """Discovers the OpenCode server credentials and API path prefix.

    @contract: Returns found=True only when a recognized endpoint responds
    @desc: Uses lsof to find ports from running opencode processes, then
           probes known ports. Handles optional HTTP basic auth from env vars.
           Auto-detects the correct API path prefix for Desktop vs TUI.
    @tags: discovery, network
    """

    # Common OpenCode server ports — scan wider range
    KNOWN_PORTS = [4096, 59499, 59000, 59001, 59002, 59010, 59020, 59030, 59040, 59050,
                   50455, 50456, 50457, 50458, 50459, 50460, 50450, 50440, 50430,
                   5000, 8080, 3000, 3001, 5173, 4173]

    # API path prefixes to try — Desktop may use different paths than TUI
    PROBE_PATHS = ["/session", "/api/session", ""]

    def __init__(self):
        self.host = "127.0.0.1"
        self.port: Optional[int] = None
        self.prefix: str = "/session"
        self.username = "opencode"
        self.password: Optional[str] = None

    def discover(self, preferred_port: int = 0) -> bool:
        """Try to find the IDE/CLI server.

        @contract: Sets self.port and self.prefix on success.
                   Prefers Desktop server (port serving HTML UI) over
                   standalone opencode serve instances.
        @param preferred_port: If > 0, try this port first (config override).
        @returns: True if a responding OpenCode server was found
        @tags: discovery, network, config
        """
        pw1 = os.environ.get("OPENCODE_SERVER_PASSWORD", "")
        pw2 = os.environ.get("OPENCODE_PASSWORD", "")
        self.password = pw1 or pw2 or None
        self.username = os.environ.get("OPENCODE_SERVER_USERNAME", "opencode")

        # Find ports from running OpenCode processes
        live_ports = self._scan_running_ports()
        all_ports = list(dict.fromkeys(live_ports + self.KNOWN_PORTS))

        # If preferred port is set, try it first (manual override)
        if preferred_port > 0:
            all_ports = [preferred_port] + [p for p in all_ports if p != preferred_port]

        # Collect ALL responding ports with Desktop detection
        candidates: dict[int, tuple[str, bool]] = {}
        for port in all_ports:
            result = self._try_port(port)
            if result is not None:
                prefix, is_desktop = result
                candidates[port] = (prefix, is_desktop)

        if not candidates:
            return False

        # Prefer Desktop port (serves HTML UI at /)
        desktop_ports = [p for p, (_, d) in candidates.items() if d]
        if desktop_ports:
            self.port = desktop_ports[0]
            self.prefix = candidates[desktop_ports[0]][0]
            print(f"[IDEDiscovery] Found Desktop server at {self.base_url}, prefix='{self.prefix}'", flush=True)
            return True

        # Fallback to any server (standalone opencode serve)
        first_port = next(iter(candidates))
        self.port = first_port
        self.prefix = candidates[first_port][0]
        print(f"[IDEDiscovery] Found server at {self.base_url}, prefix='{self.prefix}'", flush=True)
        return True

    def _scan_running_ports(self) -> list[int]:
        """Find listening ports from opencode processes (fast targeted lsof).

        @returns: Deduplicated list of port numbers from OpenCode processes
        @tags: discovery, network
        """
        ports = []
        try:
            import subprocess
            result = subprocess.run(
                ["lsof", "-iTCP", "-sTCP:LISTEN", "-P", "-n"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.split("\n"):
                if "OpenCode" in line or "opencode" in line.lower():
                    parts = line.split()
                    for part in parts:
                        if ":" in part and "127.0.0.1" in part:
                            port_str = part.split(":")[-1]
                            try:
                                p = int(port_str)
                                if p not in ports:
                                    ports.append(p)
                            except ValueError:
                                pass
        except Exception:
            pass
        return ports

    def _try_port(self, port: int) -> Optional[tuple[str, bool]]:
        """Check if port serves opencode API; returns (prefix, is_desktop) or None.

        @contract: Probes all PROBE_PATHS; detects Desktop by checking if
                   GET / returns HTML (Desktop web UI).
        @param port: Port number to probe
        @returns: Tuple (prefix, is_desktop) or None if no endpoint responds
        @tags: discovery, network
        """
        import httpx
        auth = (self.username, self.password) if self.password else None
        for path in self.PROBE_PATHS:
            try:
                url = f"http://{self.host}:{port}{path}/session" if path else f"http://{self.host}:{port}/session"
                r = httpx.get(url, auth=auth, timeout=1.5)
                if r.status_code == 200:
                    is_desktop = self._is_desktop(port, auth)
                    return (path, is_desktop)
            except Exception:
                continue
            if path:
                try:
                    url_alt = f"http://{self.host}:{port}{path}"
                    r = httpx.get(url_alt, auth=auth, timeout=1.5)
                    if r.status_code == 200:
                        is_desktop = self._is_desktop(port, auth)
                        return (path, is_desktop)
                except Exception:
                    continue
        return None

    def _is_desktop(self, port: int, auth) -> bool:
        """Check if port serves Desktop UI (returns HTML at root /).

        @contract: Returns True if GET / returns HTML content
        @param port: Port number to check
        @param auth: HTTP BasicAuth tuple or None
        @returns: True if port serves Desktop web UI
        @tags: discovery, network
        """
        try:
            import httpx
            r = httpx.get(f"http://{self.host}:{port}/", auth=auth, timeout=2)
            if r.status_code == 200:
                text = r.text.strip().lower()
                return text.startswith('<!doctype html>') or '<html' in text[:200]
            return False
        except Exception:
            return False

    @property
    def found(self) -> bool:
        return self.port is not None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}" if self.port else "http://127.0.0.1:4096"

    @property
    def auth(self) -> Optional[tuple]:
        if self.password:
            return (self.username, self.password)
        return None
