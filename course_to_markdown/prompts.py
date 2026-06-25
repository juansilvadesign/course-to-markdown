"""Prompt construction. Pulls the knowledge-compiler course reference when reachable."""
from __future__ import annotations

import datetime

from . import config

# Used only when the knowledge-compiler skill isn't reachable (project copied out of the
# repo). Mirrors the intent of course.md / SKILL.md: compress, never transcribe.
_FALLBACK_REFERENCE = """\
Produce a COMPRESSED, structured study note — never a verbatim transcript.
Suggested shape (use what fits, omit what does not):

- TL;DR (3-5 sentences: what this lesson teaches and why it matters)
- Core ideas (load-bearing claims, one line each)
- Curriculum / key points in order (the spine of the lesson)
- Exercises (what the student is asked to DO -- the verb matters)
- Rules of thumb (heuristics the instructor drops in passing)
- Frameworks / models (named structures, one-line definition each)
- Capabilities unlocked (verb-led skills the student can now perform)
- Quotes worth keeping (verbatim, sparing)
"""


def _load_reference() -> str:
    kc = config.knowledge_compiler_dir()
    if not kc:
        return _FALLBACK_REFERENCE
    parts: list[str] = []
    for name in ("course.md", "SKILL.md"):
        f = kc / name
        if f.exists():
            parts.append(f"----- {name} -----\n{f.read_text(encoding='utf-8')}")
    return "\n\n".join(parts) if parts else _FALLBACK_REFERENCE


def transcription_prompt(language: str | None = None) -> str:
    lang = (
        f"The audio is in {language}. Transcribe in {language}; do not translate.\n"
        if language
        else "Preserve the original spoken language; do not translate.\n"
    )
    return (
        "You are a transcription engine for an online-course lesson.\n"
        "Transcribe the attached audio VERBATIM into clean, readable text.\n\n"
        f"{lang}"
        "Rules:\n"
        "- Output ONLY the transcript text. No preamble, no commentary, no timestamps.\n"
        "- Use correct punctuation, capitalization, and paragraph breaks at natural pauses.\n"
        '- Drop pure filler stutters ("um", "uh") but keep all meaningful content.\n'
        "- Do NOT summarize, condense, or omit anything substantive.\n"
    )


def formatting_prompt(transcript: str, source_name: str, language: str | None = None) -> str:
    reference = _load_reference()
    lang = (
        f"Write the note in {language}.\n"
        if language
        else "Write the note in the SAME language as the transcript.\n"
    )
    return (
        "You are a knowledge compiler. Turn the raw course-lesson transcript below into a "
        "clean, COMPRESSED Markdown study note.\n\n"
        "Use the reference material as a GUIDE for structure and intent -- follow it loosely, "
        "not strictly. Include the sections that fit this lesson; omit the ones that do not. "
        "Never force empty sections.\n\n"
        f"{lang}"
        "Hard rules:\n"
        "- This is a COMPRESSION, not a transcript. Never paste the transcript back.\n"
        "- Be faithful: do not invent facts, names, or numbers that are not in the transcript.\n"
        '- Preserve named heuristics/frameworks exactly (e.g. "Hormozi\'s Value Equation").\n'
        "- Start with a single H1 title inferred from the content.\n"
        f"- If you include any date field (e.g. a `compiled:` frontmatter key), use today's date "
        f"({datetime.date.today().isoformat()}). Never invent or guess a date.\n"
        "- Output ONLY the Markdown note. No preamble; do not wrap the whole note in a code fence.\n\n"
        "===== REFERENCE (knowledge-compiler) =====\n"
        f"{reference}\n"
        "===== END REFERENCE =====\n\n"
        f"Lesson source file: {source_name}\n\n"
        "===== TRANSCRIPT =====\n"
        f"{transcript}\n"
        "===== END TRANSCRIPT =====\n"
    )
