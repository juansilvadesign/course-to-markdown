# CODEX.md — Course → Markdown

Read this first when working in this project. It is the compact operating contract for Codex sessions and mirrors [`CLAUDE.md`](CLAUDE.md) — keep the two in sync; when you change one, change the other. Read [`CONTEXT.md`](CONTEXT.md) next for the full architecture + failure-mode brief, [`MEMORY.md`](MEMORY.md) for state, and [`README.md`](README.md) for usage.

## Session start

Order: `CODEX.md`/`CLAUDE.md` → `CONTEXT.md` → `MEMORY.md` (state + gotchas) → `README.md` → only the code relevant to the request. The running code is the source of truth.

## Product in one paragraph

A two-stage pipeline that turns owned course videos into knowledge-compiler packs. **Stage 1** (`main.py`, Python + Gemini API) recurses `input/`, extracts audio with ffmpeg, chunks long lessons, transcribes with `gemini-2.5-flash`, and mirrors the folder tree into `output/<…>/<lesson>.transcript.txt`. **Stage 2** (the `course-module-compiler` agent, on the Claude subscription — *not* the API) compiles one staged `<module>.pack.md` per module via the `knowledge-compiler` `course.md` playbook, for human review before promotion to `knowledge/<domain>/courses/`.

## Hard rules (never violate)

- **`.venv` for both test and production.** Only allowed global call: the one-time `python3 -m venv .venv`.
- **Stage 2 is Claude-subscription only — never the Gemini API.** Gemini transcribes; Claude compiles.
- **Run `main.py input/` for a full course.** Output mirroring is relative to the *target*; pointing at a sub-folder flattens output into `output/`.
- **Transcripts and packs are staged.** Promotion into `knowledge/` is a human step — never auto-write the library.
- **Gemini = `gemini-2.5-flash`, thinking off.** One Google AI key in `.env`. A full course needs a **paid tier** (free tier caps at 20 requests/day).
- **Never invent dates** in frontmatter — the code injects today's date; the Stage-2 agent carries the same rule.

## Hard-won lessons — keep these, do not regress (full detail in `CONTEXT.md` §4)

- **UTF-8 re-exec guard** at the top of `main.py` — accented filenames (`módulo`) break ffmpeg/subprocess under an ASCII `C` locale.
- **`_ascii_name()` for upload temp audio** — the Gemini Files API puts the upload filename in an ASCII-only HTTP header; an accented path raises `UnicodeEncodeError`. Never pass an accented path to `client.files.upload`; the output transcript keeps the accented name.
- **Audio chunking** (`_transcribe_audio` / `audio.split_audio`, >15 min → ~10 min) — long lessons otherwise hit the 64k output ceiling *and* loop one phrase (seen 1011×). Absurd word counts or a sentence repeated dozens of times = chunking regressed.
- **10-min per-request timeout** (`HttpOptions(timeout=)`) — a slept machine once froze a call for 11h. Keep it so a frozen call errors and the batch resumes.
- **Quota handling** (`generate_with_retry` + `DailyQuotaExhausted`) — retry per-minute 429s, stop cleanly on the per-day cap. Do not replace with blind retries.

## Commands

```bash
cd knowledge/projects/course-to-markdown
PYTHONUTF8=1 .venv/bin/python -u main.py input/ --language Portuguese   # Stage 1, full course
.venv/bin/python main.py input/ --dry-run                              # audio + report, no API
.venv/bin/python -c "import course_to_markdown.pipeline"               # import smoke check
```

Stage 1 is idempotent (skips finished lessons) and batch-resilient (one bad file doesn't stop the run). Run long batches in the background and watch `.logs/transcribe.log`.

## Definition of done

- Change has an import/smoke check or a real run behind it; accented + long-lesson paths still work.
- `.venv` used throughout; no library auto-writes; staged outputs only.
- `MEMORY.md` state + this file/`CLAUDE.md` updated together when behavior or gotchas change.

## Common mistakes

- Using global Python instead of `.venv`.
- Running Stage 2 against the Gemini API instead of the Claude subscription.
- Pointing `main.py` at a sub-folder and flattening the output tree.
- Passing accented paths to `files.upload`, or removing the UTF-8 guard / `_ascii_name`.
- Removing chunking and hitting `MAX_TOKENS` / repetition loops on long lessons.
- Auto-promoting packs into `knowledge/` without human review.
- Inventing a `compiled:` date.
