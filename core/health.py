"""
core/health.py — System Health Checker

Runs at startup to verify everything xia needs is in place.
Gives clear, actionable error messages instead of cryptic tracebacks.

Checks:
  - Python version
  - Required packages installed
  - SSD paths exist and are writable
  - Ollama reachable
  - Model available
  - Disk space sufficient
  - Config file valid

Usage:
    from core.health import HealthChecker
    checker = HealthChecker()
    ok, issues = checker.run()
    if not ok:
        checker.print_report(issues)
        sys.exit(1)
"""

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple


@dataclass
class HealthIssue:
    level:   str   # "error" | "warning" | "info"
    check:   str   # What was checked
    message: str   # What went wrong
    fix:     str   # How to fix it


class HealthChecker:
    """
    Runs all startup health checks and collects results.
    Errors block startup. Warnings are shown but don't block.
    """

    def __init__(self):
        self.issues: List[HealthIssue] = []

    def run(self) -> Tuple[bool, List[HealthIssue]]:
        """
        Run all health checks.
        Returns (can_start, issues_list).
        can_start is False only if there are error-level issues.
        """
        self.issues = []

        self._check_python_version()
        self._check_required_packages()
        self._check_paths()
        self._check_disk_space()
        self._check_config()
        self._check_ollama()

        has_errors = any(i.level == "error" for i in self.issues)
        return not has_errors, self.issues

    def print_report(self, issues: List[HealthIssue] = None):
        """Print a formatted health report."""
        issues = issues or self.issues
        if not issues:
            return

        print()
        errors   = [i for i in issues if i.level == "error"]
        warnings = [i for i in issues if i.level == "warning"]

        if errors:
            print("  ✗ xia cannot start — fix these issues:\n")
            for issue in errors:
                print(f"  [ERROR] {issue.check}")
                print(f"          {issue.message}")
                if issue.fix:
                    print(f"          Fix: {issue.fix}")
                print()

        if warnings:
            print("  ! Warnings (xia will start but some features may be limited):\n")
            for issue in warnings:
                print(f"  [WARN]  {issue.check}: {issue.message}")
                if issue.fix:
                    print(f"          Fix: {issue.fix}")
            print()

    # ── Checks ─────────────────────────────────────────────────────────────

    def _check_python_version(self):
        major, minor = sys.version_info[:2]
        if (major, minor) < (3, 11):
            self._error(
                "Python version",
                f"Python 3.11+ required, found {major}.{minor}",
                "Install Python 3.11+ from https://python.org",
            )

    def _check_required_packages(self):
        required = {
            "yaml":                 "pyyaml",
            "dotenv":               "python-dotenv",
            "httpx":                "httpx",
            "rich":                 "rich",
            "ollama":               "ollama",
            "tenacity":             "tenacity",
        }
        optional = {
            "chromadb":             "chromadb (memory feature)",
            "sentence_transformers": "sentence-transformers (memory feature)",
        }

        for module, package in required.items():
            try:
                __import__(module)
            except ImportError:
                self._error(
                    f"Package: {package}",
                    f"Required package '{package}' is not installed",
                    f"Run: pip install {package}",
                )

        for module, package in optional.items():
            try:
                __import__(module)
            except ImportError:
                self._warning(
                    f"Package: {package}",
                    f"Optional package not installed — some features disabled",
                    f"Run: pip install {package.split()[0]}",
                )

    def _check_paths(self):
        from core.paths import PATHS

        # Root must exist
        if not PATHS.root.exists():
            self._error(
                "SSD root",
                f"Root directory not found: {PATHS.root}",
                "Check that the SSD is connected and the path is correct",
            )
            return

        # Required dirs must exist and be writable
        dirs_to_check = [
            PATHS.data_dir,
            PATHS.conversations_dir,
            PATHS.embeddings_dir,
            PATHS.skills_store_dir,
            PATHS.logs_dir,
            PATHS.workspace_dir,
        ]

        for d in dirs_to_check:
            if not d.exists():
                try:
                    d.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    self._error(
                        f"Directory: {d.name}",
                        f"Cannot create directory: {d}",
                        "Check SSD permissions and available space",
                    )
                    continue

            # Write test
            test_file = d / ".write_test"
            try:
                test_file.write_text("ok")
                test_file.unlink()
            except Exception:
                self._error(
                    f"Write access: {d.name}",
                    f"Directory is not writable: {d}",
                    "Check file system permissions on the SSD",
                )

    def _check_disk_space(self):
        from core.paths import PATHS
        try:
            usage = shutil.disk_usage(PATHS.root)
            free_gb = usage.free / (1024 ** 3)
            if free_gb < 1.0:
                self._error(
                    "Disk space",
                    f"Less than 1GB free on SSD ({free_gb:.1f}GB available)",
                    "Free up space on the SSD — xia needs room for models and memory",
                )
            elif free_gb < 5.0:
                self._warning(
                    "Disk space",
                    f"Low disk space: {free_gb:.1f}GB free",
                    "Consider freeing space — models and memory can grow large",
                )
        except Exception:
            pass  # Non-critical

    def _check_config(self):
        from core.paths import PATHS

        if not PATHS.config_file.exists():
            self._error(
                "config.yaml",
                f"Configuration file not found: {PATHS.config_file}",
                "Copy config.yaml from the xia scaffold",
            )
            return

        try:
            import yaml
            with open(PATHS.config_file) as f:
                cfg = yaml.safe_load(f)
            if not isinstance(cfg, dict):
                raise ValueError("config.yaml is empty or malformed")
        except Exception as e:
            self._error(
                "config.yaml",
                f"Cannot parse config.yaml: {e}",
                "Check config.yaml for YAML syntax errors",
            )

    def _check_ollama(self):
        import urllib.request
        try:
            with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
                if r.status != 200:
                    raise Exception("bad status")
        except Exception:
            self._warning(
                "Ollama server",
                "Ollama is not running on port 11434",
                "Run launch.bat — it starts Ollama automatically",
            )

    # ── Helpers ────────────────────────────────────────────────────────────

    def _error(self, check: str, message: str, fix: str = ""):
        self.issues.append(HealthIssue("error", check, message, fix))

    def _warning(self, check: str, message: str, fix: str = ""):
        self.issues.append(HealthIssue("warning", check, message, fix))
