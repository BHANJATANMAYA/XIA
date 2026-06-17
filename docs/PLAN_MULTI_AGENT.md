# XIA Multi-Agent Orchestration, Planning & Self-Learning — Implementation Plan

## Table of Contents
1. [Architecture Overview](#1-architecture-overview)
2. [New Files to Create](#2-new-files-to-create)
3. [Modifications to Existing Files](#3-modifications-to-existing-files)
4. [Orchestrator Design](#4-orchestrator-design)
5. [Planning & Decomposition](#5-planning--decomposition)
6. [Self-Reflection & Mistake Learning](#6-self-reflection--mistake-learning)
7. [User Preference Learning](#7-user-preference-learning)
8. [CLI & Config Integration](#8-cli--config-integration)
9. [Testing Approach](#9-testing-approach)
10. [Implementation Order](#10-implementation-order)

---

## 1. Architecture Overview

### Design Philosophy
- **Sequential delegation, not parallel execution** — local 4B-8B models can't handle concurrent agent reasoning. The orchestrator delegates to one sub-agent at a time, synthesizes results, then hands off to the next.
- **Each sub-agent = Agent instance with a focused system prompt and restricted tools** — no new LLM infrastructure needed. We reuse `LLMClient`, `Agent`, `ToolRegistry`.
- **Self-reflection happens inside the existing THINK step** — no new loop phases. We enhance the prompt to produce structured self-critique.
- **Lessons learned live in memory** — failures and their causes become memory entries with type `lesson`, queried before similar tasks.
- **Backward compatible** — the orchestrator wraps `Agent.run()`. If a task is simple, `Session` still routes to single-agent directly.

### High-Level Flow

```
User input
    │
    ▼
Session._needs_agent()
    │
    ├─ Simple → single Agent.run() [existing, unchanged]
    │
    └─ Complex → Orchestrator.run(task)
                      │
                      ▼
                  Planner.decompose(task) → TaskPlan (list of SubTask)
                      │
                      ▼
                  For each SubTask in topological order:
                      │
                      ├─ Retrieve lessons from memory
                      ├─ Pick agent role (planner/coder/reviewer/etc.)
                      ├─ Agent.run(subtask, context=...) 
                      ├─ SelfReflector.analyze(result) → critique
                      │      ├─ if critique says "retry" → replan this subtask
                      │      └─ if critique says "accept" → continue
                      └─ Accumulate results
                      │
                      ▼
                  Orchestrator synthesizes final answer
                      │
                      ▼
                  SelfLearner.process(results) → store lessons
```

---

## 2. New Files to Create

### 2.1 `src/agent/orchestrator.py` — Multi-Agent Orchestrator

```python
"""
agent/orchestrator.py — Multi-Agent Orchestrator

Coordinates multiple specialized agents on complex tasks.
Decomposes tasks, delegates to role-specific sub-agents,
and synthesizes results.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any

from agent.agent import Agent
from agent.base import AgentResult, AgentStep, StepType, StepStatus
from core.config import cfg
from core.llm import LLMClient, Message
from core.logger import get_logger
from core.prompt import PromptBuilder

log = get_logger(__name__)


class AgentRole(Enum):
    """Specialized roles for sub-agents."""
    PLANNER   = "planner"      # Creates detailed execution plans
    CODER     = "coder"        # Writes code, creates files
    RESEARCHER = "researcher"  # Searches, fetches, reads
    REVIEWER  = "reviewer"     # Checks quality, finds issues
    DEBUGGER  = "debugger"     # Diagnoses and fixes errors
    SYNTHESIZER = "synthesizer"  # Combines results into final answer


@dataclass
class SubTask:
    """A single decomposed unit of work."""
    id: str
    description: str
    role: AgentRole
    dependencies: List[str] = field(default_factory=list)  # IDs of subtasks this depends on
    context: str = ""
    result: Optional[AgentResult] = None
    status: str = "pending"  # pending | running | done | failed | retried
    retry_count: int = 0
    max_retries: int = 1


@dataclass
class TaskPlan:
    """Full decomposition of a complex task."""
    original_task: str
    subtasks: List[SubTask] = field(default_factory=list)
    summary: str = ""
    
    def get_ready(self) -> List[SubTask]:
        """Return subtasks whose dependencies are all satisfied."""
        done_ids = {st.id for st in self.subtasks if st.status in ("done",)}
        return [
            st for st in self.subtasks
            if st.status == "pending"
            and all(dep in done_ids for dep in st.dependencies)
        ]


class Orchestrator:
    """
    Manages multi-agent collaboration on complex tasks.
    
    Usage:
        orch = Orchestrator(llm, tool_registry, memory_manager, skill_manager)
        result = orch.run("Build a REST API with auth and tests")
    """
    
    # Role-specific system prompt fragments
    ROLE_PROMPTS = {
        AgentRole.PLANNER: (
            "You are a planning specialist. Your job is to break complex tasks "
            "into clear, sequential steps. For each step, specify: what to do, "
            "which tools to use, and what the expected output is. "
            "Think step-by-step. Be specific about file paths, commands, and code."
        ),
        AgentRole.CODER: (
            "You are a coding specialist. Write clean, working code. "
            "Always verify your output: read files after writing, run commands "
            "to check syntax. Fix errors immediately when they occur."
        ),
        AgentRole.RESEARCHER: (
            "You are a research specialist. Gather information by searching, "
            "reading files, and fetching web content. Summarize findings clearly. "
            "Always cite where you found each piece of information."
        ),
        AgentRole.REVIEWER: (
            "You are a code reviewer. Check for: bugs, security issues, "
            "missing error handling, style violations, and incomplete logic. "
            "Be thorough but practical — flag real issues, not nitpicks."
        ),
        AgentRole.DEBUGGER: (
            "You are a debugging specialist. When something fails: "
            "1) Read the error message carefully, 2) Check the relevant code, "
            "3) Identify the root cause, 4) Fix it with minimal changes, "
            "5) Verify the fix works."
        ),
        AgentRole.SYNTHESIZER: (
            "You are a synthesis specialist. Combine results from multiple "
            "agents into a clear, coherent final answer. Highlight key outcomes, "
            "list files created/modified, and note any caveats."
        ),
    }

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
        self._planner = None  # Lazy init
        self._lesson_store = None  # Lazy init

    def run(self, task: str, context: Optional[str] = None) -> AgentResult:
        """
        Execute a complex task using multi-agent orchestration.
        Falls back to single-agent if decomposition fails.
        """
        log.info("Orchestrator.run() task=%r", task[:80])
        
        # Step 1: Decompose the task
        plan = self._decompose(task, context)
        
        if not plan or not plan.subtasks:
            log.warning("Decomposition failed, falling back to single agent")
            return self._fallback_single_agent(task, context)
        
        # Step 2: Execute subtasks in dependency order
        self._emit_plan(plan)
        
        max_rounds = len(plan.subtasks) * 2  # Allow some retries
        for round_num in range(max_rounds):
            ready = plan.get_ready()
            if not ready:
                break
            
            for subtask in ready:
                self._execute_subtask(subtask, plan)
        
        # Step 3: Synthesize results
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
        
        synthesis = self._synthesize(task, successful, failed)
        
        # Step 4: Learn from this execution
        self._learn(task, plan, synthesis)
        
        return synthesis

    def _decompose(self, task: str, context: Optional[str] = None) -> Optional[TaskPlan]:
        """Use the LLM to decompose a task into subtasks."""
        planner = self._get_planner_agent()
        
        decomp_prompt = (
            f"Decompose this task into subtasks. For each subtask, specify:\n"
            f"- description: what to do\n"
            f"- role: one of [planner, coder, researcher, reviewer, debugger, synthesizer]\n"
            f"- dependencies: list of subtask IDs this depends on (empty if none)\n\n"
            f"Respond with JSON:\n"
            f'{{"subtasks": [{{"id": "T1", "description": "...", "role": "coder", "dependencies": []}}]}}\n\n'
            f"Task: {task}"
        )
        
        if context:
            decomp_prompt += f"\n\nContext:\n{context}"
        
        # Retrieve lessons for this type of task
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
        """Execute a single subtask with a specialized agent."""
        subtask.status = "running"
        
        # Build context from dependency results
        dep_context = self._build_dependency_context(subtask, plan)
        
        # Get role-specific prompt
        role_prompt = self.ROLE_PROMPTS.get(subtask.role, "")
        
        # Create a focused agent for this subtask
        agent = self._create_role_agent(subtask.role)
        
        full_task = f"{subtask.description}"
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
                subtask.status = "pending"  # Will be retried
                log.info("Retrying subtask %s (attempt %d)", subtask.id, subtask.retry_count + 1)
            else:
                subtask.status = "failed"
                log.warning("Subtask %s failed after %d retries", subtask.id, subtask.retry_count)

    def _create_role_agent(self, role: AgentRole) -> Agent:
        """Create an Agent instance with role-specific configuration."""
        # All agents share the same LLM and tools but get different prompts
        agent = Agent(
            llm=self.llm,
            tool_registry=self.tool_registry,
            memory_store=self.memory_manager,
            skill_manager=self.skill_manager,
            router=self.router,
            on_step=self.on_step,
        )
        
        # Override the prompt builder's agent identity for this role
        role_prompt = self.ROLE_PROMPTS.get(role, "")
        if role_prompt:
            # Store role prompt so it gets injected
            agent._role_prompt = role_prompt
        
        return agent

    def _build_dependency_context(self, subtask: SubTask, plan: TaskPlan) -> str:
        """Build context string from completed dependency subtasks."""
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
        """Combine subtask results into a final answer."""
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
            f"Combine these into a clear, complete final answer for the user."
        )
        
        synth_result = synth_agent.run(synth_prompt)
        
        # Merge steps from all subtasks
        return AgentResult(
            task=task,
            final_answer=synth_result.final_answer,
            steps=all_steps + synth_result.steps,
            success=len(successful) > 0 and len(failed) == 0,
            total_steps=len(all_steps) + len(synth_result.steps),
            tools_used=list(set(tools_used)),
        )

    def _get_planner_agent(self) -> Agent:
        """Get or create the planner agent."""
        if self._planner is None:
            self._planner = self._create_role_agent(AgentRole.PLANNER)
        return self._planner

    def _retrieve_lessons(self, task: str) -> str:
        """Retrieve lessons learned from memory for similar past tasks."""
        if not self.memory_manager:
            return ""
        try:
            # Query for lessons (memory_type = "lesson")
            results = self.memory_manager.retrieve(
                f"lesson learned: {task}", top_k=3
            )
            if results:
                return "\n".join(f"- {r}" for r in results)
        except Exception as e:
            log.debug("Lesson retrieval failed: %s", e)
        return ""

    def _learn(self, task: str, plan: TaskPlan, result: AgentResult):
        """Store lessons from this orchestration run."""
        if not self.memory_manager:
            return
        
        failed = [st for st in plan.subtasks if st.status == "failed"]
        if failed:
            # Store failure lessons
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
        
        # Store successful decomposition patterns
        if result.success and len(plan.subtasks) > 1:
            pattern = (
                f"Task decomposition for '{task[:60]}': "
                + " → ".join(f"{st.role.value}({st.description[:30]})" for st in plan.subtasks)
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
        """Fall back to single-agent execution."""
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
        """Emit plan steps for the renderer."""
        if not self.on_step:
            return
        
        for st in plan.subtasks:
            step = AgentStep(
                step_type=StepType.PLAN,
                content=f"[{st.id}] {st.role.value}: {st.description}",
                status=StepStatus.PENDING,
            )
            self.on_step(step)
```

### 2.2 `src/agent/planner.py` — Task Decomposer & Recursive Planner

```python
"""
agent/planner.py — Task Decomposer

Breaks complex tasks into a dependency graph of subtasks.
Supports recursive planning: if a subtask is too complex,
it can be further decomposed.
"""

import json
from dataclasses import dataclass, field
from typing import List, Optional, Dict

from core.llm import LLMClient
from core.logger import get_logger

log = get_logger(__name__)


@dataclass
class DecomposedTask:
    """A single task in the decomposition tree."""
    id: str
    description: str
    role: str
    dependencies: List[str] = field(default_factory=list)
    subtasks: List["DecomposedTask"] = field(default_factory=list)
    complexity: str = "simple"  # simple | moderate | complex


class TaskPlanner:
    """
    Decomposes tasks into subtask graphs.
    Uses the LLM to analyze task complexity and create execution plans.
    """
    
    DECOMPOSE_PROMPT = """Analyze this task and break it into subtasks.

For each subtask provide:
- id: unique identifier (T1, T2, etc.)
- description: what to do (be specific)
- role: one of [planner, coder, researcher, reviewer, debugger]
- dependencies: list of subtask IDs this needs completed first
- complexity: simple, moderate, or complex

Rules:
- Keep it to 2-5 subtasks max (local LLM context is limited)
- Each subtask should be completable by a single agent
- Use dependency arrows to define order
- If a subtask is "complex", it may need further decomposition

Task: {task}

Respond with JSON:
{{
  "analysis": "Brief analysis of what this task requires",
  "subtasks": [
    {{"id": "T1", "description": "...", "role": "coder", "dependencies": [], "complexity": "simple"}}
  ]
}}"""

    def __init__(self, llm: LLMClient):
        self.llm = llm
    
    def decompose(self, task: str) -> Optional[Dict]:
        """
        Decompose a task into subtasks.
        Returns dict with 'analysis' and 'subtasks' keys.
        """
        prompt = self.DECOMPOSE_PROMPT.format(task=task[:1000])
        
        try:
            result = self.llm.chat_json(prompt)
            if "error" in result:
                log.warning("Decomposition LLM error: %s", result.get("error"))
                return None
            
            subtasks = result.get("subtasks", [])
            if not subtasks:
                return None
            
            # Validate: ensure no circular dependencies
            if self._has_circular_deps(subtasks):
                log.warning("Circular dependencies detected, simplifying")
                subtasks = self._simplify_deps(subtasks)
            
            return result
        
        except Exception as e:
            log.error("Task decomposition failed: %s", e)
            return None
    
    def estimate_complexity(self, task: str) -> str:
        """Quick classification: should this use single-agent or orchestrator?"""
        prompt = (
            f"Classify task complexity as 'simple' or 'complex'.\n"
            f"Simple: single tool call, direct answer, read/write one file.\n"
            f"Complex: multiple steps, multiple files, requires planning.\n\n"
            f"Task: {task[:500]}\n\n"
            f'Respond with JSON: {{"complexity": "simple" or "complex", "reason": "brief reason"}}'
        )
        
        try:
            result = self.llm.chat_json(prompt)
            return result.get("complexity", "simple")
        except Exception:
            return "simple"
    
    def _has_circular_deps(self, subtasks: List[Dict]) -> bool:
        """Check for circular dependencies in subtask graph."""
        dep_map = {st["id"]: set(st.get("dependencies", [])) for st in subtasks}
        
        visited = set()
        in_stack = set()
        
        def dfs(node):
            if node in in_stack:
                return True
            if node in visited:
                return False
            visited.add(node)
            in_stack.add(node)
            for dep in dep_map.get(node, []):
                if dfs(dep):
                    return True
            in_stack.remove(node)
            return False
        
        return any(dfs(st["id"]) for st in subtasks if st["id"] not in visited)
    
    def _simplify_deps(self, subtasks: List[Dict]) -> List[Dict]:
        """Remove circular dependencies by clearing them."""
        ids = {st["id"] for st in subtasks}
        for st in subtasks:
            st["dependencies"] = [d for d in st.get("dependencies", []) if d in ids and d != st["id"]]
        return subtasks
```

### 2.3 `src/agent/reflector.py` — Self-Reflection Engine

```python
"""
agent/reflector.py — Self-Reflection & Self-Critique

After each action or subtask, analyzes what happened and decides
whether to continue, retry, or change approach.

This is the core of the self-learning loop:
  ACT → OBSERVE → REFLECT → (retry | continue | replan)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from agent.base import AgentResult, AgentStep
from core.llm import LLMClient
from core.logger import get_logger

log = get_logger(__name__)


class ReflectionVerdict(Enum):
    CONTINUE = "continue"    # Action succeeded, proceed
    RETRY = "retry"          # Failed but worth trying again with different approach
    REPLAN = "replan"        # Fundamental issue, need to change strategy
    ACCEPT = "accept"        # Good enough, wrap up


@dataclass
class Reflection:
    """Result of reflecting on an action or subtask."""
    verdict: ReflectionVerdict
    critique: str          # What went wrong / what could improve
    suggestion: str        # Concrete next step
    confidence: float      # 0.0 to 1.0
    lesson: Optional[str]  # What to remember for next time


class SelfReflector:
    """
    Analyzes agent actions and provides self-critique.
    
    Uses the LLM to:
    1. Evaluate whether an action achieved its goal
    2. Identify errors or inefficiencies
    3. Suggest corrections
    4. Extract lessons for future tasks
    """
    
    REFLECT_ON_ACTION_PROMPT = """You are analyzing an AI agent's action.

Task: {task}
Action taken: {action}
Tool used: {tool}
Result: {result}

Was this action effective? Analyze:
1. Did the tool call produce the expected output?
2. Were the parameters correct?
3. Is there an error that needs fixing?
4. Should the agent continue, retry with different params, or change strategy?

Respond with JSON:
{{
  "verdict": "continue" | "retry" | "replan" | "accept",
  "critique": "What went right/wrong (1-2 sentences)",
  "suggestion": "Specific next action to take",
  "confidence": 0.0 to 1.0,
  "lesson": "What to remember for next time (or null)"
}}"""

    REFLECT_ON_RESULT_PROMPT = """You are evaluating a completed subtask.

Original task: {task}
Subtask completed: {subtask}
Result: {result}
Steps taken: {steps}

Evaluate the quality:
1. Does the result fully address the subtask?
2. Are there missing pieces or errors?
3. Is the quality acceptable?

Respond with JSON:
{{
  "verdict": "accept" | "retry" | "replan",
  "critique": "Quality assessment",
  "suggestion": "What to do next",
  "confidence": 0.0 to 1.0,
  "lesson": "What to remember (or null)"
}}"""

    def __init__(self, llm: LLMClient):
        self.llm = llm
    
    def reflect_on_action(
        self,
        task: str,
        action: str,
        tool_name: str,
        result: str,
    ) -> Reflection:
        """Reflect on a single action (tool call + result)."""
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
        """Reflect on a completed subtask result."""
        steps_text = result.thinking_trace()[:1000]
        
        prompt = self.REFLECT_ON_RESULT_PROMPT.format(
            task=task[:500],
            subtask=subtask[:300],
            result=result.final_answer[:500],
            steps=steps_text,
        )
        
        return self._get_reflection(prompt)
    
    def extract_lesson(self, task: str, result: AgentResult, error: str) -> Optional[str]:
        """Extract a reusable lesson from a failed task."""
        prompt = (
            f"A task failed. Extract a lesson for future reference.\n\n"
            f"Task: {task[:500]}\n"
            f"Error: {error[:300]}\n"
            f"Steps taken: {result.thinking_trace()[:500]}\n\n"
            f"Provide a concise lesson (1-2 sentences) that would help "
            f"avoid this failure in the future. Just output the lesson text."
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
        """Get reflection from LLM with fallback."""
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
        """Default reflection when LLM is unavailable."""
        return Reflection(
            verdict=ReflectionVerdict.CONTINUE,
            critique=f"Could not analyze: {reason}",
            suggestion="Continue with current approach",
            confidence=0.3,
            lesson=None,
        )
```

### 2.4 `src/agent/learner.py` — Self-Learning from Mistakes

```python
"""
agent/learner.py — Self-Learning System

Learns from both successes and failures:
- Tracks failure patterns and their resolutions
- Stores "anti-patterns" (what NOT to do)
- Adapts prompts based on past experience
- Manages the lesson memory entries
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from core.config import cfg
from core.llm import LLMClient
from core.logger import get_logger

log = get_logger(__name__)


@dataclass
class Lesson:
    """A learned lesson from past experience."""
    id: str
    task_type: str         # Category of task this applies to
    lesson: str            # What was learned
    context: str           # When this applies
    source: str            # "failure" | "success" | "correction"
    confidence: float      # How reliable this lesson is
    times_applied: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class SelfLearner:
    """
    Manages the self-learning loop.
    
    Integrates with MemoryManager to:
    1. Store lessons after task completion
    2. Retrieve relevant lessons before similar tasks
    3. Track which lessons were helpful (and update confidence)
    4. Prune low-confidence or outdated lessons
    """
    
    LESSON_PROMPT = """Analyze this completed task and extract a lesson.

Task: {task}
Outcome: {outcome}
Key steps: {steps}

Provide a concise lesson (1-2 sentences) that would help in future similar tasks.
Focus on: approach that worked, pitfalls to avoid, or optimization tips.

Just output the lesson text, nothing else."""
    
    def __init__(self, llm: Optional[LLMClient] = None, memory_manager=None):
        self.llm = llm
        self.memory = memory_manager
        self._lesson_cache: Dict[str, List[str]] = {}
    
    def learn_from_result(self, task: str, result, was_corrected: bool = False):
        """
        Analyze a completed task and store lessons.
        
        Called by the agent after each task completes.
        """
        if not self.memory:
            return
        
        if not result.success:
            self._learn_from_failure(task, result)
        elif was_corrected:
            self._learn_from_correction(task, result)
        else:
            self._learn_from_success(task, result)
    
    def get_relevant_lessons(self, task: str, top_k: int = 3) -> List[str]:
        """
        Retrieve lessons relevant to the current task.
        Called before task execution to inform the agent.
        """
        if not self.memory:
            return []
        
        # Check cache first
        cache_key = self._cache_key(task)
        if cache_key in self._lesson_cache:
            return self._lesson_cache[cache_key][:top_k]
        
        try:
            # Search for lessons in memory
            results = self.memory.retrieve(
                f"lesson approach {task}",
                top_k=top_k * 2,
            )
            
            # Filter to lesson-type memories
            lessons = []
            for r in results:
                if any(keyword in r.lower() for keyword in [
                    "lesson", "approach", "pitfall", "avoid", "tip",
                    "lesson learned", "instead of", "should have",
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
        """
        Learn when the user corrects or redirects the agent.
        This is the strongest learning signal.
        """
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
                "importance": 0.9,  # User corrections are high importance
                "source": "user_correction",
                "task_type": self._classify_task(task),
            }
        )
        
        log.info("Learned from user correction: %s", task[:50])
    
    def _learn_from_failure(self, task: str, result):
        """Extract and store a lesson from a failed task."""
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
        """Store successful approach patterns."""
        if len(result.tools_used) < 2 or len(result.steps) < 3:
            return  # Too simple to learn from
        
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
        """Learn when the agent's output was accepted but with corrections."""
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
        """Simple rule-based task classification."""
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
        """Generate a cache key from task text."""
        words = task.lower().split()[:5]
        return "_".join(words)
```

### 2.5 `src/agent/user_model.py` — User Preference Learning

```python
"""
agent/user_model.py — User Preference Model

Learns and adapts to the user's communication style, preferences,
and working patterns over time.

Stores preference signals in memory as structured entries:
- Communication style (brief vs detailed, formal vs casual)
- Technical preferences (language, framework, coding style)
- Working patterns (time of day, typical tasks)
- Feedback signals (corrections, confirmations, complaints)
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from core.llm import LLMClient
from core.logger import get_logger

log = get_logger(__name__)


@dataclass
class UserPreference:
    """A single user preference signal."""
    category: str      # "communication" | "technical" | "workflow" | "personality"
    key: str           # e.g., "response_length", "language", "code_style"
    value: str         # e.g., "brief", "python", "functional"
    confidence: float  # 0.0 to 1.0
    source: str        # "explicit" | "inferred" | "corrected"


class UserModel:
    """
    Tracks and adapts to user preferences.
    
    Does NOT use a separate data store — piggybacks on MemoryManager
    with a "user_preference" memory type for simplicity.
    """
    
    PREF_EXTRACTION_PROMPT = """Analyze this conversation exchange and extract user preferences.

User said: {user_input}
Agent responded: {assistant_output}
{correction}

Extract any preference signals. Respond with JSON array:
[
  {{"category": "communication|technical|workflow", "key": "preference_name", "value": "the_preference", "confidence": 0.8}}
]

Only extract clear signals. Empty array if no preferences detected."""

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
        """
        Analyze an interaction for preference signals.
        Called after each user-assistant exchange.
        """
        if not self.llm or not self.memory:
            return
        
        # Only extract if there's meaningful content
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
        """
        Generate a prompt fragment with known user preferences.
        Injected into the system prompt for adaptation.
        """
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
        """Get a specific preference value."""
        if not self._loaded:
            self._load_preferences()
        
        for pref in self._preferences.values():
            if pref.key == key and pref.confidence >= 0.5:
                return pref.value
        return None
    
    def _store_preference(self, pref: UserPreference):
        """Store a preference in memory."""
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
        """Load cached preferences from memory."""
        self._loaded = True
        
        if not self.memory:
            return
        
        try:
            # This is a lightweight approach: retrieve recent memories
            # and filter for preference-type entries
            results = self.memory.retrieve("user preference likes prefers", top_k=20)
            
            for result in results:
                # Try to parse preference from memory text
                if "User preference:" in result:
                    # Simple parsing
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
```

### 2.6 `src/agent/self_reflect_loop.py` — Enhanced Agent Loop with Reflection

```python
"""
agent/self_reflect_loop.py — Enhanced Agent Loop

Wraps the existing Agent.run() with self-reflection at each step.
The reflector evaluates each tool call result and can:
1. Continue if successful
2. Retry with different parameters if failed
3. Replan if the approach is fundamentally wrong
4. Accept and finalize if the goal is met

This provides the "self-learning from mistakes" capability
without modifying the core Agent class.
"""

from typing import Optional

from agent.agent import Agent
from agent.base import AgentResult, AgentStep, StepType, StepStatus
from agent.reflector import SelfReflector, ReflectionVerdict
from core.llm import LLMClient
from core.logger import get_logger

log = get_logger(__name__)


class ReflectiveAgent:
    """
    An enhanced agent that reflects on each action.
    
    Usage:
        agent = ReflectiveAgent(llm, tool_registry, memory_manager, skill_manager)
        result = agent.run("Create a Python web scraper")
    
    The reflector is called after each tool execution to evaluate
    whether the action was effective and suggest corrections.
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
        self._reflector = SelfReflector(llm)
    
    def run(self, task: str, context: Optional[str] = None) -> AgentResult:
        """Run with self-reflection after each tool call."""
        # Create base agent
        agent = Agent(
            llm=self.llm,
            tool_registry=self.tool_registry,
            memory_store=self.memory_manager,
            skill_manager=self.skill_manager,
            router=self.router,
            on_step=self._wrapped_on_step,
        )
        
        # Store task for reflection context
        self._current_task = task
        
        # Run the base agent
        result = agent.run(task, context=context)
        
        # Post-execution reflection
        if result.steps:
            reflection = self._reflector.reflect_on_result(
                task=task,
                subtask=task,
                result=result,
            )
            
            # Store the lesson if the reflector found something useful
            if reflection.lesson and self.memory_manager:
                self.memory_manager.remember(
                    reflection.lesson,
                    metadata={
                        "memory_type": "lesson",
                        "importance": 0.7,
                        "source": "post_execution_reflection",
                    }
                )
        
        return result
    
    def _wrapped_on_step(self, step: AgentStep):
        """On-step callback that adds reflection context."""
        if self.on_step:
            self.on_step(step)
```

---

## 3. Modifications to Existing Files

### 3.1 `src/core/config.py` — Add Orchestration Config

**Add after `SkillsConfig` class (around line 73):**

```python
@dataclass
class OrchestrationConfig:
    enabled: bool = True
    complexity_threshold: str = "complex"  # When to use orchestrator vs single agent
    max_subtasks: int = 5
    max_retries_per_subtask: int = 1
    reflection_enabled: bool = True
    self_learning_enabled: bool = True
    user_model_enabled: bool = True
    max_lessons_retrieved: int = 3


@dataclass  
class SelfLearningConfig:
    enabled: bool = True
    learn_from_failures: bool = True
    learn_from_successes: bool = True
    learn_from_corrections: bool = True
    max_lessons: int = 200
    min_confidence: float = 0.5
```

**Add to `Config` dataclass (around line 119):**

```python
@dataclass
class Config:
    llm: LLMConfig = field(default_factory=LLMConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    skills: SkillsConfig = field(default_factory=SkillsConfig)
    tools: ToolsConfig = field(default_factory=ToolsConfig)
    interface: InterfaceConfig = field(default_factory=InterfaceConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    orchestration: OrchestrationConfig = field(default_factory=OrchestrationConfig)
    self_learning: SelfLearningConfig = field(default_factory=SelfLearningConfig)
```

**Add to `_build_config()` function:**

```python
orch_raw = raw.get("orchestration", {})
learn_raw = raw.get("self_learning", {})

# ... inside _build_config return statement:
orchestration=OrchestrationConfig(**{k: v for k, v in orch_raw.items() if k in OrchestrationConfig.__dataclass_fields__}),
self_learning=SelfLearningConfig(**{k: v for k, v in learn_raw.items() if k in SelfLearningConfig.__dataclass_fields__}),
```

### 3.2 `src/agent/session.py` — Route to Orchestrator for Complex Tasks

**Add import at top:**

```python
from agent.orchestrator import Orchestrator
from agent.reflector import SelfReflector
from agent.learner import SelfLearner
from agent.user_model import UserModel
```

**Modify `Session.__init__()` to add new subsystems (around line 88):**

```python
# Add after self.agent = Agent(...) setup:
self.orchestrator = None  # Lazy init
self.reflector = None     # Lazy init
self.learner = None       # Lazy init
self.user_model = None    # Lazy init
```

**Add to `_init_subsystems()` or create lazy init method:**

```python
def _init_advanced_systems(self):
    """Initialize orchestration and learning systems."""
    if cfg.orchestration.enabled:
        self.orchestrator = Orchestrator(
            llm=self.llm,
            tool_registry=self.tool_registry,
            memory_manager=self.memory_manager,
            skill_manager=self.skill_manager,
            router=self.router,
            on_step=self.on_step,
        )
    
    if cfg.orchestration.reflection_enabled:
        self.reflector = SelfReflector(self.llm)
    
    if cfg.self_learning.enabled:
        self.learner = SelfLearner(
            llm=self.llm,
            memory_manager=self.memory_manager,
        )
    
    if cfg.orchestration.user_model_enabled:
        self.user_model = UserModel(
            llm=self.llm,
            memory_manager=self.memory_manager,
        )
```

**Modify `_needs_agent()` to classify complexity:**

```python
def _needs_agent(self, text: str) -> str:
    """
    Returns: "chat" | "agent" | "orchestrator"
    
    Routes complex multi-step tasks to the orchestrator.
    """
    lower = text.lower()
    
    # Chat overrides always win
    if any(phrase in lower for phrase in CHAT_OVERRIDES):
        return "chat"
    
    # Check for orchestration triggers (complex tasks)
    ORCHESTRATOR_TRIGGERS = (
        "build", "create a", "set up", "implement", "design",
        "write a full", "create a complete", "scaffold",
        "refactor", "migrate", "integrate",
        "with tests", "with auth", "with database",
        "end to end", "full stack", "complete",
    )
    
    if any(trigger in lower for trigger in ORCHESTRATOR_TRIGGERS):
        if len(text.split()) > 15:  # Complex enough
            return "orchestrator"
    
    # Check agent triggers
    if any(trigger in lower for trigger in AGENT_TRIGGERS):
        return "agent"
    
    if any(lower.startswith(v) for v in ACTION_STARTERS):
        return "agent"
    
    if len(text.split()) > 25:
        return "orchestrator"  # Long requests are likely complex
    
    return "chat"
```

**Modify `send()` method to route to orchestrator:**

```python
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
```

**Add new method `_run_orchestrator()`:**

```python
def _run_orchestrator(self, user_input: str) -> AgentResult:
    """Run task through the multi-agent orchestrator."""
    self.messages.append(SessionMessage(role="user", content=user_input))
    
    # Initialize advanced systems on first use
    if self.orchestrator is None:
        self._init_advanced_systems()
    
    # Get relevant lessons
    context = None
    if self.learner:
        lessons = self.learner.get_relevant_lessons(user_input)
        if lessons:
            context = "Lessons from past experience:\n" + "\n".join(f"- {l}" for l in lessons)
    
    # Get user preferences
    if self.user_model:
        prefs_prompt = self.user_model.get_preferences_prompt()
        if prefs_prompt:
            context = (context or "") + "\n\n" + prefs_prompt
    
    # Run through orchestrator
    result = self.orchestrator.run(user_input, context=context)
    
    self.messages.append(SessionMessage(
        role="assistant", content=result.final_answer, agent_result=result,
    ))
    self.history.append(Message.user(user_input))
    self.history.append(Message.assistant(result.final_answer))
    
    # Learn from this interaction
    if self.learner:
        self.learner.learn_from_result(user_input, result)
    
    # Track user preferences
    if self.user_model:
        self.user_model.track_interaction(user_input, result.final_answer)
    
    return result
```

**Modify `_run_agent()` to add learning:**

```python
def _run_agent(self, user_input: str) -> AgentResult:
    # ... existing code ...
    
    # Add at the end, after result is obtained:
    
    # Learn from result
    if self.learner:
        self.learner.learn_from_result(user_input, result)
    
    # Track preferences
    if self.user_model:
        self.user_model.track_interaction(user_input, result.final_answer)
    
    return result
```

### 3.3 `src/agent/agent.py` — Inject Role Prompts

**Modify `Agent.__init__()` to accept role prompt (around line 23):**

```python
def __init__(
    self,
    llm: Optional[LLMClient] = None,
    tool_registry=None,
    memory_store=None,
    skill_manager=None,
    router=None,
    on_step: Optional[Callable[[AgentStep], None]] = None,
    role_prompt: Optional[str] = None,  # NEW: role-specific system prompt
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
    self._role_prompt = role_prompt  # NEW
```

**Modify `run()` method to use role prompt (around line 68):**

```python
system_prompt = self.prompt_builder.build_agent_prompt(
    tools=tool_names,
    tool_schemas=tool_schemas,
    memory_snippets=memory_snippets,
    skill_context=skill_context,
    role_prompt=self._role_prompt,  # NEW: pass role prompt
)
```

### 3.4 `src/core/prompt.py` — Support Role Prompt Injection

**Modify `build_agent_prompt()` to accept role_prompt (around line 111):**

```python
def build_agent_prompt(
    self,
    tools: Optional[List[str]] = None,
    tool_schemas: Optional[str] = None,
    memory_snippets: Optional[List[str]] = None,
    skill_context: Optional[str] = None,
    role_prompt: Optional[str] = None,  # NEW
) -> str:
    _, agent_soul = load_soul_from_file()
    
    # Add role-specific instructions
    role_section = ""
    if role_prompt:
        role_section = f"\n\nYour role: {role_prompt}\n"
    
    prompt_template = agent_soul + role_section + """

Date: {date}
Workspace: {workspace_path}

Context:
{memory_context}
{skill_context}

Reply as JSON only:
Tool call: {{"thought":"why","action":{{"tool":"name","input":{{"param":"value"}}}},"final_answer":null}}
Done: {{"thought":"why","action":{{"tool":null,"input":{{}}}},"final_answer":"short answer"}}

Tools (only use these): {tool_list}
{tool_schemas}"""

    return prompt_template.format(
        date=self._now(),
        workspace_path=self._workspace,
        tool_list=", ".join(tools) if tools else "none",
        memory_context=self._format_memory(memory_snippets),
        skill_context=skill_context or "",
        tool_schemas=tool_schemas or "(No tools available)",
    )
```

### 3.5 `src/interface/cli.py` — Add Learning Commands

**Add to dispatch table in `_handle_command()` (around line 176):**

```python
"/lessons":    self._cmd_lessons,
"/preferences": self._cmd_preferences,
"/reflect":    self._cmd_reflect,
```

**Add new command handlers:**

```python
def _cmd_lessons(self, _=""):
    """Show stored lessons from past experience."""
    if not self.memory:
        self.renderer.warning("Memory not available")
        return
    
    # Retrieve lesson-type memories
    try:
        results = self.memory.retrieve("lesson learned approach avoid", top_k=10)
        lessons = [r for r in results if any(kw in r.lower() for kw in [
            "lesson", "approach", "avoid", "pitfall", "instead",
        ])]
        
        if not lessons:
            self.renderer.info("No lessons stored yet. Complete some tasks first.")
            return
        
        self.renderer.console.print()
        self.renderer.console.print(
            f"  [content.skill]lessons learned[/content.skill]  "
            f"[ui.dim]{len(lessons)} stored[/ui.dim]\n"
        )
        for i, lesson in enumerate(lessons, 1):
            self.renderer.console.print(f"  [ui.dim]{i}.[/ui.dim] {lesson[:100]}")
        self.renderer.console.print()
    
    except Exception as e:
        self.renderer.error("Failed to retrieve lessons: " + str(e))

def _cmd_preferences(self, _=""):
    """Show learned user preferences."""
    if not self.session or not hasattr(self.session, 'user_model'):
        self.renderer.info("User model not available")
        return
    
    user_model = self.session.user_model
    if not user_model:
        self.renderer.info("User model not initialized")
        return
    
    prefs = user_model._preferences
    if not prefs:
        self.renderer.info("No preferences learned yet. Keep chatting!")
        return
    
    self.renderer.console.print()
    self.renderer.console.print("  [content.skill]learned preferences[/content.skill]\n")
    for key, pref in prefs.items():
        self.renderer.console.print(
            f"  [ui.dim]{pref.category}[/ui.dim] {pref.key}: "
            f"[content.answer]{pref.value}[/content.answer] "
            f"(confidence: {pref.confidence:.1f})"
        )
    self.renderer.console.print()

def _cmd_reflect(self, _=""):
    """Show reflection on the last task."""
    if not self.session or not self.session.messages:
        self.renderer.info("No recent tasks to reflect on")
        return
    
    last = self.session.messages[-1]
    if not last.agent_result:
        self.renderer.info("Last message was not an agent task")
        return
    
    result = last.agent_result
    self.renderer.console.print()
    self.renderer.console.print("  [content.skill]reflection[/content.skill]\n")
    self.renderer.console.print(f"  Task: {result.task[:80]}")
    self.renderer.console.print(f"  Success: {'yes' if result.success else 'no'}")
    self.renderer.console.print(f"  Steps: {result.total_steps}")
    self.renderer.console.print(f"  Tools used: {', '.join(result.tools_used) or 'none'}")
    
    if result.error:
        self.renderer.console.print(f"  [ui.warning]Error: {result.error}[/ui.warning]")
    self.renderer.console.print()
```

### 3.6 `config.yaml` — Add New Config Sections

```yaml
# Add to existing config.yaml:

orchestration:
  enabled: true
  complexity_threshold: "complex"
  max_subtasks: 5
  max_retries_per_subtask: 1
  reflection_enabled: true
  self_learning_enabled: true
  user_model_enabled: true
  max_lessons_retrieved: 3

self_learning:
  enabled: true
  learn_from_failures: true
  learn_from_successes: true
  learn_from_corrections: true
  max_lessons: 200
  min_confidence: 0.5
```

---

## 4. Orchestrator Design

### How the Orchestrator Coordinates Agents

The orchestrator does NOT run multiple agents in parallel. Instead:

1. **Decomposition Phase**: Uses a single LLM call to break the task into a dependency graph of 2-5 subtasks
2. **Sequential Execution**: Executes subtasks one at a time in topological order (respecting dependencies)
3. **Role Specialization**: Each subtask gets an `Agent` instance configured with a role-specific system prompt fragment (e.g., "You are a debugging specialist...")
4. **Context Passing**: Results from dependency subtasks are passed as context to dependent subtasks
5. **Synthesis**: After all subtasks complete, a synthesizer agent combines results into a final answer

### Key Design Decisions

- **No parallel execution**: Local 4B-8B models are too resource-consequential. One inference at a time.
- **Shared LLM instance**: All sub-agents share the same `LLMClient`. The model is hot-swapped via `switch_model()` only if different models are configured per role (future enhancement).
- **Role prompts as system prompt fragments**: No new inference pipeline needed. The role prompt is injected into the existing `build_agent_prompt()`.
- **Fallback to single agent**: If decomposition fails (LLM can't parse the task), gracefully falls back to the existing single-agent loop.

### Orchestrator State Machine

```
IDLE → DECOMPOSING → EXECUTING → SYNTHESIZING → DONE
  │         │              │              │
  │         └→ FAILED      └→ RETRYING    └→ LEARNING
  │                                    │
  └────────────────────────────────────┘ (fallback)
```

---

## 5. Planning & Decomposition

### How Planning Works

1. **Complexity Estimation**: Before decomposition, a quick LLM call classifies the task as "simple" or "complex". Simple tasks skip the orchestrator entirely.

2. **Decomposition**: The planner LLM receives the task and outputs a JSON plan with:
   - 2-5 subtasks, each with an ID, description, role, and dependencies
   - Circular dependency detection (and automatic resolution)
   - Role assignment based on task nature (code → coder, search → researcher, etc.)

3. **Recursive Decomposition**: If a subtask is classified as "complex" during execution, it can be further decomposed (not implemented in v1, but the architecture supports it).

4. **Dependency-Aware Execution**: Subtasks are executed in topological order. Results from dependency subtasks are injected as context into dependent subtasks.

### Example Decomposition

**Input**: "Build a Flask REST API with user authentication and unit tests"

**Plan**:
```
T1 (researcher): Research Flask auth best practices → []
T2 (coder): Create project structure and app.py → [T1]
T3 (coder): Implement auth endpoints → [T2]
T4 (coder): Write unit tests → [T3]
T5 (reviewer): Review code quality → [T4]
T6 (synthesizer): Combine into final summary → [T2, T3, T4, T5]
```

### Budget Constraints

For local 4B-8B models:
- Max 5 subtasks per decomposition
- Each subtask limited to `max_steps=10` (existing config)
- System prompts kept under 500 tokens to preserve context for reasoning
- Decomposition prompt itself is ~200 tokens, leaving ~3500+ tokens for the response

---

## 6. Self-Reflection & Mistake Learning

### Reflection Points

Self-reflection occurs at three points:

1. **After each tool call** (in the existing agent loop): The reflector evaluates whether the tool call achieved its goal. This is injected as a structured evaluation in the THINK step.

2. **After each subtask** (in the orchestrator): The reflector evaluates whether the subtask result is acceptable. Based on the verdict (continue/retry/replan), the orchestrator decides next steps.

3. **After task completion** (post-execution): A final reflection extracts lessons learned and stores them in memory.

### Reflection Flow

```
Tool call executed
       │
       ▼
Reflector.analyze(task, action, tool, result)
       │
       ├─ verdict=CONTINUE → proceed to next step
       ├─ verdict=RETRY → agent retries with modified parameters
       ├─ verdict=REPLAN → orchestrator creates new plan
       └─ verdict=ACCEPT → finalize answer
```

### Lesson Storage

Lessons are stored as memory entries with `memory_type: "lesson"`:

```python
memory_manager.remember(
    "When creating Flask apps, always add CORS middleware first. "
    "Past attempts failed because CORS wasn't configured.",
    metadata={
        "memory_type": "lesson",
        "importance": 0.8,
        "source": "failure",
        "task_type": "code",
    }
)
```

### Lesson Retrieval

Before executing a similar task, the learner queries memory for relevant lessons:

```python
lessons = memory.retrieve("lesson approach create flask app", top_k=3)
# → ["When creating Flask apps, always add CORS middleware first..."]
```

These are injected into the system prompt as context.

### Learning Sources

| Source | Importance | Trigger |
|--------|-----------|---------|
| Failure | 0.85 | Task fails or errors out |
| User correction | 0.90 | User says "no, do X instead" |
| Success | 0.60 | Multi-step task completes successfully |
| Post-reflection | 0.70 | Reflector identifies improvement opportunity |

---

## 7. User Preference Learning

### What Gets Tracked

| Category | Example Keys | Example Values |
|----------|-------------|----------------|
| Communication | response_length | brief / detailed |
| Communication | formality | casual / formal |
| Technical | preferred_language | python / typescript |
| Technical | code_style | functional / oop |
| Workflow | verification_level | thorough / quick |
| Workflow | explanation_style | step-by-step / summary |

### How Preferences Are Learned

1. **Inferred from interaction**: After each exchange, the LLM analyzes the conversation for preference signals
2. **From corrections**: When the user corrects the agent's approach, the correction is stored as a high-confidence preference
3. **Explicit**: User can say "I prefer brief responses" → stored as explicit preference

### How Preferences Are Applied

Preferences are injected into the system prompt:

```
Known user preferences:
  - response_length: brief (communication)
  - preferred_language: python (technical)
  - code_style: functional (technical)
```

The base agent identity already includes personality examples, but user preferences add personalization on top.

---

## 8. CLI & Config Integration

### New CLI Commands

| Command | Description |
|---------|-------------|
| `/lessons` | Show stored lessons from past experience |
| `/preferences` | Show learned user preferences |
| `/reflect` | Show reflection on the last task |
| `/orchestrate` | Force orchestrator mode for next message |
| `/plan` | Show the decomposition plan for the last complex task |

### Config Changes

**New config.yaml sections:**

```yaml
orchestration:
  enabled: true                    # Master switch
  max_subtasks: 5                  # Max decomposition depth
  reflection_enabled: true         # Enable self-reflection
  self_learning_enabled: true      # Enable lesson storage
  user_model_enabled: true         # Enable preference learning

self_learning:
  enabled: true
  learn_from_failures: true
  learn_from_successes: true
  max_lessons: 200                 # Cap stored lessons
```

### Backward Compatibility

- All new features are gated behind config flags
- Setting `orchestration.enabled: false` disables everything new
- The existing `Agent.run()` loop is completely unchanged
- The existing `Session.send()` routing still works (orchestrator is an additional route, not a replacement)
- New config fields have defaults that match current behavior

---

## 9. Testing Approach

### Unit Tests

| File | What to Test |
|------|-------------|
| `tests/test_orchestrator.py` | Plan decomposition, subtask execution order, dependency resolution, fallback to single agent |
| `tests/test_planner.py` | Task decomposition, circular dependency detection, complexity estimation |
| `tests/test_reflector.py` | Reflection verdict parsing, lesson extraction, default fallback |
| `tests/test_learner.py` | Lesson storage/retrieval, task classification, cache behavior |
| `tests/test_user_model.py` | Preference extraction, storage, prompt generation |
| `tests/test_session_routing.py` | Mode selection (chat/agent/orchestrator) for various inputs |

### Integration Tests

| Test | Description |
|------|-------------|
| `test_simple_task_unaffected` | Verify simple tasks still go through single-agent path |
| `test_orchestrator_end_to_end` | Full orchestrator flow with mocked LLM |
| `test_lesson_cycling` | Verify lessons are stored after failure, retrieved before similar task |
| `test_preference_adaptation` | Verify user preferences appear in system prompt |
| `test_fallback_resilience` | Verify graceful degradation when orchestrator fails |

### Mock Strategy

Since all LLM calls go through `LLMClient`, mock it with pre-canned responses:

```python
class MockLLM:
    def __init__(self, responses):
        self._responses = list(responses)
        self._call_count = 0
    
    def chat_json(self, prompt, **kwargs):
        resp = self._responses[self._call_count]
        self._call_count += 1
        return resp
    
    def chat(self, prompt, **kwargs):
        return MockResponse(content="mock response")
```

### Test Configuration

```python
# tests/conftest.py
@pytest.fixture
def mock_llm():
    return MockLLM(responses=[
        {"complexity": "complex", "reason": "multi-step task"},
        {"subtasks": [
            {"id": "T1", "description": "Research", "role": "researcher", "dependencies": []},
            {"id": "T2", "description": "Implement", "role": "coder", "dependencies": ["T1"]},
        ]},
        # ... more responses as needed
    ])

@pytest.fixture
def agent_with_orchestration(mock_llm, mock_registry, mock_memory):
    session = Session(llm=mock_llm, tool_registry=mock_registry, memory_manager=mock_memory)
    session._init_advanced_systems()
    return session
```

---

## 10. Implementation Order

### Phase 1: Foundation (Week 1)
1. Add config dataclasses (`OrchestrationConfig`, `SelfLearningConfig`)
2. Create `agent/reflector.py` — self-reflection engine
3. Create `agent/learner.py` — self-learning from mistakes
4. Write unit tests for reflector and learner

### Phase 2: Orchestration (Week 2)
5. Create `agent/planner.py` — task decomposer
6. Create `agent/orchestrator.py` — multi-agent coordinator
7. Modify `core/prompt.py` — role prompt injection
8. Modify `agent/agent.py` — accept role_prompt parameter
9. Write unit tests for planner and orchestrator

### Phase 3: Integration (Week 3)
10. Modify `agent/session.py` — routing and advanced system init
11. Add learning hooks to `_run_agent()` and `_run_chat()`
12. Create `agent/user_model.py` — preference learning
13. Modify `interface/cli.py` — add new commands
14. Write integration tests

### Phase 4: Polish (Week 4)
15. Add `config.yaml` defaults
16. Update documentation
17. End-to-end testing with real Ollama models
18. Performance profiling (ensure latency is acceptable)
19. Tune prompts based on real model behavior

---

## File Inventory

### New Files (6)
```
src/agent/orchestrator.py      — Multi-agent coordinator
src/agent/planner.py           — Task decomposer
src/agent/reflector.py         — Self-reflection engine
src/agent/learner.py           — Self-learning from mistakes
src/agent/user_model.py        — User preference learning
src/agent/self_reflect_loop.py — Enhanced agent loop (optional wrapper)
```

### Modified Files (6)
```
src/core/config.py             — Add orchestration/learning config
src/core/prompt.py             — Role prompt injection
src/agent/agent.py             — Accept role_prompt parameter
src/agent/session.py           — Routing + advanced system init
src/interface/cli.py           — New commands (/lessons, /preferences, /reflect)
config.yaml                    — New config sections
```

### Test Files (6)
```
tests/test_orchestrator.py
tests/test_planner.py
tests/test_reflector.py
tests/test_learner.py
tests/test_user_model.py
tests/test_session_routing.py
```
