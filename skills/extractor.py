"""
skills/extractor.py — Skill Extractor

After a successful agent task, this analyses what happened and decides
if the solution is worth saving as a reusable skill.

A skill is worth saving when:
  - The task required multiple steps
  - Tools were used in a specific pattern
  - The same kind of task will likely come up again
  - The solution had a clear structure that can be templated

Example: after xia successfully creates a Python project scaffold,
the extractor saves a "create_python_project" skill with the exact
steps and file structure used, so next time it's instant.

Usage:
    extractor = SkillExtractor(llm)
    skill = extractor.extract_from_result(agent_result)
    if skill:
        store.save(skill)
"""

import json
from typing import Optional

from agent.base import AgentResult
from core.logger import get_logger
from skills.schema import Skill

log = get_logger(__name__)

EXTRACTION_PROMPT = """You are a skill extraction system for an AI agent called xia.

A "skill" is a reusable solution pattern worth saving for future use.

Given a completed agent task, decide if it's worth saving as a skill.
A task is worth saving as a skill if:
- It required 2+ steps or tool calls
- It has a clear repeatable pattern (not one-off)
- Future similar tasks would benefit from knowing this approach
- It involved a non-trivial workflow

NOT worth saving:
- Simple single-tool tasks ("read this file", "echo hello")
- Pure knowledge questions with no tool use
- Failed tasks
- One-time specific tasks unlikely to repeat

If worth saving, respond with this JSON:
{{
  "worth_saving": true,
  "name": "snake_case_skill_name_max_4_words",
  "description": "One sentence: when to use this skill",
  "trigger_phrases": ["phrase1", "phrase2", "phrase3"],
  "steps": ["step 1", "step 2", "step 3"],
  "tools_used": ["tool1", "tool2"],
  "template": "Detailed approach: how to do this task well in 2-4 sentences",
  "tags": ["tag1", "tag2"]
}}

If NOT worth saving:
{{
  "worth_saving": false
}}

Task that was completed:
{task}

Steps taken:
{steps}

Tools used: {tools}

Final answer given:
{answer}"""


class SkillExtractor:
    """
    Analyses completed agent tasks and extracts reusable skills.
    Uses the LLM to decide what's worth saving and how to structure it.
    """

    def __init__(self, llm=None):
        self._llm = llm

    def extract_from_result(self, result: AgentResult) -> Optional[Skill]:
        """
        Try to extract a skill from a completed AgentResult.
        Returns a Skill if worth saving, None otherwise.
        """
        if not result or not result.success:
            return None

        if not result.tools_used:
            return None  # No tools used — not complex enough

        if len(result.steps) < 2:
            return None  # Too simple

        if not self._llm:
            return self._rule_based_extract(result)

        return self._llm_extract(result)

    # ── LLM-based extraction ───────────────────────────────────────────────

    def _llm_extract(self, result: AgentResult) -> Optional[Skill]:
        """Use the LLM to intelligently extract a skill."""
        steps_text = self._format_steps(result)

        prompt = EXTRACTION_PROMPT.format(
            task=result.task[:300],
            steps=steps_text[:1500],
            tools=", ".join(result.tools_used),
            answer=result.final_answer[:300],
        )

        try:
            data = self._llm.chat_json(prompt)

            if not data.get("worth_saving"):
                log.debug("Skill extractor: task not worth saving")
                return None

            skill = Skill(
                name=data.get("name", "unnamed_skill"),
                description=data.get("description", ""),
                trigger_phrases=data.get("trigger_phrases", []),
                steps=data.get("steps", []),
                tools_used=data.get("tools_used", result.tools_used),
                template=data.get("template", ""),
                examples=[{
                    "task": result.task,
                    "answer": result.final_answer[:200],
                }],
                tags=data.get("tags", []),
            )

            log.info("Skill extracted: %s", skill.name)
            return skill

        except Exception as e:
            log.warning("LLM skill extraction failed: %s", e)
            return self._rule_based_extract(result)

    # ── Rule-based fallback ────────────────────────────────────────────────

    def _rule_based_extract(self, result: AgentResult) -> Optional[Skill]:
        """
        Simple rule-based extraction when LLM is unavailable.
        Less intelligent but always works.
        """
        task_lower = result.task.lower()

        # Only save if multi-tool and non-trivial
        if len(result.tools_used) < 1 or len(result.steps) < 3:
            return None

        # Build a basic skill name from the task
        words = [w for w in task_lower.split()[:4] if len(w) > 2]
        name = "_".join(words) if words else "unnamed_skill"

        # Generate trigger phrases from task keywords
        triggers = []
        for word in task_lower.split():
            if len(word) > 3 and word not in {"with", "that", "this", "from", "into", "using"}:
                triggers.append(word)
        triggers = list(set(triggers))[:5]

        skill = Skill(
            name=name,
            description=f"How to: {result.task[:80]}",
            trigger_phrases=triggers,
            steps=[s.content[:100] for s in result.steps if s.content][:5],
            tools_used=result.tools_used,
            template=f"Task: {result.task}\nApproach: {result.final_answer[:200]}",
            examples=[{"task": result.task, "answer": result.final_answer[:200]}],
        )

        return skill

    def _format_steps(self, result: AgentResult) -> str:
        lines = []
        for i, step in enumerate(result.steps, 1):
            line = f"{i}. [{step.step_type.value}] {step.content[:100]}"
            if step.tool_name:
                line += f" (tool: {step.tool_name})"
            lines.append(line)
        return "\n".join(lines)
