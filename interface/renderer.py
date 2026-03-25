"""
interface/renderer.py — Terminal Renderer

Handles all Rich-based output for the xia CLI.
"""

from typing import List, Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich import box

from interface.theme import XIA_THEME, STEP_ICONS, STEP_STYLES


class Renderer:
    """All terminal output goes through here."""

    def __init__(self):
        self.console = Console(theme=XIA_THEME, highlight=False)
        self._step_count = 0

    # ── Startup ────────────────────────────────────────────────────────────

    def print_banner(self, model: str, root: str, mem_count: int, skill_count: int):
        self.console.print()
        self.console.rule("[xia.name]  x i a  [/xia.name]", style="dim cyan")
        self.console.print()
        table = Table(box=None, show_header=False, padding=(0, 2))
        table.add_column(style="ui.label", width=14)
        table.add_column(style="ui.value")
        table.add_row("model",   model)
        table.add_row("root",    root)
        table.add_row("memory",  f"{mem_count} stored memories")
        table.add_row("skills",  f"{skill_count} learned skills")
        self.console.print(table)
        self.console.print()

    def print_ready(self, tools: list):
        self.console.print(
            f"  [ui.success]ready[/ui.success]  [ui.dim]"
            f"tools: {', '.join(tools)}  |  /help for commands[/ui.dim]"
        )
        self.console.print()
        self.console.rule(style="dim")
        self.console.print()

    def print_connecting(self, label: str):
        self.console.print(f"  [ui.dim]{label}...[/ui.dim]", end="")

    def print_ok(self, detail: str = ""):
        suffix = f" [ui.dim]({detail})[/ui.dim]" if detail else ""
        self.console.print(f" [ui.success]ok[/ui.success]{suffix}")

    def print_failed(self, detail: str = ""):
        suffix = f"  {detail}" if detail else ""
        self.console.print(f" [ui.error]failed[/ui.error]{suffix}")

    # ── Agent steps ────────────────────────────────────────────────────────

    def reset_step_count(self):
        self._step_count = 0

    def print_step(self, step):
        """Print a single agent step as it happens."""
        step_type = step.step_type.value
        if step_type == "FINAL":
            return

        self._step_count += 1
        icon  = STEP_ICONS.get(step_type, "·")
        style = STEP_STYLES.get(step_type, "ui.dim")

        content = step.content.strip()
        if len(content) > 180:
            content = content[:180] + "…"

        self.console.print(
            f"  [{style}]{icon} {step_type}[/{style}]  "
            f"[ui.muted]{content}[/ui.muted]"
        )

        if step.tool_name:
            input_preview = ""
            if step.tool_input:
                inp = str(step.tool_input)
                input_preview = f"  [ui.dim]{inp[0:60]}{'…' if len(inp) > 60 else ''}[/ui.dim]"
            self.console.print(
                f"  [ui.dim]  └ [content.tool]{step.tool_name}[/content.tool]{input_preview}[/ui.dim]"
            )

        if step.tool_result:
            preview = str(step.tool_result).strip()
            first_line = next((l for l in preview.splitlines() if l.strip()), preview)
            if len(first_line) > 90:
                first_line = first_line[0:90] + "…"
            self.console.print(
                f"  [ui.dim]  └ {first_line}[/ui.dim]"
            )

    # ── Final answer ───────────────────────────────────────────────────────

    def print_answer(self, answer: str, tools_used: Optional[List[str]] = None):
        self.console.print()

        has_markdown = any(c in answer for c in ["**", "##", "```", "\n- ", "\n1. "])

        if has_markdown:
            self.console.print(
                Panel(
                    Markdown(answer),
                    border_style="dim cyan",
                    padding=(0, 2),
                    box=box.ROUNDED,
                    title="[xia.name]xia[/xia.name]",
                    title_align="left",
                )
            )
        else:
            self.console.print(f"  [xia.name]xia[/xia.name]  {answer}")

        if tools_used:
            self.console.print(
                f"\n  [ui.dim]used: {', '.join(tools_used)}[/ui.dim]"
            )

        self.console.print()
        self.console.rule(style="dim")
        self.console.print()

    # ── Info messages ──────────────────────────────────────────────────────

    def info(self, msg: str):
        self.console.print(f"  [ui.info]·[/ui.info]  {msg}")

    def success(self, msg: str):
        self.console.print(f"  [ui.success]✓[/ui.success]  {msg}")

    def warning(self, msg: str):
        self.console.print(f"  [ui.warning]![/ui.warning]  {msg}")

    def error(self, msg: str):
        self.console.print(f"  [ui.error]✗[/ui.error]  {msg}")

    def print(self, msg: str):
        self.console.print(f"  {msg}")

    # ── Memory & skills display ────────────────────────────────────────────

    def print_memories(self, memories: list, total: int):
        self.console.print()
        self.console.print(
            f"  [content.memory]◎ memory[/content.memory]  "
            f"[ui.dim]{total} total stored[/ui.dim]\n"
        )
        if not memories:
            self.info("No memories yet.")
            return
        for i, m in enumerate(memories, 1):
            preview = m[:80] + "…" if len(m) > 80 else m
            self.console.print(f"  [ui.dim]{i}.[/ui.dim]  [ui.muted]{preview}[/ui.muted]")
        self.console.print()

    def print_skills(self, skills: list):
        self.console.print()
        if not skills:
            self.info("No skills yet — they build up as you complete tasks.")
            self.console.print()
            return

        self.console.print(
            f"  [content.skill]◈ skills[/content.skill]  "
            f"[ui.dim]{len(skills)} learned[/ui.dim]\n"
        )
        table = Table(box=box.SIMPLE, show_header=True,
                      header_style="ui.label", padding=(0, 1))
        table.add_column("uses",  style="ui.dim", width=5, justify="right")
        table.add_column("name",  style="content.skill", width=30)
        table.add_column("description", style="ui.muted")

        for sk in skills[0:15]:
            desc = sk.description[0:55] + ("…" if len(sk.description) > 55 else "")
            table.add_row(str(sk.success_count), sk.name, desc)

        self.console.print(table)
        self.console.print()

    def print_session_saved(self, path):
        self.success(f"session saved  [ui.dim]{path}[/ui.dim]")

    # ── Help ───────────────────────────────────────────────────────────────

    def print_help(self):
        self.console.print()
        table = Table(box=None, show_header=False, padding=(0, 2))
        table.add_column(style="content.skill", width=22)
        table.add_column(style="ui.muted")

        commands = [
            ("/exit",            "quit and save session"),
            ("/end",             "quit xia AND stop ollama completely"),
            ("/clear",           "clear conversation history"),
            ("/save",            "save session to disk now"),
            ("/memory",          "show stored memories"),
            ("/remember <fact>", "manually store a memory"),
            ("/forget",          "clear all memories"),
            ("/skills",          "list learned skills"),
            ("/tools",           "list available tools"),
            ("/model <name>",    "switch LLM model"),
            ("/history",         "show message count"),
            ("/help",            "show this help"),
        ]
        for cmd, desc in commands:
            table.add_row(cmd, desc)

        self.console.print(table)
        self.console.print()
