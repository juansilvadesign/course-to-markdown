"""Legs for the book splitter (scripts/split_book.py).

The splitter's real proof is local: re-splitting the three 2026-09-23 books reproduces 51 of their
52 chapter files byte for byte (the 52nd was a defect of the lost splitter: one book's Introduction
merged into its Foreword). That oracle is book text and never enters this public repo, so these
legs run on synthetic books: the shapes that made the real ones hard, plus every refusal.

    .venv/bin/python -m unittest tests.test_split_book -v
"""
from __future__ import annotations

import contextlib
import io
import json
import pathlib
import tempfile
import unittest

from scripts.split_book import Refusal, main, normalize, read_book, split


def body(name, n=8):
    """One long paragraph per line, so no body line can look like a heading."""
    return "\n\n".join(f"This is paragraph {i} of the {name}, written only to give the {name} "
                       f"some weight so that no heading sits close to the next one." for i in range(n))


# English: a TOC up front whose entries include heading-shaped lines, a body line that looks
# like a TOC entry, an epilogue, and back matter after the last chapter.
BOOK_EN = "\n\n".join([
    "My Small Book", "Copyright © 2031 by Nobody. All rights reserved.", "ISBN 978-0-00-000000-2",
    "Contents\nIntroduction\nChapter 1: The First Step\nChapter 2: The Second Step\nEpilogue\nAbout the Author",
    "INTRODUCTION", "Why Small Wins", body("introduction"),
    "CHAPTER 1", "The First Step", body("first chapter"),
    "Chapter 2 of this book goes further, and the rest follows from it.",
    "CHAPTER 2", "The Second Step", body("second chapter"),
    "EPILOGUE", "After the Steps", body("epilogue", 6),
    "About the Author", "Nobody writes small books.",
])

# Portuguese: the Sumário sits BETWEEN two sections, a back-matter word sits in the front matter,
# and publisher ads with a bare ISBN follow the last chapter with no heading of their own.
BOOK_PT = "\n\n".join([
    "Ficha catalográfica", "ISBN 978-85-000-0000-1", "Agradecimentos", "Agradeço a quem leu.",
    "Prefácio", body("prefácio", 6),
    "Sumário\nIntrodução\nCapítulo 1 O começo de tudo\nCapítulo 2 O meio do caminho",
    "Introdução", body("introdução"),
    "Capítulo 1", "O começo de tudo", body("primeiro capítulo"),
    "Capítulo 2", "O meio do caminho", body("segundo capítulo"),
    "Outros livros da editora", "Um livro qualquer", "9788500000001",
])


def plan(text, **kw):
    return split(normalize([text], False)[0], **kw)


def ids(p):
    return [s.id for s in p["sections"]]


class Normalize(unittest.TestCase):

    def test_crlf_and_blank_line_runs(self):
        text, stats = normalize(["a\r\n\r\n\r\n\r\nb\r\nc"], False)
        self.assertEqual(text, "a\n\nb\nc")
        self.assertEqual(stats["blank_runs_collapsed"], 1)

    def test_pdfium_separator_becomes_a_hyphen_only_between_word_characters(self):
        text, stats = normalize(["pós\ufffepalestra", "end of line\ufffe"], True)
        self.assertEqual(text, "pós-palestra\nend of line\ufffe")
        self.assertEqual((stats["fffe_to_hyphen"], stats["fffe_left"]), (1, 1))

    def test_bilingual_pages_lose_their_cjk_lines(self):
        page = "An English line.\n一行中文翻译。\nAnother English line.\n另一行中文。"
        text, stats = normalize([page], True)
        self.assertEqual(text, "An English line.\nAnother English line.")
        self.assertEqual(stats["cjk_lines_dropped"], 2)

    def test_a_few_cjk_words_do_not_trigger_the_drop(self):
        page = "\n".join(["Plain line."] * 19 + ["The word 禅 appears once."])
        self.assertIn("禅", normalize([page], True)[0])
        self.assertNotIn("禅", normalize([page], True, cjk="drop")[0])


class EnglishBook(unittest.TestCase):

    def setUp(self):
        self.text = normalize([BOOK_EN], False)[0]
        self.p = split(self.text)

    def test_sections_in_book_order(self):
        self.assertEqual(ids(self.p), ["front-matter", "intro", "ch01", "ch02", "epilogue"])

    def test_toc_stays_in_the_front_matter_with_the_isbn(self):
        front = self.p["sections"][0].text
        self.assertIn("Chapter 2: The Second Step", front)
        self.assertIsNotNone(self.p["front_isbn"])

    def test_every_section_is_an_exact_slice_starting_at_its_heading(self):
        for s in self.p["sections"]:
            self.assertIn(s.text.rstrip("\n"), self.text, s.id)
        self.assertTrue(self.p["sections"][2].text.startswith("CHAPTER 1\n"))

    def test_a_section_file_has_no_edge_blank_lines_and_one_final_newline(self):
        # The byte contract the three real books were reproduced under; quote_check is indifferent
        # to it, a byte-for-byte regression is not.
        for s in self.p["sections"]:
            self.assertFalse(s.text.startswith("\n"), s.id)
            self.assertTrue(s.text.endswith("\n") and not s.text.endswith("\n\n"), s.id)

    def test_titles_come_from_the_toc_then_from_the_line_under_the_heading(self):
        titles = {s.id: s.title for s in self.p["sections"]}
        self.assertEqual(titles["ch02"], "Chapter 2: The Second Step")
        self.assertEqual(titles["intro"], "Introduction: Why Small Wins")
        self.assertEqual(titles["epilogue"], "Epilogue: After the Steps")

    def test_a_body_line_shaped_like_a_toc_entry_stays_in_its_chapter(self):
        ch01 = next(s for s in self.p["sections"] if s.id == "ch01")
        self.assertIn("Chapter 2 of this book goes further", ch01.text)

    def test_back_matter_is_omitted(self):
        self.assertFalse(any("Nobody writes small books" in s.text for s in self.p["sections"]))
        self.assertIn("About the Author", self.p["end_why"])


class PortugueseBook(unittest.TestCase):

    def test_ads_after_the_last_chapter_are_refused_with_a_hint(self):
        with self.assertRaises(Refusal) as e:
            plan(BOOK_PT)
        self.assertIn("ISBN", str(e.exception))
        self.assertIn("Outros livros da editora", str(e.exception))

    def test_end_at_cuts_the_ads_and_a_mid_book_sumario_is_omitted(self):
        p = plan(BOOK_PT, end_at="Outros livros da editora")
        self.assertEqual(ids(p), ["front-matter", "preface", "intro", "ch01", "ch02"])
        self.assertIn("Agradecimentos", p["sections"][0].text)
        self.assertFalse(any("O meio do caminho\nCapítulo" in s.text or "Sumário" in s.text
                             for s in p["sections"]))
        self.assertEqual([o.why.split()[0] for o in p["omitted"]], ["table", "--end-at"])


class Refusals(unittest.TestCase):
    """A split the tool can't trust must never be written."""

    def chapters(self, *heads):
        return "\n\n".join(x for h in heads for x in (h, body(h)))

    def test_no_chapter_one(self):
        with self.assertRaises(Refusal):
            plan(self.chapters("INTRODUCTION", "EPILOGUE"))

    def test_a_chapter_out_of_sequence(self):
        with self.assertRaises(Refusal) as e:
            plan(self.chapters("CHAPTER 1", "CHAPTER 3", "CHAPTER 2"))
        self.assertIn("out of the 1..N sequence", str(e.exception))

    def test_a_second_introduction(self):
        with self.assertRaises(Refusal):
            plan(self.chapters("INTRODUCTION", "INTRODUCTION", "CHAPTER 1"))

    def test_a_front_section_after_chapter_one(self):
        with self.assertRaises(Refusal) as e:
            plan(self.chapters("CHAPTER 1", "INTRODUCTION", "CHAPTER 2"))
        self.assertIn("after Chapter 1", str(e.exception))

    def test_end_at_past_the_back_matter_does_not_pull_the_back_matter_in(self):
        p = plan(BOOK_EN, end_at="Nobody writes small books.")
        self.assertIn("About the Author", p["end_why"])
        self.assertFalse(any("Nobody writes small books" in s.text for s in p["sections"]))

    def test_prose_under_a_heading_is_not_a_title(self):
        book = self.chapters("INTRODUCTION", "CHAPTER 1")
        self.assertEqual(plan(book)["sections"][0].title, "Introduction")

    def test_an_end_section_before_the_last_chapter_until_ignored(self):
        book = self.chapters("CHAPTER 1", "Conclusion", "CHAPTER 2")
        with self.assertRaises(Refusal) as e:
            plan(book)
        self.assertIn("--ignore-heading", str(e.exception))
        self.assertEqual(ids(plan(book, ignore={"Conclusion"})), ["ch01", "ch02"])

    def test_end_at_that_matches_nothing(self):
        with self.assertRaises(Refusal):
            plan(self.chapters("CHAPTER 1"), end_at="No such line")

    def test_front_extra_that_matches_nothing(self):
        with self.assertRaises(Refusal):
            plan(BOOK_EN, front_extra=("No such line", "ISBN"))

    def test_endnotes_grouped_by_chapter_still_end_the_book(self):
        # A real book's shape: ENDNOTES, then per-chapter group headings close together. The stop must fire
        # although the heading is crowded, and the notes' `Chapter 1` is not a chapter out of sequence.
        book = self.chapters("CHAPTER 1", "CHAPTER 2") + "\n\nENDNOTES\nIntroduction\n1. A source.\nChapter 1\n1. Another."
        p = plan(book)
        self.assertEqual(ids(p), ["ch01", "ch02"])
        self.assertIn("ENDNOTES", p["end_why"])

    def test_without_a_toc_a_body_line_never_becomes_a_title(self):
        book = "\n\n".join(["CHAPTER 1", "The First Step", body("first chapter"),
                            "Chapter 2 of this book goes further, and the rest follows from it.",
                            "CHAPTER 2", "The Second Step", body("second chapter")])
        self.assertEqual([s.title for s in plan(book)["sections"]],
                         ["Chapter 1: The First Step", "Chapter 2: The Second Step"])

    def test_front_extra_appends_the_block_from_the_omitted_tail(self):
        book = BOOK_EN + "\n\nPublisher: Small Press\n\nAll rights reserved.\n\neISBN 978-0-00-000000-9"
        p = plan(book, front_extra=("Publisher: Small Press", "eISBN"))
        self.assertTrue(p["sections"][0].text.endswith(
            "\n\nPublisher: Small Press\n\nAll rights reserved.\n\neISBN 978-0-00-000000-9\n"))


class CommandLine(unittest.TestCase):

    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(a) for a in argv])
        return code, out.getvalue() + err.getvalue()

    def test_writes_chapters_and_manifest_then_refuses_to_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            src = tmp / "My Small Book (Nobody).txt"
            src.write_text(BOOK_EN, encoding="utf-8")
            code, _ = self.run_main(src, "--out", tmp / "books")
            self.assertEqual(code, 0)
            book = tmp / "books" / "my-small-book"
            meta = json.loads((book / "chapters.json").read_text(encoding="utf-8"))
            self.assertEqual([c["id"] for c in meta["chapters"]], ["front-matter", "intro", "ch01", "ch02", "epilogue"])
            first = (book / "ch01.transcript.txt").read_bytes()
            code, msg = self.run_main(src, "--out", tmp / "books")
            self.assertEqual(code, 2)
            self.assertIn("already holds chapter files", msg)
            self.assertEqual((book / "ch01.transcript.txt").read_bytes(), first)

    def test_dry_run_and_refusal_write_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            (tmp / "en.txt").write_text(BOOK_EN, encoding="utf-8")
            (tmp / "pt.txt").write_text(BOOK_PT, encoding="utf-8")
            self.assertEqual(self.run_main(tmp / "en.txt", "--out", tmp / "books", "--dry-run")[0], 0)
            self.assertEqual(self.run_main(tmp / "pt.txt", "--out", tmp / "books")[0], 2)
            self.assertFalse((tmp / "books").exists())


def tiny_pdf(pages):
    """A text-only PDF built by hand (Helvetica, one line per Tj), so the PDF path runs on no book."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>",
            f"<< /Type /Pages /Kids [{' '.join(f'{3 + 2 * i} 0 R' for i in range(len(pages)))}] /Count {len(pages)} >>"]
    font = 3 + 2 * len(pages)
    for i, lines in enumerate(pages):
        ops = "BT /F1 12 Tf 14 TL 72 720 Td " + " ".join(f"({ln}) Tj T*" for ln in lines) + " ET"
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R "
                    f"/Resources << /Font << /F1 {font} 0 R >> >> >>")
        objs.append(f"<< /Length {len(ops)} >>\nstream\n{ops}\nendstream")
    objs.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out, offsets = "%PDF-1.4\n", []
    for n, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n{o}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offsets)
    return (out + f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n").encode("latin-1")


class PdfPath(unittest.TestCase):

    def test_pages_are_read_in_order_and_joined_with_a_newline(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = pathlib.Path(tmp) / "book.pdf"
            pdf.write_bytes(tiny_pdf([["CHAPTER 1", "First page text."], ["Second page text."]]))
            text, _ = read_book(pdf)
        self.assertEqual(text.split("\n"), ["CHAPTER 1", "First page text.", "Second page text."])


if __name__ == "__main__":
    unittest.main()
