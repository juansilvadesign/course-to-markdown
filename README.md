# Course → Markdown

Turn the course videos you own into compressed, AI-readable knowledge packs for this repo's [`knowledge-compiler`](../../skills/knowledge-compiler) skill. Two stages, two engines:

```
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

## Status / scope (MVP)

- **In:** local video/audio (nested course tree) → transcripts → per-module knowledge packs.
- **Stage 0 — downloading:** out of scope here. Use the sibling [`../one-click-video-downloader`](../one-click-video-downloader) (built MVP) or any tool, and drop the resulting MP4s into `input/`.
- **Later (v2):** a tighter hand-off from the downloader; an optional GUI (reusing `video-to-audio`); audio chunking for multi-hour lessons.

## Requirements

- Python 3.10+, and **ffmpeg** on `PATH` (`sudo apt install ffmpeg`; or `pip install imageio-ffmpeg`).
- A **Google AI (Gemini) API key** — used only in Stage 1.
- Stage 2 needs only a Claude Code session (no key).

## Setup (always use `.venv` — test and production)

```bash
cd knowledge/projects/course-to-markdown
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # put your key in GEMINI_API_KEY
```

## Stage 1 — transcribe (Python)

```bash
# Drop the whole course (folders/modules/lessons) into input/, then:
python main.py                                  # input/ -> output/, structure mirrored
python main.py input/ --language Portuguese     # language hint (default: auto/preserve)
python main.py input/ --dry-run                 # extract audio + report; no API calls
python main.py lesson.mp4 --retranscribe        # force re-transcription
python main.py input/ --gemini-format           # legacy: also let Gemini write a .md (skips Stage 2)
```

For each lesson you get `output/<…>/<lesson>.transcript.txt`. Re-runs **skip** lessons already transcribed (use `--overwrite`). The batch keeps going if one file fails.

## Stage 2 — compile per module (Claude agent)

Once transcripts exist, ask your Claude Code session to compile. It will:

1. Walk `output/` and identify the **module folders** (the folders grouping lesson transcripts).
2. Spawn one **`course-module-compiler`** agent per module (default **Sonnet**), passing the module folder.
3. The agent reads all the module's transcripts, applies `knowledge-compiler`'s `course.md`, and **decides the model**: if a module is dense enough to need **Opus**, it returns `ESCALATE_TO_OPUS: …` and the session re-spawns it on Opus.
4. The agent writes a **staged** `<module-slug>.pack.md` inside the module folder and reports the suggested `knowledge/<domain>/courses/` promotion target.
5. **You review**, then promote the packs into `knowledge/<domain>/courses/`.

The agent is registered at `.claude/agents/course-module-compiler.md` (→ `agent.md` here). Stage 2 spends **no** API quota — only the Claude subscription.

## Notes & limits

- Long lessons rely on Gemini 2.5 Flash's large context + 64k output ceiling; very long files may need chunking (v2).
- Audio is normalized to mono 16 kHz MP3 to keep uploads small/cheap; uploaded audio is deleted after each run (auto-expires in ~48h anyway).
- Packs are **staged**, never auto-written into the library — promotion to `knowledge/` is a human step.
- Only process courses you have the right to use.

## Layout

```
course-to-markdown/
  main.py                       # Stage-1 CLI entry
  agent.md                      # Stage-2 course-module-compiler agent (symlinked into .claude/agents/)
  course_to_markdown/
    config.py  audio.py  gemini_client.py  prompts.py
    transcribe.py  formatter.py  pipeline.py
  input/                        # drop the course here (gitignored)
  output/                       # transcripts + staged packs land here, structure mirrored (gitignored)
  requirements.txt  .env.example
```

Related: [`../video-to-audio`](../video-to-audio) · [`../../skills/knowledge-compiler`](../../skills/knowledge-compiler) · idea capture at `knowledge/ideas/course-videos-to-knowledge-markdown.md`.
