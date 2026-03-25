"""
interface/cli.py — xia CLI
"""

import subprocess
import sys
import os
from typing import Any, Callable, Dict, Optional

from rich.prompt import Prompt

from core.config import cfg
from core.logger import get_logger
from core.paths import PATHS
from interface.renderer import Renderer

log = get_logger(__name__)


class CLI:
    def __init__(self):
        self.renderer = Renderer()
        self.session:  Optional[Any] = None
        self.registry: Optional[Any] = None
        self.memory:   Optional[Any] = None
        self.skills:   Optional[Any] = None
        self.llm:      Optional[Any] = None
        self.router:   Optional[Any] = None

    def run(self):
        if sys.platform == "win32":
            os.system("")
        self._init_subsystems()
        self._print_startup()
        self._main_loop()

    def _init_subsystems(self):
        from core.llm import LLMClient
        from core.router import ModelRouter
        from tools.registry import build_default_registry
        from memory.manager import MemoryManager
        from skills.manager import SkillManager
        from agent.session import Session

        # LLM
        self.renderer.print_connecting("connecting to ollama")
        self.llm = LLMClient()
        if not self.llm.is_available():
            self.renderer.print_failed("model '" + cfg.llm.model + "' not found")
            self.renderer.error("Run: ollama pull " + cfg.llm.model)
            sys.exit(1)
        self.renderer.print_ok(cfg.llm.model)

        # Tools
        self.renderer.print_connecting("loading tools")
        self.registry = build_default_registry(llm=self.llm)
        self.renderer.print_ok(", ".join(self.registry.list_names()))

        # Memory
        self.renderer.print_connecting("loading memory")
        try:
            self.memory = MemoryManager(llm=self.llm)
            self.renderer.print_ok(str(self.memory.count()) + " memories")
        except Exception as e:
            log.warning("Memory unavailable: %s", e)
            self.memory = None
            self.renderer.print_failed("continuing without memory")

        # Skills
        self.renderer.print_connecting("loading skills")
        try:
            self.skills = SkillManager(llm=self.llm)
            self.renderer.print_ok(str(self.skills.count()) + " skills")
        except Exception as e:
            log.warning("Skills unavailable: %s", e)
            self.skills = None
            self.renderer.print_failed("continuing without skills")

        # Router
        self.router = ModelRouter(self.llm)
        available = self.router.available_models()
        self.renderer.info("models available: " + ", ".join(available))

        # Session
        self.session = Session(
            llm=self.llm,
            tool_registry=self.registry,
            memory_manager=self.memory,
            skill_manager=self.skills,
            router=self.router,
            on_step=self.renderer.print_step,
        )
        log.info("CLI fully initialised")

    def _print_startup(self):
        self.renderer.print_banner(
            model=cfg.llm.model,
            root=str(PATHS.root),
            mem_count=self.memory.count() if self.memory else 0,
            skill_count=self.skills.count() if self.skills else 0,
        )
        if self.memory and self.memory.count() > 0:
            recent = self.memory.recent(3)
            if recent:
                self.renderer.info("remembered from last session:")
                for m in recent:
                    self.renderer.console.print("  [ui.dim]  · " + m[:70] + "[/ui.dim]")
                self.renderer.console.print()
        self.renderer.print_ready(self.registry.list_names())

    def _main_loop(self):
        while True:
            try:
                user_input = Prompt.ask(
                    "  [ui.prompt]you[/ui.prompt]",
                    console=self.renderer.console,
                )
            except (KeyboardInterrupt, EOFError):
                self._shutdown()
                return

            user_input = user_input.strip()
            if not user_input:
                continue

            if user_input.startswith("/"):
                self._handle_command(user_input)
                continue

            self._handle_message(user_input)

    def _handle_message(self, user_input: str):
        self.renderer.reset_step_count()
        self.renderer.console.print()
        try:
            with self.renderer.console.status("  [ui.dim]thinking...[/ui.dim]", spinner="dots", spinner_style="ui.dim"):
                result = self.session.send(user_input)
                
            self.renderer.print_answer(
                answer=result.final_answer,
                tools_used=result.tools_used if result.tools_used else None,
            )
        except KeyboardInterrupt:
            self.renderer.warning("interrupted")
            self.renderer.console.print()
        except Exception as e:
            log.exception("Error handling message")
            self.renderer.error("Unexpected error: " + str(e))
            self.renderer.console.print()

    def _handle_command(self, raw: str):
        parts = raw.strip().split(None, 1)
        cmd   = parts[0].lower()
        args  = parts[1] if len(parts) > 1 else ""

        dispatch: Dict[str, Callable] = {
            "/exit":     self._cmd_exit,
            "/quit":     self._cmd_exit,
            "/q":        self._cmd_exit,
            "/end":      self._cmd_end,
            "/clear":    self._cmd_clear,
            "/save":     self._cmd_save,
            "/memory":   self._cmd_memory,
            "/remember": self._cmd_remember,
            "/forget":   self._cmd_forget,
            "/skills":   self._cmd_skills,
            "/tools":    self._cmd_tools,
            "/model":    self._cmd_model,
            "/models":   self._cmd_models,
            "/profile":  self._cmd_profile,
            "/history":  self._cmd_history,
            "/help":     self._cmd_help,
        }

        handler = dispatch.get(cmd)
        if handler:
            handler(args)
        else:
            self.renderer.warning("Unknown command: " + cmd + "  (type /help)")

    def _cmd_exit(self, _=""):
        self._shutdown()
        sys.exit(0)

    def _cmd_end(self, _=""):
        """Save session, stop Ollama, then exit everything."""
        self._shutdown()
        self._kill_ollama()
        sys.exit(0)

    def _cmd_clear(self, _=""):
        self.session.clear_history()
        self.renderer.success("conversation history cleared")
        self.renderer.console.print()

    def _cmd_save(self, _=""):
        try:
            path = self.session.save()
            self.renderer.print_session_saved(path)
        except Exception as e:
            self.renderer.error("Save failed: " + str(e))
        self.renderer.console.print()

    def _cmd_memory(self, _=""):
        if not self.memory:
            self.renderer.warning("Memory not available")
            return
        total  = self.memory.count()
        recent = self.memory.recent(8)
        self.renderer.print_memories(recent, total)

    def _cmd_remember(self, fact: str):
        if not fact.strip():
            self.renderer.warning("Usage: /remember <fact to store>")
            return
        if self.memory:
            self.memory.remember(fact.strip(), metadata={"source": "manual"})
            self.renderer.success("remembered: " + fact.strip())
        else:
            self.renderer.warning("Memory not available")
        self.renderer.console.print()

    def _cmd_forget(self, _=""):
        if not self.memory:
            self.renderer.warning("Memory not available")
            return
        self.renderer.warning("This will delete ALL stored memories.")
        confirm = Prompt.ask(
            "  [ui.warning]confirm[/ui.warning]",
            choices=["yes", "no"],
            default="no",
            console=self.renderer.console,
        )
        if confirm == "yes":
            self.memory.clear()
            self.renderer.success("all memories cleared")
        else:
            self.renderer.info("cancelled")
        self.renderer.console.print()

    def _cmd_skills(self, _=""):
        if not self.skills:
            self.renderer.warning("Skills not available")
            return
        self.renderer.print_skills(self.skills.list_all())

    def _cmd_tools(self, _=""):
        self.renderer.console.print()
        for name in self.registry.list_names():
            tool = self.registry.get(name)
            self.renderer.console.print(
                "  [content.tool]" + name + "[/content.tool]  "
                "[ui.muted]" + tool.description[:60] + "[/ui.muted]"
            )
        self.renderer.console.print()

    def _cmd_model(self, model_name: str):
        if not model_name.strip():
            self.renderer.info("current model: " + self.llm.model)
            self.renderer.info("use /models to see all available models")
            return
        self.llm.switch_model(model_name.strip())
        if self.router:
            self.router.refresh()
        self.renderer.success("switched to: " + model_name.strip())
        self.renderer.console.print()

    def _cmd_models(self, _=""):
        from rich.table import Table
        from rich import box
        from core.router import PROFILES

        available = self.llm.list_models()
        current   = self.llm.model

        self.renderer.console.print()
        self.renderer.console.print(
            "  [content.skill]models[/content.skill]  "
            "[ui.dim]" + str(len(available)) + " available  |  auto-routing active[/ui.dim]\n"
        )

        table = Table(box=box.SIMPLE, show_header=True,
                      header_style="ui.label", padding=(0, 1))
        table.add_column("", width=3)
        table.add_column("model", style="ui.value", width=28)
        table.add_column("best for", style="ui.dim")

        for m in available:
            marker = "[ui.success]●[/ui.success]" if m.replace(":latest", "") == current else " "
            m_clean = m.replace(":latest", "")
            profile = "general"
            for pname, pdata in PROFILES.items():
                if any(m_clean.startswith(p.split(":")[0]) for p in pdata["preferred"]):
                    profile = pname
                    break
            table.add_row(marker, m, profile)

        self.renderer.console.print(table)
        self.renderer.console.print(
            "\n  [ui.dim]switch: /model <name>  |  profiles: /profile[/ui.dim]\n"
        )

    def _cmd_profile(self, profile_name: str):
        from core.router import PROFILES, ModelRouter

        if not profile_name.strip():
            self.renderer.console.print()
            self.renderer.console.print("  [content.skill]profiles[/content.skill]\n")
            router = ModelRouter(self.llm)
            for name, data in PROFILES.items():
                best_model, _ = router.pick(name)
                self.renderer.console.print(
                    "  [content.skill]" + name + "[/content.skill]"
                    "  [ui.muted]" + data["description"] + "[/ui.muted]"
                )
                self.renderer.console.print(
                    "  [ui.dim]" + (" " * len(name)) + "  will use: " + best_model + "[/ui.dim]\n"
                )
            self.renderer.console.print(
                "  [ui.dim]usage: /profile <name>[/ui.dim]\n"
            )
            return

        name = profile_name.strip().lower()
        if name not in PROFILES:
            self.renderer.warning("Unknown profile '" + name + "'. Available: " + ", ".join(PROFILES))
            return

        router = ModelRouter(self.llm)
        best_model, _ = router.pick(name)
        self.llm.switch_model(best_model)
        self.llm.temperature = PROFILES[name]["temperature"]
        if self.router:
            self.router.refresh()
        self.renderer.success(
            "profile: " + name + "  →  model: " + best_model +
            "  (temp: " + str(PROFILES[name]["temperature"]) + ")"
        )
        self.renderer.console.print()

    def _cmd_history(self, _=""):
        count = len(self.session.messages)
        self.renderer.info(str(count) + " messages this session")
        self.renderer.console.print()

    def _cmd_help(self, _=""):
        self.renderer.print_help()

    def _shutdown(self):
        self.renderer.console.print()
        self.renderer.info("saving session...")
        try:
            path = self.session.save()
            self.renderer.print_session_saved(path)
        except Exception as e:
            self.renderer.warning("could not save session: " + str(e))
        self.renderer.console.print()
        self.renderer.console.rule("[xia.name]goodbye[/xia.name]", style="dim cyan")
        self.renderer.console.print()

    def _kill_ollama(self):
        """Forcefully stop the Ollama background process."""
        self.renderer.info("stopping ollama...")
        try:
            if sys.platform == "win32":
                result = subprocess.run(
                    ["taskkill", "/IM", "ollama.exe", "/F"],
                    capture_output=True, text=True,
                )
                killed = result.returncode == 0
            else:
                result = subprocess.run(
                    ["pkill", "-f", "ollama"],
                    capture_output=True, text=True,
                )
                killed = result.returncode == 0

            if killed:
                self.renderer.success("ollama stopped")
            else:
                self.renderer.warning("ollama was not running (or could not be stopped)")
        except FileNotFoundError:
            self.renderer.warning("could not find taskkill/pkill — ollama may still be running")
        except Exception as e:
            self.renderer.warning("could not stop ollama: " + str(e))
        self.renderer.console.print()
