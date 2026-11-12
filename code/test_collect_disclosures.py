"""Tests for the public CNINFO disclosure collector.

Run from repository root:
    python -m unittest discover -s code -p 'test_collect_disclosures.py' -v
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

import collect_disclosures

ROOT = Path(__file__).resolve().parents[1]
PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


def make_universe(path: Path, *, duplicate: bool = False, bad_code: bool = False) -> Path:
    security = {
        "symbol": "688041.SH", "code": "688041" if not bad_code else "68804",
        "name": "测试公司", "market": "A", "exchange": "SSE", "collection": "A_primary",
    }
    securities = [security, dict(security)] if duplicate else [security]
    path.write_text(json.dumps({"securities": securities}, ensure_ascii=False), encoding="utf-8")
    return path


class FixtureHandler(BaseHTTPRequestHandler):
    fail_pdf = False
    bad_content_type = False
    query_bodies: list[dict[str, list[str]]] = []
    request_count = 0
    pdf_requests = 0
    omit_pdf_length = False

    def log_message(self, format, *args):
        return

    def _json(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        type(self).request_count += 1
        if self.path == "/new/data/szse_stock.json":
            self._json({"stockList": [{"code": "688041", "zwjc": "测试公司", "orgId": "org-test"}]})
            return
        if self.path.startswith("/pdfs/"):
            type(self).pdf_requests += 1
            if self.fail_pdf:
                self._json({"error": "boom"}, status=500)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html" if self.bad_content_type else "application/pdf")
            if not self.omit_pdf_length:
                self.send_header("Content-Length", str(len(PDF)))
            self.end_headers()
            self.wfile.write(PDF)
            return
        self._json({"error": "not found"}, status=404)

    def do_POST(self):
        type(self).request_count += 1
        if self.path != "/new/hisAnnouncement/query":
            self._json({"error": "not found"}, status=404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        fields = parse_qs(raw)
        self.query_bodies.append(fields)
        category = fields.get("category", [""])[0]
        if category == "category_ndbg_szsh":
            items = [
                {"announcementId": "a1", "announcementTitle": "2025年年度报告", "announcementTime": 1760000000000, "adjunctUrl": "pdfs/a1.pdf"},
                {"announcementId": "a2", "announcementTitle": "2025年年度报告（修订版）", "announcementTime": 1770000000000, "adjunctUrl": "pdfs/a2.pdf"},
                {"announcementId": "a3", "announcementTitle": "2024年年度报告", "announcementTime": 1729987200000, "adjunctUrl": "pdfs/a3.pdf"},
                {"announcementId": "a4", "announcementTitle": "2025年年度报告摘要", "announcementTime": 1760000000000, "adjunctUrl": "pdfs/a4.pdf"},
                {"announcementId": "a5", "announcementTitle": "关于2025年年度报告的更正公告", "announcementTime": 1770000000000, "adjunctUrl": "pdfs/a5.pdf"},
            ]
        else:
            items = [
                {"announcementId": "b1", "announcementTitle": "2026年半年度报告", "announcementTime": 1755000000000, "adjunctUrl": "pdfs/b1.pdf"},
                {"announcementId": "b2", "announcementTitle": "2025年半年度报告", "announcementTime": 1740000000000, "adjunctUrl": "pdfs/b2.pdf"},
                {"announcementId": "b3", "announcementTitle": "2025年半年度报告摘要", "announcementTime": 1740000000000, "adjunctUrl": "pdfs/b3.pdf"},
            ]
        self._json({"announcements": items, "totalAnnouncement": len(items)})


class DisclosureCollectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FixtureHandler.query_bodies = []
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(timeout=5)
        cls.server.server_close()

    def setUp(self):
        FixtureHandler.fail_pdf = False
        FixtureHandler.bad_content_type = False
        FixtureHandler.omit_pdf_length = False
        FixtureHandler.request_count = 0
        FixtureHandler.pdf_requests = 0
        FixtureHandler.query_bodies = []

    def run_cli(self, universe: Path, output: Path, *extra: str):
        return subprocess.run(
            [sys.executable, str(ROOT / "code" / "collect_disclosures.py"),
             "--universe", str(universe), "--output", str(output),
             "--cninfo-base", self.base, "--pdf-base", self.base,
             "--start", "2024-01-01", "--end", "2026-11-11",
             "--delay", "0", "--timeout", "5", *extra],
            cwd=ROOT, text=True, capture_output=True, timeout=60,
        )

    def test_downloads_full_reports_and_excludes_summaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            universe = make_universe(root / "universe.json")
            output = root / "out"
            result = self.run_cli(universe, output, "--limit", "10", "--max-bytes", "10000", "--per-kind", "2")
            self.assertEqual(result.returncode, 0, result.stderr)
            rows = [json.loads(x) for x in (output / "metadata.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 5)
            self.assertEqual({row["document_type"] for row in rows}, {"annual_report", "interim_report"})
            self.assertTrue(all("摘要" not in row["title"] and "更正公告" not in row["title"] for row in rows))
            self.assertEqual({row["report_period"] for row in rows},
                             {"2025-12-31", "2024-12-31", "2026-06-30", "2025-06-30"})
            self.assertEqual({row["version_status"] for row in rows}, {"original_filing", "updated_filing"})
            self.assertTrue(all(row["sha256"] and row["bytes"] == len(PDF) for row in rows))
            self.assertTrue(all((output / row["cache_path"]).is_file() for row in rows))
            self.assertTrue(all(row["publisher"] == "巨潮资讯" for row in rows))
            self.assertTrue(all(row["available_at"] == row["published_at"] for row in rows))
            self.assertTrue(all(row["local_file"] == row["cache_path"] for row in rows))
            self.assertTrue(all("announcementId=" in row["availability_basis"] for row in rows))
            batch = json.loads((output / "batch.json").read_text(encoding="utf-8"))
            self.assertEqual(batch["downloaded"], 5)
            self.assertEqual(batch["requests"], 8)  # directory + 2 queries + 5 PDFs
            self.assertEqual(batch["failures"], 0)
            self.assertEqual(batch["per_kind"], 2)
            self.assertTrue(all("D:\\" not in json.dumps(row) for row in rows))
            for name in ("metadata.jsonl", "requests.jsonl", "batch.json"):
                self.assertNotIn(b"\r\n", (output / name).read_bytes())

    def test_duplicate_run_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            universe = make_universe(root / "universe.json")
            output = root / "out"
            first = self.run_cli(universe, output, "--limit", "10", "--max-bytes", "10000", "--per-kind", "2")
            self.assertEqual(first.returncode, 0, first.stderr)
            first_meta = (output / "metadata.jsonl").read_bytes()
            first_files = {p.name: p.read_bytes() for p in (output / "cache" / "pdfs").glob("*")}
            second = self.run_cli(universe, output, "--limit", "10", "--max-bytes", "10000", "--per-kind", "2")
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual((output / "metadata.jsonl").read_bytes(), first_meta)
            self.assertEqual({p.name: p.read_bytes() for p in (output / "cache" / "pdfs").glob("*")}, first_files)
            batch = json.loads((output / "batch.json").read_text(encoding="utf-8"))
            self.assertEqual(batch["downloaded"], 5)
            self.assertEqual(batch["new_completed_documents"], 0)
            self.assertEqual(batch["skipped_duplicates"], 5)
            self.assertEqual(batch["metadata_records"], 5)

    def test_byte_budget_records_failure_without_partial_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            universe = make_universe(root / "universe.json")
            output = root / "out"
            result = self.run_cli(universe, output, "--limit", "10", "--max-bytes", "10")
            self.assertEqual(result.returncode, 0, result.stderr)
            failures = [json.loads(x) for x in (output / "failures.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertTrue(any(row["stage"] == "byte_budget" for row in failures))
            self.assertEqual(list((output / "cache" / "pdfs").glob("*.pdf")), [])

    def test_http_error_is_logged(self):
        FixtureHandler.fail_pdf = True
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            universe = make_universe(root / "universe.json")
            output = root / "out"
            result = self.run_cli(universe, output, "--limit", "2", "--max-bytes", "10000")
            self.assertEqual(result.returncode, 0, result.stderr)
            failures = [json.loads(x) for x in (output / "failures.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertTrue(any(row["stage"] == "pdf" and "HTTP 500" in row["error"] for row in failures))
            self.assertEqual(list((output / "cache" / "pdfs").glob("*.pdf")), [])

    def test_wrong_content_type_is_rejected(self):
        FixtureHandler.bad_content_type = True
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            universe = make_universe(root / "universe.json")
            output = root / "out"
            result = self.run_cli(universe, output, "--limit", "2", "--max-bytes", "10000")
            self.assertEqual(result.returncode, 0, result.stderr)
            failures = [json.loads(x) for x in (output / "failures.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertTrue(any("content-type" in row["error"] for row in failures))
            self.assertEqual(list((output / "cache" / "pdfs").glob("*.pdf")), [])

    def test_invalid_parameters_and_duplicate_universe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            universe = make_universe(root / "universe.json", duplicate=True)
            bad = self.run_cli(universe, root / "out", "--limit", "2")
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("duplicate symbol", bad.stderr)

            bad_date = self.run_cli(make_universe(root / "u2.json"), root / "out2", "--start", "2024-01-01T00:00:00")
            self.assertNotEqual(bad_date.returncode, 0)
            self.assertIn("exactly YYYY-MM-DD", bad_date.stderr)

            bad_limit = self.run_cli(make_universe(root / "u3.json"), root / "out3", "--limit", "0")
            self.assertNotEqual(bad_limit.returncode, 0)
            self.assertIn("limit must be 1..100", bad_limit.stderr)

    def test_query_uses_requested_date_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            universe = make_universe(root / "universe.json")
            output = root / "out"
            FixtureHandler.query_bodies = []
            result = self.run_cli(universe, output, "--limit", "2", "--max-bytes", "10000")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(FixtureHandler.query_bodies)
            self.assertTrue(all("seDate" in body for body in FixtureHandler.query_bodies))
            self.assertTrue(all(body["seDate"][0] == "2024-01-01~2026-11-11" for body in FixtureHandler.query_bodies))

    def test_request_budget_is_checked_before_http(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            universe = make_universe(root / "universe.json")
            output = root / "out"
            result = self.run_cli(universe, output, "--limit", "1", "--request-budget", "2")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(FixtureHandler.request_count, 2)
            log = (output / "requests.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(log), 2)
            failures = (output / "failures.jsonl").read_text(encoding="utf-8")
            self.assertIn("request_budget", failures)

    def test_persistent_download_budget_is_not_reset_by_new_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            universe = make_universe(root / "universe.json")
            output = root / "out"
            output.mkdir()
            (output / "requests.jsonl").write_text(
                json.dumps({"kind": "pdf", "bytes": 100, "status": 200}) + "\n",
                encoding="utf-8",
            )
            result = self.run_cli(universe, output, "--limit", "1", "--max-bytes", "10000")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(FixtureHandler.pdf_requests, 0)
            self.assertEqual(FixtureHandler.request_count, 0)
            batch = json.loads((output / "batch.json").read_text(encoding="utf-8"))
            self.assertEqual(batch["pdf_attempts_before"], 1)
            self.assertEqual(batch["downloaded"], 1)
            self.assertEqual(batch["new_completed_documents"], 0)

    def test_streaming_byte_budget_includes_previous_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            universe = make_universe(root / "universe.json")
            output = root / "out"
            output.mkdir()
            (output / "requests.jsonl").write_text(
                json.dumps({"kind": "pdf", "bytes": 30, "status": 200}) + "\n", encoding="utf-8")
            FixtureHandler.omit_pdf_length = True
            result = self.run_cli(universe, output, "--limit", "10", "--max-bytes", str(30 + len(PDF) - 1))
            self.assertEqual(result.returncode, 0, result.stderr)
            batch = json.loads((output / "batch.json").read_text(encoding="utf-8"))
            self.assertEqual(batch["new_completed_documents"], 0)
            self.assertEqual(batch["downloaded_bytes"], 30 + len(PDF))
            self.assertIn("byte_budget", (output / "failures.jsonl").read_text(encoding="utf-8"))

    def test_corrupt_same_length_cache_is_rehashed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            universe = make_universe(root / "universe.json")
            output = root / "out"
            first = self.run_cli(universe, output, "--limit", "10", "--max-bytes", "10000", "--per-kind", "2")
            self.assertEqual(first.returncode, 0, first.stderr)
            rows = [json.loads(x) for x in (output / "metadata.jsonl").read_text(encoding="utf-8").splitlines()]
            target = rows[0]
            pdf_path = output / target["cache_path"]
            corrupted = bytearray(pdf_path.read_bytes())
            corrupted[0] = ord("X")
            pdf_path.write_bytes(corrupted)
            self.assertEqual(len(corrupted), target["bytes"])
            second = self.run_cli(universe, output, "--limit", "10", "--max-bytes", "10000", "--per-kind", "2")
            self.assertEqual(second.returncode, 0, second.stderr)
            batch = json.loads((output / "batch.json").read_text(encoding="utf-8"))
            self.assertEqual(batch["downloaded"], 6)
            self.assertEqual(batch["new_completed_documents"], 1)
            self.assertEqual(batch["skipped_duplicates"], 4)
            restored = pdf_path.read_bytes()
            self.assertTrue(restored.startswith(b"%PDF-"))
            self.assertNotEqual(restored, bytes(corrupted))

    def test_safe_paths_and_announcement_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(collect_disclosures.safe_cache_path(root, "cache/pdfs/a.pdf"),
                             (root / "cache/pdfs/a.pdf").resolve())
            with self.assertRaises(ValueError):
                collect_disclosures.safe_cache_path(root, "../outside.pdf")
            with self.assertRaises(ValueError):
                collect_disclosures.safe_component("../bad", "announcement_id")

    def test_hk_announcement_title_is_not_a_full_report(self):
        self.assertFalse(collect_disclosures.eligible_title("港股公告：2024年度报告", "annual_report"))
        self.assertTrue(collect_disclosures.eligible_title("2025年年度报告（修订版）", "annual_report"))
        self.assertFalse(collect_disclosures.eligible_title("关于2025年年度报告的更正公告", "annual_report"))

    def test_public_doc_example_uses_fingraph(self):
        text = (ROOT / "code" / "collect_disclosures.py").read_text(encoding="utf-8")
        self.assertIn(".fingraph/disclosures", text)
        self.assertNotIn(".local/disclosures", text)


if __name__ == "__main__":
    unittest.main()
