"""
core/router.py — Model Router

Automatically selects the best available local model for each task.
Falls back gracefully if the preferred model isn't pulled.

Profiles:
  coding   → qwen2.5-coder  (best for code, algorithms, debugging)
  fast     → phi3 / phi4     (small, instant responses)
  smart    → llama3.1 / deepseek-r1  (best reasoning, hard problems)
  default  → mistral          (balanced, your primary model)

Usage:
    router = ModelRouter(llm_client)
    model  = router.pick(task="write a binary search function")
    # → "qwen2.5-coder"  (if available, else falls back to mistral)
"""

import re
from typing import Dict, List, Optional, Tuple

from core.logger import get_logger

log = get_logger(__name__)


# ── Model profiles ─────────────────────────────────────────────────────────────

PROFILES: Dict[str, dict] = {
    "coding": {
        "description": "Best for writing code, debugging, algorithms, LeetCode",
        "preferred":   ["qwen2.5-coder", "qwen2.5-coder:7b", "deepseek-coder",
                        "codellama", "starcoder2"],
        "fallback":    "mistral",
        "temperature": 0.2,   # Lower = more precise code
    },
    "fast": {
        "description": "Instant responses for simple questions",
        "preferred":   ["phi4", "phi3", "phi3:mini", "gemma2:2b", "qwen2.5:3b"],
        "fallback":    "mistral",
        "temperature": 0.7,
    },
    "smart": {
        "description": "Deep reasoning for hard problems",
        "preferred":   ["deepseek-r1", "llama3.1", "llama3.1:8b",
                        "qwen2.5:14b", "mistral-large"],
        "fallback":    "mistral",
        "temperature": 0.7,
    },
    "default": {
        "description": "Balanced general-purpose model",
        "preferred":   ["mistral", "llama3", "llama3.2", "gemma2"],
        "fallback":    "mistral",
        "temperature": 0.7,
    },
}

# ── Task → profile mapping ─────────────────────────────────────────────────────

CODING_SIGNALS = [
    "code", "function", "class", "algorithm", "debug", "fix", "bug",
    "implement", "write a", "leetcode", "solve", "python", "javascript",
    "typescript", "rust", "go ", "java", "c++", "sql", "api", "script",
    "program", "error", "exception", "syntax", "compile", "refactor",
    "test", "unit test", "complexity", "time complexity", "space complexity",
    "array", "linked list", "tree", "graph", "sort", "search", "recursion",
    "dynamic programming", "binary", "hash", "stack", "queue",
]

FAST_SIGNALS = [
    "what is", "define", "explain briefly", "quick question",
    "yes or no", "true or false", "how do you spell",
    "what does", "meaning of", "translate",
]

SMART_SIGNALS = [
    "analyze", "compare", "evaluate", "design", "architecture",
    "strategy", "plan", "reasoning", "why does", "how should i",
    "best approach", "tradeoffs", "pros and cons", "in depth",
    "research", "comprehensive", "detailed explanation",
]


class ModelRouter:
    """
    Picks the best available model for a given task.
    Caches available models to avoid repeated Ollama API calls.
    """

    def __init__(self, llm):
        self._llm = llm
        self._available: Optional[List[str]] = None
        self._current_profile: str = "default"

    def pick(self, task: str) -> Tuple[str, str]:
        """
        Pick the best model for a task.
        Returns (model_name, profile_name).
        """
        available = self._get_available()
        profile_name = self._detect_profile(task)
        profile = PROFILES[profile_name]

        # Try preferred models in order
        for model in profile["preferred"]:
            # Match by prefix — "qwen2.5-coder" matches "qwen2.5-coder:7b"
            for avail in available:
                if avail.startswith(model.split(":")[0]):
                    log.debug("Router: task profile=%s → model=%s", profile_name, avail)
                    return avail, profile_name

        # Fall back to profile default, then current model
        fallback = profile["fallback"]
        for avail in available:
            if avail.startswith(fallback):
                return avail, profile_name

        # Last resort: whatever is currently loaded
        return self._llm.model, profile_name

    def pick_temperature(self, profile_name: str) -> float:
        return PROFILES.get(profile_name, PROFILES["default"])["temperature"]

    def profile_for(self, name: str) -> Optional[dict]:
        return PROFILES.get(name.lower())

    def available_models(self) -> List[str]:
        return self._get_available()

    def describe_profiles(self) -> str:
        lines = []
        available = self._get_available()
        for name, profile in PROFILES.items():
            best = next(
                (m for m in profile["preferred"]
                 for a in available if a.startswith(m.split(":")[0])),
                f"{profile['fallback']} (fallback)"
            )
            lines.append(f"  {name:<10} {profile['description']}")
            lines.append(f"             will use: {best}")
        return "\n".join(lines)

    # ── Internal ───────────────────────────────────────────────────────────

    def _detect_profile(self, task: str) -> str:
        lower = task.lower()

        coding_score = sum(1 for s in CODING_SIGNALS if s in lower)
        fast_score   = sum(1 for s in FAST_SIGNALS   if s in lower)
        smart_score  = sum(1 for s in SMART_SIGNALS  if s in lower)

        scores = {
            "coding":  coding_score * 3,  # Coding signals weighted higher
            "fast":    fast_score,
            "smart":   smart_score * 2,
            "default": 0,
        }

        best = max(scores, key=scores.get)
        if scores[best] == 0:
            return "default"
        return best

    def _get_available(self) -> List[str]:
        if self._available is not None:
            return self._available
        try:
            models = self._llm.list_models()
            # Normalise — strip :latest suffix
            self._available = [m.replace(":latest", "") for m in models]
            log.debug("Available models: %s", self._available)
        except Exception:
            self._available = [self._llm.model]
        return self._available

    def refresh(self):
        """Refresh model list (call after ollama pull)."""
        self._available = None
