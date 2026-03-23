"""
tools/terminal.py — Terminal Tool

Gives the agent the ability to run shell commands on the host machine.
Includes safety checks for dangerous commands and a configurable timeout.

The agent calls this as:
  {
    "tool": "terminal",
    "input": {
      "command": "dir D:\\xia",
      "working_dir": "D:\\xia"
    }
  }
"""

import subprocess
import shlex
import sys
from pathlib import Path
from typing import Optional

from core.config import cfg
from core.logger import get_logger
from core.paths import PATHS
from tools.base import BaseTool, ToolParam, ToolResult, ToolSchema

log = get_logger(__name__)

# Hard-blocked commands — never run regardless of config
HARD_BLOCKED = {
    "format", "mkfs", "fdisk", "diskpart",
    "shutdown", "reboot", "halt",
    "reg delete", "regedit",
}


class TerminalTool(BaseTool):

    name        = "terminal"
    description = (
        "Run shell commands on the host machine. "
        "Use for installing packages, running scripts, checking system info, "
        "compiling code, or any command-line task."
    )

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            params=[
                ToolParam("command",     "string", "The shell command to run", required=True),
                ToolParam("working_dir", "string", "Directory to run the command in (default: xia root)", required=False, default="."),
                ToolParam("timeout",     "integer","Seconds before killing the command (default: 30)", required=False, default=30),
            ],
        )

    def execute(
        self,
        command: str,
        working_dir: str = ".",
        timeout: int = None,
        **_,
    ) -> ToolResult:

        timeout = timeout or cfg.tools.terminal.timeout
        command = command.strip()

        if not command:
            return self._err("No command provided.")

        # ── Safety checks ────────────────────────────────────────────────
        blocked = self._check_blocked(command)
        if blocked:
            return self._err(f"Command blocked for safety: '{blocked}'. This command is not permitted.")

        # Warn about dangerous but allowed commands
        dangerous = self._check_dangerous(command)
        if dangerous:
            log.warning("Dangerous command being executed: %s", command)

        # ── Resolve working directory ────────────────────────────────────
        cwd = self._resolve_cwd(working_dir)

        log.info("terminal: running %r in %s (timeout=%ds)", command[:80], cwd, timeout)

        # ── Execute ──────────────────────────────────────────────────────
        try:
            is_windows = sys.platform == "win32"

            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(cwd),
                encoding="utf-8",
                errors="replace",
            )

            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            returncode = result.returncode

            # Build output
            output_parts = []

            if stdout:
                output_parts.append(stdout)

            if stderr:
                # Many programs write info to stderr — include it
                output_parts.append(f"[stderr]\n{stderr}")

            output = "\n".join(output_parts) if output_parts else "(no output)"

            # Cap output length
            if len(output) > 3000:
                output = output[:3000] + f"\n... (truncated, {len(output)} chars total)"

            if returncode == 0:
                return self._ok(
                    f"Command: {command}\n"
                    f"Exit code: 0\n\n"
                    f"{output}"
                )
            else:
                # Non-zero exit — still return as ok so agent can reason about it
                return self._ok(
                    f"Command: {command}\n"
                    f"Exit code: {returncode} (non-zero)\n\n"
                    f"{output}"
                )

        except subprocess.TimeoutExpired:
            return self._err(
                f"Command timed out after {timeout}s: {command}\n"
                "Try increasing timeout or breaking into smaller commands."
            )
        except FileNotFoundError as e:
            return self._err(f"Command not found: {e}")
        except Exception as e:
            return self._err(f"Failed to run command: {e}")

    # ── Safety ───────────────────────────────────────────────────────────────

    def _check_blocked(self, command: str) -> Optional[str]:
        """Return the blocked keyword if found, else None."""
        cmd_lower = command.lower()
        for blocked in HARD_BLOCKED:
            if blocked in cmd_lower:
                return blocked
        return None

    def _check_dangerous(self, command: str) -> Optional[str]:
        """Return the dangerous keyword if found, else None. (Logged but allowed.)"""
        cmd_lower = command.lower()
        for dangerous in cfg.tools.terminal.dangerous_commands:
            if dangerous.lower() in cmd_lower:
                return dangerous
        return None

    def _resolve_cwd(self, working_dir: str) -> Path:
        """Resolve working directory, defaulting to xia root."""
        if not working_dir or working_dir == ".":
            return PATHS.root

        path = Path(working_dir)
        if not path.is_absolute():
            path = PATHS.root / path

        if path.exists() and path.is_dir():
            return path

        log.warning("Working dir not found: %s — using xia root", path)
        return PATHS.root
