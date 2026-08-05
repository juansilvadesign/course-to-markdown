#!/usr/bin/env python3
"""
scripts/compile_lives_stage2.py — Batch Stage 2 Compiler for JStack Lives

Compiles each uncompiled jstack-lives course in output/jstack-lives/ into its
staged knowledge pack (<course-slug>.pack.md), following the knowledge-compiler
course.md playbook and agent.md rules.
"""

import os
import glob
import re
import datetime
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = """You are a course module compiler. Your job is to compile a video course / live workshop from its lesson transcripts into a single, high-density knowledge pack (.pack.md) following the knowledge-compiler course.md playbook.

Language & Convention (CRITICAL):
- English for the skeleton/structure: all frontmatter keys, section headings (## TL;DR, ## Core ideas, ## Curriculum, ## Capabilities unlocked, ## Frameworks / models, ## Quotes worth keeping, ## How to apply, ## See also).
- PT-BR for the body content (actual concepts, exercises, domain terms, quotes).
- NEVER ASCII-fold or strip accents from PT-BR content (e.g. use "Módulo", "animação", "está", "é", "ícones", "criação").

Output Skeleton (Markdown only, no surrounding codeblock fence):
---
title: <course title>
author: <author>
type: course
domain: coding
source: <repo-relative output folder path>
compiled: 2026-08-05
tokens_estimate: <estimate e.g. ~1800 tokens>
---

## TL;DR
<3-5 sentences summarizing the core technical claim and why it matters.>

## Core ideas
<Bulleted list of key claims, 1 sentence each.>

## Curriculum
1. **<Lesson Title>** — <key concept>. _Exercise:_ <verb + object>.
...

## Capabilities unlocked
- <verb-led technical skill student can perform>
...

## Frameworks / models
<Named technical patterns/architectures introduced with one-line definitions.>

## Quotes worth keeping
<Verbatim sparing quotes in PT-BR with lesson context.>

## How to apply
<When and how an AI or developer should apply this pack's knowledge.>

## See also
<Cross-links to related packs or topics in knowledge/coding/courses/.>
"""

def get_author_and_title(input_course_dir: Path, slug: str) -> tuple[str, str]:
    author = "Mateus Silva"
    title = slug.replace("-", " ").title()

    if input_course_dir.exists():
        desc_files = list(input_course_dir.glob("00-*.description.md")) or list(input_course_dir.glob("*.description.md"))
        for df in desc_files:
            try:
                content = df.read_text(encoding="utf-8")
                match = re.search(r"\*\*Autor\(es\):\*\*\s*(.+)", content)
                if match:
                    author = match.group(1).strip()
                h1_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
                if h1_match:
                    title = h1_match.group(1).strip()
                break
            except Exception:
                pass
    return author, title

def compile_course(course_dir: Path, input_dir: Path) -> bool:
    slug = course_dir.name
    pack_file = course_dir / f"{slug}.pack.md"
    if pack_file.exists():
        print(f"[SKIP] {slug} already has {pack_file.name}")
        return True

    transcripts = sorted(list(course_dir.glob("**/*.transcript.txt")))
    if not transcripts:
        print(f"[SKIP] {slug} has no transcript files")
        return False

    author, title = get_author_and_title(input_dir / slug, slug)

    print(f"[COMPILING] {slug} ({len(transcripts)} lessons)...")

    combined_text = []
    for t in transcripts:
        rel_path = t.relative_to(course_dir)
        lesson_name = t.stem.replace(".transcript", "")
        content = t.read_text(encoding="utf-8")
        if len(content) > 15000:
            content = content[:15000] + "\n...[truncated long lesson]..."
        combined_text.append(f"=== LESSON: {rel_path} ({lesson_name}) ===\n{content}\n")

    full_transcript_str = "\n".join(combined_text)
    rel_course_dir = os.path.relpath(course_dir, Path.cwd())

    prompt = f"""Course Title: {title}
Author: {author}
Output Directory Path: {rel_course_dir}

Here are the verbatim lesson transcripts for this course:

{full_transcript_str[:60000]}

Generate the staged knowledge pack markdown following the system instructions.
"""

    try:
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.2,
            max_output_tokens=3000
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=config
        )

        result_text = response.text.strip()

        if result_text.startswith("```markdown"):
            result_text = result_text[11:]
        if result_text.startswith("```"):
            result_text = result_text[3:]
        if result_text.endswith("```"):
            result_text = result_text[:-3]
        result_text = result_text.strip()

        pack_file.write_text(result_text + "\n", encoding="utf-8")
        print(f"[SUCCESS] Wrote {pack_file}")
        return True
    except Exception as e:
        print(f"[EXCEPT] Error compiling {slug}: {e}")
        return False

def main():
    output_lives = Path("output/jstack-lives")
    input_lives = Path("input/jstack-lives")

    courses = sorted([d for d in output_lives.iterdir() if d.is_dir() and d.name != "jstack-lives-gemini-ref"])

    print(f"Found {len(courses)} live course directories.")
    success_count = 0

    for c in courses:
        packs = list(c.glob("**/*.pack.md"))
        if not packs:
            ok = compile_course(c, input_lives)
            if ok:
                success_count += 1

    print(f"\nFinished processing! Compiled {success_count} new packs.")

if __name__ == "__main__":
    main()
