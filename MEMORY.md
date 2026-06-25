---
name: Course-to-Markdown Project Memory
description: Working memory for the course-to-markdown two-stage pipeline — architecture, decisions, gotchas, and state.
type: project
---

# course-to-markdown — Project Memory

Turns owned course videos into `knowledge-compiler` packs. Built 2026-06-19 (MVP). See [`README.md`](README.md) for usage; this file holds the decisions, gotchas, and state a future session needs.

## Architecture — two stages, two engines

**Stage 1 — transcription (Python + Gemini API · bulk, cheap).** `main.py` recurses `input/`, extracts audio (ffmpeg subprocess), transcribes each lesson with `gemini-2.5-flash` (thinking off, `google-genai` SDK + Files API), and writes `output/<course>/<module>/<lesson>.transcript.txt` — **mirroring the input folder tree**. The transcript is the deliverable / hand-off.

**Stage 2 — compilation (Claude Code agent · subscription, NO API).** The `course-module-compiler` agent (`agent.md` → symlinked into `.claude/agents/`) compiles **one pack per module** from that module's transcripts, via the `knowledge-compiler` skill's `course.md`. Defaults to **Sonnet**; returns `ESCALATE_TO_OPUS: <reason>` when a module is dense → the orchestrator re-spawns it on Opus. Packs are **staged** as `<module>/<slug>.pack.md`; a human promotes them to `knowledge/<domain>/courses/`.

## Key decisions
- **Granularity = per MODULE** (user, 2026-06-19) — honors `course.md`'s "split by module cluster" + ~2k-token cap. Not per-lesson, not per-course.
- **Gemini = transcription only.** Compilation moved to the Claude agent (judgment + Sonnet/Opus choice, on the subscription). The old Gemini-formatting path is kept as legacy `--gemini-format`.
- **Transcript is the default output**; `--gemini-format` is opt-in legacy.
- **`.venv` for BOTH test and production** (user rule). `.venv/` and `.env` are gitignored.
- **Download (Stage 0)** is out of scope here — done manually, or via the sibling [`../one-click-video-downloader`](../one-click-video-downloader) (Cat Catch–based extension, built MVP). Its MP4s get dropped into `input/`.

## Gotchas / implementation notes
- **ffmpeg via subprocess**, not moviepy (moviepy 1.0.3 is rough on Py 3.12; system ffmpeg is present). Audio normalized to **mono 16 kHz 64k MP3** to keep Files-API uploads small.
- **Files API is required** for course audio (inline request cap is ~20 MB). Uploaded files are deleted after each run (and auto-expire ~48h).
- **Date-hallucination fix:** the formatting prompt injects today's date — otherwise the model invents a `compiled:` date (it guessed `2023-11-20` on the first run). The Stage-2 agent carries the same "never invent a date" rule.
- **Idempotency:** re-runs skip a lesson whose final artifact already exists (`--overwrite` forces). An existing transcript is reused unless `--retranscribe` → cheap re-formatting only.
- **Batch resilience:** a bad file is caught + reported; the batch keeps going.
- **Model/key:** `gemini-2.5-flash`, thinking off — same provider/pattern as the PsiAtiva gender workflow. Single Google AI key in `.env`.

## Hardening from the first full course run (Motion Boost, 80 lessons, 2026-06-23)
The simple validation lesson hid four bugs that only a real nested course surfaced — all fixed:
- **Accented filenames, two separate breaks.** (1) Under an ASCII `C` locale (cron/bare shell/background), ffmpeg/subprocess on `módulo`/`composição` raises `'ascii' codec can't encode`. Fixed by a UTF-8 re-exec guard at the top of `main.py` (`-X utf8`). (2) The Gemini Files API sends the upload filename in an **ASCII-only HTTP header** (httpx `_normalize_header_value`), so even under UTF-8 the accented *temp audio* name raises `UnicodeEncodeError` on upload. Fixed by `_ascii_name()` in `pipeline.py` — the uploaded temp `.norm.mp3` is transliterated; the output transcript keeps the accented lesson name.
- **Free-tier daily cap = 20 `generate_content`/day.** Hit it at ~18 lessons. `gemini_client.generate_with_retry` now sleeps+retries per-minute 429s but raises `DailyQuotaExhausted` on a `PerDay` cap so the batch stops cleanly (resumable) instead of churning ffmpeg on doomed calls. **Resolution: user enabled billing → Tier 1**, then the rest flew through.
- **Frozen call hangs forever.** Machine slept mid-run → the in-flight HTTP call never returned → silent 11h stall at 25/80. Fixed with a **10-min per-request timeout** (`config.REQUEST_TIMEOUT_MS` → `HttpOptions(timeout=)`); a frozen call now errors and the batch continues/resumes.
- **Long-audio repetition loops.** 38-46 min `rive` lessons made the model loop one phrase (worst: **1011×**) until it burned all 64k output tokens (`MAX_TOKENS`). Fixed with **audio chunking**: files > `AUDIO_CHUNK_THRESHOLD_SEC` (15 min) are split into `AUDIO_CHUNK_LENGTH_SEC` (~10 min) segments (`audio.split_audio`), each transcribed and concatenated (`pipeline._transcribe_audio`). The 3 looped files re-ran to 5.9-7.5k sane words, 0 repeats.

## State (2026-06-23)
- ✅ **Stage 1 DONE on a real full course.** Motion Boost: **80/80 lessons, 12 module folders, 3 sections (conceito-e-teoria · after-effects · rive), 17.35h, ~158.6k words** — all transcribed clean (0 errors, 0 `MAX_TOKENS`) on Tier 1. Note the **3-level nesting** (course → section → module → lesson); Stage-2 "module" = the numbered leaf folders.
- ⚠️ **Footgun:** structure-mirroring is relative to the *target*. Run `main.py input/` (root = `input/`) for the full tree; pointing at a sub-folder flattens output into `output/`.
- ✅ **Stage 2 DONE — 12/12 module packs compiled & staged** (2026-06-23), all on **Sonnet** (none needed Opus, even the 17-lesson `cards-para-web` at ~1950 tok). Each is `<module>/<slug>.pack.md`, dated correctly, English structure + PT content, under the 2k cap, nothing leaked into `knowledge/`. Language convention chosen by user: **English skeleton, PT content** (cross-lingual).
- ✅ **Accent caveat RESOLVED.** First batch stripped PT diacritics on ~10 packs (`cards-para-web`/`lottie` fully ASCII) — a cross-lingual artifact of reasoning in English. Root-caused → `agent.md` now mandates "preserve diacritics EXACTLY" (English structure / PT content with full accents). All 10 regenerated in batches of 4; verified all 12 now carry proper accents (non-ASCII counts 54–195).
- 💡 **Batch lessons:** (1) spawning ~11 `course-module-compiler` agents at once hit a **session limit** mid-run — but agents that had already `Write`-n their pack kept it (disk is ground truth; reports said "limit" yet 11/12 packs were on disk). **Batches of ≤4 are safe; 11 is not.** (2) An agent flagged module-06 lessons 05/06 as "identical transcripts" — **false alarm** (distinct hashes, 40 vs 45 min source videos, different openings); they're distinct lessons sharing a project theme.
- ✅ **PROMOTED, then RE-CUT to section level (2026-06-25).** First promoted as 12 module packs (06-23); the user judged them too granular vs the `ux-unicornio-*` by-discipline shape, so re-cut to **4 section packs**: `motion-boost-{conceito-e-teoria, after-effects-fundamentos, after-effects-projetos-web, rive}.md` (After Effects split in two — 6 modules / 4 projects won't compress to one). The 12 old library files were deleted; `courses/` now holds 7 `ux-unicornio-*` + 4 `motion-boost-*`. Also distilled **4 reusable `design/guides/`** from this course (rive-interactive-animation · lottie-for-web · web-motion-delivery-decision · animating-ui-cards-for-web — filling the library's zero Rive/Lottie coverage) and fixed 2 dangling refs the rename created. Uncommitted. Two lessons: **(a) granularity = the source's reusable unit, not reflexively per-module** (section/tool here, like ux-unicornio's discipline); **(b) when the parallel `course-module-compiler` fan-out hits the account session limit, compile in the main thread from the already-approved module packs** (atomic Writes, resumable) instead of waiting for the reset. **Pipeline exercised end-to-end: 80 videos → 80 transcripts → 4 section packs + 4 guides.**

## Map
- `main.py` — Stage-1 CLI · `course_to_markdown/` — package (`config`, `audio`, `gemini_client`, `prompts`, `transcribe`, `formatter`, `pipeline`)
- `agent.md` — Stage-2 agent (→ `.claude/agents/course-module-compiler.md`)
- `input/` (drop the course here) · `output/` (transcripts + staged packs) — both gitignored
- Skill: [`../../skills/knowledge-compiler`](../../skills/knowledge-compiler) · Idea: `knowledge/ideas/course-videos-to-knowledge-markdown.md`
