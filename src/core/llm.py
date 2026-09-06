"""
core/llm.py — Ollama LLM Client

The single interface between xia and the local language model.
All reasoning, planning, and response generation flows through here.

Features:
  - Streaming and non-streaming responses
  - Structured JSON output (for tool calling in Part 5)
  - Automatic retry on failure
  - Token usage tracking
  - System prompt injection
  - Chat history management

Usage:
    from core.llm import LLMClient
    llm = LLMClient()

    # Simple one-shot
    response = llm.chat("What is the capital of France?")
    print(response.content)

    # With streaming
    for chunk in llm.stream("Explain quantum computing"):
        print(chunk, end="", flush=True)

    # Full conversation
    history = []
    response = llm.chat("My name is Aryan", history=history)
    history = response.updated_history
    response2 = llm.chat("What is my name?", history=history)
"""

import json
import re
import time
from dataclasses import dataclass, field
from typing import Generator, List, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from core.config import cfg
from core.logger import get_logger

log = get_logger(__name__)


# ── Data types ─────────────────────────────────────────────────────────────────

@dataclass
class Message:
    """A single message in a conversation."""
    role: str       # "system", "user", "assistant"
    content: str

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}

    @classmethod
    def system(cls, content: str) -> "Message":
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str) -> "Message":
        return cls(role="user", content=content)

    @classmethod
    def assistant(cls, content: str) -> "Message":
        return cls(role="assistant", content=content)


@dataclass
class LLMResponse:
    """Response from the LLM."""
    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    duration_ms: int = 0
    updated_history: List[Message] = field(default_factory=list)

    @property
    def tokens(self) -> int:
        return self.total_tokens

    def __str__(self) -> str:
        return self.content


@dataclass
class StreamChunk:
    """A single chunk from a streaming response."""
    content: str
    done: bool = False


# ── System prompt ──────────────────────────────────────────────────────────────

DEFAULT_SYSTEM_PROMPT = """You are xia. You are NOT Mistral, ChatGPT, or Claude. Never describe your own personality. Just respond to what the user said."""


def strip_thinking(text: str) -> str:
    """Remove <think>...</think> blocks from the response text."""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    if "<think>" in cleaned:
        parts = cleaned.split("</think>", 1)
        if len(parts) > 1:
            cleaned = parts[1]
        else:
            cleaned = re.sub(r"<think>.*", "", cleaned, flags=re.DOTALL)
    return cleaned.strip()


# ── LLM Client ────────────────────────────────────────────────────────────────

class LLMError(Exception):
    """Raised when the LLM request fails after all retries."""
    pass


class LLMClient:
    """
    Client for the local Ollama LLM.

    This is a long-lived object — create one instance and reuse it.
    Thread-safe for sequential use (not concurrent).
    """

    def __init__(
        self,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.model = model or cfg.llm.model
        self.base_url = (base_url or cfg.llm.base_url).rstrip("/")
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.temperature = cfg.llm.temperature
        self.max_tokens = cfg.llm.max_tokens
        self.timeout = cfg.llm.timeout

        self._client = httpx.Client(timeout=self.timeout)
        self._tags_cache = None
        self._tags_cache_time = 0
        self._response_cache: dict = {}
        self._response_cache_times: dict = {}
        self._cache_ttl = cfg.llm.cache_ttl
        log.info("LLMClient initialised: model=%s base_url=%s", self.model, self.base_url)

    # ── Public API ─────────────────────────────────────────────────────────

    def chat(
        self,
        user_message: str,
        history: Optional[List[Message]] = None,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        """
        Send a message and get a complete response (non-streaming).
        """
        # Check cache (only for non-streaming, no-history calls)
        if not history and self._cache_ttl > 0:
            cache_key = self._cache_key(user_message, system_prompt, json_mode)
            cached = self._get_cached(cache_key)
            if cached is not None:
                log.debug("chat() cache hit for %d chars", len(user_message))
                return cached

        messages = self._build_messages(user_message, history, system_prompt, json_mode)
        log.debug("chat() → model=%s messages=%d", self.model, len(messages))

        start = time.monotonic()
        raw = self._call_api(messages, temperature=temperature, stream=False)
        elapsed_ms = int((time.monotonic() - start) * 1000)

        content = raw.get("message", {}).get("content", "")
        content = strip_thinking(content)
        usage = raw.get("usage", {})

        new_history = list(history or []) + [
            Message.user(user_message),
            Message.assistant(content),
        ]

        response = LLMResponse(
            content=content,
            model=self.model,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            duration_ms=elapsed_ms,
            updated_history=new_history,
        )

        # Store in cache (only for no-history calls)
        if not history and self._cache_ttl > 0:
            self._set_cached(cache_key, response)

        log.debug(
            "chat() ← %d chars, %dms, ~%d tokens",
            len(content), elapsed_ms, response.total_tokens
        )
        return response

    def stream(
        self,
        user_message: str,
        history: Optional[List[Message]] = None,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> Generator[str, None, None]:
        """
        Send a message and stream the response token by token.

        Usage:
            for chunk in llm.stream("Tell me a story"):
                print(chunk, end="", flush=True)

        Yields:
            String chunks as they arrive from the model.
        """
        messages = self._build_messages(user_message, history, system_prompt)
        log.debug("stream() → model=%s", self.model)

        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "stream": True,
            "options": {
                "temperature": temperature or self.temperature,
                "num_predict": self.max_tokens,
            },
        }

        with self._client.stream("POST", url, json=payload) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    chunk = data.get("message", {}).get("content", "")
                    if chunk:
                        yield chunk
                    if data.get("done"):
                        break
                except json.JSONDecodeError:
                    continue

    def chat_json(
        self,
        user_message: str,
        history: Optional[List[Message]] = None,
        system_prompt: Optional[str] = None,
    ) -> dict:
        """
        Request a JSON-structured response from the model.
        Used by the tool-calling system in Part 5.

        Returns:
            Parsed dict, or {"error": "...", "raw": "..."} on parse failure.
        """
        response = self.chat(
            user_message,
            history=history,
            system_prompt=system_prompt,
            json_mode=True,
        )

        content = response.content.strip()

        # Strip markdown code fences if model added them
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            log.warning("JSON parse failed: %s\nRaw: %s", e, content[:200])
            return {"error": str(e), "raw": content}

    def is_available(self) -> bool:
        """Check if the Ollama server is reachable and the model is loaded."""
        try:
            names = self._get_tags()
            model_base = self.model.split(":")[0]
            return any(n == self.model or n.split(":")[0] == model_base for n in names)
        except Exception:
            return False

    def list_models(self) -> List[str]:
        """Return list of locally available model names."""
        try:
            return list(self._get_tags())
        except Exception as e:
            log.warning("Could not list models: %s", e)
            return []

    def list_model_details(self) -> List[dict]:
        """Return downloaded Ollama model metadata, including quantized size."""
        try:
            response = self._client.get(f"{self.base_url}/api/tags", timeout=3)
            response.raise_for_status()
            return response.json().get("models", [])
        except Exception as e:
            log.warning("Could not list model details: %s", e)
            return []

    def _get_tags(self) -> List[str]:
        """Fetch and cache the model tag list from Ollama."""
        now = time.monotonic()
        if self._tags_cache is not None and (now - self._tags_cache_time) < 10:
            return self._tags_cache
        resp = self._client.get(f"{self.base_url}/api/tags", timeout=3)
        resp.raise_for_status()
        self._tags_cache = [m["name"] for m in resp.json().get("models", [])]
        self._tags_cache_time = now
        return self._tags_cache

    def switch_model(self, model_name: str):
        """Hot-swap to a different model without recreating the client."""
        log.info("Switching model: %s → %s", self.model, model_name)
        self.model = model_name

    # ── Internal ───────────────────────────────────────────────────────────

    def _build_messages(
        self,
        user_message: str,
        history: Optional[List[Message]],
        system_prompt: Optional[str],
        json_mode: bool = False,
    ) -> List[Message]:
        """Assemble the full message list to send to the model."""
        sys_content = system_prompt or self.system_prompt
        if json_mode:
            sys_content += "\n\nIMPORTANT: Respond with valid JSON only. No explanation, no markdown fences."

        messages = [Message.system(sys_content)]
        if history:
            # Keep only the last 6 messages of history to minimize latency
            messages.extend(history[-6:])
        messages.append(Message.user(user_message))
        return messages

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
        reraise=True,
    )
    def _call_api(self, messages: List[Message], temperature=None, stream=False) -> dict:
        """
        Make the actual HTTP call to Ollama /api/chat.
        Retries automatically on connection errors.
        """
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "stream": stream,
            "options": {
                "temperature": temperature or self.temperature,
                "num_predict": self.max_tokens,
            },
        }

        try:
            response = self._client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError:
            raise LLMError(
                f"Cannot connect to Ollama at {self.base_url}.\n"
                "Is Ollama running? Try: ollama serve"
            )
        except httpx.HTTPStatusError as e:
            body = e.response.text[:300]
            raise LLMError(f"Ollama API error {e.response.status_code}: {body}")

    def __repr__(self) -> str:
        return f"LLMClient(model={self.model}, url={self.base_url})"

    # ── Cache helpers ──────────────────────────────────────────────────────

    def _cache_key(self, user_message: str, system_prompt: Optional[str], json_mode: bool) -> str:
        import hashlib
        raw = f"{self.model}|{system_prompt or ''}|{user_message}|{json_mode}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _get_cached(self, key: str) -> Optional[LLMResponse]:
        if key not in self._response_cache:
            return None
        age = time.monotonic() - self._response_cache_times.get(key, 0)
        if age > self._cache_ttl:
            del self._response_cache[key]
            del self._response_cache_times[key]
            return None
        return self._response_cache[key]

    def _set_cached(self, key: str, response: LLMResponse):
        self._response_cache[key] = response
        self._response_cache_times[key] = time.monotonic()
        # Evict old entries if cache grows too large
        if len(self._response_cache) > 100:
            oldest = min(self._response_cache_times, key=self._response_cache_times.get)
            del self._response_cache[oldest]
            del self._response_cache_times[oldest]
