"""Thin client for an OpenAI-compatible chat endpoint (Groq by default).

Swapping the provider (self-hosted Llama via vLLM/Ollama, etc.) only means changing
LLM_BASE_URL / LLM_MODEL. Every caller must handle a None result, because the LLM is
auxiliary: the planner must work without it (NFR 3.2.2).
"""

import json
import logging
import time

import httpx

from ..config import get_settings

log = logging.getLogger(__name__)


def chat(messages: list[dict], *, json_mode: bool = False, temperature: float = 0.2,
         max_tokens: int = 800, rate_limit_retries: int = 0) -> str | None:
    """`rate_limit_retries` > 0 waits out HTTP 429s; only for batch jobs, never user requests."""
    s = get_settings()
    if not s.llm_enabled:
        return None
    # Reasoning models (e.g. gpt-oss) spend completion tokens thinking before they answer,
    # so `max_tokens` covers the answer only and the headroom covers the thinking.
    body = {"model": s.llm_model, "messages": messages, "temperature": temperature,
            "max_tokens": max_tokens + s.llm_reasoning_headroom_tokens}
    if s.llm_reasoning_effort:
        body["reasoning_effort"] = s.llm_reasoning_effort
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    try:
        for attempt in range(rate_limit_retries + 1):
            r = httpx.post(
                f"{s.llm_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {s.groq_api_key}"},
                json=body,
                timeout=s.llm_timeout_seconds,
            )
            if r.status_code != 429 or attempt == rate_limit_retries:
                break
            wait = min(float(r.headers.get("retry-after", 10)), 60.0)
            log.info("LLM rate-limited; retrying in %.0fs", wait)
            time.sleep(wait)
        r.raise_for_status()
        choice = r.json()["choices"][0]
        content = (choice["message"].get("content") or "").strip()
        if not content:
            log.warning("LLM returned no content (finish_reason=%s)", choice.get("finish_reason"))
            return None
        return content
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        log.warning("LLM call failed: %s", exc)
        return None


def chat_json(messages: list[dict], **kw) -> dict | None:
    raw = chat(messages, json_mode=True, **kw)
    if raw is None:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        log.warning("LLM returned non-JSON output")
        return None
