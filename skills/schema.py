"""
skills/schema.py — Skill Data Types

A "skill" is a reusable pattern extracted from a successful agent task.
It captures: what the user asked for, how xia solved it, and which tools were used.

Example skill:
    name:        "create_python_script"
    description: "Create a new Python script file with boilerplate"
    trigger:     ["create python file", "new python script", "make a .py file"]
    steps:       ["Ask for filename and purpose", "Write file to workspace"]
    tools:       ["filesystem"]
    template:    "To create a Python script: use filesystem write action..."
    success_count: 7
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class Skill:
    """
    A single reusable skill extracted from agent interactions.
    Skills are stored as JSON files in data/skills_store/.
    """
    name:          str
    description:   str
    trigger_phrases: List[str]       # Phrases that indicate this skill applies
    steps:         List[str]         # High-level steps to accomplish the task
    tools_used:    List[str]         # Which tools this skill typically uses
    template:      str               # Detailed instructions for the agent
    examples:      List[Dict]        # Raw examples this was extracted from
    skill_id:      str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at:    str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at:    str = field(default_factory=lambda: datetime.now().isoformat())
    success_count: int = 0           # Times this skill was applied successfully
    tags:          List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id":       self.skill_id,
            "name":           self.name,
            "description":    self.description,
            "trigger_phrases": self.trigger_phrases,
            "steps":          self.steps,
            "tools_used":     self.tools_used,
            "template":       self.template,
            "examples":       self.examples,
            "created_at":     self.created_at,
            "updated_at":     self.updated_at,
            "success_count":  self.success_count,
            "tags":           self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Skill":
        return cls(
            skill_id=data.get("skill_id", str(uuid.uuid4())[:8]),
            name=data["name"],
            description=data["description"],
            trigger_phrases=data.get("trigger_phrases", []),
            steps=data.get("steps", []),
            tools_used=data.get("tools_used", []),
            template=data.get("template", ""),
            examples=data.get("examples", []),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            success_count=data.get("success_count", 0),
            tags=data.get("tags", []),
        )

    def to_prompt_str(self) -> str:
        """Format skill as a compact string for injection into system prompt."""
        lines = [
            f"Skill: {self.name}",
            f"  When: {self.description}",
        ]
        if self.steps:
            lines.append(f"  Steps: {' → '.join(self.steps)}")
        if self.tools_used:
            lines.append(f"  Tools: {', '.join(self.tools_used)}")
        if self.template:
            lines.append(f"  Approach: {self.template[:200]}")
        return "\n".join(lines)

    def matches(self, query: str) -> bool:
        """Check if this skill's triggers match a query (simple keyword check)."""
        query_lower = query.lower()
        return any(phrase.lower() in query_lower for phrase in self.trigger_phrases)

    def __repr__(self) -> str:
        return f"Skill(name={self.name}, uses={self.success_count})"
