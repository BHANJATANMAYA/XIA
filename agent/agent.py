"""
agent/agent.py — The xia Agent (Part 8: Skills integrated)

THINK → PLAN → ACT → OBSERVE → REASON → FINAL
Now with skill context injection and post-task skill extraction.
"""

import json
from typing import Callable, List, Optional

from agent.base import (
    AgentDecision, AgentResult, AgentStep,
    StepStatus, StepType, ToolCall, ToolResult,
)
from core.config import cfg
from core.llm import LLMClient, Message
from core.logger import get_logger
from core.prompt import PromptBuilder

log = get_logger(__name__)


class Agent:
    def __init__(
        self,
        llm: Optional[LLMClient] = None,
        tool_registry=None,
        memory_store=None,      # MemoryManager
        skill_manager=None,     # SkillManager
        router=None,            # ModelRouter
        on_step: Optional[Callable[[AgentStep], None]] = None,
    ):
        self.llm = llm or LLMClient()
        self.tool_registry = tool_registry
        self.memory_store = memory_store
        self.skill_manager = skill_manager
        self.router = router
        self.on_step = on_step
        self.prompt_builder = PromptBuilder()
        self.max_steps = cfg.agent.max_steps
        self.max_retries = cfg.agent.max_retries

        log.info("Agent initialised: model=%s max_steps=%d", self.llm.model, self.max_steps)

    def run(self, task: str, context: Optional[str] = None) -> AgentResult:
        log.info("Agent.run() task=%r", task[:80])

        steps: List[AgentStep] = []
        tools_used: List[str] = []
        history: List[Message] = []

        # ── Auto-route to best model for this task ─────────────────────────
        if self.router:
            best_model, profile = self.router.pick(task)
            if best_model != self.llm.model:
                log.info("Router: switching %s → %s (profile: %s)",
                         self.llm.model, best_model, profile)
                self.llm.switch_model(best_model)
                self.llm.temperature = self.router.pick_temperature(profile)

        # ── Build system prompt with skills + memory ───────────────────────
        tool_names    = self._get_tool_descriptions()
        tool_schemas  = self._get_tool_schemas()
        memory_snippets = self._retrieve_memory(task)
        skill_context   = self._retrieve_skills(task)

        system_prompt = self.prompt_builder.build_agent_prompt(
            tools=tool_names,
            tool_schemas=tool_schemas,
            memory_snippets=memory_snippets,
            skill_context=skill_context,
        )

        user_message = task
        if context:
            user_message = f"{task}\n\nContext:\n{context}"

        # ── Main loop ──────────────────────────────────────────────────────
        for iteration in range(self.max_steps):
            log.debug("Loop iteration %d/%d", iteration + 1, self.max_steps)

            decision = self._think(user_message, history, system_prompt)

            think_step = AgentStep(step_type=StepType.THINK, content=decision.thought)
            steps.append(think_step)
            self._emit(think_step)

            if decision.plan and iteration == 0:
                plan_step = AgentStep(
                    step_type=StepType.PLAN,
                    content="\n".join(f"  {i+1}. {s}" for i, s in enumerate(decision.plan)),
                )
                steps.append(plan_step)
                self._emit(plan_step)

            # ── Final answer ───────────────────────────────────────────────
            if decision.is_done:
                final_step = AgentStep(step_type=StepType.FINAL, content=decision.final_answer)
                steps.append(final_step)
                self._emit(final_step)

                result = AgentResult(
                    task=task,
                    final_answer=decision.final_answer,
                    steps=steps,
                    success=True,
                    total_steps=len(steps),
                    tools_used=tools_used,
                )

                # Auto-extract skill from successful task
                self._maybe_extract_skill(result)
                return result

            # ── Tool call ──────────────────────────────────────────────────
            if decision.has_tool_call:
                tool_call = decision.tool_call

                act_step = AgentStep(
                    step_type=StepType.ACT,
                    content=f"Calling tool: {tool_call.name}",
                    tool_name=tool_call.name,
                    tool_input=tool_call.input,
                    status=StepStatus.RUNNING,
                )
                steps.append(act_step)
                self._emit(act_step)

                tool_result = self._execute_tool(tool_call)
                act_step.tool_result = str(tool_result)
                act_step.status = StepStatus.DONE if tool_result.success else StepStatus.FAILED

                if tool_call.name not in tools_used:
                    tools_used.append(tool_call.name)

                observe_step = AgentStep(
                    step_type=StepType.OBSERVE,
                    content=str(tool_result)[:500],
                )
                steps.append(observe_step)
                self._emit(observe_step)

                observe_message = self.prompt_builder.build_tool_result_prompt(
                    tool_name=tool_call.name,
                    tool_input=tool_call.input,
                    tool_result=str(tool_result),
                )

                history.append(Message.user(user_message))
                history.append(Message.assistant(self._decision_to_json(decision)))
                user_message = observe_message

            else:
                log.warning("No tool call and no final answer at iteration %d", iteration + 1)
                confusion_step = AgentStep(
                    step_type=StepType.REASON,
                    content="No tool call and no final answer. Prompting to conclude.",
                    status=StepStatus.FAILED,
                )
                steps.append(confusion_step)
                self._emit(confusion_step)
                user_message = (
                    "You must either use a tool from the available list "
                    "or provide a final_answer. Please conclude now."
                )

        # ── Max steps hit ──────────────────────────────────────────────────
        log.warning("Agent hit max_steps=%d", self.max_steps)
        fallback = (
            "I reached the maximum reasoning steps without completing this task. "
            "Please try breaking it into smaller parts."
        )
        timeout_step = AgentStep(step_type=StepType.FINAL, content=fallback, status=StepStatus.FAILED)
        steps.append(timeout_step)
        self._emit(timeout_step)

        return AgentResult(
            task=task, final_answer=fallback, steps=steps,
            success=False, error="max_steps exceeded",
            total_steps=len(steps), tools_used=tools_used,
        )

    # ── Internal ───────────────────────────────────────────────────────────

    def _think(self, user_message, history, system_prompt) -> AgentDecision:
        for attempt in range(self.max_retries):
            try:
                raw = self.llm.chat_json(user_message, history=history, system_prompt=system_prompt)
                if "error" in raw and "raw" in raw:
                    log.warning("JSON parse failed (attempt %d): %s", attempt + 1, raw["error"])
                    if attempt < self.max_retries - 1:
                        user_message += "\n\nRespond ONLY with a valid JSON object."
                        continue
                    return AgentDecision.error_decision(raw["error"])
                return AgentDecision.from_dict(raw)
            except Exception as e:
                log.error("_think() error (attempt %d): %s", attempt + 1, e)
                if attempt == self.max_retries - 1:
                    return AgentDecision.error_decision(str(e))
        return AgentDecision.error_decision("All retries exhausted")

    def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
        if self.tool_registry is None:
            return ToolResult(
                tool_name=tool_call.name, output="", success=False,
                error="Tool registry not available.",
            )
        try:
            return self.tool_registry.execute(tool_call)
        except Exception as e:
            log.error("Tool execution error: %s", e)
            return ToolResult(tool_name=tool_call.name, output="", success=False, error=str(e))

    def _get_tool_descriptions(self) -> List[str]:
        if self.tool_registry is None:
            return ["(No tools available)"]
        return self.tool_registry.describe_all()

    def _get_tool_schemas(self) -> str:
        if self.tool_registry is None:
            return "(No tools available)"
        return self.tool_registry.schemas_as_prompt()

    def _retrieve_memory(self, task: str) -> List[str]:
        if self.memory_store is None:
            return []
        try:
            return self.memory_store.retrieve(task, top_k=cfg.memory.max_results)
        except Exception as e:
            log.warning("Memory retrieval failed: %s", e)
            return []

    def _retrieve_skills(self, task: str) -> str:
        if self.skill_manager is None:
            return ""
        try:
            return self.skill_manager.get_context(task)
        except Exception as e:
            log.warning("Skill retrieval failed: %s", e)
            return ""

    def _maybe_extract_skill(self, result: AgentResult):
        if self.skill_manager is None:
            return
        try:
            saved = self.skill_manager.process_result(result)
            if saved:
                log.info("New skill auto-extracted from task: %s", result.task[:50])
        except Exception as e:
            log.warning("Skill extraction failed: %s", e)

    def _emit(self, step: AgentStep):
        if self.on_step:
            try:
                self.on_step(step)
            except Exception:
                pass

    def _decision_to_json(self, decision: AgentDecision) -> str:
        data = {
            "thought": decision.thought,
            "plan": decision.plan,
            "action": {
                "tool": decision.tool_call.name if decision.tool_call else None,
                "input": decision.tool_call.input if decision.tool_call else {},
            },
            "final_answer": decision.final_answer,
        }
        return json.dumps(data, indent=2)
