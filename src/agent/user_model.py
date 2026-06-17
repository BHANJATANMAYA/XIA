"""
agent/user_model.py — User Preference Model

Learns and adapts to the user's communication style, preferences,
and working patterns over time.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from core.llm import LLMClient
from core.logger import get_logger

log = get_logger(__name__)


@dataclass
class UserPreference:
    category: str
    key: str
    value: str
    confidence: float
    source: str


class UserModel:
    """
    Tracks and adapts to user preferences.
    Piggybacks on MemoryManager with "user_preference" memory type.
    """

    PREF_EXTRACTION_PROMPT = (
        "Analyze this conversation exchange and extract user preferences.\n\n"
        "User said: {user_input}\n"
        "Agent responded: {assistant_output}\n"
        "{correction}\n\n"
        "Extract any preference signals. Respond with JSON array:\n"
        '[{{"category": "communication|technical|workflow", '
        '"key": "preference_name", "value": "the_preference", "confidence": 0.8}}]\n\n'
        "Only extract clear signals. Empty array if no preferences detected."
    )

    def __init__(self, llm: Optional[LLMClient] = None, memory_manager=None):
        self.llm = llm
        self.memory = memory_manager
        self._preferences: Dict[str, UserPreference] = {}
        self._loaded = False

    def track_interaction(
        self,
        user_input: str,
        assistant_output: str,
        was_corrected: bool = False,
        correction_text: Optional[str] = None,
    ):
        if not self.llm or not self.memory:
            return

        if len(user_input.split()) < 3:
            return

        correction_context = ""
        if was_corrected and correction_text:
            correction_context = f"User corrected with: {correction_text}"

        prompt = self.PREF_EXTRACTION_PROMPT.format(
            user_input=user_input[:500],
            assistant_output=assistant_output[:300],
            correction=correction_context,
        )

        try:
            raw = self.llm.chat_json(prompt)
            if isinstance(raw, list):
                prefs = raw
            elif isinstance(raw, dict):
                prefs = raw.get("preferences", raw if "category" in raw else [])
            else:
                return

            if not isinstance(prefs, list):
                return

            for pref_data in prefs:
                if not isinstance(pref_data, dict):
                    continue

                pref = UserPreference(
                    category=pref_data.get("category", "general"),
                    key=pref_data.get("key", ""),
                    value=pref_data.get("value", ""),
                    confidence=float(pref_data.get("confidence", 0.5)),
                    source="corrected" if was_corrected else "inferred",
                )

                if pref.key and pref.value:
                    self._preferences[f"{pref.category}:{pref.key}"] = pref
                    self._store_preference(pref)

        except Exception as e:
            log.debug("Preference extraction failed: %s", e)

    def get_preferences_prompt(self) -> str:
        if not self._loaded:
            self._load_preferences()

        if not self._preferences:
            return ""

        lines = ["Known user preferences:"]
        for pref in self._preferences.values():
            if pref.confidence >= 0.6:
                lines.append(f"  - {pref.key}: {pref.value} ({pref.category})")

        return "\n".join(lines) if len(lines) > 1 else ""

    def get_preference(self, key: str) -> Optional[str]:
        if not self._loaded:
            self._load_preferences()

        for pref in self._preferences.values():
            if pref.key == key and pref.confidence >= 0.5:
                return pref.value
        return None

    def _store_preference(self, pref: UserPreference):
        if not self.memory:
            return

        content = f"User preference: {pref.key} = {pref.value} (category: {pref.category})"

        self.memory.remember(
            content,
            metadata={
                "memory_type": "user_preference",
                "importance": 0.6 + pref.confidence * 0.3,
                "source": pref.source,
                "category": pref.category,
                "key": pref.key,
                "value": pref.value,
            }
        )

    def _load_preferences(self):
        self._loaded = True

        if not self.memory:
            return

        try:
            results = self.memory.retrieve("user preference likes prefers", top_k=20)

            for result in results:
                if "User preference:" in result:
                    parts = result.replace("User preference:", "").strip()
                    if "=" in parts:
                        key_val = parts.split("=", 1)
                        key = key_val[0].strip()
                        value = key_val[1].strip().split("(")[0].strip()

                        self._preferences[f"general:{key}"] = UserPreference(
                            category="general",
                            key=key,
                            value=value,
                            confidence=0.7,
                            source="inferred",
                        )
        except Exception as e:
            log.debug("Preference loading failed: %s", e)
