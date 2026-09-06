"""
core/config.py

Loads and exposes xia configuration from config.yaml and .env.
Provides typed access to all config values with sensible defaults.

Usage:
    from core.config import cfg
    print(cfg.llm.model)       # "mistral"
    print(cfg.agent.max_steps) # 10
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml
from dotenv import load_dotenv

from core.paths import PATHS


# ── Dataclasses for typed config access ───────────────────────────────────────

@dataclass
class LLMConfig:
    provider: str = "ollama"
    model: str = "mistral"
    base_url: str = "http://localhost:11434"
    temperature: float = 0.7
    max_tokens: int = 4096
    stream: bool = True
    timeout: int = 120
    cache_ttl: int = 300
    auto_select: bool = True
    auto_select_memory_fraction: float = 0.60


@dataclass
class AgentConfig:
    name: str = "xia"
    max_steps: int = 10
    max_retries: int = 3
    verbose: bool = True


@dataclass
class MemoryConfig:
    enabled: bool = True
    provider: str = "chromadb"
    collection_name: str = "xia_memory"
    embedding_model: str = "all-MiniLM-L6-v2"
    max_results: int = 5
    similarity_threshold: float = 0.75
    working_memory_size: int = 8
    cache_ttl_seconds: int = 300
    rerank_candidates: int = 20
    relevance_weight: float = 0.60
    recency_weight: float = 0.25
    importance_weight: float = 0.15
    default_importance: float = 0.50
    default_memory_type: str = "semantic"
    typed_extraction_enabled: bool = True
    graph_enabled: bool = True
    graph_max_results: int = 3


@dataclass
class SkillsConfig:
    enabled: bool = True
    auto_extract: bool = True
    max_skills: int = 500


@dataclass
class FilesystemToolConfig:
    enabled: bool = True
    allowed_paths: List[str] = field(default_factory=lambda: ["."])


@dataclass
class TerminalToolConfig:
    enabled: bool = True
    timeout: int = 30
    dangerous_commands: List[str] = field(
        default_factory=lambda: ["rm", "del", "format", "rmdir"]
    )


@dataclass
class SearchToolConfig:
    enabled: bool = False
    provider: str = "serpapi"
    max_results: int = 5


@dataclass
class ToolsConfig:
    filesystem: FilesystemToolConfig = field(default_factory=FilesystemToolConfig)
    terminal: TerminalToolConfig = field(default_factory=TerminalToolConfig)
    search: SearchToolConfig = field(default_factory=SearchToolConfig)


@dataclass
class InterfaceConfig:
    type: str = "cli"
    theme: str = "dark"
    show_thinking: bool = True
    show_tool_calls: bool = True


@dataclass
class VoiceConfig:
    enabled: bool = True
    model: str = "base.en"
    language: str = "en"
    sample_rate: int = 16000
    max_record_seconds: int = 30
    silence_seconds: float = 1.2
    silence_threshold: float = 0.015
    device: Optional[str] = None
    confirm_transcript: bool = False
    speak_responses: bool = False
    speech_rate: int = 180


@dataclass
class LoggingConfig:
    level: str = "INFO"
    log_to_file: bool = True
    max_log_size_mb: int = 10
    backup_count: int = 3


@dataclass
class OrchestrationConfig:
    enabled: bool = True
    max_subtasks: int = 5
    max_retries_per_subtask: int = 1
    reflection_enabled: bool = True
    self_learning_enabled: bool = True
    user_model_enabled: bool = True
    max_lessons_retrieved: int = 3
    parallel_subtasks: bool = True
    sub_agent_max_steps: int = 5


@dataclass
class SelfLearningConfig:
    enabled: bool = True
    learn_from_failures: bool = True
    learn_from_successes: bool = True
    learn_from_corrections: bool = True
    max_lessons: int = 200
    min_confidence: float = 0.5


@dataclass
class Config:
    llm: LLMConfig = field(default_factory=LLMConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    skills: SkillsConfig = field(default_factory=SkillsConfig)
    tools: ToolsConfig = field(default_factory=ToolsConfig)
    interface: InterfaceConfig = field(default_factory=InterfaceConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    orchestration: OrchestrationConfig = field(default_factory=OrchestrationConfig)
    self_learning: SelfLearningConfig = field(default_factory=SelfLearningConfig)


# ── Loader ────────────────────────────────────────────────────────────────────

def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base recursively."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _apply_env_overrides(raw: dict) -> dict:
    """Allow environment variables to override config values."""
    # XIA_MODEL overrides llm.model
    if model := os.environ.get("XIA_MODEL"):
        raw.setdefault("llm", {})["model"] = model

    # XIA_DEBUG=true sets logging to DEBUG and agent.verbose to true
    if os.environ.get("XIA_DEBUG", "").lower() == "true":
        raw.setdefault("logging", {})["level"] = "DEBUG"
        raw.setdefault("agent", {})["verbose"] = True

    return raw


def _build_config(raw: dict) -> Config:
    """Convert raw dict into typed Config dataclass."""
    llm_raw = raw.get("llm", {})
    agent_raw = raw.get("agent", {})
    memory_raw = raw.get("memory", {})
    skills_raw = raw.get("skills", {})
    tools_raw = raw.get("tools", {})
    iface_raw = raw.get("interface", {})
    voice_raw = raw.get("voice", {})
    log_raw = raw.get("logging", {})
    orch_raw = raw.get("orchestration", {})
    learn_raw = raw.get("self_learning", {})

    return Config(
        llm=LLMConfig(**{k: v for k, v in llm_raw.items() if k in LLMConfig.__dataclass_fields__}),
        agent=AgentConfig(**{k: v for k, v in agent_raw.items() if k in AgentConfig.__dataclass_fields__}),
        memory=MemoryConfig(**{k: v for k, v in memory_raw.items() if k in MemoryConfig.__dataclass_fields__}),
        skills=SkillsConfig(**{k: v for k, v in skills_raw.items() if k in SkillsConfig.__dataclass_fields__}),
        tools=ToolsConfig(
            filesystem=FilesystemToolConfig(**{k: v for k, v in tools_raw.get("filesystem", {}).items() if k in FilesystemToolConfig.__dataclass_fields__}),
            terminal=TerminalToolConfig(**{k: v for k, v in tools_raw.get("terminal", {}).items() if k in TerminalToolConfig.__dataclass_fields__}),
            search=SearchToolConfig(**{k: v for k, v in tools_raw.get("search", {}).items() if k in SearchToolConfig.__dataclass_fields__}),
        ),
        interface=InterfaceConfig(**{k: v for k, v in iface_raw.items() if k in InterfaceConfig.__dataclass_fields__}),
        voice=VoiceConfig(**{k: v for k, v in voice_raw.items() if k in VoiceConfig.__dataclass_fields__}),
        logging=LoggingConfig(**{k: v for k, v in log_raw.items() if k in LoggingConfig.__dataclass_fields__}),
        orchestration=OrchestrationConfig(**{k: v for k, v in orch_raw.items() if k in OrchestrationConfig.__dataclass_fields__}),
        self_learning=SelfLearningConfig(**{k: v for k, v in learn_raw.items() if k in SelfLearningConfig.__dataclass_fields__}),
    )


def load_config() -> Config:
    """Load config from disk and environment. Call once at startup."""
    # Load .env first so env vars are available
    load_dotenv(PATHS.env_file)

    raw = _load_yaml(PATHS.config_file)
    raw = _apply_env_overrides(raw)
    return _build_config(raw)


# Module-level singleton
cfg: Config = load_config()


