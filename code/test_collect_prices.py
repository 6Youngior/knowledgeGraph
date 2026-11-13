"""Tests for the bounded daily-price collector; local HTTP fixtures only."""
from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
DATES = ("2021-01-04", "2021-01-05")


class PriceHandler(BaseHTTPRequestHandler):
    bad_close = False
    bad_bounds = False
    bad_order = False
    redirect = False
    omit_length = False
    request_count = 0

    def log_message(self, format, *args):
        return

    def do_GET(self):
        type(self).request_count += 1
        parsed = urlparse(self.path)
        if parsed.path != "/api/qt/stock/kline/get":
            self.send_response(404)
            self.end_headers()
            return
        if self.redirect:
            self.send_response(302)
            self.send_header("Location", "/somewhere-else")
            self.end_headers()
            return
        query = parse_qs(parsed.query)
        fqt = query.get("fqt", ["0"])[0]
        base = 10.0 if query.get("secid", ["1.000300"])[0] == "1.000300" else 20.0
        if fqt == "1":
            base += 5.0
        klines = []
        days = (DATES[1], DATES[0]) if self.bad_order else DATES
        for index, day in enumerate(days):
            close = 0.0 if self.bad_close and index == 0 else base + index
            open_ = close + 3 if self.bad_bounds else close
            klines.append(f"{day},{open_},{close},{close + 1},{close - 1},1000,20000,0,0,0,0,0")
        payload = json.dumps({"data": {"klines": klines}}, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        if not self.omit_length:
            self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def make_universe(path: Path) -> Path:
    path.write_text(json.dumps({"securities": [{
        "symbol": "688041.SH", "code": "688041", "name": "测试公司",
        "market": "A", "exchange": "SSE",
    }]}, ensure_ascii=False), encoding="utf-8")
    return path


def run_cli(universe: Path, output: Path, base: str, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / "code" / "collect_prices.py"),
         "--universe", str(universe), "--output", str(output),
         "--base-url", base, "--start", "2021-01-01", "--end", "2026-11-12",
         "--delay", "0", "--timeout", "5", *extra],
        cwd=ROOT, text=True, capture_output=True, timeout=60,
    )


class PriceCollectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), PriceHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(timeout=5)
        cls.server.server_close()

    def setUp(self):
        PriceHandler.bad_close = False
        PriceHandler.bad_bounds = False
        PriceHandler.bad_order = False
        PriceHandler.redirect = False
        PriceHandler.omit_length = False
        PriceHandler.request_count = 0

    def test_writes_raw_qfq_and_index_with_valid_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            universe = make_universe(root / "universe.json")
            output = root / "out"
            result = run_cli(universe, output, self.base, "--budget-requests", "3", "--budget-bytes", "100000")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(PriceHandler.request_count, 3)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["counts"]["stock_series"], 2)
            self.assertEqual(manifest["counts"]["index_series"], 1)
            self.assertEqual(manifest["counts"]["rows"], 6)
            for name in ("688041_SH_none.csv", "688041_SH_qfq.csv", "index_000300_none.csv"):
                path = output / name
                self.assertTrue(path.is_file())
                with path.open(encoding="utf-8", newline="") as handle:
                    rows = list(csv.DictReader(handle))
                self.assertEqual([row["date"] for row in rows], list(DATES))
                self.assertEqual(list(rows[0].keys()), ["date", "open", "high", "low", "close", "volume", "amount"])
                self.assertEqual(rows[0]["amount"], "20000.0")
            self.assertNotEqual((output / "688041_SH_none.csv").read_bytes(),
                                (output / "688041_SH_qfq.csv").read_bytes())
            self.assertTrue(all("D:\\" not in json.dumps(item) for item in manifest["series"]))
            self.assertNotIn(b"\r\n", (output / "688041_SH_none.csv").read_bytes())
            request_log = (output / "requests.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(request_log), 3)

    def test_resume_does_not_request_existing_series(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            universe = make_universe(root / "universe.json")
            output = root / "out"
            first = run_cli(universe, output, self.base, "--budget-requests", "3", "--budget-bytes", "100000")
            self.assertEqual(first.returncode, 0, first.stderr)
            files = {p.name: p.read_bytes() for p in output.glob("*.csv")}
            PriceHandler.request_count = 0
            second = run_cli(universe, output, self.base, "--budget-requests", "3", "--budget-bytes", "100000")
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(PriceHandler.request_count, 0)
            self.assertEqual({p.name: p.read_bytes() for p in output.glob("*.csv")}, files)
            self.assertEqual(len((output / "requests.jsonl").read_text(encoding="utf-8").splitlines()), 3)

    def test_request_budget_is_persistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            universe = make_universe(root / "universe.json")
            output = root / "out"
            (output).mkdir()
            (output / "requests.jsonl").write_text(
                (json.dumps({"kind": "prices_none", "bytes": 10}) + "\n") * 2,
                encoding="utf-8",
            )
            result = run_cli(universe, output, self.base, "--budget-requests", "2", "--budget-bytes", "100000")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(PriceHandler.request_count, 0)

    def test_invalid_price_is_rejected_without_csv(self):
        PriceHandler.bad_close = True
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            universe = make_universe(root / "universe.json")
            output = root / "out"
            result = run_cli(universe, output, self.base, "--budget-requests", "3", "--budget-bytes", "100000")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((output / "688041_SH_none.csv").exists())
            failures = (output / "failures.jsonl").read_text(encoding="utf-8")
            self.assertIn("positive", failures)

    def test_two_network_failures_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            universe = make_universe(root / "universe.json")
            output = root / "out"
            result = run_cli(universe, output, "http://127.0.0.1:1", "--budget-requests", "5", "--budget-bytes", "100000")
            self.assertNotEqual(result.returncode, 0)
            log = (output / "requests.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(log), 2)

    def test_response_byte_budget_is_persisted(self):
        PriceHandler.omit_length = True
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            universe = make_universe(root / "universe.json")
            output = root / "out"
            first = run_cli(universe, output, self.base, "--budget-requests", "5", "--budget-bytes", "50")
            self.assertNotEqual(first.returncode, 0)
            log = [json.loads(x) for x in (output / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(log), 1)
            self.assertGreater(log[0]["bytes"], 50)
            PriceHandler.request_count = 0
            second = run_cli(universe, output, self.base, "--budget-requests", "5", "--budget-bytes", "50")
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual(PriceHandler.request_count, 0)

    def test_redirect_is_not_followed(self):
        PriceHandler.redirect = True
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            universe = make_universe(root / "universe.json")
            output = root / "out"
            result = run_cli(universe, output, self.base, "--budget-requests", "5", "--budget-bytes", "100000")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(PriceHandler.request_count, 3)
            self.assertIn("HTTP 302", (output / "failures.jsonl").read_text(encoding="utf-8"))

    def test_manifest_range_mismatch_forces_refetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            universe = make_universe(root / "universe.json")
            output = root / "out"
            first = run_cli(universe, output, self.base, "--budget-requests", "3", "--budget-bytes", "100000")
            self.assertEqual(first.returncode, 0, first.stderr)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            manifest["requested_range"]["start"] = "2020-01-01"
            (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            PriceHandler.request_count = 0
            second = run_cli(universe, output, self.base, "--budget-requests", "6", "--budget-bytes", "100000")
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(PriceHandler.request_count, 3)

    def test_bad_ohlc_bounds_and_order_are_rejected(self):
        for flag, marker in (("bad_bounds", "outside low/high"), ("bad_order", "not strictly ascending")):
            with self.subTest(flag=flag):
                setattr(PriceHandler, flag, True)
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    universe = make_universe(root / "universe.json")
                    output = root / "out"
                    result = run_cli(universe, output, self.base, "--budget-requests", "5", "--budget-bytes", "100000")
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn(marker, (output / "failures.jsonl").read_text(encoding="utf-8"))
                    self.assertFalse((output / "688041_SH_none.csv").exists())
                setattr(PriceHandler, flag, False)

    def test_invalid_symbol_is_not_used_as_a_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            universe = root / "universe.json"
            universe.write_text(json.dumps({"securities": [{
                "symbol": "../../escape.SH", "code": "688041", "name": "bad",
                "market": "A", "exchange": "SSE",
            }]}, ensure_ascii=False), encoding="utf-8")
            output = root / "out"
            result = run_cli(universe, output, self.base, "--budget-requests", "3", "--budget-bytes", "100000")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(any("escape" in path.name for path in output.glob("*.csv")))
            self.assertIn("unsafe or invalid symbol", (output / "failures.jsonl").read_text(encoding="utf-8"))

    def test_invalid_parameters_and_path_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            universe = make_universe(root / "universe.json")
            bad = run_cli(universe, root / "out", self.base, "--start", "2021-01-01T00:00:00")
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("exactly YYYY-MM-DD", bad.stderr)
            bad_budget = run_cli(universe, root / "out2", self.base, "--budget-requests", "81")
            self.assertNotEqual(bad_budget.returncode, 0)
            self.assertIn("1..80", bad_budget.stderr)


if __name__ == "__main__":
    unittest.main()
