"""
agent/session.py — Session Manager

Manages a single user session with xia.
Now wired to persistent memory — retrieves relevant context before each
message and saves facts after the session ends.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from agent.agent import Agent
from agent.base import AgentResult, AgentStep, StepType
from core.config import cfg
from core.llm import LLMClient, Message
from core.logger import get_logger
from core.paths import PATHS
from core.prompt import PromptBuilder

log = get_logger(__name__)

# Triggers that suggest the agent loop is needed (tools required)
AGENT_TRIGGERS = (
    # File operations
    "create file", "write file", "read file", "delete file", "list files",
    "make a file", "new file", "save file", "open file",
    "folder", "directory", "mkdir",
    # Terminal
    "run", "execute", "command", "terminal", "install", "pip",
    # Browser — always use browser tool for these
    "go to", "open browser", "navigate to", "browse to",
    "click on", "fill in", "type into",
    # Web search
    "search for", "look up", "google", "browse",
    "latest news", "recent news", "current price", "today's",
    "find online", "search online",
    # Multi-step tasks
    "step by step", "build", "set up", "configure", "deploy",
    "how do i", "can you help me",
)

# Questions that should ALWAYS go to chat (memory-backed), never web search
CHAT_OVERRIDES = (
    "what is my", "what's my", "who am i", "do you remember",
    "what do you know about me", "my name", "my age", "my location",
    "i told you", "you remember", "from last time",
    # Config/settings questions — answer directly, no tools needed
    "how do i change", "how to change", "default model", "change model",
    "change xia", "change the model", "what model", "which model",
    "how do i switch", "how to switch",
)

# Tasks that MUST use the browser tool — injected into system prompt hint
BROWSER_TRIGGERS = (
    "go to", "open browser", "navigate to", "browse to",
    "click on", "fill in",
)

ACTION_STARTERS = (
    "create ", "make a ", "build ", "write a ", "generate ",
    "run ", "execute ", "install ",
)

MEMORY_QUERY_SIGNALS = (
    "remember", "memory", "what is my", "what's my", "who am i",
    "what do you know about me", "my name", "my age", "my location",
    "i told you", "you remember", "from last time", "my project",
    "my preference", "i prefer", "i use", "i work", "i like",
    "i hate", "i love",
)

LOW_SIGNAL_CHAT = {
    "hi", "hii", "hello", "hey", "yo", "sup", "thanks", "thank you",
    "ok", "okay", "cool", "nice", "lol", "hmm", "hmmm",
}


class SessionMessage:
    def __init__(self, role: str, content: str, agent_result: Optional[AgentResult] = None):
        self.role = role
        self.content = content
        self.agent_result = agent_result
        self.timestamp = datetime.now().isoformat()


class Session:
    def __init__(
        self,
        llm: Optional[LLMClient] = None,
        tool_registry=None,
        memory_manager=None,
        skill_manager=None,
        router=None,
        on_step: Optional[callable] = None,
    ):
        self.session_id = str(uuid.uuid4())[:8]
        self.llm = llm or LLMClient()
        self.tool_registry = tool_registry
        self.memory_manager = memory_manager
        self.skill_manager = skill_manager
        self.router = router
        self.on_step = on_step

        self.agent = Agent(
            llm=self.llm,
            tool_registry=tool_registry,
            memory_store=memory_manager,
            skill_manager=skill_manager,
            router=router,
            on_step=on_step,
        )

        self.orchestrator = None
        self.learner = None
        self.user_model = None
        self._advanced_initialized = False

        self.prompt_builder = PromptBuilder()
        self.history: List[Message] = []
        self.messages: List[SessionMessage] = []

        mem_count = memory_manager.count() if memory_manager else 0
        log.info("Session %s started (memories available: %d)", self.session_id, mem_count)

    def _init_advanced_systems(self):
        if self._advanced_initialized:
            return
        self._advanced_initialized = True

        if cfg.orchestration.enabled:
            from agent.orchestrator import Orchestrator
            self.orchestrator = Orchestrator(
                llm=self.llm,
                tool_registry=self.tool_registry,
                memory_manager=self.memory_manager,
                skill_manager=self.skill_manager,
                router=self.router,
                on_step=self.on_step,
            )

        if cfg.self_learning.enabled:
            from agent.learner import SelfLearner
            self.learner = SelfLearner(
                llm=self.llm,
                memory_manager=self.memory_manager,
            )

        if cfg.orchestration.user_model_enabled:
            from agent.user_model import UserModel
            self.user_model = UserModel(
                llm=self.llm,
                memory_manager=self.memory_manager,
            )

    # ── Public API ─────────────────────────────────────────────────────────

    def send(self, user_input: str) -> AgentResult:
        user_input = user_input.strip()
        if not user_input:
            return self._wrap_simple("(empty input)")

        mode = self._needs_agent(user_input)
        log.info("Session.send(): %r (mode=%s)", user_input[:60], mode)

        if mode == "orchestrator":
            return self._run_orchestrator(user_input)
        elif mode == "agent":
            return self._run_agent(user_input)
        else:
            return self._run_chat(user_input)

    def clear_history(self):
        self.history = []
        self.messages = []
        log.info("Session %s history cleared", self.session_id)

    def save(self) -> Path:
        """Save session transcript to disk and persist memories."""
        # Auto-save memories from this session
        if self.memory_manager and self.messages:
            try:
                count = self.memory_manager.save_session(self)
                if count:
                    log.info("Auto-saved %d memories from session", count)
            except Exception as e:
                log.warning("Memory save failed: %s", e)

        # Save conversation transcript
        session_data = {
            "session_id": self.session_id,
            "started_at": self.messages[0].timestamp if self.messages else None,
            "message_count": len(self.messages),
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp,
                    "had_tool_calls": bool(m.agent_result and m.agent_result.tools_used),
                }
                for m in self.messages
            ],
        }

        save_path = PATHS.conversations_dir / f"session_{self.session_id}.json"
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=2, ensure_ascii=False)

        log.info("Session saved to %s", save_path)
        return save_path

    # ── Routing ────────────────────────────────────────────────────────────

    ORCHESTRATOR_TRIGGERS = (
        "build", "create a", "set up", "implement", "design",
        "write a full", "create a complete", "scaffold",
        "refactor", "migrate", "integrate",
        "with tests", "with auth", "with database",
        "end to end", "full stack", "complete",
    )

    def _needs_agent(self, text: str) -> str:
        """Returns: 'chat' | 'agent' | 'orchestrator'"""
        lower = text.lower()

        if any(phrase in lower for phrase in CHAT_OVERRIDES):
            return "chat"

        if cfg.orchestration.enabled:
            if any(trigger in lower for trigger in self.ORCHESTRATOR_TRIGGERS):
                if len(text.split()) > 8:
                    return "orchestrator"

        if any(trigger in lower for trigger in AGENT_TRIGGERS):
            return "agent"

        if any(lower.startswith(v) for v in ACTION_STARTERS):
            return "agent"

        if len(text.split()) > 25:
            if cfg.orchestration.enabled:
                return "orchestrator"
            return "agent"

        return "chat"

    # ── Execution ──────────────────────────────────────────────────────────

    def _run_orchestrator(self, user_input: str) -> AgentResult:
        self.messages.append(SessionMessage(role="user", content=user_input))

        if not self._advanced_initialized:
            self._init_advanced_systems()

        context = None
        if self.learner:
            lessons = self.learner.get_relevant_lessons(user_input)
            if lessons:
                context = "Lessons from past experience:\n" + "\n".join(f"- {l}" for l in lessons)

        if self.user_model:
            prefs_prompt = self.user_model.get_preferences_prompt()
            if prefs_prompt:
                context = (context or "") + "\n\n" + prefs_prompt

        if self.orchestrator:
            result = self.orchestrator.run(user_input, context=context)
        else:
            result = self.agent.run(user_input, context=context)

        self.messages.append(SessionMessage(
            role="assistant", content=result.final_answer, agent_result=result,
        ))
        self.history.append(Message.user(user_input))
        self.history.append(Message.assistant(result.final_answer))

        if self.learner:
            self.learner.learn_from_result(user_input, result)

        if self.user_model:
            self.user_model.track_interaction(user_input, result.final_answer)

        if self.memory_manager:
            try:
                self.memory_manager.track_interaction(user_input, result.final_answer)
            except Exception as e:
                log.debug("Working memory track failed (orchestrator mode): %s", e)

        return result

    def _run_agent(self, user_input: str) -> AgentResult:
        self.messages.append(SessionMessage(role="user", content=user_input))

        task = user_input
        lower = user_input.lower()
        if any(t in lower for t in BROWSER_TRIGGERS):
            hint = (
                "[System hint: This task requires the browser tool. "
                "Use action='navigate' to open URLs, action='extract_text' "
                "to read content, action='click' to click, action='type' to type. "
                "Do NOT use the search tool for tasks that say 'go to' a specific site.]"
            )
            task = user_input + "\n\n" + hint

        result = self.agent.run(task)
        self.messages.append(SessionMessage(
            role="assistant", content=result.final_answer, agent_result=result,
        ))
        self.history.append(Message.user(user_input))
        self.history.append(Message.assistant(result.final_answer))

        if self.memory_manager:
            try:
                self.memory_manager.track_interaction(user_input, result.final_answer)
            except Exception as e:
                log.debug("Working memory track failed (agent mode): %s", e)

        if not self._advanced_initialized:
            self._init_advanced_systems()

        if self.learner:
            self.learner.learn_from_result(user_input, result)

        if self.user_model:
            self.user_model.track_interaction(user_input, result.final_answer)

        return result

    def _run_chat(self, user_input: str) -> AgentResult:
        self.messages.append(SessionMessage(role="user", content=user_input))

        memory_snippets = []
        if self.memory_manager and self._should_retrieve_memory(user_input):
            try:
                memory_snippets = self.memory_manager.retrieve(user_input, top_k=3)
            except Exception as e:
                log.debug("Memory retrieval failed in chat mode: %s", e)

        system_prompt = self.prompt_builder.build_chat_prompt(
            memory_snippets=memory_snippets,
        )

        response = self.llm.chat(
            user_input,
            history=self.history,
            system_prompt=system_prompt,
        )

        self.history = response.updated_history
        self.messages.append(SessionMessage(role="assistant", content=response.content))

        if self.memory_manager:
            try:
                self.memory_manager.track_interaction(user_input, response.content)
            except Exception as e:
                log.debug("Working memory track failed (chat mode): %s", e)

        if not self._advanced_initialized:
            self._init_advanced_systems()

        if self.user_model:
            self.user_model.track_interaction(user_input, response.content)

        return self._wrap_simple(response.content)

    def _should_retrieve_memory(self, user_input: str) -> bool:
        lower = " ".join(user_input.lower().split())
        if not lower:
            return False

        if any(signal in lower for signal in MEMORY_QUERY_SIGNALS):
            return True

        words = lower.split()
        if lower in LOW_SIGNAL_CHAT:
            return False

        # Avoid waking the embedding model for tiny casual messages.
        return len(words) >= 4

    def _wrap_simple(self, content: str) -> AgentResult:
        return AgentResult(
            task="",
            final_answer=content,
            steps=[AgentStep(step_type=StepType.FINAL, content=content)],
            success=True,
            total_steps=1,
        )

