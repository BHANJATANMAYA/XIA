"""
test_agent.py — Verify Part 4 agent loop is working.

Run with:
    .venv\Scripts\python test_agent.py
"""

import sys
from pathlib import Path

root = Path(__file__).parent
sys.path.insert(0, str(root))


def check(label, condition, fix=""):
    status = "  OK  " if condition else " FAIL "
    symbol = "✓" if condition else "✗"
    print(f"  [{status}] {symbol} {label}")
    if not condition and fix:
        print(f"         → {fix}")
    return condition


def main():
    all_ok = True

    print()
    print("=" * 55)
    print("  xia — Part 4 Agent Loop Verification")
    print("=" * 55)

    # ── File checks ────────────────────────────────────────────────────────
    print("\n[ New files ]")
    files = [
        "agent/base.py",
        "agent/agent.py",
        "agent/session.py",
    ]
    for f in files:
        all_ok &= check(f, (root / f).exists(), f"Copy {f} from Part 4 scaffold")

    # ── Import checks ──────────────────────────────────────────────────────
    print("\n[ Imports ]")
    try:
        from agent.base import AgentDecision, AgentResult, AgentStep, StepType, ToolCall
        all_ok &= check("agent.base imports", True)
    except ImportError as e:
        all_ok &= check("agent.base imports", False, str(e))
        _summary(all_ok); return

    try:
        from agent.agent import Agent
        all_ok &= check("agent.agent imports", True)
    except ImportError as e:
        all_ok &= check("agent.agent imports", False, str(e))
        _summary(all_ok); return

    try:
        from agent.session import Session
        all_ok &= check("agent.session imports", True)
    except ImportError as e:
        all_ok &= check("agent.session imports", False, str(e))
        _summary(all_ok); return

    # ── Data type tests ────────────────────────────────────────────────────
    print("\n[ Agent data types ]")
    from agent.base import AgentDecision, ToolCall

    # Test from_dict with tool call
    d1 = AgentDecision.from_dict({
        "thought": "I need to check files",
        "plan": ["Step 1", "Step 2"],
        "action": {"tool": "filesystem", "input": {"path": "."}},
        "final_answer": None,
    })
    all_ok &= check("AgentDecision.from_dict() with tool", d1.has_tool_call)
    all_ok &= check("Tool name parsed correctly", d1.tool_call.name == "filesystem")
    all_ok &= check("is_done is False when no final_answer", not d1.is_done)

    # Test from_dict with final answer
    d2 = AgentDecision.from_dict({
        "thought": "Done",
        "plan": [],
        "action": {"tool": None, "input": {}},
        "final_answer": "Here is your answer.",
    })
    all_ok &= check("AgentDecision final_answer parsed", d2.final_answer == "Here is your answer.")
    all_ok &= check("is_done is True with final_answer", d2.is_done)
    all_ok &= check("has_tool_call is False with null tool", not d2.has_tool_call)

    # ── Agent without tools (knowledge-only) ──────────────────────────────
    print("\n[ Agent (no tools, Ollama required) ]")

    from core.llm import LLMClient
    llm = LLMClient()
    if not llm.is_available():
        print("  [ SKIP ] Ollama not running — skipping live agent tests")
        print("           Start Ollama and re-run to test fully")
        _summary(all_ok)
        return

    all_ok &= check("Ollama available", True)

    # Test agent on a simple task that needs no tools
    from agent.agent import Agent
    steps_received = []

    def capture_step(step):
        steps_received.append(step)

    agent = Agent(llm=llm, on_step=capture_step)

    print("  Running agent on simple task (no tools needed)...")
    print("  Task: 'What is 15 multiplied by 7? Just give the number.'")

    result = agent.run("What is 15 multiplied by 7? Just give the number.")

    all_ok &= check("Agent returned a result", result is not None)
    all_ok &= check("Agent has a final_answer", bool(result.final_answer))
    all_ok &= check("Agent succeeded", result.success)
    all_ok &= check("Steps were recorded", len(result.steps) > 0)
    all_ok &= check("on_step callback fired", len(steps_received) > 0)

    print(f"         Answer  : {result.final_answer.strip()[:80]}")
    print(f"         Steps   : {len(result.steps)}")
    print(f"         Callback: {len(steps_received)} calls")

    # ── Session routing ────────────────────────────────────────────────────
    print("\n[ Session routing ]")
    from agent.session import Session, AGENT_TRIGGERS

    session = Session(llm=llm, on_step=capture_step)

    # Test routing logic
    simple  = session._needs_agent("what is the capital of France?")
    complex = session._needs_agent("find all Python files in my project folder")
    all_ok &= check("Simple question routes to chat (not agent)", not simple)
    all_ok &= check("File task routes to agent", complex)

    # Test simple chat via session
    print("  Running simple chat via session...")
    result2 = session.send("What colour is the sky? One word.")
    all_ok &= check("Session.send() works for simple chat", bool(result2.final_answer))
    print(f"         Response: {result2.final_answer.strip()[:60]}")

    # Test session save
    save_path = session.save()
    all_ok &= check("Session.save() creates file", save_path.exists())

    _summary(all_ok)


def _summary(all_ok):
    print()
    print("=" * 55)
    if all_ok:
        print("  All checks passed — ready for Part 5!")
        print("  Try it: launch.bat")
    else:
        print("  Some checks failed — see details above.")
    print("=" * 55)
    print()
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
