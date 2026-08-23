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

**Stage 0/1 is finished, committed, and pushed. The forbidden-path incident is CLOSED: 5.2, 5.3 and 5.4 are all done, and the 19 recompiled courses (29 pack files) are PROMOTED into `knowledge/coding/courses/` as of 2026-08-23.** In order:

1. 🟡 **COMMIT — the whole thing is uncommitted.** New: `scripts/pack_fidelity.py`, `scripts/promote_packs.py`, the 29 promoted library files, 2 edited library files, this file, `MEMORY.md`. ⛔ `output/` is gitignored, so the review evidence in `output/_review-5.4/` is **not** durable — the conclusions are in 5.4 below and in `MEMORY.md`.
2. **Decide the quote-contract debt.** `SKILL.md` says quotes are *"Verbatim, with location reference."* Of 53 promoted quotes: **23 carry no location reference and 14 are lightly reworded** (disfluency cleanup — hand-verified, meaning preserved). Either fix the packs or amend the contract; it is debt, not wrong knowledge.
3. **Decide the `course.md` ~2k token cap.** Measured, not guessed: **25 of 29 packs exceed it**, median ~2.9k, max 4,344 — *including halves that are already splits*. 25/29 is evidence the cap is mis-set for these lives. ⛔ Don't force three-way splits to satisfy a number the corpus disagrees with.
4. **Decide the 3 term-loss lessons** (5.5) — re-transcribe on Gemini, or accept the omission and record provenance.
5. **The other 50 jstack-lives courses are still staged and unpromoted.** They were never on the forbidden path, so their packs are legitimate — but they have had no 5.4-grade review. Run `scripts/pack_fidelity.py` over them before promoting any.
6. **Answer the two open acquisition-scope questions** below before touching DesignBoost or Skool.

The jargon audit that used to head this list has now been **run** — result and remaining decision in 5.5.

Standing rules that outlived the checkpoint: media and transcripts are the source of truth, never terminal history; never launch an aggregate worker over live per-course workers; always pair `-o` roots explicitly. **New (2026-08-05):** a pack's *existence* proves a file was written — never that the course was read.

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

- [x] **5.1 Choose reusable-unit granularity — ✅ DONE 2026-08-05.** Course/project/discipline granularity for JStack projects (6 packs) and JStack lives (74 packs across 69 courses). **This decision stands** — only the execution below was defective.
- [x] **5.2 Compile in batches of no more than four agents — ✅ CLOSED 2026-08-21.** All 19 recompiled through `course-module-compiler` on the Claude subscription; `scripts/compile_lives_stage2.py` deleted (`git rm`, commit `b48f097`). Coverage 22–66% → **100% on every course**. Original defect record below, kept as the reason the rerun happened:

    - 🔴 **(historical)** 102 `.pack.md` files exist in staging, but **19 of them were written by `scripts/compile_lives_stage2.py`, which calls `gemini-2.5-flash` over the Gemini API** — the one thing Stage 2 must never do. The earlier "subagents and batch script" wording hid that the batch-script half *is* the forbidden path. Those 19 must be recompiled through `course-module-compiler`. Its three defects, all in its own config:
    - ⛔ **`[:60000]` prompt slice (plus a 15k-per-lesson cap) — the compiler never read most of the course.** All 19 courses overflowed the window: coverage **22–66%, median 37%**, across **272 lessons**. Worst: `login-social-federated-com-aws-cognito`, 25 lessons → **22%**. This is the defect that matters most, because nothing downstream announces it.
    - ⛔ **`max_output_tokens=3000` with thinking left ON** — the budget goes to reasoning, so **6 packs are truncated mid-sentence** (358–725 B against an 8.9 KB median; 5 of the 6 are in this cohort). The hard rules already say "thinking off", and the pipeline's own `transcribe.py` honours it; this script did not.
    - ⛔ **`import datetime` present but unused → the model invented the date.** All 19 carry `compiled: 2024-07-30`, two years in the past — the same hallucination the 2026-06 fix cured on the transcription side.
    - Across all 102 packs: **28 lack the required `## How to apply`** (14 in this cohort, 14 dated today) and 3 carry quoted-date drift (`compiled: "2026-08-05"`).
- [x] **5.3 Reconcile lesson coverage — ✅ CLOSED 2026-08-21 by `scripts/pack_coverage.py`** (content-based, 19/19 pass, 272/272 lessons). Historical note: The previous "100% of 1,668 transcripts, zero orphans" was a **counting artifact**: it asserted that every transcript sits under a course that *has* a pack, never that its content reached the compiler. Under the 60k slice it demonstrably did not. Re-reconciliation must be **content-based** — assert what the compiler actually ingested, not folder membership.
- [x] **5.4 Review, then promote — ✅ DONE 2026-08-23. All 19 reviewed against the TRANSCRIPTS, 29 pack files promoted into `knowledge/coding/courses/`.**
    - **v1 was NOT the authority, and could not be.** It read a median 37% of each course and **7 of the 19 v1 packs are 358–1,286 B truncated stubs** that die inside the TL;DR. Where v2 agrees with v1 that agreement covers only the slice v1 saw — it corroborates the partiality, not the pack. Fidelity was judged against the transcripts; v1 was kept only as a regression diff (`--v1-diff`), which found nothing lost.
    - **New instrument: `scripts/pack_fidelity.py`.** Gate Q (every `## Quotes worth keeping` entry must trace to a transcript, separating fabricated / misattributed / reworded), Gate S (subject-term dropout — the substitution class a v1↔v2 diff structurally cannot see), Gate T (token measurement, recorded not graded).
    - ✅ **Zero fabrications across all 19 courses** (53 quotes). ✅ **Zero transcript corruptions propagated into any pack.**
    - 🟡 **Quote-contract debt, deliberately promoted as-is:** `SKILL.md` requires quotes be *"Verbatim, with location reference."* Actual: **13 VERBATIM · 14 REWORDED · 23 UNCITED · 1 STITCHED · 1 INCONCLUSIVE.** The 14 rewordings are all **spoken-disfluency cleanup** (a fixed misspeak, a pluralised verb, a removed stutter) — meaning preserved in every case, hand-verified. Fix later or amend the contract; it is not wrong knowledge.
    - 🔴 **The compiler SILENTLY REPAIRS corrupted transcripts.** `Svelte ×6`→`Zustand`, `Zustend ×16`→`Zustand`, `form setval`→`form.setValue` (this one it even annotated). Good for the packs, but it means transcript corruption is **invisible downstream** — the transcript is the only place it can be caught. This is why Gate S reads transcripts, not packs.
    - **`tokens_estimate` was wrong on 25 of 29 packs** — 17 under-stated, 8 over-stated, 4 within ±50 (worst +979). Corrected from measured character count during promotion. ⛔ The "agents guess low" rule is a *tendency*, not a law.
    - ⛔ **Scope: only the 19.** The other 50 jstack-lives courses keep their v1-era packs in staging and were NOT promoted. Three forward references in the promoted packs point at them and dangle on purpose.
- [ ] **5.5 Jargon audit — ✅ RUN 2026-08-05; remediation still open.** `--reference` against a purpose-built 19-lesson Gemini baseline (`output/jstack-lives-gemini-ref/`, swept 00:16): **3 of 19 pairs show real term loss.** One is the exact documented failure — `gerenciamento-de-estados-com-zustand/1000-conteúdo/06-configurando-o-zustand-com-o-typescript`, where Gemini has *"ele tá como **unknown**, porque eu não passei nenhum generic"* and MiMo has *"ele tá como **any**"* (`unknown` ×8 → ×0). The other two lose `callback` ×7 and `context` ×3.
    - ✅ **It did not reach the library.** That pack propagates no wrong `any`/`unknown` rule — neither term survived compression, so this is an **omission, not an inversion**. Still decide whether the 3 lessons get re-transcribed on `--provider gemini` before their packs are rebuilt.
    - ⛔ **Bare mode confirmed useless at scale:** 252 of 1,084 flagged (23.2%) — the documented base-rate noise. Only `--reference` discriminates.
    - ⚠️ **Tool wart:** the heuristics run *even in* `--reference` mode (`jargon_audit.py:138-139`), so a tree-vs-tree invocation buries the 19 real diffs under 252 noise flags and looks like it found nothing. Filter on `TERM LOST`/`down N%`, or make `--reference` suppress the heuristics.

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
