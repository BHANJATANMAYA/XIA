"""
core/errors.py — Structured Error Types

Custom exceptions with user-friendly messages.
The CLI catches these and displays them cleanly instead of crashing.

Usage:
    from core.errors import XiaError, ModelUnavailableError

    raise ModelUnavailableError("mistral")
    # → "Model 'mistral' is not available. Run: ollama pull mistral"
"""


class XiaError(Exception):
    """Base class for all xia errors."""

    def __init__(self, message: str, fix: str = "", code: str = ""):
        super().__init__(message)
        self.message = message
        self.fix     = fix
        self.code    = code

    def __str__(self) -> str:
        if self.fix:
            return f"{self.message}\n  Fix: {self.fix}"
        return self.message


# ── Specific error types ───────────────────────────────────────────────────────

class ModelUnavailableError(XiaError):
    def __init__(self, model: str):
        super().__init__(
            message=f"Model '{model}' is not available locally",
            fix=f"Run: ollama pull {model}",
            code="MODEL_UNAVAILABLE",
        )


class OllamaNotRunningError(XiaError):
    def __init__(self):
        super().__init__(
            message="Cannot connect to Ollama server at localhost:11434",
            fix="Run launch.bat — it starts Ollama automatically",
            code="OLLAMA_NOT_RUNNING",
        )


class ConfigError(XiaError):
    def __init__(self, detail: str):
        super().__init__(
            message=f"Configuration error: {detail}",
            fix="Check config.yaml for syntax errors or missing values",
            code="CONFIG_ERROR",
        )


class ToolError(XiaError):
    def __init__(self, tool: str, detail: str):
        super().__init__(
            message=f"Tool '{tool}' failed: {detail}",
            code="TOOL_ERROR",
        )


class MemoryError(XiaError):
    def __init__(self, detail: str):
        super().__init__(
            message=f"Memory system error: {detail}",
            fix="Check that ChromaDB is installed: pip install chromadb",
            code="MEMORY_ERROR",
        )


class PathNotAllowedError(XiaError):
    def __init__(self, path: str):
        super().__init__(
            message=f"Path '{path}' is outside allowed directories",
            fix="Use paths inside the workspace folder or configure allowed_paths in config.yaml",
            code="PATH_NOT_ALLOWED",
        )


class DiskSpaceError(XiaError):
    def __init__(self, available_gb: float):
        super().__init__(
            message=f"Insufficient disk space: {available_gb:.1f}GB available",
            fix="Free up space on the SSD",
            code="DISK_SPACE",
        )


# ── Global error handler ───────────────────────────────────────────────────────

def handle_error(error: Exception, renderer=None) -> bool:
    """
    Handle any exception gracefully.
    Returns True if handled, False if it should propagate.

    If renderer is provided, prints a rich error message.
    Otherwise prints to stderr.
    """
    from core.logger import get_logger
    log = get_logger("core.errors")

    if isinstance(error, XiaError):
        log.error("[%s] %s", error.code or "XIA_ERROR", error.message)
        if renderer:
            renderer.error(error.message)
            if error.fix:
                renderer.info(f"Fix: {error.fix}")
        else:
            print(f"\n  Error: {error.message}", file=__import__("sys").stderr)
            if error.fix:
                print(f"  Fix: {error.fix}", file=__import__("sys").stderr)
        return True

    elif isinstance(error, KeyboardInterrupt):
        return False  # Let it propagate for clean shutdown

    else:
        log.exception("Unhandled exception")
        if renderer:
            renderer.error(f"Unexpected error: {error}")
            renderer.info("Check logs/xia.log for details")
        else:
            print(f"\n  Unexpected error: {error}", file=__import__("sys").stderr)
        return True
