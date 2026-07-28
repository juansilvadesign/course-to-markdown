# Course → Markdown

Turn courses you are entitled to use into compressed, AI-readable knowledge packs for this repo's [`knowledge-compiler`](../../skills/knowledge-compiler) skill. The full path has an optional authenticated acquisition stage followed by two processing engines:

```
STAGE 0 — acquisition                (Python + exported browser session)
  JStack / DesignBoost / Skool
      └─ authenticated curriculum + media ─► input/<platform>/<course>/…/*.m4a
         manifest.json makes every platform run resumable

STAGE 1 — transcription            (Python + Gemini API · bulk, cheap)
  input/<course>/<module>/<lesson>.mp4
      └─ audio (ffmpeg) ─► verbatim transcript (Gemini)
         output/<course>/<module>/<lesson>.transcript.txt        ← folder structure mirrored

STAGE 2 — compilation              (Claude Code agent · subscription, NO API)
  output/<course>/<module>/*.transcript.txt
      └─ course-module-compiler agent ─► applies the knowledge-compiler course.md playbook
         output/<course>/<module>/<module-slug>.pack.md          ← one pack per MODULE (staged)
              └─ human review ─► knowledge/<domain>/courses/<slug>.md
```

Stage 1 only transcribes (the verbatim `.txt` is the hand-off). Stage 2 is where the *compression into a knowledge pack* happens — done by a Claude agent that can pick Sonnet or Opus per module, **not** by Gemini.

## Status / scope

- **In:** authenticated JStack, DesignBoost, and Skool acquisition; local video/audio ingestion; resumable transcription; staged knowledge-pack compilation.
- **Proven end to end:** full nested courses, multi-hour batches, accented paths, long lessons, and human-reviewed library promotion.
- **Current execution state:** [`TASKS.md`](TASKS.md). Deferred enhancements and scope boundaries: [`ROADMAP.md`](ROADMAP.md).
- **One-off videos:** the sibling [`../one-click-video-downloader`](../one-click-video-downloader) remains useful when no platform adapter is needed.

## Requirements

- Python 3.10+, and **ffmpeg** on `PATH` (`sudo apt install ffmpeg`; or `pip install imageio-ffmpeg`).
- **httpx + yt-dlp** (installed by `requirements.txt`) for Stage 0.
- A **Google AI (Gemini) API key** — used only in Stage 1 (the default provider).
- *(Optional)* a **Groq API key** if you want `--provider groq` (Whisper STT — cheaper/faster). Free key at <https://console.groq.com/keys>.
- Stage 2 needs only a Claude Code session (no key).

## Setup (always use `.venv` — test and production)

```bash
cd knowledge/projects/course-to-markdown
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # put your key in GEMINI_API_KEY (and GROQ_API_KEY if you'll use --provider groq)
```

## Stage 0 — acquire authenticated courses

The adapters accept **Netscape-format cookie exports from your own logged-in browser**. They do not automate login, broaden access, or decrypt DRM. Keep cookie files under `input/`; that tree is gitignored. Re-export a session if the platform returns 401/403.

Downloads are audio-only `.m4a` by default because Stage 1 does not need video. Add `--video` only when visual reference is genuinely required. Every adapter supports `--dry-run`; run it before a real download.

### JStack

```bash
# Whole authenticated catalog
.venv/bin/python downloaders/jstack.py --list \
  --cookies input/cookies-jstack.txt

# One course, then every live (sequential + resumable)
.venv/bin/python downloaders/jstack.py \
  "https://app.jstack.com.br/lives/react-router-v7" \
  --cookies input/cookies-jstack.txt --dry-run
.venv/bin/python -u downloaders/jstack.py --all lives \
  --cookies input/cookies-jstack.txt --resume
```

JStack supports `lives`, `projects`, and `trainings`. Batch output lands under `input/jstack-lives/`, `input/jstack-projects/`, or the legacy flat training folders.

### DesignBoost

The public `designboost.com.br` page is the catalog/marketing entry; authenticated content lives behind `aluno.designboost.com.br`. The adapter understands courses, workshops, single classes/lives, and AI catalog entries.

```bash
.venv/bin/python downloaders/designboost.py --list
.venv/bin/python downloaders/designboost.py --all courses --limit 1 --dry-run
.venv/bin/python downloaders/designboost.py \
  "https://aluno.designboost.com.br/sala-de-aula/32/491?type=course" \
  --dry-run
```

Default session path: `input/cookies-designboost.txt`.

### Skool

```bash
.venv/bin/python downloaders/skool.py \
  "https://www.skool.com/win-elite-3896/classroom/3d94f2ce?md=424159aee10f42158da196f19ce0f7e0" \
  --dry-run
```

Default session path: `input/cookies-skool.txt`. The adapter resolves external embeds or Skool's signed native HLS internally, suppresses signed queries from logs, and marks commercial DRM as `skipped-drm`.

Only download material your account is entitled to access and that you are permitted to retain offline. Platform terms can be narrower than technical access.

## Stage 1 — transcribe (Python)

```bash
# Drop the whole course (folders/modules/lessons) into input/, then:
python main.py                                  # input/ -> output/, structure mirrored
python main.py input/ --language Portuguese     # language hint (default: auto/preserve)
python main.py input/ --dry-run                 # extract audio + report; no API calls
python main.py input/ --provider groq           # transcribe via Groq Whisper instead of Gemini (needs GROQ_API_KEY)
python main.py lesson.mp4 --retranscribe        # force re-transcription
python main.py input/ --gemini-format           # legacy: also let Gemini write a .md (skips Stage 2)
```

For each lesson you get `output/<…>/<lesson>.transcript.txt`. Re-runs **skip** lessons already transcribed (use `--overwrite`). The batch keeps going if one file fails.

Output mirroring is relative to the input target. For the entire tree, use `input/`. For an isolated platform batch, pair the roots explicitly so the platform folder is not flattened:

```bash
.venv/bin/python -u main.py input/jstack-projects \
  -o output/jstack-projects --provider gemini --language Portuguese
```

**Providers.** Stage 1 defaults to Gemini (`gemini-2.5-flash`). Pass `--provider groq` to transcribe with Groq's Whisper (`whisper-large-v3-turbo`) instead — a purpose-built STT that's cheaper and faster, with none of the LLM output-ceiling / repetition-loop failure modes. Tradeoff: Whisper turbo can mis-render English technical terms spoken inside Portuguese (on the TypeScript course the type `any` came out as "N"), so for code-dense courses Gemini reads keywords more faithfully — though the Stage-2 Claude compilation usually repairs it from context. Groq's free tier is rate-limited — for `whisper-large-v3-turbo` the binding cap is audio duration: roughly **8 hours of audio per day** (plus ~2 h/hour, 20 req/min, 2,000 req/day), so a long course spans several days unless you upgrade. See [`groq-rate-limits.md`](../../sources/groq-rate-limits.md) for the full table. *(Zen/opencode was evaluated but can't transcribe — it's a text-only gateway; only Gemini takes audio and Zen's Gemini integration is broken.)*

## Stage 2 — compile per module (Claude agent)

Once transcripts exist, ask your Claude Code session to compile. It will:

1. Walk `output/` and identify the **module folders** (the folders grouping lesson transcripts).
2. Spawn one **`course-module-compiler`** agent per module (default **Sonnet**), passing the module folder.
3. The agent reads all the module's transcripts, applies `knowledge-compiler`'s `course.md`, and **decides the model**: if a module is dense enough to need **Opus**, it returns `ESCALATE_TO_OPUS: …` and the session re-spawns it on Opus.
4. The agent writes a **staged** `<module-slug>.pack.md` inside the module folder and reports the suggested `knowledge/<domain>/courses/` promotion target.
5. **You review**, then promote the packs into `knowledge/<domain>/courses/`.

The agent is registered at `.claude/agents/course-module-compiler.md` (→ `agent.md` here). Stage 2 spends **no** API quota — only the Claude subscription.

## Notes & limits

- Lessons longer than 15 minutes are automatically split into ~10-minute transcription chunks, then concatenated.
- Audio is normalized to mono 16 kHz MP3 to keep uploads small/cheap; uploaded audio is deleted after each run (auto-expires in ~48h anyway).
- Packs are **staged**, never auto-written into the library — promotion to `knowledge/` is a human step.
- Only process courses you have the right to use.

## Layout

```
course-to-markdown/
  TASKS.md  ROADMAP.md          # active execution state + deferred scope
  downloaders/
    _shared.py                  # auth/session safety, DRM, resume, yt-dlp core
    jstack.py  designboost.py  skool.py
  main.py                       # Stage-1 CLI entry
  agent.md                      # Stage-2 course-module-compiler agent (symlinked into .claude/agents/)
  course_to_markdown/
    config.py  audio.py  gemini_client.py  prompts.py
    transcribe.py  formatter.py  pipeline.py
  input/                        # drop the course here (gitignored)
  output/                       # transcripts + staged packs land here, structure mirrored (gitignored)
  tests/                        # offline downloader contract/safety tests
  requirements.txt  .env.example
```

### Verification

```bash
.venv/bin/python -m compileall -q downloaders course_to_markdown
.venv/bin/python -m unittest discover -s tests -v
```

Related: [`TASKS.md`](TASKS.md) · [`ROADMAP.md`](ROADMAP.md) · [`../video-to-audio`](../video-to-audio) · [`../../skills/knowledge-compiler`](../../skills/knowledge-compiler) · idea capture at `knowledge/ideas/course-videos-to-knowledge-markdown.md`.
