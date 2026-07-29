"""Gemini API client helpers (google-genai SDK)."""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

from . import config


class DailyQuotaExhausted(RuntimeError):
    """The per-day free-tier request quota is spent. Retrying today is futile, so the
    batch should stop and resume later (on quota reset) or on a higher tier — the
    already-written transcripts are skipped on the next run."""


class TruncatedResponseError(RuntimeError):
    """Gemini stopped before a complete response could be produced."""


def _classify_quota_error(exc) -> tuple[bool, float] | None:
    """If `exc` is a 429 / RESOURCE_EXHAUSTED quota error, return
    (is_daily, retry_delay_seconds); otherwise return None."""
    msg = f"{getattr(exc, 'message', '') or ''} {exc}"
    if "RESOURCE_EXHAUSTED" not in msg and getattr(exc, "code", None) != 429 and "429" not in msg:
        return None
    is_daily = "PerDay" in msg or "RequestsPerDay" in msg
    m = re.search(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)\s*s", msg)
    return is_daily, (float(m.group(1)) if m else 30.0)


def generate_with_retry(call, *, label: str, max_attempts: int = 5, max_sleep: float = 90.0):
    """Run a Gemini call, retrying transient per-minute 429s (sleeping the server's
    retryDelay, capped). Raises DailyQuotaExhausted immediately on a per-day cap, since
    no amount of waiting clears it within the day."""
    attempt = 0
    while True:
        try:
            return call()
        except Exception as e:  # noqa: BLE001
            q = _classify_quota_error(e)
            if q is None:
                raise
            is_daily, retry_delay = q
            if is_daily:
                raise DailyQuotaExhausted(str(e)) from e
            attempt += 1
            if attempt >= max_attempts:
                raise
            sleep_s = min(retry_delay, max_sleep)
            print(f"  ! {label}: rate-limited; retry {attempt}/{max_attempts} in {sleep_s:.0f}s",
                  file=sys.stderr)
            time.sleep(sleep_s)


def get_client():
    """Construct a google-genai client from the configured API key."""
    api_key = config.get_api_key()
    if not api_key:
        raise RuntimeError(
            "No API key. Set GEMINI_API_KEY (or GOOGLE_API_KEY) in your environment "
            "or in a .env file (see .env.example)."
        )
    try:
        from google import genai
        from google.genai import types
    except ImportError as e:
        raise RuntimeError(
            "google-genai is not installed. Run: pip install -r requirements.txt"
        ) from e
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=config.REQUEST_TIMEOUT_MS),
    )


def _state_name(file_obj) -> str:
    return getattr(file_obj.state, "name", str(file_obj.state))


def upload_and_wait(client, path: Path, poll_seconds: float = 2.0, timeout: float = 600.0):
    """Upload a file via the Files API and wait until it is ACTIVE."""
    uploaded = client.files.upload(file=str(path))
    waited = 0.0
    while _state_name(uploaded) == "PROCESSING":
        if waited >= timeout:
            raise RuntimeError(f"File processing timed out for {path.name}")
        time.sleep(poll_seconds)
        waited += poll_seconds
        uploaded = client.files.get(name=uploaded.name)
    if _state_name(uploaded) == "FAILED":
        raise RuntimeError(f"File processing failed for {path.name}")
    return uploaded


def delete_file(client, file_obj) -> None:
    """Best-effort cleanup. Files auto-expire after ~48h regardless."""
    try:
        client.files.delete(name=file_obj.name)
    except Exception:  # noqa: BLE001
        pass


def response_text(resp) -> str:
    """Extract text robustly across SDK versions / multi-part responses."""
    try:
        if resp.text:
            return resp.text
    except Exception:  # noqa: BLE001 - .text can raise on non-text/multi-part responses
        pass
    out: list[str] = []
    try:
        for cand in (resp.candidates or []):
            content = getattr(cand, "content", None)
            for part in (getattr(content, "parts", None) or []):
                t = getattr(part, "text", None)
                if t:
                    out.append(t)
    except Exception:  # noqa: BLE001
        pass
    return "".join(out)


def check_truncated(resp, label: str) -> None:
    """Reject generation that stopped for a non-STOP reason (e.g. token limit)."""
    try:
        fr = resp.candidates[0].finish_reason
        fr_name = getattr(fr, "name", str(fr))
        if fr_name and fr_name not in ("STOP", "FINISH_REASON_STOP"):
            raise TruncatedResponseError(
                f"{label} finish_reason={fr_name}; refusing truncated output"
            )
    except TruncatedResponseError:
        raise
    except Exception:  # noqa: BLE001
        pass
