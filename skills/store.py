"""
skills/store.py — Skill Store

Persists skills as JSON files on the SSD.
Each skill is its own file: data/skills_store/<skill_id>.json

Also maintains an index file for fast lookup without loading all skills.

Usage:
    store = SkillStore()
    store.save(skill)
    skill = store.get_by_name("create_python_script")
    matches = store.find_matching("create a python file")
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from core.logger import get_logger
from core.paths import PATHS
from skills.schema import Skill

log = get_logger(__name__)

INDEX_FILE = "skills_index.json"


class SkillStore:
    """
    File-based skill storage.
    Skills live in data/skills_store/ as individual JSON files.
    An index file enables fast name/trigger lookups.
    """

    def __init__(self, store_dir: Optional[Path] = None):
        self.store_dir = store_dir or PATHS.skills_store_dir
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._index: Dict[str, dict] = {}  # skill_id → {name, triggers, tags}
        self._load_index()
        log.info("SkillStore ready: %d skills", len(self._index))

    # ── Public API ─────────────────────────────────────────────────────────

    def save(self, skill: Skill) -> Path:
        """Save or update a skill. Returns the file path."""
        skill.updated_at = datetime.now().isoformat()
        skill_path = self.store_dir / f"{skill.skill_id}.json"

        with open(skill_path, "w", encoding="utf-8") as f:
            json.dump(skill.to_dict(), f, indent=2, ensure_ascii=False)

        # Update index
        self._index[skill.skill_id] = {
            "name":            skill.name,
            "description":     skill.description,
            "trigger_phrases": skill.trigger_phrases,
            "tags":            skill.tags,
            "success_count":   skill.success_count,
            "file":            skill_path.name,
        }
        self._save_index()
        log.info("Skill saved: %s (%s)", skill.name, skill.skill_id)
        return skill_path

    def get(self, skill_id: str) -> Optional[Skill]:
        """Load a skill by ID."""
        skill_path = self.store_dir / f"{skill_id}.json"
        if not skill_path.exists():
            return None
        try:
            data = json.loads(skill_path.read_text(encoding="utf-8"))
            return Skill.from_dict(data)
        except Exception as e:
            log.error("Failed to load skill %s: %s", skill_id, e)
            return None

    def get_by_name(self, name: str) -> Optional[Skill]:
        """Find a skill by name."""
        name_lower = name.lower()
        for skill_id, meta in self._index.items():
            if meta["name"].lower() == name_lower:
                return self.get(skill_id)
        return None

    def find_matching(self, query: str, top_k: int = 3) -> List[Skill]:
        """
        Find skills whose trigger phrases match the query.
        Returns top_k most relevant skills sorted by success_count.
        """
        query_lower = query.lower()
        matches = []

        for skill_id, meta in self._index.items():
            triggers = meta.get("trigger_phrases", [])
            score = sum(1 for t in triggers if t.lower() in query_lower)
            if score > 0:
                skill = self.get(skill_id)
                if skill:
                    matches.append((score, skill.success_count, skill))

        # Sort by match score, then by usage count
        matches.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [skill for _, _, skill in matches[:top_k]]

    def all(self) -> List[Skill]:
        """Return all stored skills."""
        skills = []
        for skill_id in self._index:
            skill = self.get(skill_id)
            if skill:
                skills.append(skill)
        return sorted(skills, key=lambda s: s.success_count, reverse=True)

    def delete(self, skill_id: str) -> bool:
        """Remove a skill permanently."""
        skill_path = self.store_dir / f"{skill_id}.json"
        if skill_path.exists():
            skill_path.unlink()
        if skill_id in self._index:
            del self._index[skill_id]
            self._save_index()
            return True
        return False

    def increment_usage(self, skill_id: str):
        """Mark a skill as successfully used."""
        skill = self.get(skill_id)
        if skill:
            skill.success_count += 1
            self.save(skill)

    def count(self) -> int:
        return len(self._index)

    # ── Index management ───────────────────────────────────────────────────

    def _load_index(self):
        index_path = self.store_dir / INDEX_FILE
        if index_path.exists():
            try:
                self._index = json.loads(index_path.read_text(encoding="utf-8"))
            except Exception as e:
                log.warning("Could not load skill index: %s", e)
                self._index = {}
        else:
            self._index = {}

    def _save_index(self):
        index_path = self.store_dir / INDEX_FILE
        try:
            index_path.write_text(
                json.dumps(self._index, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception as e:
            log.error("Could not save skill index: %s", e)
