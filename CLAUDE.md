# CLAUDE.md — Course → Markdown

Operating contract for Claude Code sessions in this project. It mirrors [`CODEX.md`](CODEX.md) — keep the two in sync; when you change one, change the other. Read [`CONTEXT.md`](CONTEXT.md) for the full architecture + failure-mode brief, [`MEMORY.md`](MEMORY.md) for state and the hardening narrative, and [`README.md`](README.md) for user-facing usage.

## Session start

Read in this order: `CLAUDE.md`/`CODEX.md` → `CONTEXT.md` → `MEMORY.md` (state + gotchas) → `README.md` (usage) → only the code relevant to the request. The running code is the source of truth.

## Product in one paragraph

A two-stage pipeline that turns owned course videos into knowledge-compiler packs. **Stage 1** (`main.py`, Python + Gemini API) recurses `input/`, extracts audio with ffmpeg, chunks long lessons, transcribes with `gemini-2.5-flash` (or Groq Whisper via `--provider groq`), and mirrors the folder tree into `output/<…>/<lesson>.transcript.txt`. **Stage 2** (the `course-module-compiler` agent, on the Claude subscription — *not* the API) compiles one staged `<module>.pack.md` per module via the `knowledge-compiler` `course.md` playbook, for human review before promotion to `knowledge/<domain>/courses/`.

## Hard rules (never violate)

- **`.venv` for both test and production.** Only allowed global call: the one-time `python3 -m venv .venv`. See [[feedback-python-tests-use-venv]].
- **Stage 2 is Claude-subscription only — never the Gemini API.** Gemini transcribes; Claude compiles.
- **Run `main.py input/` for a full course.** Output mirroring is relative to the *target*; pointing at a sub-folder flattens output into `output/`.
- **Transcripts and packs are staged.** Promotion into `knowledge/` is a human step — never auto-write the library.
- **Gemini = `gemini-2.5-flash`, thinking off.** One Google AI key in `.env`. A full course needs a **paid tier** (free tier caps at 20 requests/day).
- **Provider is pluggable; Gemini is the default.** `--provider groq` swaps Stage-1 transcription to Groq Whisper (`whisper-large-v3-turbo`, needs `GROQ_API_KEY`) — cheaper/faster STT with no 64k-ceiling or repetition-loop failure modes; it does **not** change Stage 2. **Choose per course by how much English jargon the audio carries — see _Choosing a provider_ below.** Zen/opencode **can't** transcribe (text-only gateway, its Gemini is broken) — see `MEMORY.md` 2026-07-02.
- **Never invent dates** in any frontmatter — the code injects today's date; the Stage-2 agent carries the same rule.

## Choosing a provider (Gemini vs Groq)

Decide **per course, at invocation** — this affects **Stage 1 only** (Stage 2 Claude compilation is unchanged). The deciding variable is **how much English technical vocabulary the audio contains**: Whisper turbo garbles English terms spoken inside Portuguese (it rendered the TS type `any` as "N", "um N.ts"), while Gemini reads them faithfully.

- **Lots of English jargon → Gemini (default).** Programming / DevOps / data courses, and any course thick with English tool, product, or API names (TypeScript, React, Node, Docker, After Effects, Rive, Figma…). Fidelity wins exactly where the words carry the meaning.
- **Mostly Portuguese prose → Groq (`--provider groq`).** Business, marketing, communication, soft-skills, or theory courses where English terms are rare — Whisper's weakness never bites, and you get cheaper + faster transcription with no output-ceiling or repetition-loop risk.
- **Gemini quota exhausted with no paid tier?** For a low-jargon course, switch to Groq to keep moving. For a jargon-heavy one, prefer waiting / upgrading Gemini over accepting the `any`→"N" class of errors.
- **Unsure → Gemini** (safer on fidelity), or transcribe one representative lesson with each and eyeball how the English terms render before committing the whole batch.

Tell from the `input/<course>/` folder name + any `*.description.md` / `manifest.json`. Both free tiers are rate-limited — a full course usually needs a paid tier. **Gemini free** caps at ~20 requests/day; **Groq Whisper-turbo free**'s binding cap is audio-seconds — **~8 h of audio/day** (28,800 ASD) + ~2 h/hour (7,200 ASH), 20 RPM, 2,000 RPD — so a long course spans several days (Motion Boost's 17 h ≈ 3 days). Full table + 429/`retry-after` headers: `knowledge/sources/groq-rate-limits.md`.

## Hard-won lessons — keep these, do not regress (full detail in `CONTEXT.md` §4)

- **UTF-8 re-exec guard** at the top of `main.py` — accented filenames (`módulo`) break ffmpeg/subprocess under an ASCII `C` locale. Keep it.
- **`_ascii_name()` for upload temp audio** — the Gemini Files API puts the upload filename in an ASCII-only HTTP header; an accented path raises `UnicodeEncodeError`. Never pass an accented path to `client.files.upload`. The output transcript keeps the accented name.
- **Audio chunking** (`_transcribe_audio` / `audio.split_audio`, >15 min → ~10 min) — long lessons otherwise trip the 64k output ceiling *and* push the model into phrase-repetition loops (seen 1011×). If a transcript is absurdly large or repeats a sentence dozens of times, chunking regressed.
- **10-min per-request timeout** (`HttpOptions(timeout=)`) — a slept machine froze a call for 11h. Keep it so a frozen call errors and the batch resumes.
- **Quota handling** (`generate_with_retry` + `DailyQuotaExhausted`) — retry per-minute 429s, stop cleanly on the per-day cap. Don't replace with blind retries.

## Commands

```bash
cd knowledge/projects/course-to-markdown
PYTHONUTF8=1 .venv/bin/python -u main.py input/ --language Portuguese   # Stage 1, full course (Gemini, default)
.venv/bin/python main.py input/ --provider groq --language Portuguese   # Stage 1 via Groq Whisper (needs GROQ_API_KEY)
.venv/bin/python main.py input/ --dry-run                              # audio + report, no API
.venv/bin/python -c "import course_to_markdown.pipeline"               # import smoke check
```

Stage 1 is idempotent (skips finished lessons) and batch-resilient (one bad file doesn't stop the run). Run long batches in the background and watch `.logs/transcribe.log`.

## Definition of done

- Change has an import/smoke check or a real run behind it; accented + long-lesson paths still work.
- `.venv` used throughout; no library auto-writes; staged outputs only.
- `MEMORY.md` state + this file/`CODEX.md` updated together when behavior or gotchas change.

## Common mistakes

- Using global Python instead of `.venv`.
- Running Stage 2 against the Gemini API instead of the Claude subscription.
- Pointing `main.py` at a sub-folder and flattening the output tree.
- Passing accented paths to `files.upload`, or removing the UTF-8 guard / `_ascii_name`.
- Removing chunking and hitting `MAX_TOKENS` / repetition loops on long lessons.
- Auto-promoting packs into `knowledge/` without human review.
- Inventing a `compiled:` date.
