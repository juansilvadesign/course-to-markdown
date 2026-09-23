# Book digest brief — Pass 1 of `knowledge/skills/knowledge-compiler/book.md`

You write the **per-chapter digest** (scratch) that Claude will later compress into a knowledge pack.
You do **not** write the pack. Fidelity beats polish: a missing idea is recoverable, an invented one is not.

## Input

One folder `knowledge/projects/course-to-markdown/output/books/<slug>/` holding one `<id>.transcript.txt`
per chapter and a `chapters.json` listing the ids and titles **in book order**.

- Read the chapter files listed in `chapters.json` in that order. Read each one **completely** before
  writing its section: never digest from a partial read.
- **Save as you go.** After each chapter, rewrite `digest.md` with that chapter's `### <id>` section added,
  so an interrupted run keeps every chapter it finished. Write `## Whole book` last, once every chapter is in.
- `front-matter` is for bibliographic data only — do not digest its content.

## Output

Write `knowledge/projects/course-to-markdown/output/books/<slug>/digest.md` in exactly this shape. If it already holds
chapter sections from an interrupted run, keep them and continue from the first chapter that is missing;
otherwise start it fresh.

```markdown
---
book: <title as printed, with subtitle>
authors: <as printed; name a foreword/preface writer separately>
publisher_year: <publisher, year>
isbn: <as printed, or "not printed">
---

## Bibliographic evidence
- "<the exact copyright line>" — front-matter

## Chapters

### <id> — <title>
- **TL;DR:** 1–3 sentences — what the chapter argues.
- **Key claim:** one sentence.
- **Frameworks / named models:** `Name exactly as printed` — one-line definition. Only names the author actually uses. If none: "none named".
- **Procedures / exercises / steps:** numbered, in the author's order, if the chapter gives any.
- **Numbers & examples worth keeping:** figures, cases, names — exactly as printed, never rounded.
- **Candidate quotes (2–4):**
  - "<quote>" — <id>
- **Load-bearing?** yes/no — one-line reason.

## Whole book
- **Thesis:** 2–3 sentences.
- **Load-bearing chapters:** 3–5 ids, one reason each.
- **How the frameworks interact:** 3–6 bullets.
- **Practical toolkit:** the 5–10 most actionable moves or exercises in the book, each ending with its chapter id.
- **Doubts:** anything you could not resolve, or "none".
```

## Quote rules — these are machine-checked, so follow them literally

- Each quote is **one contiguous span** copied **character for character** from the chapter file named after the dash.
- Keep the original punctuation, curly quotes, capitalisation and accents. No `...`, no `[brackets]`,
  no joining two sentences that are not adjacent in the file, no fixing typos, no translating.
- 8–45 words. Prefer lines the author clearly means as a maxim or a definition.
- End the line with ` — <id>` using the bare file stem (`— ch03`, `— intro`), nothing after it.

## Other rules

- **Language:** English for headings and labels; the book's own language for content, terms and quotes.
  A Portuguese book gets Portuguese content with its accents preserved exactly (`produção`, never `producao`).
- **Never invent** names, numbers, quotes or dates. Anything uncertain goes under **Doubts**.
- **Compress:** 150–400 words per chapter, scaled to the chapter's weight; the whole digest stays under ~8,000 words.
- Foreword, preface, epilogue and appendix: at most ~150 words each, unless they introduce a framework (then say so).
- An author-written "Chapter Takeaways" section is a cross-check for your digest — do not paste it wholesale.
- Use only your file read/write tools. Do **not** run shell commands or git, and do not touch any other file.

When done, reply with exactly one line: `DONE <digest path> · <word count> words · doubts: <n>`.
