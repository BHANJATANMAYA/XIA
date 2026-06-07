"""
interface/theme.py — CLI Theme

All colours, styles, and layout constants in one place.
Change the theme here and it propagates everywhere.
"""

from rich.theme import Theme
from rich.style import Style

# ── Colour palette ─────────────────────────────────────────────────────────────

XIA_THEME = Theme({
    # Brand
    "xia.name":       "bold #a855f7",
    "xia.version":    "dim #a855f7",

    # Step types
    "step.think":     "bold #a855f7",
    "step.plan":      "bold yellow",
    "step.act":       "bold #ec4899",
    "step.observe":   "bold #6366f1",
    "step.reason":    "bold green",
    "step.final":     "bold green",
    "step.error":     "bold red",

    # UI elements
    "ui.prompt":      "bold white",
    "ui.separator":   "dim white",
    "ui.label":       "dim white",
    "ui.value":       "white",
    "ui.success":     "bold green",
    "ui.warning":     "bold yellow",
    "ui.error":       "bold red",
    "ui.info":        "#a855f7",
    "ui.dim":         "dim white",
    "ui.muted":       "dim",

    # Content
    "content.user":   "bold white",
    "content.answer": "white",
    "content.code":   "green",
    "content.tool":   "dim #ec4899",
    "content.memory": "dim #a855f7",
    "content.skill":  "dim yellow",
})

# ── Layout constants ───────────────────────────────────────────────────────────

PANEL_WIDTH   = 80
SEPARATOR     = "-" * 52
THICK_SEP     = "=" * 52

STEP_ICONS = {
    "THINK":   "*",
    "PLAN":    "+",
    "ACT":     ">",
    "OBSERVE": "<",
    "REASON":  ":",
    "FINAL":   "*",
}

STEP_STYLES = {
    "THINK":   "step.think",
    "PLAN":    "step.plan",
    "ACT":     "step.act",
    "OBSERVE": "step.observe",
    "REASON":  "step.reason",
    "FINAL":   "step.final",
}

