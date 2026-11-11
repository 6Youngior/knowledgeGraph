"""Tests for the public finance package and the explicit-import CLI."""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import finance
import import_finance

ROOT = Path(__file__).resolve().parents[1]
FINANCE = ROOT / "data" / "finance"
SYMBOLS = {"688041.SH", "000977.SZ", "603019.SH", "09988.HK", "00700.HK"}
SNAPSHOT = "2026-11-11"


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def make_fixture(root: Path, *, revenue: str = "100.0", report_date: str = "2026-09-30") -> Path:
    """Build a one-company standardized input; no ignored task directory needed."""
    source = root / "input"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.mkdir()
    source_registry = {
        "generated_at": "2026-11-11T08:39:59+00:00",
        "securities": [{
            "symbol": "688041.SH", "name": "测试公司", "market": "A",
            "role": "测试角色", "fiscal_year_end_md": "12-31",
        }],
        "sources": [{"id": "cninfo", "url": "http://www.cninfo.com.cn/"}],
    }
    (source / "source_registry.json").write_text(json.dumps(source_registry, ensure_ascii=False), encoding="utf-8")
    (source / "manifest.json").write_text(json.dumps({"generated_at": "2026-11-11T08:39:59+00:00"}), encoding="utf-8")
    write_csv(
        source / "financial_indicators.csv",
        ["security", "security_name", "report_date", "report_type", "notice_date", "currency_iso",
         "revenue", "net_profit", "eps", "roe", "gross_margin", "retrieved_at"],
        [{"security": "688041.SH", "security_name": "测试公司", "report_date": report_date,
          "report_type": "三季报", "notice_date": "2026-10-20", "currency_iso": "CNY",
          "revenue": revenue, "net_profit": "10.0", "eps": "0.5", "roe": "3.2",
          "gross_margin": "40.0", "retrieved_at": "2026-11-11T08:39:59+00:00"}],
    )
    write_csv(
        source / "business_mix.csv",
        ["security", "股票代码", "报告日期", "分类类型", "主营构成", "主营收入", "收入比例",
         "主营成本", "成本比例", "主营利润", "利润比例", "毛利率"],
        [{"security": "688041.SH", "股票代码": "688041", "报告日期": "2026-06-30",
          "分类类型": "按产品分类", "主营构成": "测试产品", "主营收入": "80",
          "收入比例": "0.8", "主营成本": "40", "成本比例": "0.5",
          "主营利润": "40", "利润比例": "0.5", "毛利率": "0.5"}],
    )
    write_csv(
        source / "prices.csv",
        ["security", "market", "date", "open", "high", "low", "close", "volume", "amount",
         "currency", "adjustment", "volume_unit", "amount_unit", "price_unit"],
        [{"security": "688041.SH", "market": "A", "date": "2026-11-10", "open": "10",
          "high": "11", "low": "9", "close": "10.5", "volume": "100", "amount": "1050",
          "currency": "CNY", "adjustment": "qfq", "volume_unit": "lot_100_shares",
          "amount_unit": "CNY", "price_unit": "CNY/share"}],
    )
    write_csv(
        source / "index_prices.csv",
        ["index_code", "date", "open", "close", "high", "low", "volume", "amount",
         "currency", "adjustment", "volume_unit", "amount_unit", "price_unit"],
        [{"index_code": "sh000300", "date": "2026-11-10", "open": "4000", "close": "4010",
          "high": "4020", "low": "3990", "volume": "1000", "amount": "2000",
          "currency": "CNY", "adjustment": "none", "volume_unit": "index_volume_native",
          "amount_unit": "CNY", "price_unit": "index_points"}],
    )
    pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
    pdf_path = source / "annual.pdf"
    pdf_path.write_bytes(pdf)
    disclosure = {
        "security": "688041.SH", "company": "测试公司", "document_type": "annual_report",
        "title": "2025年年度报告", "published_at": "2026-04-08",
        "published_at_basis": "fixture", "retrieved_at": "2026-11-11T08:39:59+00:00",
        "source_id": "cninfo", "source_page": "", "detail_url": "http://example.test/detail",
        "source_url": "http://example.test/annual.pdf", "local_file": "annual.pdf",
        "sha256": hashlib.sha256(pdf).hexdigest(), "bytes": len(pdf), "pages": 1,
    }
    (source / "disclosures.jsonl").write_text(json.dumps(disclosure, ensure_ascii=False) + "\n", encoding="utf-8")
    return source


def run_import(source: Path, output: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ROOT / "code" / "import_finance.py"),
         "--input", str(source), "--output", str(output)],
        cwd=ROOT, text=True, capture_output=True, timeout=180,
    )


class FinancePackageTests(unittest.TestCase):
    def test_public_package_counts_and_companies(self):
        rows = finance.list_companies()
        self.assertEqual({row["symbol"] for row in rows}, SYMBOLS)
        self.assertEqual(len(rows), 5)
        manifest = json.loads((FINANCE / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["counts"]["financial_records"], 206)
        self.assertEqual(manifest["counts"]["business_mix_records"], 483)
        self.assertEqual(manifest["counts"]["price_rows"], 2243)
        self.assertEqual(manifest["counts"]["index_rows"], 449)
        self.assertEqual(manifest["counts"]["disclosures"], 5)

    def test_package_has_no_local_paths_or_pdfs(self):
        forbidden = ("subagent", ".venv", "D:\\", "C:\\", "docs/")
        for path in FINANCE.iterdir():
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="ignore")
                for token in forbidden:
                    self.assertNotIn(token, text, f"{token} in {path.name}")
        self.assertEqual(list(FINANCE.glob("*.pdf")), [])
        manifest = json.loads((FINANCE / "manifest.json").read_text(encoding="utf-8"))
        for name, meta in manifest["files"].items():
            body = (FINANCE / name).read_bytes()
            self.assertEqual(len(body), meta["bytes"])
            self.assertEqual(hashlib.sha256(body).hexdigest(), meta["sha256"])

    def test_as_of_and_period_basis(self):
        for symbol in SYMBOLS:
            self.assertEqual(finance.company_financials(symbol, "2026-11-10"), [])
        rows = finance.company_financials("688041.SH", "2026-11-11", limit=4)
        self.assertEqual([row["report_period"] for row in rows],
                         ["2026-09-30", "2026-06-30", "2026-03-31", "2025-12-31"])
        self.assertEqual([row["period_basis"] for row in rows],
                         ["cumulative_ytd_9m", "cumulative_ytd_h1", "cumulative_ytd_q1", "annual"])
        self.assertEqual(rows[0]["fiscal_year_end"], "2026-12-31")
        self.assertNotEqual(rows[0]["fiscal_year_end"], rows[0]["report_period"])
        self.assertEqual(rows[0]["gross_margin_unit"], "percent")
        self.assertIn("PARENTNETPROFIT", rows[0]["profit_definition"])
        self.assertEqual(finance.company_financials("688041.SH", "2026-11-11", limit=0), [])
        self.assertEqual(finance.company_financials("688041.SH", "2026-11-11", limit=1)[0]["report_period"], "2026-09-30")
        with self.assertRaises(ValueError):
            finance.company_financials("688041.SH", "2026-11-11T00:00:00", limit=1)
        with self.assertRaises(ValueError):
            finance.company_financials("688041.SH", "2026-11-11", limit=-1)

    def test_hk_definitions_and_missing_dates(self):
        rows = finance.company_financials("09988.HK", "2026-11-11", limit=2)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["notice_date"] is None for row in rows))
        self.assertTrue(all(row["period_basis"] == "annual" for row in rows))
        self.assertEqual(rows[0]["fiscal_year_end"], "2026-03-31")
        self.assertIn("HOLDER_PROFIT", rows[0]["profit_definition"])
        self.assertEqual(finance.company_financials("09988", "2026-11-11"), [])
        self.assertEqual(finance.company_financials("09988.hk", "2026-11-11", limit=1)[0]["symbol"], "09988.HK")

    def test_definitions_are_chinese_with_raw_fields(self):
        definitions = finance.metric_definitions()
        self.assertIn("营业收入", definitions["metrics"]["revenue"]["label"])
        self.assertEqual(definitions["metrics"]["revenue"]["raw_fields"]["A"], "TOTALOPERATEREVE")
        self.assertEqual(definitions["metrics"]["net_profit"]["raw_fields"]["HK"], "HOLDER_PROFIT")
        self.assertEqual(definitions["gross_margin_units"]["business_mix"], "fraction_0_1")
        rows = finance.company_financials("00700.HK", "2026-11-11", limit=1)
        self.assertEqual(rows[0]["metric_definitions"]["gross_margin"]["unit"], "百分比")

    def test_business_mix_gross_margin_is_a_ratio(self):
        rows = [json.loads(line) for line in (FINANCE / "business_mix.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertGreater(len(rows), 0)
        self.assertTrue(all("gross_margin_ratio" in row for row in rows))
        self.assertTrue(all("gross_margin" not in row for row in rows))
        self.assertTrue(all(row["gross_margin_ratio_unit"] == "fraction" for row in rows))

    def test_import_minimal_fixture_and_determinism(self):
        with tempfile.TemporaryDirectory() as root:
            source = make_fixture(Path(root))
            first, second = Path(root) / "out1", Path(root) / "out2"
            one = run_import(source, first)
            two = run_import(source, second)
            self.assertEqual(one.returncode, 0, one.stderr)
            self.assertEqual(two.returncode, 0, two.stderr)
            for name in sorted(p.name for p in first.iterdir() if p.is_file()):
                self.assertEqual((first / name).read_bytes(), (second / name).read_bytes(), name)
            data = json.loads((first / "financials.jsonl").read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(data["fiscal_year_end"], "2026-12-31")
            self.assertEqual(data["period_basis"], "cumulative_ytd_9m")
            self.assertEqual(data["gross_margin_unit"], "percent")
            self.assertEqual(data["available_at"], SNAPSHOT)
            store = finance.FinanceStore(first)
            self.assertEqual(store.company_financials("688041.SH", "2026-11-10"), [])
            self.assertEqual(len(store.company_financials("688041.SH", "2026-11-11", limit=1)), 1)
            business = json.loads((first / "business_mix.jsonl").read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(business["gross_margin_ratio"], 0.5)
            self.assertNotIn("gross_margin", business)
            self.assertNotIn("NaN", (first / "financials.jsonl").read_text(encoding="utf-8"))
            self.assertNotIn("Infinity", (first / "financials.jsonl").read_text(encoding="utf-8"))

    def test_import_rejects_nonfinite_and_suffixed_dates(self):
        with tempfile.TemporaryDirectory() as root:
            bad_number = make_fixture(Path(root) / "number", revenue="inf")
            result = run_import(bad_number, Path(root) / "out-number")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("non-finite", result.stderr)

            bad_date = make_fixture(Path(root) / "date", report_date="2026-09-30T00:00:00")
            result = run_import(bad_date, Path(root) / "out-date")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exactly YYYY-MM-DD", result.stderr)

    def test_hk_source_resolution_does_not_default_to_tencent(self):
        registry = {"sources": [{"id": "company_ir_acme", "url": "https://acme.example/ir"}]}
        resolved = import_finance.source_urls(
            {"source_page": "raw/ir/acme.html"}, "00999.HK", registry
        )
        self.assertEqual(resolved["source_id"], "company_ir_acme")
        self.assertEqual(resolved["source_page_url"], "https://acme.example/ir")
        unresolved = import_finance.source_urls({}, "00999.HK", {"sources": []})
        self.assertEqual(unresolved["source_id"], "company_ir_unresolved")
        self.assertNotIn("tencent", unresolved["source_page_url"].lower())

    def test_import_requires_explicit_input(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "code" / "import_finance.py")],
            cwd=ROOT, text=True, capture_output=True, timeout=60,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--input", result.stderr)

    def test_snapshot_day_uses_china_time(self):
        day, _ = import_finance.snapshot_from_manifest({"generated_at": "2026-11-11T18:00:00+00:00"})
        self.assertEqual(day, "2026-11-12")
        with self.assertRaisesRegex(ValueError, "timezone"):
            import_finance.snapshot_from_manifest({"generated_at": "2026-11-11T18:00:00"})


if __name__ == "__main__":
    unittest.main()
