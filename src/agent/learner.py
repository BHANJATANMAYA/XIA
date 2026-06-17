"""
agent/learner.py — Self-Learning System

Learns from both successes and failures:
- Tracks failure patterns and their resolutions
- Stores "anti-patterns" (what NOT to do)
- Retrieves relevant lessons before similar tasks
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from core.llm import LLMClient
from core.logger import get_logger

log = get_logger(__name__)


@dataclass
class Lesson:
    id: str
    task_type: str
    lesson: str
    context: str
    source: str
    confidence: float
    times_applied: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class SelfLearner:
    """
    Manages the self-learning loop.
    Integrates with MemoryManager to store and retrieve lessons.
    """

    LESSON_PROMPT = (
        "Analyze this completed task and extract a lesson.\n\n"
        "Task: {task}\n"
        "Outcome: {outcome}\n"
        "Key steps: {steps}\n\n"
        "Provide a concise lesson (1-2 sentences) that would help in future similar tasks. "
        "Focus on: approach that worked, pitfalls to avoid, or optimization tips.\n\n"
        "Just output the lesson text, nothing else."
    )

    def __init__(self, llm: Optional[LLMClient] = None, memory_manager=None):
        self.llm = llm
        self.memory = memory_manager
        self._lesson_cache: Dict[str, List[str]] = {}

    def learn_from_result(self, task: str, result, was_corrected: bool = False):
        """Analyze a completed task and store lessons."""
        if not self.memory:
            return

        if not result.success:
            self._learn_from_failure(task, result)
        elif was_corrected:
            self._learn_from_correction(task, result)
        else:
            self._learn_from_success(task, result)

    def get_relevant_lessons(self, task: str, top_k: int = 3) -> List[str]:
        """Retrieve lessons relevant to the current task."""
        if not self.memory:
            return []

        cache_key = self._cache_key(task)
        if cache_key in self._lesson_cache:
            return self._lesson_cache[cache_key][:top_k]

        try:
            results = self.memory.retrieve(
                f"lesson approach {task}",
                top_k=top_k * 2,
            )

            lessons = []
            for r in results:
                if any(keyword in r.lower() for keyword in [
                    "lesson", "approach", "pitfall", "avoid", "tip",
                    "instead of", "should have", "failed",
                ]):
                    lessons.append(r)
                    if len(lessons) >= top_k:
                        break

            self._lesson_cache[cache_key] = lessons
            return lessons

        except Exception as e:
            log.debug("Lesson retrieval failed: %s", e)
            return []

    def learn_from_user_feedback(self, task: str, user_correction: str):
        """Learn when the user corrects or redirects the agent."""
        if not self.memory:
            return

        lesson = (
            f"User correction for task '{task[:60]}': {user_correction[:200]}. "
            f"Remember this preference for similar future tasks."
        )

        self.memory.remember(
            lesson,
            metadata={
                "memory_type": "lesson",
                "importance": 0.9,
                "source": "user_correction",
                "task_type": self._classify_task(task),
            }
        )
        log.info("Learned from user correction: %s", task[:50])

    def _learn_from_failure(self, task: str, result):
        lesson_text = None

        if self.llm:
            prompt = self.LESSON_PROMPT.format(
                task=task[:500],
                outcome="FAILED: " + (result.error or "unknown error"),
                steps=result.thinking_trace()[:500],
            )
            try:
                response = self.llm.chat(prompt)
                lesson_text = response.content.strip()
            except Exception:
                pass

        if not lesson_text:
            lesson_text = (
                f"Task '{task[:80]}' failed. Error: {result.error or 'unknown'}. "
                f"Consider a different approach next time."
            )

        self.memory.remember(
            lesson_text,
            metadata={
                "memory_type": "lesson",
                "importance": 0.85,
                "source": "failure",
                "task_type": self._classify_task(task),
                "error": (result.error or "")[:200],
            }
        )

    def _learn_from_success(self, task: str, result):
        if len(result.tools_used) < 2 or len(result.steps) < 3:
            return

        prompt = self.LESSON_PROMPT.format(
            task=task[:500],
            outcome="SUCCESS",
            steps=result.thinking_trace()[:500],
        )

        try:
            if self.llm:
                response = self.llm.chat(prompt)
                lesson_text = response.content.strip()
            else:
                lesson_text = f"Task '{task[:80]}' succeeded using tools: {', '.join(result.tools_used)}"

            if lesson_text:
                self.memory.remember(
                    lesson_text,
                    metadata={
                        "memory_type": "lesson",
                        "importance": 0.6,
                        "source": "success",
                        "task_type": self._classify_task(task),
                    }
                )
        except Exception:
            pass

    def _learn_from_correction(self, task: str, result):
        lesson = (
            f"Task '{task[:80]}' completed but needed correction. "
            f"Result was close but not perfect. Review requirements more carefully next time."
        )

        self.memory.remember(
            lesson,
            metadata={
                "memory_type": "lesson",
                "importance": 0.7,
                "source": "correction",
                "task_type": self._classify_task(task),
            }
        )

    def _classify_task(self, task: str) -> str:
        lower = task.lower()
        categories = {
            "file_ops": ["create file", "write file", "read file", "delete file", "mkdir"],
            "code": ["write code", "create script", "function", "class", "implement"],
            "debug": ["fix error", "debug", "traceback", "crash", "bug"],
            "research": ["search", "find", "look up", "what is", "how to"],
            "config": ["configure", "setup", "install", "settings", "config"],
        }
        for category, keywords in categories.items():
            if any(kw in lower for kw in keywords):
                return category
        return "general"

    def _cache_key(self, task: str) -> str:
        words = task.lower().split()[:5]
        return "_".join(words)
