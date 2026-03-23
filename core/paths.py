"""
core/paths.py — Single source of truth for all paths in xia.
Drive-letter agnostic — finds itself at runtime.
"""

import os
from pathlib import Path


def _find_xia_root() -> Path:
    if env_root := os.environ.get("XIA_ROOT"):
        return Path(env_root).resolve()
    current = Path(__file__).resolve()
    for parent in [current.parent, current.parent.parent]:
        if (parent / "config.yaml").exists():
            return parent
    return Path.cwd()


class Paths:
    def __init__(self):
        self.root: Path = _find_xia_root()
        self._ensure_dirs()

    # ── Top-level ──────────────────────────────────────────────────────────
    @property
    def config_file(self) -> Path:
        return self.root / "config.yaml"

    @property
    def env_file(self) -> Path:
        return self.root / ".env"

    # ── Workspace — where the agent stores ALL user files ─────────────────
    @property
    def workspace_dir(self) -> Path:
        return self.root / "workspace"

    # ── Data dirs ──────────────────────────────────────────────────────────
    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def conversations_dir(self) -> Path:
        return self.data_dir / "conversations"

    @property
    def embeddings_dir(self) -> Path:
        return self.data_dir / "embeddings"

    @property
    def skills_store_dir(self) -> Path:
        return self.data_dir / "skills_store"

    # ── Module dirs ────────────────────────────────────────────────────────
    @property
    def agent_dir(self) -> Path:
        return self.root / "agent"

    @property
    def tools_dir(self) -> Path:
        return self.root / "tools"

    @property
    def memory_dir(self) -> Path:
        return self.root / "memory"

    @property
    def skills_dir(self) -> Path:
        return self.root / "skills"

    @property
    def models_dir(self) -> Path:
        return self.root / "models"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    # ── Specific files ─────────────────────────────────────────────────────
    @property
    def model_config_file(self) -> Path:
        return self.models_dir / "model_config.yaml"

    @property
    def main_log_file(self) -> Path:
        return self.logs_dir / "xia.log"

    # ── Helpers ────────────────────────────────────────────────────────────
    def relative(self, path: Path) -> Path:
        try:
            return path.relative_to(self.root)
        except ValueError:
            return path

    def _ensure_dirs(self):
        dirs = [
            self.data_dir,
            self.conversations_dir,
            self.embeddings_dir,
            self.skills_store_dir,
            self.logs_dir,
            self.models_dir,
            self.workspace_dir,   # Always ensure workspace exists
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    def __repr__(self) -> str:
        return f"Paths(root={self.root})"


PATHS = Paths()
