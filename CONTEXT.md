# CONTEXT.md — Course → Markdown

> Self-contained project brief for a new AI or human contributor. Read after `CLAUDE.md`/`CODEX.md` and the live [`TASKS.md`](TASKS.md). The running code, on-disk manifests/transcripts, and [`MEMORY.md`](MEMORY.md) are the source of truth; [`README.md`](README.md) is the user-facing usage guide. This file explains the system and, crucially, the failure modes already paid for so they are not rediscovered.

## 1. What this project is

Turns courses the user is entitled to use into compact, AI-readable knowledge packs for the repo's [`knowledge-compiler`](../../skills/knowledge-compiler) skill. **Three stages, two processing engines:** optional authenticated acquisition writes local media; Gemini/Groq does bulk transcription; a Claude agent compresses selected transcripts into packs on the subscription. The processing engines never mix — Gemini never writes a pack, Claude never burns API quota transcribing.

## 2. Architecture (three stages)

```text
STAGE 0 — authenticated acquisition  (Python + user's exported browser session)
  JStack / DesignBoost / Skool
    └ curriculum + media → input/<platform>/<course>/<module>/<lesson>.m4a
       atomic manifest.json → safe --resume; DRM is skipped, never decrypted

STAGE 1 — transcription            (Python + Gemini API · bulk, cheap)
  input/<course>/<section>/<module>/<lesson>.(mp4|m4a|…)
    └ ffmpeg → mono 16 kHz mp3 → [split into ~10-min chunks if > 15 min] → Gemini
       → verbatim transcript → output/<…same tree…>/<lesson>.transcript.txt

STAGE 2 — compilation              (Claude course-module-compiler agent · subscription, NO API)
  output/<…>/<module>/*.transcript.txt
    └ knowledge-compiler `course.md` playbook → staged pack(s) by reusable unit/cluster
       → human review → knowledge/<domain>/courses/<slug>.md
```

Stage 0 is optional when media already exists. Stage 1 only transcribes; the verbatim `.txt` is the hand-off. Stage 2 is where the *compression into a knowledge pack* happens — a Claude agent that picks Sonnet (default) or Opus, **never** Gemini. Start from numbered leaf modules, then re-cut by the source's reusable unit when that produces a better library artifact. Real courses nest 3+ levels; Stage 1 mirrors whatever tree it is given.

## 3. Hard rules (do not violate)

- **`.venv` for BOTH test and production.** The only allowed global call is the one-time `python3 -m venv .venv`. See [[feedback-python-tests-use-venv]].
- **Legitimate Stage 0 access only.** Use the user's exported Netscape cookie session; never automate credentials, broaden access, bypass DRM, or leak cookie/bearer/signed-query values. Working media and transcripts stay gitignored.
- **Every Stage 0 adapter is resumable and conservative.** Audio-only default, atomic manifest, dry-run, polite rate floor, redacted output, and explicit `skipped-drm`.
- **Stage 2 runs on the Claude subscription — never the Gemini API.** Compilation is judgment work; transcription is the only API spend.
- **Mirroring is relative to the input target.** Run `main.py input/` for the whole tree. For an isolated batch, explicitly pair roots (`main.py input/<batch> -o output/<batch>`); otherwise the batch folder is flattened.
- **Transcripts and packs are STAGED.** Promotion into `knowledge/<domain>/courses/` is a human step; never auto-write into the library.
- **Gemini = `gemini-2.5-flash`, thinking off** (same provider/pattern as the PsiAtiva gender workflow). One Google AI key in `.env` (`GEMINI_API_KEY` or `GOOGLE_API_KEY`).
- **A full course needs a paid Gemini tier** (see §4, daily cap).

## 4. Failure modes already fixed (regression list)

These four bit on the first real course (Motion Boost, 80 lessons). A trivial validation lesson hides all of them. Full narrative in [`MEMORY.md`](MEMORY.md).

1. **Accented filenames — two separate breaks.**
   - Under an ASCII `C` locale (cron, bare shell, background task), ffmpeg/subprocess on `módulo`/`composição` raises `'ascii' codec can't encode`. → Fixed by a **UTF-8 re-exec guard** at the top of `main.py` (re-execs with `-X utf8` when the fs encoding is not UTF-8).
   - The Gemini Files API sends the **upload filename in an ASCII-only HTTP header** (httpx `_normalize_header_value`), so even under UTF-8 an accented upload path raises `UnicodeEncodeError`. → Fixed by `_ascii_name()` in `pipeline.py`: the *temp upload audio* is transliterated; the output transcript keeps the accented lesson name. **Never pass an accented path to `client.files.upload`.**
2. **Long-audio repetition loops.** On 30–46-min lessons the model can fall into a loop repeating one phrase (observed **1011×**) until it exhausts the 64k output ceiling (`finish_reason=MAX_TOKENS`) — producing a huge, garbage transcript. → Fixed by **audio chunking**: files over `AUDIO_CHUNK_THRESHOLD_SEC` (15 min) are split into `AUDIO_CHUNK_LENGTH_SEC` (~10 min) segments (`audio.split_audio`), each transcribed and concatenated (`pipeline._transcribe_audio`). Any non-`STOP` finish reason is now rejected instead of saving a potentially truncated transcript; retry that lesson with a shorter chunk length. Symptom to watch for in legacy output: an absurd word count or a sentence repeated dozens+ times.
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

## 6. Current state (2026-07-28)

- **The pipeline is proven end to end.** Motion Boost and JStack Full Stack moved through transcription, compilation/re-cut, review, and manual promotion; long lessons and nested accented paths are production-tested.
- **Stage 0 supports three platforms.** JStack covers trainings/projects/lives; DesignBoost covers its four member catalogs; Skool covers authenticated classroom URLs and native/external video.
- **DesignBoost + supplied Skool URL pass authenticated dry-runs.** Offline downloader suite is 10/10.
- **JStack completion is the live work.** Projects are downloaded and their Gemini transcription is resumable; the 69-live media batch is resumable. Exact current checkboxes and restart commands live in [`TASKS.md`](TASKS.md), not in this slower-moving brief.

## 7. File map

```text
course-to-markdown/
  downloaders/
    _shared.py                  # cookie/redaction/DRM/manifest/download core
    jstack.py                   # JStack trainings/projects/lives
    designboost.py  skool.py    # authenticated platform adapters
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
  tests/                        # offline downloader contract/safety tests
  scripts/transcribe_batches.py # bounded child-course Stage-1 fan-out
  input/   output/   .logs/     # all gitignored
  TASKS.md  ROADMAP.md
  README.md  MEMORY.md  CONTEXT.md  CLAUDE.md  CODEX.md
```

## 8. Commands

```bash
cd knowledge/projects/course-to-markdown
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
cp .env.example .env                              # GEMINI_API_KEY=...

.venv/bin/python downloaders/jstack.py --list --cookies input/cookies-jstack.txt
.venv/bin/python downloaders/designboost.py --list
.venv/bin/python downloaders/skool.py "https://www.skool.com/<group>/classroom/<course>" --dry-run
PYTHONUTF8=1 .venv/bin/python -u main.py input/ --language Portuguese   # Stage 1 (full course)
.venv/bin/python -u main.py input/jstack-projects -o output/jstack-projects --provider gemini --language Portuguese
.venv/bin/python -u scripts/transcribe_batches.py input/jstack-lives output/jstack-lives --jobs 3 --provider gemini --language Portuguese
.venv/bin/python main.py input/ --dry-run         # extract audio + report; no API
.venv/bin/python -m unittest discover -s tests -v
# Stage 2: ask the Claude session to compile — it spawns course-module-compiler per module.
```

Stage 1 is idempotent (re-runs skip finished lessons) and batch-resilient (one bad file does not stop the run). Background long runs and `tail -f .logs/transcribe.log`; if the machine sleeps the run may stall — re-run to resume.
