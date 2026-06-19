"""OpenCode IDE auto-discovery.

Finds the running OpenCode Desktop IDE or CLI server credentials.
"""

import os
from typing import Optional


class IDEDiscovery:
    """Discovers the OpenCode server credentials."""

    # Common OpenCode server ports — scan wider range
    KNOWN_PORTS = [4096, 59499, 59000, 59001, 59002, 59010, 59020, 59030, 59040, 59050,
                   50455, 50456, 50457, 50458, 50459, 50460, 50450, 50440, 50430]

    def __init__(self):
        self.host = "127.0.0.1"
        self.port: Optional[int] = None
        self.username = "opencode"
        self.password: Optional[str] = None

    def discover(self) -> bool:
        """Try to find the IDE/CLI server. Returns True if found."""
        self.password = os.environ.get("OPENCODE_SERVER_PASSWORD", "") or os.environ.get("OPENCODE_SERVER_PASSWORD", "")
        self.username = os.environ.get("OPENCODE_SERVER_USERNAME", "opencode")

        # Find ports from running OpenCode processes
        live_ports = self._scan_running_ports()
        all_ports = live_ports + self.KNOWN_PORTS

        for port in all_ports:
            if self._try_port(port):
                self.port = port
                return True

        return False

    def _scan_running_ports(self) -> list[int]:
        """Find listening ports from opencode processes (fast targeted lsof)."""
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

    def _try_port(self, port: int) -> bool:
        """Check if port serves opencode API."""
        import httpx
        try:
            url = f"http://{self.host}:{port}/session"
            auth = (self.username, self.password) if self.password else None
            r = httpx.get(url, auth=auth, timeout=2)
            return r.status_code == 200
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
