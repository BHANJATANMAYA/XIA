"""
test_final.py — Complete xia System Verification

Runs a full end-to-end check of all 10 parts.
Run this to confirm your xia installation is complete and healthy.

    .venv\Scripts\python test_final.py
"""

import sys
import os
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


def section(title):
    print(f"\n[ {title} ]")


def main():
    all_ok = True
    print()
    print("=" * 60)
    print("  xia — Complete System Verification (All 10 Parts)")
    print("=" * 60)

    # ── Part 1: Scaffold ───────────────────────────────────────────────────
    section("Part 1 — Scaffold & SSD layout")
    dirs = ["core", "agent", "tools", "memory", "skills",
            "interface", "models", "logs", "workspace",
            "data/conversations", "data/embeddings", "data/skills_store"]
    for d in dirs:
        all_ok &= check(d, (root / d).exists())

    files = ["config.yaml", "requirements.txt", "main.py",
             "core/paths.py", "core/config.py", "core/logger.py"]
    for f in files:
        all_ok &= check(f, (root / f).exists())

    # ── Part 2: Launcher ───────────────────────────────────────────────────
    section("Part 2 — Launcher")
    all_ok &= check("launch.bat", (root / "launch.bat").exists())
    all_ok &= check("launch.py",  (root / "launch.py").exists())
    all_ok &= check(".venv exists", (root / ".venv").exists(),
                    "Run launch.bat to create it")
    all_ok &= check(".venv/Scripts/python.exe",
                    (root / ".venv/Scripts/python.exe").exists())

    # ── Part 3: LLM ───────────────────────────────────────────────────────
    section("Part 3 — Local LLM (Ollama)")
    all_ok &= check("core/llm.py",    (root / "core/llm.py").exists())
    all_ok &= check("core/prompt.py", (root / "core/prompt.py").exists())
    try:
        from core.llm import LLMClient
        llm = LLMClient()
        ollama_ok = llm.is_available()
        all_ok &= check(f"Ollama reachable + model '{llm.model}' loaded", ollama_ok,
                        f"Run: ollama pull {llm.model}")
        if ollama_ok:
            models = llm.list_models()
            check(f"Models available ({len(models)})", len(models) > 0)
    except Exception as e:
        all_ok &= check("LLM client", False, str(e))
        ollama_ok = False

    # ── Part 4: Agent loop ─────────────────────────────────────────────────
    section("Part 4 — Agentic loop")
    for f in ["agent/base.py", "agent/agent.py", "agent/session.py"]:
        all_ok &= check(f, (root / f).exists())
    try:
        from agent.base import AgentDecision, AgentResult
        from agent.agent import Agent
        from agent.session import Session
        all_ok &= check("Agent classes import", True)
        d = AgentDecision.from_dict({"thought":"t","plan":[],"action":{"tool":None,"input":{}},"final_answer":"ok"})
        all_ok &= check("AgentDecision parses correctly", d.is_done)
    except Exception as e:
        all_ok &= check("Agent imports", False, str(e))

    # ── Part 5: Tools ─────────────────────────────────────────────────────
    section("Part 5 — Tool system")
    for f in ["tools/base.py", "tools/registry.py",
              "tools/filesystem.py", "tools/terminal.py"]:
        all_ok &= check(f, (root / f).exists())
    try:
        from tools.registry import build_default_registry
        reg = build_default_registry()
        all_ok &= check("filesystem tool registered", "filesystem" in reg.list_names())
        all_ok &= check("terminal tool registered",   "terminal"   in reg.list_names())
        # Quick filesystem test
        from tools.filesystem import FilesystemTool
        fs = FilesystemTool()
        r = fs.execute(action="exists", path=str(root))
        all_ok &= check("filesystem.exists() works", r.success)
    except Exception as e:
        all_ok &= check("Tools", False, str(e))

    # ── Part 6: Search ────────────────────────────────────────────────────
    section("Part 6 — Web search")
    for f in ["tools/search.py", "tools/fetch.py"]:
        all_ok &= check(f, (root / f).exists())
    try:
        from tools.search import SearchTool
        from tools.fetch import FetchTool
        all_ok &= check("search + fetch import", True)
        reg2 = build_default_registry()
        all_ok &= check("search tool registered", "search" in reg2.list_names())
        all_ok &= check("fetch tool registered",  "fetch"  in reg2.list_names())
    except Exception as e:
        all_ok &= check("Search tools", False, str(e))

    # ── Part 7: Memory ────────────────────────────────────────────────────
    section("Part 7 — Persistent memory")
    for f in ["memory/embedder.py", "memory/store.py",
              "memory/extractor.py", "memory/manager.py"]:
        all_ok &= check(f, (root / f).exists())
    try:
        from memory.embedder import Embedder
        from memory.manager import MemoryManager
        e = Embedder()
        all_ok &= check("Embedding model loads", e.is_available(),
                        "Run: pip install sentence-transformers")
        if e.is_available():
            v = e.embed("test")
            all_ok &= check("embed() returns 384-dim vector", len(v) == 384)
        m = MemoryManager(llm=None)
        all_ok &= check("MemoryManager initialises", m.is_available(),
                        "Run: pip install chromadb")
    except Exception as e:
        all_ok &= check("Memory system", False, str(e))

    # ── Part 8: Skills ────────────────────────────────────────────────────
    section("Part 8 — Skill system")
    for f in ["skills/schema.py", "skills/store.py",
              "skills/extractor.py", "skills/manager.py"]:
        all_ok &= check(f, (root / f).exists())
    try:
        from skills.schema import Skill
        from skills.manager import SkillManager
        sm = SkillManager(llm=None)
        all_ok &= check("SkillManager initialises", True)
    except Exception as e:
        all_ok &= check("Skills system", False, str(e))

    # ── Part 9: CLI ───────────────────────────────────────────────────────
    section("Part 9 — Rich CLI")
    for f in ["interface/theme.py", "interface/renderer.py", "interface/cli.py"]:
        all_ok &= check(f, (root / f).exists())
    try:
        from interface.renderer import Renderer
        from interface.cli import CLI
        r = Renderer()
        all_ok &= check("Renderer + CLI import", True)
    except Exception as e:
        all_ok &= check("CLI", False, str(e))

    # ── Part 10: Robustness ───────────────────────────────────────────────
    section("Part 10 — Robustness & portability")
    for f in ["core/health.py", "core/host.py", "core/errors.py"]:
        all_ok &= check(f, (root / f).exists())
    try:
        from core.health import HealthChecker
        from core.host import HostInfo
        from core.errors import XiaError, handle_error
        h = HostInfo()
        all_ok &= check(f"Host detected: {h.summary()}", True)
        checker = HealthChecker()
        ok_flag, issues = checker.run()
        errors = [i for i in issues if i.level == "error"]
        warns  = [i for i in issues if i.level == "warning"]
        all_ok &= check(f"Health check: {len(errors)} errors, {len(warns)} warnings",
                        len(errors) == 0,
                        "See health check output above for details")
    except Exception as e:
        all_ok &= check("Robustness modules", False, str(e))

    # ── Live agent test (Ollama required) ─────────────────────────────────
    if ollama_ok:
        section("Live end-to-end agent test")
        try:
            from tools.registry import build_default_registry
            from memory.manager import MemoryManager
            from skills.manager import SkillManager
            from agent.session import Session

            registry = build_default_registry()
            memory   = MemoryManager(llm=llm)
            skills   = SkillManager(llm=llm)
            session  = Session(
                llm=llm,
                tool_registry=registry,
                memory_manager=memory,
                skill_manager=skills,
            )

            result = session.send("what is the capital of France?")
            all_ok &= check("Simple question answered", result.success)
            has_paris = "Paris" in result.final_answer
            all_ok &= check("Answer is correct (contains 'Paris')", has_paris)
            print(f"         Answer: {result.final_answer[:80]}")

        except Exception as e:
            all_ok &= check("Live agent test", False, str(e))

    # ── Summary ───────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    if all_ok:
        print()
        print("  ✓  xia is fully operational.")
        print()
        print("  Launch with:   launch.bat")
        print()
        print("  What xia can do:")
        print("    · Answer questions from its local LLM")
        print("    · Create, read, write, and manage files")
        print("    · Run terminal commands")
        print("    · Search the web and fetch pages")
        print("    · Remember you across sessions (ChromaDB)")
        print("    · Learn reusable skills from your tasks")
        print("    · Work on any Windows machine from your SSD")
        print()
        print("  Commands inside xia:")
        print("    /memory    /skills    /tools    /help")
        print()
    else:
        print()
        print("  Some checks failed. Fix the issues above and re-run.")
        print()
    print("=" * 60)
    print()

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
