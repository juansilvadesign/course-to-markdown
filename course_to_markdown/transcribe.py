"""Audio -> verbatim transcript via Gemini."""
from __future__ import annotations

from . import config, gemini_client, prompts


def transcribe(client, audio_file, model: str, thinking_budget: int | None,
               language: str | None = None) -> str:
    from google.genai import types

    cfg_kwargs: dict = {
        "temperature": 0.0,
        "max_output_tokens": config.TRANSCRIBE_MAX_OUTPUT_TOKENS,
    }
    if thinking_budget is not None and "2.5" in model:
        cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=thinking_budget)

    resp = gemini_client.generate_with_retry(
        lambda: client.models.generate_content(
            model=model,
            contents=[prompts.transcription_prompt(language), audio_file],
            config=types.GenerateContentConfig(**cfg_kwargs),
        ),
        label="transcription",
    )
    gemini_client.check_truncated(resp, "transcription")
    return gemini_client.response_text(resp).strip()
