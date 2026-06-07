"""
interface/cli.py — xia CLI
"""

import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from rich.prompt import Prompt

from core.config import cfg
from core.logger import get_logger
from core.paths import PATHS
from interface.renderer import Renderer

log = get_logger(__name__)


class CLI:
    def __init__(self):
        self.renderer = Renderer()
        self.session  = None
        self.registry = None
        self.memory   = None
        self.skills   = None
        self.llm      = None
        self.router   = None

    def run(self):
        if sys.platform == "win32":
            os.system("")
        self._init_subsystems()
        self._print_startup()
        self._main_loop()

    def _init_subsystems(self):
        from core.llm import LLMClient
        from core.router import ModelRouter

        # LLM — must be first (others depend on it)
        self.renderer.print_connecting("connecting to ollama")
        self.llm = LLMClient()
        if not self.llm.is_available():
            self.renderer.print_failed("model '" + cfg.llm.model + "' not found")
            self.renderer.error("Run: ollama pull " + cfg.llm.model)
            sys.exit(1)
        self.renderer.print_ok(cfg.llm.model)

        # Load tools, memory, and skills in parallel — they're independent
        def _load_tools():
            from tools.registry import build_default_registry
            return build_default_registry(llm=self.llm)

        def _load_memory():
            from memory.manager import MemoryManager
            try:
                return MemoryManager(llm=self.llm)
            except Exception as e:
                log.warning("Memory unavailable: %s", e)
                return None

        def _load_skills():
            from skills.manager import SkillManager
            try:
                return SkillManager(llm=self.llm)
            except Exception as e:
                log.warning("Skills unavailable: %s", e)
                return None

        with ThreadPoolExecutor(max_workers=3) as pool:
            fut_tools  = pool.submit(_load_tools)
            fut_memory = pool.submit(_load_memory)
            fut_skills = pool.submit(_load_skills)

            # Collect results (order doesn't matter, but print in order)
            self.registry = fut_tools.result()
            self.renderer.print_connecting("loading tools")
            self.renderer.print_ok(", ".join(self.registry.list_names()))

            self.memory = fut_memory.result()
            self.renderer.print_connecting("loading memory")
            if self.memory:
                self.renderer.print_ok(str(self.memory.count()) + " memories")
            else:
                self.renderer.print_failed("continuing without memory")

            self.skills = fut_skills.result()
            self.renderer.print_connecting("loading skills")
            if self.skills:
                self.renderer.print_ok(str(self.skills.count()) + " skills")
            else:
                self.renderer.print_failed("continuing without skills")

        # Router (reuses cached tag list from LLMClient)
        self.router = ModelRouter(self.llm)
        available = self.router.available_models()
        self.renderer.info("models available: " + ", ".join(available))

        # Session
        from agent.session import Session
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
                    self.renderer.console.print("  [ui.dim]  - " + m[:70] + "[/ui.dim]")
                self.renderer.console.print()
        self.renderer.print_ready(self.registry.list_names())

    def _main_loop(self):
        while True:
            try:
                user_input = Prompt.ask(
                    "\n  [ui.prompt]you[/ui.prompt]",
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
        self.renderer.print_thinking_start(user_input)
        try:
            result = self.session.send(user_input)
            self.renderer.print_answer(
                answer=result.final_answer,
                tools_used=result.tools_used if result.tools_used else None,
            )
        except KeyboardInterrupt:
            self.renderer.print_thinking_stop()
            self.renderer.warning("interrupted")
            self.renderer.console.print()
        except Exception as e:
            self.renderer.print_thinking_stop()
            err_str = str(e).lower()
            if "timeout" in err_str or "timed out" in err_str or "readtimeout" in err_str:
                self.renderer.warning("Model took too long to respond.")
                self.renderer.info("Try /model mistral (faster) or increase llm.timeout in config.yaml")
            else:
                log.exception("Error handling message")
                self.renderer.error("Unexpected error: " + str(e))
            self.renderer.console.print()

    def _handle_command(self, raw: str):
        parts = raw.strip().split(None, 1)
        cmd   = parts[0].lower()
        args  = parts[1] if len(parts) > 1 else ""

        dispatch = {
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
            "/use_model":self._cmd_model,
            "/set_default_model": self._cmd_set_default_model,
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
        """Shut down xia AND forcefully stop ALL ollama processes."""
        import subprocess
        self._shutdown()

        self.renderer.info("stopping all ollama processes...")

        # List of all ollama-related process names to kill
        processes = ["ollama.exe", "ollama_runners.exe", "ollama app.exe"]
        killed = False

        for proc in processes:
            try:
                # /F = force, /T = kill entire process tree, /IM = by image name
                result = subprocess.run(
                    ["taskkill", "/F", "/T", "/IM", proc],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    self.renderer.success("killed: " + proc)
                    killed = True
            except Exception:
                pass

        if not killed:
            self.renderer.info("no ollama processes found (already stopped)")
        else:
            self.renderer.success("all ollama processes terminated")

        self.renderer.console.print()
        self.renderer.console.rule("[xia.name]everything stopped[/xia.name]", characters="-", style="dim cyan")
        self.renderer.console.print()

        # Use os._exit to guarantee immediate termination —
        # sys.exit can be caught and background threads may linger
        os._exit(0)

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

    def _cmd_set_default_model(self, model_name: str):
        import re
        if not model_name.strip():
            self.renderer.warning("Usage: /set_default_model <modelname>")
            return
        name = model_name.strip()
        try:
            with open(PATHS.config_file, "r", encoding="utf-8") as f:
                content = f.read()
            new_content = re.sub(r"(\n\s*model:\s*)[^\s#]+", r"\g<1>" + name, content, count=1)
            with open(PATHS.config_file, "w", encoding="utf-8") as f:
                f.write(new_content)
            cfg.llm.model = name
            self.renderer.success("default model set to: " + name + " in config.yaml")
            self.llm.switch_model(name)
            if self.router:
                self.router.refresh()
        except Exception as e:
            self.renderer.error("Failed to update config.yaml: " + str(e))
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
        self.renderer.console.rule("[xia.name]goodbye[/xia.name]", characters="-", style="dim cyan")
        self.renderer.console.print()
