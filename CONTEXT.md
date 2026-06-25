# CONTEXT.md — Course → Markdown

> Self-contained project brief for a new AI or human contributor. Read after `CLAUDE.md`/`CODEX.md`. The running code and [`MEMORY.md`](MEMORY.md) are the source of truth; [`README.md`](README.md) is the user-facing usage guide. This file explains the system and, crucially, the failure modes already paid for so they are not rediscovered.

## 1. What this project is

Turns course videos you own into compact, AI-readable knowledge packs for the repo's [`knowledge-compiler`](../../skills/knowledge-compiler) skill. **Two stages, two engines:** Gemini does bulk transcription (API, cheap, dumb); a Claude agent does the compression into packs (subscription, judgment). The two never mix — Gemini never writes a pack, Claude never burns API quota transcribing.

## 2. Architecture (two stages)

```text
STAGE 1 — transcription            (Python + Gemini API · bulk, cheap)
  input/<course>/<section>/<module>/<lesson>.mp4
    └ ffmpeg → mono 16 kHz mp3 → [split into ~10-min chunks if > 15 min] → Gemini
       → verbatim transcript → output/<…same tree…>/<lesson>.transcript.txt

STAGE 2 — compilation              (Claude course-module-compiler agent · subscription, NO API)
  output/<…>/<module>/*.transcript.txt
    └ knowledge-compiler `course.md` playbook → one staged <module-slug>.pack.md per MODULE
       → human review → knowledge/<domain>/courses/<slug>.md
```

Stage 1 only transcribes; the verbatim `.txt` is the hand-off. Stage 2 is where the *compression into a knowledge pack* happens — a Claude agent that picks Sonnet (default) or Opus per module, **never** Gemini. Granularity is **per module** = the numbered leaf folders. Note real courses nest 3+ levels (course → section → module → lesson); Stage 1 mirrors whatever tree it is given.

## 3. Hard rules (do not violate)

- **`.venv` for BOTH test and production.** The only allowed global call is the one-time `python3 -m venv .venv`. See [[feedback-python-tests-use-venv]].
- **Stage 2 runs on the Claude subscription — never the Gemini API.** Compilation is judgment work; transcription is the only API spend.
- **Run `main.py input/` for a full course** (root = `input/` → full tree mirrored). Pointing at a *sub-folder* makes that folder the root, so output **flattens** into `output/`. Footgun — see §4.
- **Transcripts and packs are STAGED.** Promotion into `knowledge/<domain>/courses/` is a human step; never auto-write into the library.
- **Gemini = `gemini-2.5-flash`, thinking off** (same provider/pattern as the PsiAtiva gender workflow). One Google AI key in `.env` (`GEMINI_API_KEY` or `GOOGLE_API_KEY`).
- **A full course needs a paid Gemini tier** (see §4, daily cap).

## 4. Failure modes already fixed (regression list)

These four bit on the first real course (Motion Boost, 80 lessons). A trivial validation lesson hides all of them. Full narrative in [`MEMORY.md`](MEMORY.md).

1. **Accented filenames — two separate breaks.**
   - Under an ASCII `C` locale (cron, bare shell, background task), ffmpeg/subprocess on `módulo`/`composição` raises `'ascii' codec can't encode`. → Fixed by a **UTF-8 re-exec guard** at the top of `main.py` (re-execs with `-X utf8` when the fs encoding is not UTF-8).
   - The Gemini Files API sends the **upload filename in an ASCII-only HTTP header** (httpx `_normalize_header_value`), so even under UTF-8 an accented upload path raises `UnicodeEncodeError`. → Fixed by `_ascii_name()` in `pipeline.py`: the *temp upload audio* is transliterated; the output transcript keeps the accented lesson name. **Never pass an accented path to `client.files.upload`.**
2. **Long-audio repetition loops.** On 30–46-min lessons the model can fall into a loop repeating one phrase (observed **1011×**) until it exhausts the 64k output ceiling (`finish_reason=MAX_TOKENS`) — producing a huge, garbage transcript. → Fixed by **audio chunking**: files over `AUDIO_CHUNK_THRESHOLD_SEC` (15 min) are split into `AUDIO_CHUNK_LENGTH_SEC` (~10 min) segments (`audio.split_audio`), each transcribed and concatenated (`pipeline._transcribe_audio`). Symptom to watch for: a transcript with an absurd word count or a sentence repeated dozens+ times.
3. **Frozen call hangs forever.** If the machine sleeps mid-run, the in-flight HTTP call never returns (once stalled 11h at 25/80, with the process alive but making no progress). → Fixed by a **10-min per-request timeout** (`config.REQUEST_TIMEOUT_MS` → `HttpOptions(timeout=)`); a frozen call now errors and the resilient batch continues / resumes.
4. **Free-tier daily cap = 20 `generate_content`/day** for `gemini-2.5-flash` (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`). → `gemini_client.generate_with_retry` sleeps+retries genuine per-minute 429s but raises `DailyQuotaExhausted` on a `PerDay` cap so the batch **stops cleanly** (resumable) instead of churning ffmpeg on doomed calls. A full course requires **billing enabled (Tier 1)**.

## 5. Config knobs (env overrides, see `config.py`)

| Env var | Default | Purpose |
|---|---|---|
| `COURSE_TO_MD_MODEL` | `gemini-2.5-flash` | transcription model |
| `COURSE_TO_MD_THINKING_BUDGET` | `0` | 2.5 thinking off |
| `COURSE_TO_MD_REQUEST_TIMEOUT_MS` | `600000` | per-request timeout (anti-hang) |
| `COURSE_TO_MD_CHUNK_THRESHOLD_SEC` | `900` | split lessons longer than this |
| `COURSE_TO_MD_CHUNK_LENGTH_SEC` | `600` | chunk size |
| `COURSE_TO_MD_TRANSCRIBE_MAX_TOKENS` | `65536` | output ceiling |
| `KNOWLEDGE_COMPILER_DIR` | (auto) | override the `course.md` reference path |

## 6. Current state (2026-06-23)

- **Stage 1 done on a real full course.** Motion Boost: 80/80 lessons, 12 module folders, 3 sections (`conceito-e-teoria` · `after-effects` · `rive`), 17.35 h, ~158.6k words — clean (0 errors, 0 `MAX_TOKENS`) on Tier 1.
- **Stage 2 not yet run on it** (chosen to wait until all 80 were transcribed). Next step: compile the 12 modules → review → promote, target domain likely `knowledge/design/courses/`.

## 7. File map

```text
course-to-markdown/
  main.py                       # Stage-1 CLI entry (UTF-8 re-exec guard at top)
  agent.md                      # Stage-2 course-module-compiler agent (symlinked into .claude/agents/)
  course_to_markdown/
    config.py                   # env, model, timeout, chunk thresholds, paths
    audio.py                    # ffmpeg normalize + probe_duration + split_audio
    gemini_client.py            # client (with timeout), upload, retry/quota classify
    prompts.py                  # transcription/formatting prompts (+ today's date injection)
    transcribe.py               # single generate_content call (wrapped in retry)
    formatter.py                # legacy Gemini .md path (--gemini-format only)
    pipeline.py                 # orchestration: _ascii_name, _transcribe_audio (chunking), run()
  input/   output/   .logs/     # all gitignored
  README.md  MEMORY.md  CONTEXT.md  CLAUDE.md  CODEX.md
```

## 8. Commands

```bash
cd knowledge/projects/course-to-markdown
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
cp .env.example .env                              # GEMINI_API_KEY=...

PYTHONUTF8=1 .venv/bin/python -u main.py input/ --language Portuguese   # Stage 1 (full course)
.venv/bin/python main.py input/ --dry-run         # extract audio + report; no API
# Stage 2: ask the Claude session to compile — it spawns course-module-compiler per module.
```

Stage 1 is idempotent (re-runs skip finished lessons) and batch-resilient (one bad file does not stop the run). Background long runs and `tail -f .logs/transcribe.log`; if the machine sleeps the run may stall — re-run to resume.
