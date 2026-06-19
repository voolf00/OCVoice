"""OpenCode process launcher.

Spawns and manages the opencode serve process.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


class OpenCodeLauncher:
    """Manages the opencode serve process lifecycle."""

    def __init__(
        self,
        binary_path: str = "opencode",
        host: str = "127.0.0.1",
        port: int = 4096,
        working_dir: Optional[str] = None,
    ):
        self.binary_path = binary_path
        self.host = host
        self.port = port
        self.working_dir = working_dir or os.getcwd()

        self._process: Optional[subprocess.Popen] = None
        self._pid_file = Path.home() / ".config" / "ocvoice" / "opencode.pid"

    def start(self, timeout: float = 30.0) -> bool:
        """Start opencode serve.

        Args:
            timeout: Maximum time to wait for server to be ready.

        Returns:
            True if server started successfully.
        """
        if self.is_running():
            print("[OCVoice] OpenCode server already running")
            return True

        # Ensure pid directory
        self._pid_file.parent.mkdir(parents=True, exist_ok=True)

        # Build command
        cmd = [
            self.binary_path,
            "serve",
            "--port", str(self.port),
            "--hostname", self.host,
        ]

        print(f"[OCVoice] Starting OpenCode: {' '.join(cmd)}")
        print(f"[OCVoice] Working directory: {self.working_dir}")

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.working_dir,
                text=True,
            )

            # Save PID
            self._pid_file.write_text(str(self._process.pid))

            # Wait for server to be ready
            return self._wait_ready(timeout)

        except FileNotFoundError:
            print(f"[OCVoice] ERROR: '{self.binary_path}' not found. Is OpenCode installed?")
            return False
        except Exception as e:
            print(f"[OCVoice] ERROR: Failed to start OpenCode: {e}")
            return False

    def stop(self, timeout: float = 5.0):
        """Stop the opencode serve process."""
        if self._process:
            print("[OCVoice] Stopping OpenCode server...")
            self._process.send_signal(signal.SIGTERM)
            try:
                self._process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
            self._process = None

        # Also try by PID file
        if self._pid_file.exists():
            try:
                pid = int(self._pid_file.read_text().strip())
                if sys.platform == "win32":
                    os.kill(pid, signal.SIGTERM)
                else:
                    os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, ValueError, OSError):
                pass
            self._pid_file.unlink(missing_ok=True)

    def is_running(self) -> bool:
        """Check if opencode serve is running."""
        # Check via PID file
        if self._pid_file.exists():
            try:
                pid = int(self._pid_file.read_text().strip())
                if sys.platform == "win32":
                    # Windows: use tasklist or similar
                    import ctypes
                    kernel32 = ctypes.windll.kernel32
                    handle = kernel32.OpenProcess(0x0400, False, pid)
                    if handle:
                        kernel32.CloseHandle(handle)
                        return True
                else:
                    os.kill(pid, 0)
                    return True
            except (ProcessLookupError, OSError, ValueError):
                pass

        # Check via HTTP
        try:
            import httpx
            r = httpx.get(f"http://{self.host}:{self.port}/global/health", timeout=2.0)
            return r.status_code == 200
        except Exception:
            return False

    def _wait_ready(self, timeout: float) -> bool:
        """Wait for the server health endpoint to respond."""
        deadline = time.time() + timeout

        while time.time() < deadline:
            if self._process and self._process.poll() is not None:
                # Process exited
                stderr = self._process.stderr.read() if self._process.stderr else ""
                print(f"[OCVoice] OpenCode process exited unexpectedly:\n{stderr}")
                return False

            try:
                import httpx
                r = httpx.get(
                    f"http://{self.host}:{self.port}/global/health",
                    timeout=1.0,
                )
                if r.status_code == 200:
                    print("[OCVoice] OpenCode server is ready")
                    return True
            except Exception:
                pass

            time.sleep(0.5)

        print("[OCVoice] Timeout waiting for OpenCode server")
        return False

    def restart(self) -> bool:
        """Restart opencode serve."""
        self.stop()
        time.sleep(1)
        return self.start()
