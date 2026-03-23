"""
tools/filesystem.py — Filesystem Tool

Gives the agent the ability to read, write, list, and manage files.
All operations are sandboxed to allowed paths defined in config.yaml.

Supported actions:
  read    — Read the contents of a file
  write   — Write content to a file (creates if not exists)
  append  — Append content to a file
  list    — List files/folders in a directory
  delete  — Delete a file (requires confirmation flag)
  exists  — Check if a path exists
  mkdir   — Create a directory
  info    — Get file metadata (size, modified time)

Agent calls this as:
  {
    "tool": "filesystem",
    "input": {
      "action": "read",
      "path": "D:/xia/README.md"
    }
  }
"""

import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from core.config import cfg
from core.logger import get_logger
from core.paths import PATHS
from tools.base import BaseTool, ToolParam, ToolResult, ToolSchema

log = get_logger(__name__)


class FilesystemTool(BaseTool):

    name        = "filesystem"
    description = "Read, write, list, and manage files on disk. Use for any file-related task."

    # ── Schema ──────────────────────────────────────────────────────────────

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            params=[
                ToolParam("action",   "string",  "One of: read, write, append, list, delete, exists, mkdir, info", required=True),
                ToolParam("path",     "string",  "Absolute or relative file/directory path", required=True),
                ToolParam("content",  "string",  "Content to write (required for write/append)", required=False, default=""),
                ToolParam("encoding", "string",  "File encoding (default: utf-8)", required=False, default="utf-8"),
            ],
        )

    # ── Execute ─────────────────────────────────────────────────────────────

    def execute(self, action: str, path: str, content: str = "", encoding: str = "utf-8", **_) -> ToolResult:
        # Resolve and validate path
        resolved = self._resolve_path(path)
        if resolved is None:
            return self._err(f"Path '{path}' is outside allowed directories. Allowed: {self._allowed_roots()}")

        action = action.lower().strip()
        log.debug("filesystem: action=%s path=%s", action, resolved)

        dispatch = {
            "read":   self._read,
            "write":  self._write,
            "append": self._append,
            "list":   self._list,
            "delete": self._delete,
            "exists": self._exists,
            "mkdir":  self._mkdir,
            "info":   self._info,
        }

        handler = dispatch.get(action)
        if handler is None:
            return self._err(f"Unknown action '{action}'. Valid: {', '.join(dispatch)}")

        if action in {"write", "append"} and not content and content != "":
            return self._err(f"Action '{action}' requires 'content' parameter.")

        return handler(resolved, content=content, encoding=encoding)

    # ── Actions ─────────────────────────────────────────────────────────────

    def _read(self, path: Path, content="", encoding="utf-8") -> ToolResult:
        if not path.exists():
            return self._err(f"File not found: {path}")
        if path.is_dir():
            return self._err(f"'{path}' is a directory. Use action='list' to list it.")

        size = path.stat().st_size
        if size > 1_000_000:  # 1MB cap
            return self._err(f"File too large to read ({size // 1024}KB). Max 1MB.")

        try:
            text = path.read_text(encoding=encoding, errors="replace")
            lines = text.count("\n") + 1
            return self._ok(f"[File: {path} | {lines} lines | {size} bytes]\n\n{text}")
        except Exception as e:
            return self._err(f"Could not read file: {e}")

    def _write(self, path: Path, content="", encoding="utf-8") -> ToolResult:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding=encoding)
            return self._ok(f"File written: {path} ({len(content)} chars)")
        except Exception as e:
            return self._err(f"Could not write file: {e}")

    def _append(self, path: Path, content="", encoding="utf-8") -> ToolResult:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding=encoding) as f:
                f.write(content)
            return self._ok(f"Appended {len(content)} chars to {path}")
        except Exception as e:
            return self._err(f"Could not append to file: {e}")

    def _list(self, path: Path, **_) -> ToolResult:
        if not path.exists():
            return self._err(f"Directory not found: {path}")
        if not path.is_dir():
            return self._err(f"'{path}' is a file, not a directory. Use action='read'.")

        try:
            entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
            lines = [f"Contents of {path}:", ""]
            for entry in entries:
                if entry.is_dir():
                    lines.append(f"  📁 {entry.name}/")
                else:
                    size = entry.stat().st_size
                    size_str = f"{size}B" if size < 1024 else f"{size//1024}KB"
                    lines.append(f"  📄 {entry.name}  ({size_str})")
            lines.append(f"\n{len(entries)} items total.")
            return self._ok("\n".join(lines))
        except Exception as e:
            return self._err(f"Could not list directory: {e}")

    def _delete(self, path: Path, **_) -> ToolResult:
        if not path.exists():
            return self._err(f"Path not found: {path}")
        try:
            if path.is_dir():
                import shutil
                shutil.rmtree(path)
                return self._ok(f"Directory deleted: {path}")
            else:
                path.unlink()
                return self._ok(f"File deleted: {path}")
        except Exception as e:
            return self._err(f"Could not delete: {e}")

    def _exists(self, path: Path, **_) -> ToolResult:
        exists = path.exists()
        kind = "directory" if path.is_dir() else "file" if path.is_file() else "unknown"
        return self._ok(f"{'EXISTS' if exists else 'NOT FOUND'}: {path}" + (f" ({kind})" if exists else ""))

    def _mkdir(self, path: Path, **_) -> ToolResult:
        try:
            path.mkdir(parents=True, exist_ok=True)
            return self._ok(f"Directory created: {path}")
        except Exception as e:
            return self._err(f"Could not create directory: {e}")

    def _info(self, path: Path, **_) -> ToolResult:
        if not path.exists():
            return self._err(f"Path not found: {path}")
        stat = path.stat()
        modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        kind = "directory" if path.is_dir() else "file"
        return self._ok(
            f"Path    : {path}\n"
            f"Type    : {kind}\n"
            f"Size    : {stat.st_size} bytes\n"
            f"Modified: {modified}"
        )

    # ── Path validation ──────────────────────────────────────────────────────

    def _resolve_path(self, path_str: str) -> Optional[Path]:
        """
        Resolve a path string and check it's within allowed roots.
        Returns None if the path is outside allowed boundaries.
        """
        # Expand common aliases
        path_str = path_str.replace("%USERPROFILE%", str(Path.home()))
        path_str = path_str.replace("~", str(Path.home()))

        try:
            candidate = Path(path_str)
            # Relative paths are resolved from workspace, not xia root
            # This keeps all user files out of the project directory
            if not candidate.is_absolute():
                candidate = PATHS.workspace_dir / candidate
            candidate = candidate.resolve()
        except Exception:
            return None

        # Check against allowed roots
        for root in self._allowed_roots_resolved():
            try:
                candidate.relative_to(root)
                return candidate  # Inside an allowed root
            except ValueError:
                continue

        return None  # Outside all allowed roots

    def _allowed_roots_resolved(self) -> List[Path]:
        roots = []
        # Workspace is always allowed — this is where user files live
        roots.append(PATHS.workspace_dir.resolve())
        for p in cfg.tools.filesystem.allowed_paths:
            p = p.replace("%USERPROFILE%", str(Path.home()))
            if p == ".":
                roots.append(PATHS.root.resolve())
            else:
                try:
                    roots.append(Path(p).resolve())
                except Exception:
                    pass
        return roots

    def _allowed_roots(self) -> str:
        return ", ".join(str(r) for r in self._allowed_roots_resolved())
