"""
skills/manager.py — Skill Manager

High-level interface for the skill system.
The agent and session use this — never the store or extractor directly.

Responsibilities:
  - Extract skills from successful agent tasks
  - Retrieve relevant skills before agent runs
  - Inject skill context into system prompt
  - Track skill usage and effectiveness

Usage:
    manager = SkillManager(llm=llm)

    # Before agent run — get relevant skills
    skill_context = manager.get_context("create a python project")

    # After successful task — auto-extract skill
    manager.process_result(agent_result)
"""

from typing import List, Optional

from agent.base import AgentResult
from core.config import cfg
from core.logger import get_logger
from skills.store import SkillStore

log = get_logger(__name__)


class SkillManager:
    """
    Single interface for all skill operations.
    """

    def __init__(self, llm=None):
        self._llm = llm
        self._store = SkillStore()
        self._extractor = None  # Lazy init

        log.info("SkillManager ready: %d skills stored", self._store.count())

    # ── Retrieval ──────────────────────────────────────────────────────────

    def find_relevant(self, query: str, top_k: int = 2) -> List:
        """Find skills relevant to a query."""
        return self._store.find_matching(query, top_k=top_k)

    def get_context(self, query: str) -> str:
        """
        Get skill context string for injection into the system prompt.
        Returns empty string if no relevant skills found.
        """
        skills = self.find_relevant(query, top_k=2)
        if not skills:
            return ""

        lines = ["Relevant skills from past experience:"]
        for skill in skills:
            lines.append(skill.to_prompt_str())
            lines.append("")

        return "\n".join(lines)

    # ── Extraction ─────────────────────────────────────────────────────────

    def process_result(self, result: AgentResult) -> bool:
        """
        Analyse a completed AgentResult and extract a skill if worthwhile.
        Called automatically after each successful agent task.
        Returns True if a skill was saved.
        """
        if not cfg.skills.enabled or not cfg.skills.auto_extract:
            return False

        if not result or not result.success or not result.tools_used:
            return False

        if self._store.count() >= cfg.skills.max_skills:
            log.warning("Skill store at capacity (%d)", cfg.skills.max_skills)
            return False

        # Check if we already have a very similar skill
        existing = self._store.find_matching(result.task, top_k=1)
        if existing and existing[0].matches(result.task):
            # Update existing skill's usage count instead
            self._store.increment_usage(existing[0].skill_id)
            log.debug("Updated existing skill: %s", existing[0].name)
            return False

        extractor = self._get_extractor()
        skill = extractor.extract_from_result(result)

        if skill:
            self._store.save(skill)
            log.info("New skill saved: %s", skill.name)
            return True

        return False

    def save_skill_manually(self, name: str, description: str,
                            triggers: List[str], steps: List[str],
                            tools: List[str], template: str) -> bool:
        """Manually create and save a skill."""
        from skills.schema import Skill
        skill = Skill(
            name=name,
            description=description,
            trigger_phrases=triggers,
            steps=steps,
            tools_used=tools,
            template=template,
            examples=[],
        )
        self._store.save(skill)
        return True

    # ── Stats ──────────────────────────────────────────────────────────────

    def count(self) -> int:
        return self._store.count()

    def list_all(self) -> List:
        return self._store.all()

    def delete(self, skill_id: str) -> bool:
        return self._store.delete(skill_id)

    # ── Internal ───────────────────────────────────────────────────────────

    def _get_extractor(self):
        if self._extractor is None:
            from skills.extractor import SkillExtractor
            self._extractor = SkillExtractor(llm=self._llm)
        return self._extractor
