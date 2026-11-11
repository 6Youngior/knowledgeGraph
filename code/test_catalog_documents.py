import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from catalog_documents import build_catalog


class CatalogTests(unittest.TestCase):
    def test_same_body_is_one_document_and_prefers_the_verified_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            text = "Identical original document"
            text_hash = hashlib.sha256(text.encode()).hexdigest()
            inputs = []
            for index, status in enumerate(["observed_version", "original_filing"]):
                directory = root / str(index)
                directory.mkdir()
                (directory / "body.txt").write_text(text, encoding="utf-8")
                row = {"id": str(index), "symbol": "TEST.SH", "title": "Test report",
                       "url": f"https://example.test/{index}.pdf", "text_file": "body.txt",
                       "pdf_sha256": str(index) * 64, "text_sha256": text_hash,
                       "version_status": status, "available_at": "2024-01-01",
                       "complete": True, "pages": 2, "chunks": 3, "text_characters": len(text)}
                (directory / "documents.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
                inputs.append(directory)
            output = root / "catalog"
            report = build_catalog(inputs, output)
            self.assertEqual(report["documents"], 1)
            self.assertEqual(report["duplicates"], 1)
            self.assertEqual(report["pages"], 2)
            row = json.loads((output / "documents.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(row["version_status"], "original_filing")
            self.assertEqual(len(row["urls"]), 2)
            self.assertNotIn("text_file", row)
