"""Claude API access. Called from exactly three places: scoring, message
drafting, and answering custom application questions.

Credentials come from the environment only (ANTHROPIC_API_KEY or an auth
token); nothing is stored. Without them the app still runs: matches stay
unscored and drafts fall back to templates."""
from __future__ import annotations

import os
import re
import threading
from typing import Any, TypeVar

from pydantic import BaseModel

from . import config

T = TypeVar("T", bound=BaseModel)

# Server-side refusal fallback: a declined request is re-run on the model
# Anthropic recommends for that refusal category, inside the same call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_TOKENS = 16000


class LLMError(Exception):
    """The call failed or returned nothing usable."""


class LLMUnavailable(LLMError):
    """No credentials, or they were rejected."""


class LLMRefused(LLMError):
    """The model (and its fallback) declined the request."""


_lock = threading.Lock()
_client: Any = None


def available() -> bool:
    mode = os.getenv("COPILOT_LLM", "auto").lower()
    if mode in ("off", "0", "false"):
        return False
    if mode in ("on", "1", "true"):       # e.g. credentials from `ant auth login`
        return True
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))


def client() -> Any:
    global _client
    if not available():
        raise LLMUnavailable("no Claude API credentials in the environment")
    with _lock:
        if _client is None:
            import anthropic
            _client = anthropic.Anthropic(max_retries=3)
        return _client


def set_client(fake: Any) -> None:
    """Test hook."""
    global _client
    _client = fake


def _request(effort: str) -> dict:
    kwargs: dict[str, Any] = {
        "model": config.MODEL,
        "max_tokens": MAX_TOKENS,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": effort},
    }
    if os.getenv("COPILOT_FALLBACKS", "default").lower() not in ("off", "0", "false"):
        kwargs["betas"] = [FALLBACK_BETA]
        kwargs["fallbacks"] = "default"
    return kwargs


def system_blocks(instructions: str, stable_context: str = "") -> list[dict]:
    """Instructions plus the stable context (resume, preferences) as a cached
    prefix. What changes per call goes in the user turn, after the breakpoint."""
    text = instructions.strip()
    if stable_context.strip():
        text += "\n\n" + stable_context.strip()
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


def _call(fn, **kwargs):
    import anthropic
    try:
        resp = fn(**kwargs)
    except anthropic.AuthenticationError as e:
        raise LLMUnavailable(f"Claude API rejected the credentials: {e.message}") from e
    except anthropic.APIStatusError as e:
        raise LLMError(f"Claude API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise LLMError(f"could not reach the Claude API: {e}") from e
    if resp.stop_reason == "refusal":
        raise LLMRefused("the model declined this request")
    if resp.stop_reason == "max_tokens":
        raise LLMError("response was cut off at max_tokens")
    return resp


def structured(system: list[dict], user: str, schema: type[T], *, effort: str = "low") -> T:
    c = client()
    resp = _call(c.beta.messages.parse, system=system, output_format=schema,
                 messages=[{"role": "user", "content": user}], **_request(effort))
    out = resp.parsed_output
    if out is None:
        raise LLMError("model returned no structured output")
    return out


def text(system: list[dict], messages: list[dict], *, effort: str = "medium") -> str:
    c = client()
    resp = _call(c.beta.messages.create, system=system, messages=messages,
                 **_request(effort))
    return "".join(b.text for b in resp.content if b.type == "text").strip()


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\d)(\+?\d[\d\s().-]{8,}\d)(?!\d)")


def redact(text_: str) -> str:
    """Strip email addresses and phone numbers before text leaves the machine.
    The model needs the experience, not the contact block."""
    return _PHONE.sub("[phone]", _EMAIL.sub("[email]", text_ or ""))


def plain(text_: str) -> str:
    """House style for anything drafted in my voice: no em or en dashes."""
    out = re.sub("\\s*[\u2014\u2013]\\s*", ", ", text_ or "")
    return re.sub(r",\s*,", ",", out).strip()
