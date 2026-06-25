"""Transcript -> compressed Markdown note via Gemini."""
from __future__ import annotations

from . import config, gemini_client, prompts


def format_markdown(client, transcript: str, source_name: str, model: str,
                    thinking_budget: int | None, language: str | None = None) -> str:
    from google.genai import types

    cfg_kwargs: dict = {
        "temperature": 0.3,
        "max_output_tokens": config.FORMAT_MAX_OUTPUT_TOKENS,
    }
    if thinking_budget is not None and "2.5" in model:
        cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=thinking_budget)

    resp = client.models.generate_content(
        model=model,
        contents=[prompts.formatting_prompt(transcript, source_name, language)],
        config=types.GenerateContentConfig(**cfg_kwargs),
    )
    gemini_client.check_truncated(resp, "formatting")
    return _strip_outer_fence(gemini_client.response_text(resp).strip())


def _strip_outer_fence(text: str) -> str:
    """Remove an accidental ```/```markdown fence wrapping the entire note."""
    t = text.strip()
    if not t.startswith("```"):
        return t
    lines = t.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()
