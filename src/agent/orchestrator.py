"""
agent/orchestrator.py — Multi-Agent Orchestrator

Coordinates multiple specialized agents on complex tasks.
Decomposes tasks, delegates to role-specific sub-agents,
and synthesizes results.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from agent.agent import Agent
from agent.base import AgentResult, AgentStep, StepType, StepStatus
from core.config import cfg
from core.llm import LLMClient
from core.logger import get_logger
from core.prompt import PromptBuilder

log = get_logger(__name__)


class AgentRole(Enum):
    PLANNER = "planner"
    CODER = "coder"
    RESEARCHER = "researcher"
    REVIEWER = "reviewer"
    DEBUGGER = "debugger"
    SYNTHESIZER = "synthesizer"


@dataclass
class SubTask:
    id: str
    description: str
    role: AgentRole
    dependencies: List[str] = field(default_factory=list)
    context: str = ""
    result: Optional[AgentResult] = None
    status: str = "pending"
    retry_count: int = 0
    max_retries: int = 1


@dataclass
class TaskPlan:
    original_task: str
    subtasks: List[SubTask] = field(default_factory=list)
    summary: str = ""

    def get_ready(self) -> List[SubTask]:
        done_ids = {st.id for st in self.subtasks if st.status == "done"}
        return [
            st for st in self.subtasks
            if st.status == "pending"
            and all(dep in done_ids for dep in st.dependencies)
        ]


ROLE_PROMPTS = {
    AgentRole.PLANNER: (
        "You are a planning specialist. Break complex tasks into clear, "
        "sequential steps. For each step, specify: what to do, which tools "
        "to use, and what the expected output is. Be specific about file "
        "paths, commands, and code."
    ),
    AgentRole.CODER: (
        "You are a coding specialist. Write clean, working code. "
        "Always verify your output: read files after writing, run commands "
        "to check syntax. Fix errors immediately when they occur."
    ),
    AgentRole.RESEARCHER: (
        "You are a research specialist. Gather information by searching, "
        "reading files, and fetching web content. Summarize findings clearly."
    ),
    AgentRole.REVIEWER: (
        "You are a code reviewer. Check for: bugs, security issues, "
        "missing error handling, style violations, and incomplete logic. "
        "Be thorough but practical."
    ),
    AgentRole.DEBUGGER: (
        "You are a debugging specialist. When something fails: "
        "1) Read the error message carefully, 2) Check the relevant code, "
        "3) Identify the root cause, 4) Fix it with minimal changes, "
        "5) Verify the fix works."
    ),
    AgentRole.SYNTHESIZER: (
        "You are a synthesis specialist. Combine results from multiple "
        "agents into a clear, coherent final answer. Highlight key outcomes "
        "and note any caveats."
    ),
}


class Orchestrator:
    """
    Manages multi-agent collaboration on complex tasks.

    Usage:
        orch = Orchestrator(llm, tool_registry, memory_manager, skill_manager)
        result = orch.run("Build a REST API with auth and tests")
    """

    def __init__(
        self,
        llm: LLMClient,
        tool_registry=None,
        memory_manager=None,
        skill_manager=None,
        router=None,
        on_step=None,
    ):
        self.llm = llm
        self.tool_registry = tool_registry
        self.memory_manager = memory_manager
        self.skill_manager = skill_manager
        self.router = router
        self.on_step = on_step
        self.prompt_builder = PromptBuilder()
        self._planner = None

    def run(self, task: str, context: Optional[str] = None) -> AgentResult:
        log.info("Orchestrator.run() task=%r", task[:80])

        plan = self._decompose(task, context)
        if not plan or not plan.subtasks:
            log.warning("Decomposition failed, falling back to single agent")
            return self._fallback_single_agent(task, context)

        self._emit_plan(plan)

        max_rounds = len(plan.subtasks) * 2
        for round_num in range(max_rounds):
            ready = plan.get_ready()
            if not ready:
                break
            if cfg.orchestration.parallel_subtasks and len(ready) > 1:
                self._execute_subtasks_parallel(ready, plan)
            else:
                for subtask in ready:
                    self._execute_subtask(subtask, plan)

        successful = [st for st in plan.subtasks if st.status == "done"]
        failed = [st for st in plan.subtasks if st.status == "failed"]

        if not successful:
            return AgentResult(
                task=task,
                final_answer="All subtasks failed. Please try a simpler approach.",
                steps=[],
                success=False,
                error="All subtasks failed",
            )

        # Skip synthesis when only 1 subtask succeeded — return directly
        if len(successful) == 1 and not failed:
            result = successful[0].result
            self._learn(task, plan, result)
            return result

        synthesis = self._synthesize(task, successful, failed)
        self._learn(task, plan, synthesis)
        return synthesis

    def _decompose(self, task: str, context: Optional[str] = None) -> Optional[TaskPlan]:
        decomp_prompt = (
            "Decompose this task into subtasks. For each subtask, specify:\n"
            "- description: what to do\n"
            "- role: one of [planner, coder, researcher, reviewer, debugger, synthesizer]\n"
            "- dependencies: list of subtask IDs this depends on (empty if none)\n\n"
            "Respond with JSON:\n"
            '{"subtasks": [{"id": "T1", "description": "...", "role": "coder", "dependencies": []}]}\n\n'
            f"Task: {task}"
        )

        if context:
            decomp_prompt += f"\n\nContext:\n{context}"

        if self.memory_manager:
            lessons = self._retrieve_lessons(task)
            if lessons:
                decomp_prompt += f"\n\nLessons from past attempts:\n{lessons}"

        try:
            raw = self.llm.chat_json(decomp_prompt)
            if "error" in raw:
                return None

            subtasks = []
            for st_data in raw.get("subtasks", []):
                role_str = st_data.get("role", "coder")
                try:
                    role = AgentRole(role_str)
                except ValueError:
                    role = AgentRole.CODER

                subtasks.append(SubTask(
                    id=st_data.get("id", f"T{len(subtasks)+1}"),
                    description=st_data.get("description", ""),
                    role=role,
                    dependencies=st_data.get("dependencies", []),
                ))

            return TaskPlan(original_task=task, subtasks=subtasks)

        except Exception as e:
            log.error("Decomposition failed: %s", e)
            return None

    def _execute_subtask(self, subtask: SubTask, plan: TaskPlan):
        subtask.status = "running"

        dep_context = self._build_dependency_context(subtask, plan)
        agent = self._create_role_agent(subtask.role)

        full_task = subtask.description
        if dep_context:
            full_task += f"\n\nResults from previous steps:\n{dep_context}"
        if subtask.context:
            full_task += f"\n\nAdditional context:\n{subtask.context}"

        result = agent.run(full_task, context=dep_context)
        subtask.result = result

        if result.success:
            subtask.status = "done"
        else:
            if subtask.retry_count < subtask.max_retries:
                subtask.retry_count += 1
                subtask.status = "pending"
                log.info("Retrying subtask %s (attempt %d)", subtask.id, subtask.retry_count + 1)
            else:
                subtask.status = "failed"
                log.warning("Subtask %s failed after %d retries", subtask.id, subtask.retry_count)

    def _execute_subtasks_parallel(self, subtasks: List[SubTask], plan: TaskPlan):
        """Execute independent subtasks concurrently."""
        with ThreadPoolExecutor(max_workers=len(subtasks)) as pool:
            futures = {
                pool.submit(self._execute_subtask, st, plan): st
                for st in subtasks
            }
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    st = futures[future]
                    log.error("Parallel subtask %s failed: %s", st.id, e)
                    st.status = "failed"
                    st.result = AgentResult(
                        task=st.description, final_answer="", success=False,
                        error=str(e),
                    )

    def _create_role_agent(self, role: AgentRole) -> Agent:
        role_prompt = ROLE_PROMPTS.get(role, "")
        agent = Agent(
            llm=self.llm,
            tool_registry=self.tool_registry,
            memory_store=self.memory_manager,
            skill_manager=self.skill_manager,
            router=self.router,
            on_step=self.on_step,
            role_prompt=role_prompt,
        )
        agent.max_steps = cfg.orchestration.sub_agent_max_steps
        return agent

    def _build_dependency_context(self, subtask: SubTask, plan: TaskPlan) -> str:
        dep_ids = set(subtask.dependencies)
        if not dep_ids:
            return ""

        parts = []
        for st in plan.subtasks:
            if st.id in dep_ids and st.result:
                parts.append(
                    f"Step {st.id} ({st.role.value}): {st.result.final_answer[:500]}"
                )
        return "\n\n".join(parts)

    def _synthesize(
        self, task: str, successful: List[SubTask], failed: List[SubTask]
    ) -> AgentResult:
        synth_agent = self._create_role_agent(AgentRole.SYNTHESIZER)

        parts = []
        all_steps = []
        tools_used = []

        for st in successful:
            if st.result:
                parts.append(f"**{st.role.value.title()} ({st.id})**:\n{st.result.final_answer}")
                all_steps.extend(st.result.steps)
                tools_used.extend(st.result.tools_used)

        if failed:
            parts.append(f"\n**Failed steps**: {', '.join(st.id for st in failed)}")

        synth_prompt = (
            f"Original task: {task}\n\n"
            f"Results from sub-agents:\n\n" + "\n\n".join(parts) + "\n\n"
            "Combine these into a clear, complete final answer for the user."
        )

        synth_result = synth_agent.run(synth_prompt)

        return AgentResult(
            task=task,
            final_answer=synth_result.final_answer,
            steps=all_steps + synth_result.steps,
            success=len(successful) > 0 and len(failed) == 0,
            total_steps=len(all_steps) + len(synth_result.steps),
            tools_used=list(set(tools_used)),
        )

    def _retrieve_lessons(self, task: str) -> str:
        if not self.memory_manager:
            return ""
        try:
            results = self.memory_manager.retrieve(
                f"lesson learned: {task}", top_k=3
            )
            if results:
                return "\n".join(f"- {r}" for r in results)
        except Exception as e:
            log.debug("Lesson retrieval failed: %s", e)
        return ""

    def _learn(self, task: str, plan: TaskPlan, result: AgentResult):
        if not self.memory_manager:
            return

        failed = [st for st in plan.subtasks if st.status == "failed"]
        if failed:
            for st in failed:
                lesson = (
                    f"Task '{task[:80]}' failed at step '{st.description[:60]}' "
                    f"({st.role.value}). Consider different approach next time."
                )
                self.memory_manager.remember(
                    lesson,
                    metadata={
                        "memory_type": "lesson",
                        "importance": 0.8,
                        "source": "orchestrator_failure",
                    }
                )

        if result.success and len(plan.subtasks) > 1:
            pattern = (
                f"Task decomposition for '{task[:60]}': "
                + " -> ".join(f"{st.role.value}({st.description[:30]})" for st in plan.subtasks)
            )
            self.memory_manager.remember(
                pattern,
                metadata={
                    "memory_type": "procedural",
                    "importance": 0.6,
                    "source": "orchestrator_pattern",
                }
            )

    def _fallback_single_agent(self, task: str, context: Optional[str] = None) -> AgentResult:
        agent = Agent(
            llm=self.llm,
            tool_registry=self.tool_registry,
            memory_store=self.memory_manager,
            skill_manager=self.skill_manager,
            router=self.router,
            on_step=self.on_step,
        )
        return agent.run(task, context=context)

    def _emit_plan(self, plan: TaskPlan):
        if not self.on_step:
            return
        for st in plan.subtasks:
            step = AgentStep(
                step_type=StepType.PLAN,
                content=f"[{st.id}] {st.role.value}: {st.description}",
                status=StepStatus.PENDING,
            )
            self.on_step(step)
