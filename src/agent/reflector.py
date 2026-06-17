"""
agent/reflector.py — Self-Reflection & Self-Critique

After each action or subtask, analyzes what happened and decides
whether to continue, retry, or change approach.

  ACT → OBSERVE → REFLECT → (retry | continue | replan)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from agent.base import AgentResult
from core.llm import LLMClient
from core.logger import get_logger

log = get_logger(__name__)


class ReflectionVerdict(Enum):
    CONTINUE = "continue"
    RETRY = "retry"
    REPLAN = "replan"
    ACCEPT = "accept"


@dataclass
class Reflection:
    verdict: ReflectionVerdict
    critique: str
    suggestion: str
    confidence: float
    lesson: Optional[str]


class SelfReflector:
    """
    Analyzes agent actions and provides self-critique.
    """

    REFLECT_ON_ACTION_PROMPT = (
        "You are analyzing an AI agent's action.\n\n"
        "Task: {task}\n"
        "Action taken: {action}\n"
        "Tool used: {tool}\n"
        "Result: {result}\n\n"
        "Was this action effective? Analyze:\n"
        "1. Did the tool call produce the expected output?\n"
        "2. Were the parameters correct?\n"
        "3. Is there an error that needs fixing?\n"
        "4. Should the agent continue, retry with different params, or change strategy?\n\n"
        'Respond with JSON:\n'
        '{{"verdict": "continue" | "retry" | "replan" | "accept",'
        ' "critique": "What went right/wrong (1-2 sentences)",'
        ' "suggestion": "Specific next action to take",'
        ' "confidence": 0.0 to 1.0,'
        ' "lesson": "What to remember for next time (or null)"}}'
    )

    REFLECT_ON_RESULT_PROMPT = (
        "You are evaluating a completed subtask.\n\n"
        "Original task: {task}\n"
        "Subtask completed: {subtask}\n"
        "Result: {result}\n"
        "Steps taken: {steps}\n\n"
        "Evaluate the quality:\n"
        "1. Does the result fully address the subtask?\n"
        "2. Are there missing pieces or errors?\n"
        "3. Is the quality acceptable?\n\n"
        'Respond with JSON:\n'
        '{{"verdict": "accept" | "retry" | "replan",'
        ' "critique": "Quality assessment",'
        ' "suggestion": "What to do next",'
        ' "confidence": 0.0 to 1.0,'
        ' "lesson": "What to remember (or null)"}}'
    )

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def reflect_on_action(
        self,
        task: str,
        action: str,
        tool_name: str,
        result: str,
    ) -> Reflection:
        prompt = self.REFLECT_ON_ACTION_PROMPT.format(
            task=task[:500],
            action=action[:300],
            tool=tool_name,
            result=result[:500],
        )
        return self._get_reflection(prompt)

    def reflect_on_result(
        self,
        task: str,
        subtask: str,
        result: AgentResult,
    ) -> Reflection:
        steps_text = result.thinking_trace()[:1000]
        prompt = self.REFLECT_ON_RESULT_PROMPT.format(
            task=task[:500],
            subtask=subtask[:300],
            result=result.final_answer[:500],
            steps=steps_text,
        )
        return self._get_reflection(prompt)

    def extract_lesson(self, task: str, result: AgentResult, error: str) -> Optional[str]:
        prompt = (
            "A task failed. Extract a lesson for future reference.\n\n"
            f"Task: {task[:500]}\n"
            f"Error: {error[:300]}\n"
            f"Steps taken: {result.thinking_trace()[:500]}\n\n"
            "Provide a concise lesson (1-2 sentences) that would help "
            "avoid this failure in the future. Just output the lesson text."
        )
        try:
            response = self.llm.chat(prompt)
            lesson = response.content.strip()
            if lesson and len(lesson) > 10:
                return lesson
        except Exception as e:
            log.debug("Lesson extraction failed: %s", e)
        return None

    def _get_reflection(self, prompt: str) -> Reflection:
        try:
            raw = self.llm.chat_json(prompt)
            if "error" in raw:
                return self._default_reflection(raw.get("error", "LLM error"))

            verdict_str = raw.get("verdict", "continue")
            try:
                verdict = ReflectionVerdict(verdict_str)
            except ValueError:
                verdict = ReflectionVerdict.CONTINUE

            return Reflection(
                verdict=verdict,
                critique=raw.get("critique", ""),
                suggestion=raw.get("suggestion", ""),
                confidence=float(raw.get("confidence", 0.5)),
                lesson=raw.get("lesson"),
            )
        except Exception as e:
            log.error("Reflection failed: %s", e)
            return self._default_reflection(str(e))

    def _default_reflection(self, reason: str) -> Reflection:
        return Reflection(
            verdict=ReflectionVerdict.CONTINUE,
            critique=f"Could not analyze: {reason}",
            suggestion="Continue with current approach",
            confidence=0.3,
            lesson=None,
        )
