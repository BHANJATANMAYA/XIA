"""
agent/planner.py — Task Decomposer

Breaks complex tasks into a dependency graph of subtasks.
"""

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from core.llm import LLMClient
from core.logger import get_logger

log = get_logger(__name__)


@dataclass
class DecomposedTask:
    id: str
    description: str
    role: str
    dependencies: List[str] = field(default_factory=list)
    complexity: str = "simple"


class TaskPlanner:
    """
    Decomposes tasks into subtask graphs using the LLM.
    """

    DECOMPOSE_PROMPT = (
        "Analyze this task and break it into subtasks.\n\n"
        "For each subtask provide:\n"
        "- id: unique identifier (T1, T2, etc.)\n"
        "- description: what to do (be specific)\n"
        "- role: one of [planner, coder, researcher, reviewer, debugger]\n"
        "- dependencies: list of subtask IDs this needs completed first\n"
        "- complexity: simple, moderate, or complex\n\n"
        "Rules:\n"
        "- Keep it to 2-5 subtasks max\n"
        "- Each subtask should be completable by a single agent\n"
        "- Use dependency arrows to define order\n\n"
        "Task: {task}\n\n"
        'Respond with JSON:\n'
        '{{"analysis": "Brief analysis of what this task requires",'
        ' "subtasks": ['
        '{{"id": "T1", "description": "...", "role": "coder", "dependencies": [], "complexity": "simple"}}'
        "]}}"
    )

    COMPLEXITY_PROMPT = (
        "Classify task complexity as 'simple' or 'complex'.\n"
        "Simple: single tool call, direct answer, read/write one file.\n"
        "Complex: multiple steps, multiple files, requires planning.\n\n"
        "Task: {task}\n\n"
        'Respond with JSON: {{"complexity": "simple" or "complex", "reason": "brief reason"}}'
    )

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def decompose(self, task: str) -> Optional[Dict]:
        prompt = self.DECOMPOSE_PROMPT.format(task=task[:1000])

        try:
            result = self.llm.chat_json(prompt)
            if "error" in result:
                log.warning("Decomposition LLM error: %s", result.get("error"))
                return None

            subtasks = result.get("subtasks", [])
            if not subtasks:
                return None

            if self._has_circular_deps(subtasks):
                log.warning("Circular dependencies detected, simplifying")
                subtasks = self._simplify_deps(subtasks)

            return result

        except Exception as e:
            log.error("Task decomposition failed: %s", e)
            return None

    def estimate_complexity(self, task: str) -> str:
        prompt = self.COMPLEXITY_PROMPT.format(task=task[:500])
        try:
            result = self.llm.chat_json(prompt)
            return result.get("complexity", "simple")
        except Exception:
            return "simple"

    def _has_circular_deps(self, subtasks: List[Dict]) -> bool:
        dep_map = {st["id"]: set(st.get("dependencies", [])) for st in subtasks}
        visited = set()
        in_stack = set()

        def dfs(node):
            if node in in_stack:
                return True
            if node in visited:
                return False
            visited.add(node)
            in_stack.add(node)
            for dep in dep_map.get(node, []):
                if dfs(dep):
                    return True
            in_stack.remove(node)
            return False

        return any(dfs(st["id"]) for st in subtasks if st["id"] not in visited)

    def _simplify_deps(self, subtasks: List[Dict]) -> List[Dict]:
        ids = {st["id"] for st in subtasks}
        for st in subtasks:
            st["dependencies"] = [
                d for d in st.get("dependencies", [])
                if d in ids and d != st["id"]
            ]
        return subtasks
