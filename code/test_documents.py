"""PDF preparation checks use synthetic documents, with no model calls."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from prepare_documents import prepare, checked_pdf, read_records

HAS_DOCUMENTS = all(importlib.util.find_spec(name) for name in ["pymupdf", "langchain_text_splitters"])


@unittest.skipUnless(HAS_DOCUMENTS, "install code/requirements-documents.txt for PDF processing checks")
class DocumentPreparationTests(unittest.TestCase):
    def setUp(self):
        import pymupdf
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cache = self.root / "raw"
        self.cache.mkdir()
        self.pdf = self.cache / "report.pdf"
        with pymupdf.open() as doc:
            for section in ["Hardware products", "Cloud services"]:
                page = doc.new_page()
                page.insert_textbox(pymupdf.Rect(50, 50, 550, 750),
                    section + "\n" + ("Acme produces servers. The annual report is evidence for its products.\n" * 14), fontsize=10)
            doc.save(self.pdf)
        self.record = {"symbol": "ACME.HK", "title": "Acme annual report", "local_file": "report.pdf",
                       "source_url": "https://example.test/report.pdf", "published_at": "2024-01-01",
                       "retrieved_at": "2026-01-01T00:00:00+08:00",
                       "sha256": hashlib.sha256(self.pdf.read_bytes()).hexdigest()}

    def tearDown(self):
        self.temp.cleanup()

    def test_pages_and_chunks_retain_exact_parent_text_and_time(self):
        out = self.root / "prepared"
        result = prepare([self.record], self.cache, out, chunk_size=300, chunk_overlap=40)
        self.assertEqual(result["documents"], 1)
        self.assertEqual(result["pages"], 2)
        self.assertGreater(result["chunks"], 2)
        document = read_records(out / "documents.jsonl")[0]
        self.assertEqual(document["available_at"], "2026-01-01")
        self.assertTrue(document["complete"])
        body = (out / document["text_file"]).read_text(encoding="utf-8")
        self.assertEqual(hashlib.sha256(body.encode()).hexdigest(), document["text_sha256"])
        pages = {p["page"]: p["text"] for p in read_records(out / document["pages_file"])}
        for chunk in read_records(out / "chunks.jsonl"):
            self.assertEqual(chunk["source_id"], document["id"])
            self.assertEqual(pages[chunk["page"]][chunk["char_start"]:chunk["char_end"]], chunk["text"])

    def test_duplicates_are_not_extra_documents_or_pages(self):
        result = prepare([self.record, self.record], self.cache, self.root / "prepared")
        self.assertEqual(result["documents"], 1)
        self.assertEqual(result["pages"], 2)
        self.assertEqual(result["duplicates"], 1)

    def test_invalid_hash_and_outside_cache_are_reported(self):
        with self.assertRaisesRegex(ValueError, "inside"):
            checked_pdf({**self.record, "local_file": "../outside.pdf"}, self.cache, 100000)
        result = prepare([{**self.record, "sha256": "wrong"}], self.cache, self.root / "prepared")
        self.assertEqual(result["failures"], 1)
        self.assertEqual(result["documents"], 0)
        self.assertEqual(result["chunks"], 0)

    def test_same_source_produces_identical_prepared_records(self):
        first, second = self.root / "one", self.root / "two"
        for out in [first, second]:
            prepare([self.record], self.cache, out)
        for name in ["documents.jsonl", "chunks.jsonl", "manifest.json"]:
            self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())

    @unittest.skipUnless(importlib.util.find_spec("pymupdf4llm"), "markdown extraction is optional")
    def test_markdown_extraction_preserves_the_page_reference(self):
        out = self.root / "markdown"
        report = prepare([self.record], self.cache, out, output_format="markdown")
        self.assertEqual(report["documents"], 1)
        self.assertEqual(report["pages"], 2)
        self.assertEqual(report["failures"], 0)
        document = read_records(out / "documents.jsonl")[0]
        self.assertIn("Acme produces servers", (out / document["text_file"]).read_text(encoding="utf-8"))
