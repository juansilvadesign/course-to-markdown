# Course → Markdown — Build Task Tracker

> **Open this first, every session.** This file is the running execution state. Check a box only after the artifact and its verification exist. Deferred/v2+ work lives in [`ROADMAP.md`](ROADMAP.md); decisions and dated operational state live in [`MEMORY.md`](MEMORY.md); commands and architecture live in [`README.md`](README.md).

**Two levels of done — do not conflate them:**

- **Pipeline MVP — ✅ SHIPPED.** Owned media can move through Stage 0 download, Stage 1 transcription, and Stage 2 staged knowledge-pack compilation. The full Motion Boost and JStack Full Stack courses proved the path end to end.
- **Authenticated-platform expansion — the current release.** DesignBoost and the supplied Skool classroom URL have working, session-backed adapters; the remaining JStack catalog is not complete until every accessible lesson is downloaded, transcribed, and count-reconciled.

## Delivery frame

- **Timebox:** the current implementation cycle, closing at a verified handoff rather than a calendar date.
- **Capacity:** one local workstation; at most one long media download and one isolated transcription batch at the same time; existing Gemini paid tier and user-exported sessions.
- **Fixed outcome:** reliable DesignBoost + Skool support and a finished JStack Stage 0/1 corpus.
- **Open scope:** convenience features, attachment capture, bulk Skool discovery, and Stage 2 compilation may move to [`ROADMAP.md`](ROADMAP.md) to protect the fixed outcome.
- **Replan trigger:** a platform response shape changes, a session expires, DRM is encountered, or provider quota prevents a clean resumable run.

---

## ✅ Done so far

- [x] **Stage 1 is production-proven.** Nested input mirroring, UTF-8 paths, ASCII-safe Gemini uploads, long-audio chunking, per-request timeout, quota-aware clean stop, and resumable output all survived full courses.
- [x] **Stage 2 is production-proven.** Packs are compiled on the Claude subscription, staged for review, and never auto-promoted into `knowledge/`.
- [x] **JStack downloader generalized.** `downloaders/jstack.py` covers lives, projects, and trainings; cursor pagination, per-library Bunny hosts, YouTube outliers, audio-only default, manifests, and `--resume` are implemented.
- [x] **JStack trainings complete.** `formacao-typescript` and `formacao-full-stack` are downloaded and transcribed; Full Stack has also been compiled and promoted through the human-review flow.
- [x] **JStack projects downloaded.** Fincheck, Foodiary, and WaiterApp media trees are complete and manifest-backed.
- [x] **DesignBoost adapter implemented.** `downloaders/designboost.py` authenticates through the exported member session, lists all four catalogs, resolves course/workshop module trees plus lives and AI-course entries, and delegates Vimeo media to the shared downloader core.
- [x] **DesignBoost live dry-run passed (2026-07-28).** Course `32` resolved 12/12 lessons across two modules, with zero unresolved videos.
- [x] **Skool adapter implemented.** `downloaders/skool.py` reads authenticated `__NEXT_DATA__`, preserves sets/sections, resolves external or signed native HLS video, extracts TipTap descriptions/resource links, and rejects commercial HLS DRM markers.
- [x] **Supplied Skool course live dry-run passed (2026-07-28).** `Equação de Valor` resolved 1/1 lesson and its signed stream with zero DRM/unresolved assets.
- [x] **Shared safety core added.** `_shared.py` owns Netscape-cookie parsing, query/token redaction, quiet signed-URL yt-dlp calls, DRM checks, atomic manifests, audio/video modes, and resumability.
- [x] **Downloader tests added.** Ten offline unit tests cover cookie parsing, secret redaction, DRM discrimination, DesignBoost curriculum mapping, Skool Next-data parsing, nested curriculum flattening, native signed URLs/resources, and TipTap text.

## ▶ Next session — start here

1. **Check disk state before starting another long job.** Media and transcripts are the source of truth; terminal history is not.
2. **Resume JStack lives if incomplete:**

   ```bash
   .venv/bin/python -u downloaders/jstack.py --all lives \
     --cookies input/cookies-jstack.txt --resume
   ```

3. **Resume the isolated JStack transcription batches with explicit output roots:**

   ```bash
   .venv/bin/python -u main.py input/jstack-projects \
     -o output/jstack-projects --provider gemini --language Portuguese
   .venv/bin/python -u main.py input/jstack-lives \
     -o output/jstack-lives --provider gemini --language Portuguese
   ```

4. **Reconcile media, manifest, and transcript counts.** Re-run the resumable command for any failed/missing lessons; do not infer completeness from folder presence.
5. **Update the live counts and checkboxes below.** Never leave an “in progress” statement without the command needed to resume it.

---

## Phase 1 — Reliable local pipeline ✅ DONE

- [x] **1.1 Stage 1 CLI** — recursive media discovery, folder mirroring, Gemini/Groq provider seam, language hint, dry-run, overwrite, and retranscribe modes.
- [x] **1.2 Audio hardening** — ffmpeg normalization, UTF-8 re-exec, ASCII upload names, long-file chunking, and temporary-file cleanup.
- [x] **1.3 Provider resilience** — retry/backoff, request timeout, daily/hourly quota detection, clean resumable stop.
- [x] **1.4 Stage 2 handoff** — transcript-first output and subscription-backed `course-module-compiler`.
- [x] **1.5 Human promotion gate** — packs remain staged until reviewed.

## Phase 2 — Authenticated platform adapters

- [x] **2.1 JStack** — trainings, projects, and lives; full catalog enumeration and resumable batches.
- [x] **2.2 DesignBoost reconnaissance** — member app/API boundary, bearer-session cookie, four catalog types, module/class detail shapes, Vimeo media.
- [x] **2.3 DesignBoost implementation** — list, single content, catalog batch, limit, dry-run, resume, audio/video modes.
- [x] **2.4 DesignBoost verification** — authenticated 12-lesson dry-run and offline parser tests.
- [x] **2.5 Skool reconnaissance** — authenticated Next data, one-module target curriculum, native signed HLS shape, normal browser user-agent requirement.
- [x] **2.6 Skool implementation** — course URL, curriculum/description/resource parsing, native/external video resolution, DRM guard, resume.
- [x] **2.7 Skool verification** — authenticated target-course dry-run and offline parser tests.
- [ ] **2.8 Documentation pass** — README, operating contracts, memory, task tracker, and roadmap agree with the shipped behavior.

## Phase 3 — Finish the JStack corpus

- [x] **3.1 Trainings media + transcripts** — both formations complete.
- [x] **3.2 Projects media** — Fincheck, Foodiary, and WaiterApp complete.
- [ ] **3.3 Projects transcripts** — run Gemini against `input/jstack-projects` with the paired `output/jstack-projects` root; retry transient errors.
- [ ] **3.4 Lives media** — complete all 69 accessible catalog items with `--resume`.
- [ ] **3.5 Lives transcripts** — start only against finished/resolved media trees; use Gemini because the courses are code-jargon-heavy.
- [ ] **3.6 Reconciliation** — for each content item: accessible lesson count = manifest terminal states = media + legitimate non-video entries; media count = transcript count.
- [ ] **3.7 Failure sweep** — no `failed` manifest entries, no zero-byte/`.part` files, no missing transcript for an audio file.

## Phase 4 — Release verification and handoff

- [x] **4.1 Import/compile smoke** — every downloader imports and both new CLIs expose help successfully.
- [x] **4.2 Offline downloader suite** — `.venv/bin/python -m unittest discover -s tests -v` passes 10/10.
- [x] **4.3 Authenticated adapter smoke** — DesignBoost and Skool dry-runs pass without downloading media.
- [ ] **4.4 Full test rerun after docs/final edits.**
- [ ] **4.5 Git hygiene** — no cookies, API payloads, media, transcripts, tokens, or signed URLs are tracked.
- [ ] **4.6 Durable state** — final counts and any genuine blockers recorded in this file and `MEMORY.md`.

## Phase 5 — Stage 2 for the new corpus

> Not required to finish the current Stage 0/1 request. Start only after Phase 3 count reconciliation.

- [ ] **5.1 Choose reusable-unit granularity** for JStack projects/lives (course, discipline, or coherent cluster — not reflexively one pack per source module).
- [ ] **5.2 Compile in batches of no more than four agents** to avoid the known session ceiling.
- [ ] **5.3 Reconcile lesson coverage** — zero orphan and zero double-covered transcripts.
- [ ] **5.4 Review, then promote manually** if the packs add net-new knowledge.

---

## Cross-cutting checklist

- [ ] Process only content the user is entitled to access and permitted to retain offline.
- [ ] Use exported sessions only; never automate credentials, defeat access controls, or broaden access.
- [ ] Stop and mark `skipped-drm` when commercial DRM is detected; never decrypt it.
- [ ] Keep cookies, tokens, signed URLs, media, transcripts, and manifests with sensitive payloads out of Git.
- [ ] Use `.venv` for every Python test and production command.
- [ ] Keep API/catalog polling polite and sequential; resume instead of restarting.
- [ ] Use Gemini for code-heavy Portuguese courses; use Groq only when jargon fidelity is not material.
- [ ] Never auto-promote Stage 2 artifacts into the knowledge library.

## Open questions still to decide

- [ ] **DesignBoost acquisition scope:** download one selected course, one catalog, or all four catalogs after adapter verification?
- [ ] **Skool acquisition scope:** download/transcribe only the supplied `Equação de Valor` course or add group-wide course discovery first?
- [ ] **Attachments:** should native Skool files and DesignBoost tool/resource downloads be first-class Stage 0 artifacts, or are descriptions + external links sufficient?
- [ ] **JStack Stage 2 granularity:** which projects/lives contain reusable knowledge worth compiling versus archival transcripts only?
- [ ] **Retention:** keep all source `.m4a` after verified transcription, or introduce an explicit, recoverable archive policy?

## Open inputs still needed from the user

- **None for the current adapter/JStack completion work.** Re-export the relevant cookie file only if a session begins returning 401/403.
- **A scope choice is needed before bulk-downloading DesignBoost or Skool.** Adapter verification alone does not imply authorization to download every newly visible course.
