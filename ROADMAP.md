# Course → Markdown — Roadmap (post-current-release / v2+)

> Deliberately outside the active authenticated-platform/JStack release tracked in [`TASKS.md`](TASKS.md). The fixed outcome for this cycle is working DesignBoost + Skool adapters and a count-reconciled JStack Stage 0/1 corpus. Capacity is one workstation and one maintainer; scope below stays open and is pulled only when it does not threaten that outcome.

## Release horizon

| Horizon | User benefit | Exit signal |
|---|---|---|
| **Current — authenticated sources + JStack completion** | The user can reliably turn entitled JStack, DesignBoost, and the supplied Skool course into transcription-ready audio; the existing JStack backlog becomes a complete transcript corpus. | Both adapter dry-runs pass; all JStack accessible lessons have terminal manifests and matching transcripts; zero failed/partial files. |
| **Next — one-command safe acquisition** | A course URL can be detected, downloaded, transcribed, and reconciled without hand-building paired input/output commands. | One orchestrator preserves resumability and platform rate limits, never overlaps a file still being downloaded, and emits a machine-readable reconciliation report. |
| **Later — durable knowledge operations** | Selected corpora become reviewed, maintainable knowledge packs with drift detection and storage controls. | Compilation coverage is reconciled; library promotion remains human-gated; source changes and retention are explicit. |

**Replanning cadence:** review this table when the current release closes, when a platform contract changes, or when storage/provider cost becomes the binding constraint. Pull the smallest item that unlocks a complete user-visible workflow; do not start several infrastructure items at once.

## Deferred items

| # | Item | Extends | Why deferred / notes |
|---|------|---------|----------------------|
| R1 | **Move JStack onto `downloaders/_shared.py`** | Stage 0 core | The two new adapters share one safety/resume core, while the mature JStack script still carries its own proven copy. Refactor only after the catalog run finishes; changing manifest/download behavior mid-run creates avoidable regression risk. |
| R2 | **Unified `course-download` CLI with URL auto-detection** | All downloaders | Today each adapter has a clear platform CLI. A façade is useful only after all three contracts have stabilized and can expose the same exit/status semantics. |
| R3 | **Stage 0 → Stage 1 orchestrator** | Downloader + `main.py` | One command should download, wait for terminal manifests, transcribe only complete files, and reconcile counts. It must never let Stage 1 read a `.part` or media file still being written. |
| R4 | **First-class attachment capture** | DesignBoost + Skool | v1 keeps descriptions and external resource links. Native Skool files need a short-lived authenticated download URL; DesignBoost tools/resources need endpoint mapping. Add only for courses where the attachments carry learning value. |
| R5 | **Skool group-wide catalog discovery and batch mode** | `downloaders/skool.py` | The supplied course is fully supported. Enumerating every classroom course adds group navigation/pagination and a much larger implied download scope; require an explicit user selection first. |
| R6 | **Browser-session fallback for hostile edge layers** | Auth core | A normal browser user-agent plus exported cookies is enough for the supplied Skool course. Playwright/Chromium would add a large operational dependency; introduce it only if a legitimately accessible course cannot be fetched otherwise. |
| R7 | **Session diagnostics and expiry preflight** | Auth core | Add domain/name-only cookie checks, expiry warnings, and one redacted auth probe before a long batch. Never print values or silently fall back to login automation. |
| R8 | **Subtitle-first ingestion** | Stage 0/1 | Prefer official VTT/SRT where complete and language-correct, falling back to transcription. This can save cost but needs timestamp cleanup and a quality gate against incomplete auto-captions. |
| R9 | **Automatic provider recommendation** | Stage 1 | Infer code/jargon density from catalog metadata and descriptions, then suggest Gemini vs Groq. Keep the final choice explicit until the heuristic is calibrated; technical-term errors are semantic, not cosmetic. |
| R10 | **Curriculum integrity + drift report** | Manifests | Persist non-secret lesson IDs/hashes and compare a later catalog snapshot: added, removed, renamed, media changed. Current manifests answer “downloaded?” but not “source changed?”. |
| R11 | **Content-addressed media/transcript cache** | Storage + Stage 1 | Avoid retranscribing duplicate videos exposed in multiple catalogs or renamed lessons. Needs careful path/reference semantics and an explicit garbage-collection policy. |
| R12 | **Stage 2 compilation orchestrator** | `course-module-compiler` | Select reusable clusters, spawn at most four compiler agents, reconcile zero-orphan/zero-double-coverage, and stage packs. Automatic promotion remains forbidden. |
| R13 | **Pack QA and link validation** | Stage 2 | Automate token-envelope checks, diacritic preservation, date validation, bare/full wikilink resolution, and sibling-slug drift after cluster splits. |
| R14 | **Machine-readable run report** | All stages | JSON summary of source count, terminal states, durations, provider/model, retries, bytes, transcripts, and unresolved assets. Useful before a UI; no database required. |
| R15 | **Dependency lock / reproducible environment** | `requirements.txt` | Lower bounds can drift across google-genai/httpx/yt-dlp releases. Pin or adopt a lockfile after the active adapter changes settle, then automate an intentional yt-dlp refresh cadence. |
| R16 | **Storage/retention policy** | Local corpus | Transcription-ready audio is large and recoverable only while access remains. Design a recoverable archive/delete policy with verified transcript checksums; never delete merely because disk use is high. |
| R17 | **Operator UI** | All stages | A local GUI could select a platform/course and show progress, but it adds little until the orchestration/status contract is stable. The CLI remains the source of truth. |

## Out of scope

- **DRM decryption, key extraction, or access-control bypass.** DRM content is marked and skipped.
- **Credential capture or automated login.** Only user-exported sessions are accepted.
- **Downloading locked, unowned, or otherwise unauthorized material.**
- **Redistribution or publishing of source media/transcripts.** Working artifacts stay gitignored and local.
- **Automatic promotion into `knowledge/`.** Stage 2 output always receives human review.
- **Platform-evasion features** intended to defeat rate limits, bot controls, or terms rather than reproduce the user's legitimate browser session.

## Parking lot

- Timestamped transcript segments and chapter links.
- Speaker diarization for interview/cohort-style lessons.
- Translation alongside the source-language transcript.
- Search/index over staged transcripts before pack compilation.
- Optional screenshots/slide extraction for visually essential lessons.
- Scheduled “new lesson” sync after curriculum-drift support exists.
- Encrypted cookie/session storage outside `input/`.
