"""Configuration, env loading, and path resolution."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Project root = parent of this package directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load .env from the project root if present (does not override real env vars).
load_dotenv(PROJECT_ROOT / ".env")

# --- Gemini ---
DEFAULT_MODEL = os.getenv("COURSE_TO_MD_MODEL", "gemini-2.5-flash")
DEFAULT_THINKING_BUDGET = int(os.getenv("COURSE_TO_MD_THINKING_BUDGET", "0"))

# Per-request timeout (ms). Bounds a frozen connection (e.g. the machine sleeping
# mid-run) so the call errors and the batch can continue/resume, instead of hanging
# forever. Generous ceiling: the longest lessons transcribe in a few minutes.
REQUEST_TIMEOUT_MS = int(os.getenv("COURSE_TO_MD_REQUEST_TIMEOUT_MS", "600000"))  # 10 min


def get_api_key() -> str | None:
    """Google AI (Gemini) key. Accepts GEMINI_API_KEY or GOOGLE_API_KEY."""
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


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

# --- Generation limits ---
TRANSCRIBE_MAX_OUTPUT_TOKENS = int(os.getenv("COURSE_TO_MD_TRANSCRIBE_MAX_TOKENS", "65536"))
FORMAT_MAX_OUTPUT_TOKENS = int(os.getenv("COURSE_TO_MD_FORMAT_MAX_TOKENS", "16384"))
