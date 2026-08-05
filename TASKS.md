# Course → Markdown — Build Task Tracker

> **Open this first, every session.** This file is the running execution state. Check a box only after the artifact and its verification exist. Deferred/v2+ work lives in [`ROADMAP.md`](ROADMAP.md); decisions and dated operational state live in [`MEMORY.md`](MEMORY.md); commands and architecture live in [`README.md`](README.md).

**Two levels of done — do not conflate them:**

- **Pipeline MVP — ✅ SHIPPED.** Owned media can move through Stage 0 download, Stage 1 transcription, and Stage 2 staged knowledge-pack compilation. The full Motion Boost and JStack Full Stack courses proved the path end to end.
- **Authenticated-platform expansion — the current release.** DesignBoost and the supplied Skool classroom URL have working, session-backed adapters; the remaining JStack catalog is not complete until every accessible lesson is downloaded, transcribed, and count-reconciled.

## Delivery frame

- **Timebox:** the current implementation cycle, closing at a verified handoff rather than a calendar date.
- **Capacity:** one local workstation; at most one long media download and four non-overlapping, isolated transcription batches at the same time (fan-out defaults to three); existing Gemini paid tier and user-exported sessions.
- **Fixed outcome:** reliable DesignBoost + Skool support and a finished JStack Stage 0/1 corpus.
- **Open scope:** convenience features, attachment capture, bulk Skool discovery, and Stage 2 compilation may move to [`ROADMAP.md`](ROADMAP.md) to protect the fixed outcome.
- **Replan trigger:** a platform response shape changes, a session expires, DRM is encountered, or provider quota prevents a clean resumable run.

## ✅ Checkpoint — 2026-08-04: JStack Stage 0/1 COMPLETE

**The whole JStack corpus is transcribed and reconciled: 1,668/1,668 lessons.**

| batch | transcripts / media |
|---|---|
| `jstack-lives` | **1084 / 1084** — 69/69 courses, `reconcile.py` reports 0 needing attention |
| `jstack-projects` | 182 / 182 |
| `formacao-full-stack` | 372 / 372 |
| `formacao-typescript` | 30 / 30 |

Zero `.part`, zero `.ytdl`, zero zero-byte files anywhere in `input/`/`output/`.

- **The Gemini pause was LIFTED on 2026-08-04, with explicit user approval, for a bounded 9-lesson sweep** — see Phase 3.5. It is no longer a standing block, but the default provider remains `openrouter`; do not read this as a general licence to run Gemini batches.
- **Provider provenance is now mixed — record it, it matters for Stage 2.** The corpus is MiMo/OpenRouter except: 1 Fincheck lesson (see 3.3) and the **9 lives lessons** listed in 3.5. If a Stage-2 pack ever shows a fidelity discrepancy, check provenance before blaming the compiler.
- **46 numbering gaps remain advisory across the lives tree.** Only a live catalog session can settle whether those are real lessons or JStack's own skipped numbering; `reconcile.py` flags but never fails on them.

### Superseded (kept for the reasoning, not the instruction)

The 2026-07-28 checkpoint paused Gemini and listed a three-minute Fincheck repair command as the first action after resume. Both are dead: Fincheck was repaired via OpenRouter/MiMo on 2026-08-04 (3.3), and the pause was lifted for the sweep above.
- **Quality guards reject three failure modes:** a non-`STOP` finish reason, an exact 8-word sequence repeated 50+ times, and a words-per-minute floor that catches the silent audio-drop. The offline suite passes **26/26**.

---

## ✅ Done so far

- [x] **Stage 1 is production-proven.** Nested input mirroring, UTF-8 paths, ASCII-safe Gemini uploads, long-audio chunking, per-request timeout, quota-aware clean stop, and resumable output all survived full courses.
- [x] **Stage 2 is production-proven.** Packs are compiled on the Claude subscription, staged for review, and never auto-promoted into `knowledge/`.
- [x] **JStack downloader generalized.** `downloaders/jstack.py` covers lives, projects, and trainings; cursor pagination, per-library Bunny hosts, YouTube outliers, audio-only default, manifests, and `--resume` are implemented.
- [x] **New JStack cookie export verified (2026-07-28).** `input/cookies-jstack.txt` authenticates and sees the full 74-item catalog: 69 lives, 3 projects, and 2 trainings.
- [x] **JStack trainings complete.** `formacao-typescript` and `formacao-full-stack` are downloaded and transcribed; Full Stack has also been compiled and promoted through the human-review flow.
- [x] **JStack projects downloaded.** Fincheck, Foodiary, and WaiterApp media trees are complete and manifest-backed.
- [x] **DesignBoost adapter implemented.** `downloaders/designboost.py` authenticates through the exported member session, lists all four catalogs, resolves course/workshop module trees plus lives and AI-course entries, and delegates Vimeo media to the shared downloader core.
- [x] **DesignBoost live dry-run passed (2026-07-28).** Course `32` resolved 12/12 lessons across two modules, with zero unresolved videos.
- [x] **Skool adapter implemented.** `downloaders/skool.py` reads authenticated `__NEXT_DATA__`, preserves sets/sections, resolves external or signed native HLS video, extracts TipTap descriptions/resource links, and rejects commercial HLS DRM markers.
- [x] **Supplied Skool course live dry-run passed (2026-07-28).** `Equação de Valor` resolved 1/1 lesson and its signed stream with zero DRM/unresolved assets.
- [x] **Shared safety core added.** `_shared.py` owns Netscape-cookie parsing, query/token redaction, quiet signed-URL yt-dlp calls, DRM checks, atomic manifests, audio/video modes, and resumability.
- [x] **Bounded Stage 1 fan-out added.** `scripts/transcribe_batches.py` maps each direct child course to its own output root, caps concurrent subprocesses, validates manifests/partials, logs per course, and holds a batch lock so workers cannot overlap.
- [x] **Offline safety/contract tests added.** Thirteen unit tests cover cookie parsing, secret redaction, DRM discrimination, truncated/repetitive-model-output rejection, DesignBoost curriculum mapping, Skool Next-data parsing, nested curriculum flattening, native signed URLs/resources, TipTap text, and fan-out discovery/validation.

## ▶ Next session — start here

**JStack Stage 0/1 is finished — there is no long job left to resume.** The next real decisions:

1. **Run the jargon audit before any of this reaches Stage 2.** ⚠️ **Still unrun on 1,084 lives transcripts**, which are MiMo output on AWS/SQL/React material — precisely the code-dense case where MiMo's substitutions are *fluent* and pass every guard the pipeline has. The 9 Gemini lessons in 3.5 are a ready-made `--reference` baseline drawn from those same courses:

   ```bash
   .venv/bin/python scripts/jargon_audit.py output/jstack-lives
   .venv/bin/python scripts/jargon_audit.py <mimo>.transcript.txt --reference <gemini>.transcript.txt
   ```

   ⛔ The bare orphan-pair heuristic is base-rate noise at corpus scale (23.5% MiMo vs 24.6% Gemini — indistinguishable). **Only `--reference` discriminates.**

2. **Commit the working tree** (4.5) — the backend pin, the wpm fix, the tests, these docs.
3. **Decide Phase 5 granularity** for projects/lives before compiling anything (5.1).
4. **Answer the two open acquisition-scope questions** below before touching DesignBoost or Skool.

Standing rules that outlived the checkpoint: media and transcripts are the source of truth, never terminal history; never launch an aggregate worker over live per-course workers; always pair `-o` roots explicitly.

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
- [x] **2.8 Documentation pass** — README, operating contracts, memory, task tracker, and roadmap agree with the shipped behavior.

## Phase 3 — Finish the JStack corpus

- [x] **3.1 Trainings media + transcripts** — both formations complete.
- [x] **3.2 Projects media** — Fincheck, Foodiary, and WaiterApp complete.
- [x] **3.3 Projects transcripts — ✅ DONE 2026-08-04.** 182 media / 182 transcripts, quality scan **0 flags (CLEAN)**: no repetition loops, no empty/orphan/missing transcripts, no `.part` leftovers, no zero-byte media. The Fincheck lesson `02-front-end/03-dashboard/04-implementando-dropdown-de-sair-da-conta` was repaired **with MiMo-V2.5 via OpenRouter, not Gemini** (Stage 1 stays paused): 11,928 words / 8-gram ×1,051 → **10,444 words / ×4**, diacritics intact. ⚠️ This is the corpus's **only non-Gemini transcript**. Broken original backed up in the session scratchpad; scan script rebuilt at `scratchpad/quality_scan.py` (the `/tmp` original was cleared).
- [x] **3.4 Lives media — ✅ DONE 2026-08-04.** 69/69 courses, 1,084 media, ~13 GB, after the cookie was renewed. Zero local courses absent from the catalog.
- [x] **3.5 Lives transcripts — ✅ DONE 2026-08-04. 1084/1084.** Ran as three passes of `scripts/transcribe_batches.py --jobs 3`: `openrouter` took 542 → 1069 (**$1.2511 for 527 lessons = $0.0024/lesson**, beating the $0.0032 baseline — the Xiaomi pin holding); a second `openrouter` pass recovered 5 more at **$0.022/lesson**, 9× the clean rate, because a looping generation bills to the `max_tokens` ceiling. The last 10 split into two unrelated causes:
    - **1 was a pipeline bug, not the model** — see the `MIN_DURATION_FOR_WPM_SEC` fix under 4.4. Recovered on `openrouter` once fixed (`dynamodb-single-table…/10-paginação-no-dynamodb`, 5,275 w @ 195 wpm).
    - **9 looped deterministically on MiMo**, failing all 4 retries on two consecutive passes. ⛔ **Retrying is the documented cure for the *stochastic* loop but does nothing for these** — the cure is a provider switch. Transcribed with `--provider gemini` (pause lifted with explicit user approval), sweep returned **69/69 clean, exit 0**. These 9 are the corpus's Gemini island:
      | course | lesson |
      |---|---|
      | `dominando-o-react-hook-form` | `11-limpando-erros-com-clearerrors…` |
      | `autenticacao-jwt-em-apis-node-js` | `03-entendendo-o-fluxo-de-autenticação-com-sessions` |
      | `gerenciamento-de-estados-com-zustand` | `02-ferramentas-de-gerenciamento-de-estado` |
      | `processamento-de-imagens-assincrona-…` | `05-redimensionando-a-imagem-com-o-sharp` |
      | `s3-mais-seguranca-com-presigned-posts` | `07-criando-conditions-no-presigned-post` |
      | `otimizando-configurando-ci-cd-…` | `02-conhecendo-os-presets-do-tailwindcss` · `03-criando-o-access-token-no-npm` |
      | `upload-para-o-s3-com-lambda-functions-…` | `03-configurando-as-permissões-da-lambda-no-iam` |
      | `sql-subqueries-transactions-e-triggers` | `04-trabalhando-com-as-transactions-na-prática…` |
- [x] **3.6 Reconciliation — ✅ DONE 2026-08-04.** `scripts/reconcile.py input/jstack-lives output/jstack-lives` → **1084/1084 across 69 courses, 0 needing attention.** 46 numbering gaps remain advisory (only a live catalog session can settle them).
- [x] **3.7 Failure sweep — ✅ DONE 2026-08-04.** No `failed` manifest entries, no `.part`/`.ytdl`, no zero-byte media or transcripts, no audio file without a non-empty transcript — across all four batches.

## Phase 4 — Release verification and handoff

- [x] **4.1 Import/compile smoke** — every downloader imports and both new CLIs expose help successfully.
- [x] **4.2 Offline safety/contract suite** — `.venv/bin/python -m unittest discover -s tests -v` passes 13/13.
- [x] **4.3 Authenticated adapter smoke** — DesignBoost and Skool dry-runs pass without downloading media.
- [x] **4.4 Full test rerun — ✅ 26/26 passing (2026-08-04).** Grew from 13 with two regression tests for the wpm-floor fix: `MIN_DURATION_FOR_WPM_SEC` (30s) exempts short trailing chunks, because `ffmpeg -f segment` leaves a sliver whenever a lesson runs just past a multiple of the chunk length (1622s at 540s → a 2.0s tail; the one word genuinely spoken there scored 28.2 wpm and failed the whole 27-minute lesson). The second test asserts the exemption is not a hole — a real silent-drop on a 60s chunk still fails.
- [x] **4.5 Git hygiene — ✅ verified 2026-08-04.** No cookies, API payloads, media, transcripts, tokens, or signed URLs tracked or untracked-visible; `input/`/`output/` stay ignored. Code landed in `54dfafa` (backend pin + short-chunk density exemption + 2 tests); the docs above are the only uncommitted files.
- [x] **4.6 Durable state — ✅ 2026-08-04.** Final counts, provider provenance, and the cost-per-lesson figures are recorded in this file and `MEMORY.md`.

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
