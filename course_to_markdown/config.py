"""Configuration, env loading, and path resolution."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Project root = parent of this package directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load .env from the project root if present (does not override real env vars).
load_dotenv(PROJECT_ROOT / ".env")

# --- Transcription provider (Stage 1) ---
# "openrouter" (default since 2026-08-04) sends base64 audio to xiaomi/mimo-v2.5 via
# chat/completions — ~$0.014/h of audio, and a 131k output ceiling (2x Gemini's) that
# repaired a lesson Gemini could not transcribe at any chunk size. "gemini" uploads to
# gemini-2.5-flash via the Files API. "groq" POSTs to Groq Whisper, a purpose-built STT.
# Stage 2 is unaffected by all of this. (Zen/opencode was evaluated and rejected: text-only
# gateway, its Gemini is broken — it cannot ingest audio. See MEMORY.md 2026-07-02.)
#
# ⚠️ The default trades JARGON FIDELITY for cost and loop-immunity. MiMo rewrote the
# TypeScript type `unknown` as `any` in 7/7 occurrences on a real lesson — fluently, so it
# passes every guard in this pipeline. For a code-dense course prefer `--provider gemini`,
# and audit any MiMo output with `scripts/jargon_audit.py`. See MEMORY.md 2026-08-04.
DEFAULT_PROVIDER = os.getenv("COURSE_TO_MD_PROVIDER", "openrouter")

# --- Gemini ---
DEFAULT_MODEL = os.getenv("COURSE_TO_MD_MODEL", "gemini-2.5-flash")
DEFAULT_THINKING_BUDGET = int(os.getenv("COURSE_TO_MD_THINKING_BUDGET", "0"))

# --- Groq (Whisper STT) ---
DEFAULT_GROQ_MODEL = os.getenv("COURSE_TO_MD_GROQ_MODEL", "whisper-large-v3-turbo")

# --- OpenRouter (LLM transcription; audio is base64-inline, there is no STT route) ---
DEFAULT_OPENROUTER_MODEL = os.getenv("COURSE_TO_MD_OPENROUTER_MODEL", "xiaomi/mimo-v2.5")

# Per-request timeout (ms). Bounds a frozen connection (e.g. the machine sleeping
# mid-run) so the call errors and the batch can continue/resume, instead of hanging
# forever. Generous ceiling: the longest lessons transcribe in a few minutes.
REQUEST_TIMEOUT_MS = int(os.getenv("COURSE_TO_MD_REQUEST_TIMEOUT_MS", "600000"))  # 10 min


def get_api_key() -> str | None:
    """Google AI (Gemini) key. Accepts GEMINI_API_KEY or GOOGLE_API_KEY."""
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def get_groq_api_key() -> str | None:
    """Groq key, used when --provider groq. Create one at https://console.groq.com/keys."""
    return os.getenv("GROQ_API_KEY")


def get_openrouter_api_key() -> str | None:
    """OpenRouter key, used when --provider openrouter. Create one at
    https://openrouter.ai/keys.

    Note: a valid key is not sufficient for audio. OpenRouter gates *every* audio request
    behind a minimum account balance (~$0.50) and returns 402 below it — even for `:free`
    models and even for a 15-second clip. Top up at https://openrouter.ai/credits."""
    return os.getenv("OPENROUTER_API_KEY")


# --- Paths ---
DEFAULT_INPUT_DIR = PROJECT_ROOT / "input"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"


def knowledge_compiler_dir() -> Path | None:
    """Locate the knowledge-compiler skill (course.md + SKILL.md) used as the formatting reference.

    Resolves relative to this project's place in the repo
    (knowledge/projects/course-to-markdown -> knowledge/skills/knowledge-compiler),
    or honours the KNOWLEDGE_COMPILER_DIR override for standalone use.
    """
    override = os.getenv("KNOWLEDGE_COMPILER_DIR")
    if override:
        p = Path(override).expanduser()
        return p if p.exists() else None
    candidate = PROJECT_ROOT.parent.parent / "skills" / "knowledge-compiler"
    return candidate if candidate.exists() else None


# --- Supported media extensions (for folder scanning) ---
VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".m4v", ".wmv", ".ts", ".mpg", ".mpeg"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".wma"}
MEDIA_EXTS = VIDEO_EXTS | AUDIO_EXTS

# --- Audio normalization (small mono file = cheap, fast upload) ---
AUDIO_SAMPLE_RATE = 16000
AUDIO_BITRATE = "64k"

# --- Long-audio chunking ---
# A long lesson is split into chunks before transcription. Two failure modes bite on
# 30-45 min files: the output-token ceiling, and the model falling into a repetition
# loop on long, repetitive narration (burning all output tokens repeating one phrase).
# ~10-min chunks dodge both. Tune via env if a course has unusually long/short lessons.
AUDIO_CHUNK_THRESHOLD_SEC = int(os.getenv("COURSE_TO_MD_CHUNK_THRESHOLD_SEC", "900"))  # split if > 15 min
AUDIO_CHUNK_LENGTH_SEC = int(os.getenv("COURSE_TO_MD_CHUNK_LENGTH_SEC", "600"))        # into ~10-min chunks

# OpenRouter's MiMo providers hard-reject audio longer than 600s with a 400
# ("Audio exceeds maximum allowed duration of 600s"). The THRESHOLD matters as much as the
# chunk length: at the 900s default, every 10-15 min lesson is under the threshold, so it
# is sent whole and fails outright. Both must sit below the cap, with margin for the
# frame-boundary overshoot in `-c copy` segmenting.
OPENROUTER_MAX_AUDIO_SEC = int(os.getenv("COURSE_TO_MD_OPENROUTER_MAX_AUDIO_SEC", "540"))

# MiMo is a reasoning model, and transcription needs no chain-of-thought. With no explicit
# budget it can spend the provider's default entirely on reasoning and return
# finish_reason="length" carrying zero content -- billed in full (22x on jstack-lives).
#
# The size is a cost lever, not just a safety net: when a generation falls into the
# repetition loop it runs to exactly this ceiling and every token is billed, so the cap is
# the per-loop bill. A real 540s chunk measures 1,647-1,755 words (~3.5k tokens), so 8k
# keeps >2x headroom while halving what each loop costs.
OPENROUTER_MAX_OUTPUT_TOKENS = int(os.getenv("COURSE_TO_MD_OPENROUTER_MAX_TOKENS", "8000"))

# Six backends serve this model and they are NOT interchangeable. Left to auto-routing,
# every observed request went to DeepInfra -- the only bf16 one, the dearest, and the one
# that loops. Measured on one identical 540s chunk (2026-08-04):
#     Xiaomi     fp8   clean   1,771 words   $0.00125
#     DeepInfra  bf16  LOOPED  8,003 words   $0.03338   (27x a clean Xiaomi chunk)
#     DeepInfra  bf16  clean   1,753 words   $0.00667   (5.3x Xiaomi)
# Novita and Venice reject audio (404 "no allowed providers" / 429). Pin hard rather than
# ordering with fallbacks: a silent fallback reintroduces both the cost and the loop, and
# transient Xiaomi 429s are already retried by the client.
OPENROUTER_PROVIDERS = [p.strip() for p in os.getenv(
    "COURSE_TO_MD_OPENROUTER_PROVIDERS", "Xiaomi").split(",") if p.strip()]

# --- Generation limits ---
TRANSCRIBE_MAX_OUTPUT_TOKENS = int(os.getenv("COURSE_TO_MD_TRANSCRIBE_MAX_TOKENS", "65536"))
FORMAT_MAX_OUTPUT_TOKENS = int(os.getenv("COURSE_TO_MD_FORMAT_MAX_TOKENS", "16384"))
