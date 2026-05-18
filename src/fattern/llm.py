"""Optional server-side LLM advisor integration."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any, Callable
from urllib import request as urllib_request


HttpPost = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]

SYSTEM_PROMPT = """You are Fattern Advisor.
Explain Fattern marker-yield results for garment costing users.
Use only the provided result context.
Do not recalculate geometry, marker length, quote_yield, area, efficiency, or confidence.
Do not ask for shell, filesystem, network, or arbitrary tool access.
If the user needs a new calculation, tell them to update the Web UI fields and run Fattern again.
Keep the answer concise and label quote_yield as an estimate, not production-confirmed yield."""


@dataclass(frozen=True)
class LlmConfig:
    provider: str
    api_key: str
    model: str
    max_tokens: int = 700


def llm_status(environ: dict[str, str] | None = None) -> dict[str, str | bool]:
    try:
        config = load_llm_config(environ)
    except ValueError as exc:
        return {"available": False, "reason": str(exc)}
    return {"available": True, "provider": config.provider, "model": config.model}


def load_llm_config(environ: dict[str, str] | None = None) -> LlmConfig:
    env = environ or os.environ
    provider = env.get("FATTERN_LLM_PROVIDER", "auto").strip().lower()
    model = env.get("FATTERN_LLM_MODEL", "").strip()
    if provider == "auto":
        if env.get("OPENAI_API_KEY") and (model or env.get("OPENAI_MODEL")):
            provider = "openai"
        elif env.get("ANTHROPIC_API_KEY") and (model or env.get("ANTHROPIC_MODEL")):
            provider = "anthropic"
        else:
            raise ValueError("LLM advisor is disabled. Set FATTERN_LLM_MODEL and an API key on the server.")

    if provider == "openai":
        api_key = env.get("OPENAI_API_KEY", "").strip()
        model = model or env.get("OPENAI_MODEL", "").strip()
    elif provider == "anthropic":
        api_key = env.get("ANTHROPIC_API_KEY", "").strip()
        model = model or env.get("ANTHROPIC_MODEL", "").strip()
    else:
        raise ValueError("FATTERN_LLM_PROVIDER must be openai, anthropic, or auto.")

    if not api_key:
        raise ValueError(f"{provider} API key is not configured on the server.")
    if not model:
        raise ValueError("FATTERN_LLM_MODEL is required for the LLM advisor.")
    return LlmConfig(provider=provider, api_key=api_key, model=model)


def ask_llm_advisor(
    *,
    user_message: str,
    result: dict[str, Any],
    environ: dict[str, str] | None = None,
    http_post: HttpPost | None = None,
) -> dict[str, Any]:
    message = user_message.strip()
    if not message:
        return {"status": "disabled", "message": "Ask a question first."}
    if len(message) > 2000:
        return {"status": "blocked", "message": "Question is too long."}

    try:
        config = load_llm_config(environ)
    except ValueError as exc:
        return {"status": "disabled", "message": str(exc)}

    context = build_llm_context(result)
    post = http_post or _http_post_json
    try:
        if config.provider == "openai":
            answer = _ask_openai(config, message, context, post)
        else:
            answer = _ask_anthropic(config, message, context, post)
    except Exception:
        return {"status": "error", "message": "LLM advisor request failed."}
    return {"status": "completed", "provider": config.provider, "model": config.model, "answer": answer}


def build_llm_context(result: dict[str, Any]) -> dict[str, Any]:
    """Return a sanitized context without DXF bytes, artifact IDs, or local paths."""

    return {
        "status": result.get("status"),
        "layout": result.get("layout"),
        "minimum_yield": result.get("minimum_yield"),
        "quote_yield": result.get("quote_yield"),
        "allowance_breakdown": result.get("allowance_breakdown"),
        "allowance_reasons": result.get("allowance_reasons"),
        "confidence": result.get("confidence"),
        "partial_csv_fields": result.get("partial_csv_fields"),
        "warnings": _public_messages(result.get("warnings")),
        "errors": _public_messages(result.get("errors")),
    }


def _ask_openai(config: LlmConfig, user_message: str, context: dict[str, Any], post: HttpPost) -> str:
    payload = {
        "model": config.model,
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "Result context:\n"
                + json.dumps(context, ensure_ascii=False, sort_keys=True)
                + "\n\nUser question:\n"
                + user_message,
            },
        ],
        "max_output_tokens": config.max_tokens,
    }
    data = post(
        "https://api.openai.com/v1/responses",
        {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
        payload,
    )
    if isinstance(data.get("output_text"), str):
        return data["output_text"].strip()
    return _collect_openai_output_text(data).strip()


def _ask_anthropic(config: LlmConfig, user_message: str, context: dict[str, Any], post: HttpPost) -> str:
    payload = {
        "model": config.model,
        "max_tokens": config.max_tokens,
        "system": SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": "Result context:\n"
                + json.dumps(context, ensure_ascii=False, sort_keys=True)
                + "\n\nUser question:\n"
                + user_message,
            }
        ],
    }
    data = post(
        "https://api.anthropic.com/v1/messages",
        {
            "x-api-key": config.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        payload,
    )
    parts = []
    for item in data.get("content", []):
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text", "")))
    return "\n".join(part.strip() for part in parts if part.strip()).strip()


def _http_post_json(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib_request.Request(url, data=data, headers=headers, method="POST")
    with urllib_request.urlopen(req, timeout=30) as response:  # noqa: S310 - configured server-side API endpoint only.
        return json.loads(response.read().decode("utf-8"))


def _collect_openai_output_text(data: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in data.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                parts.append(content["text"])
    return "\n".join(parts)


def _public_messages(value: object) -> list[dict[str, str]]:
    messages = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        messages.append(
            {
                "code": str(item.get("code", "")),
                "severity": str(item.get("severity", "")),
                "message": str(item.get("message", "")),
            }
        )
    return messages
