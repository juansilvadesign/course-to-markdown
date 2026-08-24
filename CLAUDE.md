# CLAUDE.md — Course → Markdown

Operating contract for Claude Code sessions in this project. It mirrors [`CODEX.md`](CODEX.md) — keep the two in sync; when you change one, change the other. Then open [`TASKS.md`](TASKS.md) for the live execution state, [`CONTEXT.md`](CONTEXT.md) for the full architecture + failure-mode brief, [`MEMORY.md`](MEMORY.md) for durable state, [`README.md`](README.md) for user-facing usage, and [`ROADMAP.md`](ROADMAP.md) only for deferred scope.

## Session start

Read in this order: `CLAUDE.md`/`CODEX.md` → `TASKS.md` → `CONTEXT.md` → `MEMORY.md` (state + gotchas) → `README.md` (usage) → only the code relevant to the request. The running code and on-disk manifests/transcripts are the source of truth.

## Product in one paragraph

A three-stage path that turns courses the user is entitled to use into knowledge-compiler packs. **Stage 0** (`downloaders/`) uses exported browser sessions to enumerate and resumably acquire JStack, DesignBoost, or Skool media as transcription-ready `.m4a`, while redacting secrets and refusing DRM. **Stage 1** (`main.py`, Python) recurses `input/`, extracts audio with ffmpeg, chunks long lessons, transcribes with `xiaomi/mimo-v2.5` via OpenRouter by default (or `gemini-2.5-flash`, or Groq Whisper — `--provider {openrouter,gemini,groq}`), and mirrors the folder tree into `output/<…>/<lesson>.transcript.txt`. **Stage 2** (the `course-module-compiler` agent, on the Claude subscription — *not* the API) compiles staged packs via the `knowledge-compiler` `course.md` playbook, for human review before promotion to `knowledge/<domain>/courses/`.

## Hard rules (never violate)

- **`.venv` for both test and production.** Only allowed global call: the one-time `python3 -m venv .venv`. See [[feedback-python-tests-use-venv]].
- **Legitimate Stage 0 access only.** Accept the user's own Netscape cookie export; never automate credentials, broaden access, defeat platform controls, or decrypt DRM. Cookie files, signed URLs, media, and transcripts never enter Git or logs.
- **Stage 0 defaults to audio-only.** The pipeline transcribes; it does not need watch-quality video. Every new adapter needs dry-run, atomic manifest/resume, redaction, polite rate limiting, and a DRM guard.
- **Stage 2 is Claude-subscription only — never the Gemini API.** Gemini transcribes; Claude compiles.
- **Output mirroring is relative to the input target.** Run `main.py input/` for the whole tree. For an isolated batch, pair roots explicitly (`main.py input/<batch> -o output/<batch>`); pointing at a subfolder while leaving the default output flattens it.
- **Transcripts and packs are staged.** Promotion into `knowledge/` is a human step — never auto-write the library.
- **Gemini = `gemini-2.5-flash`, thinking off.** One Google AI key in `.env`. A full course needs a **paid tier** (free tier caps at 20 requests/day).
- **Provider is pluggable; `openrouter` is the default (changed 2026-08-04, was `gemini`).** `--provider {openrouter,gemini,groq}` selects the Stage-1 backend; none of them change Stage 2. `openrouter` = `xiaomi/mimo-v2.5` with base64-inline audio (needs `OPENROUTER_API_KEY` **and a funded balance**); `groq` = Whisper `whisper-large-v3-turbo` (needs `GROQ_API_KEY`). **Choose per course by how much English jargon the audio carries — see _Choosing a provider_ below.** Zen/opencode **can't** transcribe (text-only gateway, its Gemini is broken) — see `MEMORY.md` 2026-07-02.
- **⚠️ The default trades jargon fidelity for cost and loop-immunity — know this before pointing it at a code-dense course.** MiMo rewrote the TypeScript type `unknown` as `any` in **7/7** occurrences on a real lesson, *fluently* — so it passes every guard here (finish reason, repetition, word count, diacritics, wpm). Audit MiMo output with `scripts/jargon_audit.py`; for code-dense courses prefer `--provider gemini`.
- **Never invent dates** in any frontmatter — the code injects today's date; the Stage-2 agent carries the same rule.
- **⛔🔴 `input/` and `output/` are gitignored, so they have exactly ONE copy — and `input/` is not just media.** Alongside the `.m4a` it holds the **74 `manifest.json`** (the only record of curriculum order — 6 modules name every lesson `1000-<title>`, so filename sort silently goes alphabetical) and **1,705 `.description.md`** author sidecars: 1.85 MB that no re-download restores in isolation. **Delete by media extension, never by directory**, and never on the belief that git has a copy — it never has, deliberately, because this repo is public. Archive at `knowledge/backups/course-to-markdown/` in the private parent. **Source media was deleted 2026-08-23** (21.49 GB); only `gerenciamento-de-estados-com-zustand`, `dominando-o-react-hook-form` and `websockets-e-cronjobs-serverless-na-aws` can still be re-transcribed.

## Choosing a provider (OpenRouter / Gemini / Groq)

Decide **per course, at invocation** — this affects **Stage 1 only** (Stage 2 Claude compilation is unchanged). The deciding variable is **how much English technical vocabulary the audio contains**. Only Gemini reads English terms embedded in Portuguese speech faithfully; **both cheap providers corrupt them, in different ways**:

| provider | $/h audio | output ceiling | jargon fidelity |
|---|---|---|---|
| `openrouter` (`xiaomi/mimo-v2.5`, **pinned to the Xiaomi backend**) — **default** | **~$0.008** | 131k model / **8k `max_tokens`** | ⛔ **fluent** substitution (`unknown`→`any`, 7/7) |
| `gemini` (`gemini-2.5-flash`) | ~$0.155 | 65,535 | ✅ best |
| `groq` (`whisper-large-v3-turbo`) | ~$0.040 | n/a (real STT) | ⛔ garbled (`any`→"N") |

- **Lots of English jargon → `--provider gemini`.** Programming / DevOps / data courses thick with English tool, product, or API names. Fidelity wins exactly where the words carry the meaning. **This is still true after the default changed** — the default optimizes cost and loop-immunity, not fidelity.
- **Mostly Portuguese prose → the default (`openrouter`), or `groq`.** Business, marketing, communication, soft-skills, theory. Neither weakness bites when English terms are rare.
- **A lesson Gemini cannot transcribe at any chunk size → `openrouter`.** MiMo's 131k ceiling is the specific cure for the `MAX_TOKENS`+repetition-loop failure; it repaired a Fincheck lesson that had survived two Gemini repair attempts. Verify the result with `scripts/jargon_audit.py` before accepting it.
- **Unsure → `gemini`** (safest on fidelity), or transcribe one representative lesson with each and diff the English terms (`scripts/jargon_audit.py --reference`) before committing the whole batch.
- ⛔ **The two cheap providers fail differently and that matters.** Groq's corruption is self-announcing ("N" is obviously wrong). MiMo's is grammatical and plausible, so it survives review and Stage 2 compresses it into a **wrong rule**. Never accept MiMo output on a code-dense course without the jargon audit.

Tell from the `input/<course>/` folder name + any `*.description.md` / `manifest.json`. Both free tiers are rate-limited — a full course usually needs a paid tier. **Gemini free** caps at ~20 requests/day; **Groq Whisper-turbo free**'s binding cap is audio-seconds — **~8 h of audio/day** (28,800 ASD) + ~2 h/hour (7,200 ASH), 20 RPM, 2,000 RPD — so a long course spans several days (Motion Boost's 17 h ≈ 3 days). Full table + 429/`retry-after` headers: `knowledge/sources/groq-rate-limits.md`.

## Hard-won lessons — keep these, do not regress (full detail in `CONTEXT.md` §4)

- **UTF-8 re-exec guard** at the top of `main.py` — accented filenames (`módulo`) break ffmpeg/subprocess under an ASCII `C` locale. Keep it.
- **`_ascii_name()` for upload temp audio** — the Gemini Files API puts the upload filename in an ASCII-only HTTP header; an accented path raises `UnicodeEncodeError`. Never pass an accented path to `client.files.upload`. The output transcript keeps the accented name.
- **Audio chunking** (`_transcribe_audio` / `audio.split_audio`, >15 min → ~10 min) — long lessons otherwise trip the 64k output ceiling *and* push the model into phrase-repetition loops (seen 1011×). If a transcript is absurdly large or repeats a sentence dozens of times, chunking regressed.
- **10-min per-request timeout** (`HttpOptions(timeout=)`) — a slept machine froze a call for 11h. Keep it so a frozen call errors and the batch resumes.
- **Quota handling** (`generate_with_retry` + `DailyQuotaExhausted`) — retry per-minute 429s, stop cleanly on the per-day cap. Don't replace with blind retries.
- **⛔🔴 An OpenRouter model name is not one model — PIN THE BACKEND (`config.OPENROUTER_PROVIDERS`).** Six providers serve `xiaomi/mimo-v2.5` and they differ in quantization, output ceiling, audio support and price. **Auto-routing sent every observed request to the single worst one.** Measured on one identical 540s chunk, 2026-08-04:
  | backend | quant | result | cost/chunk |
  |---|---|---|---|
  | **Xiaomi** (pinned default) | fp8 | clean, 1,771 w | **$0.00125** |
  | DeepInfra (what auto-routing picks) | bf16 | **LOOPED**, 8,003 w | **$0.03338** |
  | DeepInfra | bf16 | clean, 1,753 w | $0.00667 |
  | Novita / Venice | — | reject audio (404 / 429) | — |
  A looped generation bills **27× a clean chunk**, and DeepInfra's 16,384 output ceiling sits right at a working `max_tokens`. Pinning cut the projected cost of 577 lessons from **~$6.75 to ~$1.00**. Pin hard (`allow_fallbacks: False`) — a silent fallback restores both the price and the loop.
- **The OpenRouter silent audio-drop is common, not exotic** (`_assert_audio_was_received` + the retry in `transcribe_file`'s 200-branch) — MiMo returns HTTP 200, `finish_reason: stop`, and a fluent *"I don't see an audio file attached"* on **~7% of requests** (4 of 57 measured on `jstack-lives`, 2026-08-04). It is a per-request delivery fault, not a property of the file, so the client retries it like a 429. Keep both halves: the wpm floor is the only thing that detects it, and the retry is the only thing that stops every batch from leaving a residue. ⚠️ **But the floor needs a duration to be meaningful, and `ffmpeg -f segment` emits a sliver whenever a lesson runs just past a multiple of the chunk length** — a 1622s lesson at 540s leaves a 2.0s tail. The one real word spoken there scored 28.2 wpm and failed the entire 27-minute lesson (2026-08-04). `MIN_DURATION_FOR_WPM_SEC` (30s) exempts those; the guard had no power down there anyway, since the ~8-word apology it hunts scores 240 wpm on a 2s chunk. Don't remove the exemption to "tighten" the guard.

## Commands

```bash
cd knowledge/projects/course-to-markdown
.venv/bin/python downloaders/jstack.py --list --cookies input/cookies-jstack.txt
.venv/bin/python downloaders/designboost.py --list
.venv/bin/python downloaders/skool.py "https://www.skool.com/<group>/classroom/<course>" --dry-run
PYTHONUTF8=1 .venv/bin/python -u main.py input/ --language Portuguese   # Stage 1, full course (openrouter/MiMo, default)
.venv/bin/python -u main.py input/jstack-projects -o output/jstack-projects --provider gemini --language Portuguese
.venv/bin/python -u scripts/transcribe_batches.py input/jstack-lives output/jstack-lives --jobs 3 --provider openrouter --language Portuguese
.venv/bin/python main.py input/ --provider groq --language Portuguese   # Stage 1 via Groq Whisper (needs GROQ_API_KEY)
.venv/bin/python scripts/reconcile.py input/<batch> output/<batch>       # is the batch actually finished? (TASKS 3.6+3.7)
.venv/bin/python scripts/reconcile.py input/<batch> output/<batch> -v 5  # ...and name the missing lessons
.venv/bin/python scripts/jargon_audit.py output/<course>                # flag fluent term substitution (MiMo)
.venv/bin/python scripts/jargon_audit.py output/<c>/<l>.transcript.txt --reference <other-provider>.transcript.txt
.venv/bin/python main.py input/ --dry-run                              # audio + report, no API
.venv/bin/python -c "import course_to_markdown.pipeline"               # import smoke check
.venv/bin/python -m unittest discover -s tests -v                      # downloader safety/contracts
```

Stage 1 is idempotent (skips finished lessons) and batch-resilient (one bad file doesn't stop the run). A Gemini response with a non-`STOP` finish reason or an exact 8-word sequence repeated 50+ times is an error and is never saved as a successful transcript; retry the lesson with shorter chunk env values plus `--retranscribe`. Run long batches in the background and watch `.logs/transcribe.log`.

## Definition of done

- Change has an import/smoke check or a real run behind it; downloader changes also pass the offline suite and an authenticated dry-run when a session is available.
- No secrets or signed queries are printed/tracked; DRM remains skipped; accented + long-lesson paths still work.
- `.venv` used throughout; no library auto-writes; staged outputs only.
- `MEMORY.md` state + this file/`CODEX.md` updated together when behavior or gotchas change.

## Common mistakes

- Using global Python instead of `.venv`.
- Printing an authenticated/signed media URL (quiet yt-dlp is mandatory for signed streams).
- Treating a 200 catalog response, folder presence, or one `done` entry as proof that a course is complete — run `scripts/reconcile.py`. **A clean manifest proves nothing:** a killed downloader leaves `<lesson>.mp4.part`/`.ytdl` behind and writes *no* manifest entry at all, so the course reads 100% `done` with the lesson simply absent (dynamodb lesson 11, 2026-08-04). The manifest records what the downloader finished, never what the curriculum contains; only the catalog listing does, and that needs a live session.
- **Running Stage 2 against the Gemini API instead of the Claude subscription — this actually happened on 2026-08-05.** A convenience script (`scripts/compile_lives_stage2.py` — never commit it) compiled 19 lives packs on `gemini-2.5-flash`, and re-acquired two bugs the package had already paid for: thinking left on under `max_output_tokens=3000` → 6 packs truncated mid-sentence; `import datetime` unused → an invented `compiled: 2024-07-30`. A side script that re-implements a call `course_to_markdown/` already makes correctly inherits none of its fixes.
- ⛔ **Concatenating a whole course into one Stage-2 prompt.** That same script capped each lesson at 15k chars and sliced the prompt at `[:60000]`; **all 19 courses overflowed it**, so the compiler read **22–66% (median 37%)** of each course and wrote a confident pack about the part it saw. Nothing downstream announces this. Compile **per module** through `course-module-compiler` — it has no window to overflow.
- ⛔ **Believing a coverage reconciliation that counts folder membership.** "100% of 1,668 transcripts, zero orphans" passed while the compiler had ingested ~37%: it asserted every transcript sits under a course that *has* a pack, never that its content reached the model. Reconcile on the compiler's actual input.
- **Accepting MiMo/OpenRouter output on a code-dense course without `scripts/jargon_audit.py`** — its substitutions are fluent and pass every other guard.
- Assuming a model's advertised `input_modalities: [audio]` means its OpenRouter provider actually delivers the audio — `nemotron-omni:free` ignores it **always**, and **MiMo drops it on ~7% of requests**; both return HTTP 200 + `stop`. Treat a batch that ends with a few `did not receive the audio` errors as normal residue to re-run, not as broken media.
- Pointing `main.py` at a sub-folder without the paired `-o output/<batch>` root and flattening the output tree.
- Starting `scripts/transcribe_batches.py` before the Stage 0 batch exits, or alongside an overlapping `main.py` worker.
- Passing accented paths to `files.upload`, or removing the UTF-8 guard / `_ascii_name`.
- Removing chunking and hitting `MAX_TOKENS` / repetition loops on long lessons.
- **Blaming a repetition loop on the audio or the chunk size.** On OpenRouter it is **stochastic and backend-specific**: the same 540s chunk looped ~1-in-6 at `temperature: 0`, and halving to 300s looped exactly the same. Retry it (the client now does) and pin the backend — do not go hunting for a chunk size that fixes it.
- Auto-promoting packs into `knowledge/` without human review.
- Inventing a `compiled:` date.
