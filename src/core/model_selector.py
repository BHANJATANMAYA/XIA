"""Choose locally downloaded Ollama models that fit the current machine."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from core.config import cfg
from core.logger import get_logger

log = get_logger(__name__)

_EMBEDDING_MARKERS = ("embed", "embedding", "nomic", "bge-", "all-minilm")
_PARAMETERS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*b", re.IGNORECASE)


@dataclass(frozen=True)
class ModelCandidate:
    name: str
    size_gb: float
    parameters_b: float
    required_gb: float


@dataclass(frozen=True)
class ModelSelection:
    model: str
    allowed_models: tuple[str, ...]
    budget_gb: float
    reason: str


class HardwareAwareModelSelector:
    """Rank downloaded generative models without downloading or deleting anything."""

    def __init__(self, llm, host):
        self.llm = llm
        self.host = host

    def select(self) -> ModelSelection | None:
        candidates = list(self._candidates(self.llm.list_model_details()))
        if not candidates:
            return None

        budget_gb = self._budget_gb()
        suitable = [candidate for candidate in candidates if candidate.required_gb <= budget_gb]
        # A very small machine should still get the least demanding downloaded
        # chat model rather than failing because none meet the conservative limit.
        allowed = suitable or [min(candidates, key=lambda candidate: candidate.required_gb)]
        selected = max(allowed, key=lambda candidate: (candidate.parameters_b, candidate.size_gb))
        allowance = ", ".join(candidate.name for candidate in allowed)
        reason = (
            f"{self.host.ram_gb:.1f}GB RAM"
            + (f", {self.host.vram_gb:.1f}GB VRAM" if self.host.vram_gb else "")
            + f"; {budget_gb:.1f}GB model budget; eligible: {allowance}"
        )
        return ModelSelection(
            model=selected.name,
            allowed_models=tuple(candidate.name for candidate in allowed),
            budget_gb=budget_gb,
            reason=reason,
        )

    def _budget_gb(self) -> float:
        # Keep substantial memory available for the OS, context window, and xia's
        # embedding model. GPU memory augments the usable budget for Ollama.
        ram_budget = max(2.0, self.host.ram_gb * cfg.llm.auto_select_memory_fraction)
        gpu_budget = self.host.vram_gb * 0.60 if self.host.has_gpu() else 0.0
        return ram_budget + gpu_budget

    def _candidates(self, models: Iterable[dict[str, Any]]) -> Iterable[ModelCandidate]:
        for model in models:
            name = str(model.get("name", "")).strip()
            if not name or any(marker in name.lower() for marker in _EMBEDDING_MARKERS):
                continue
            size_gb = float(model.get("size", 0) or 0) / (1024 ** 3)
            parameters_b = self._parameter_count(name, model.get("details", {}))
            # Disk size is a good proxy for a quantized model's runtime footprint.
            # Add headroom for runtime state and the configured context window.
            required_gb = max(size_gb * 1.20 + 0.75, parameters_b * 0.35 + 0.75)
            yield ModelCandidate(name, size_gb, parameters_b, required_gb)

    @staticmethod
    def _parameter_count(name: str, details: Any) -> float:
        parameter_size = ""
        if isinstance(details, dict):
            parameter_size = str(details.get("parameter_size", ""))
        match = _PARAMETERS_RE.search(parameter_size) or _PARAMETERS_RE.search(name)
        if match:
            return float(match.group(1))
        return 0.0
