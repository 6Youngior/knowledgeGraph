"""Financial research boundaries and the public API, without model calls."""
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import create_app
from financial_tools import FinancialResearch

ROOT = Path(__file__).resolve().parents[1]


class FinancialResearchTests(unittest.TestCase):
    def test_past_view_hides_the_financial_catalog_and_sources(self):
        research = FinancialResearch(ROOT / "data" / "finance", "2026-11-10")
        self.assertEqual(research.overview(), {
            "as_of": "2026-11-10", "companies": [], "financial_records": 0,
        })
        self.assertEqual(research.company_financials("09988.HK"), {
            "as_of": "2026-11-10", "found": False, "reports": [],
        })

    def test_hk_reporting_currency_is_not_the_quote_currency(self):
        result = FinancialResearch(ROOT / "data" / "finance", "2026-11-11").company_financials("09988.HK", 1)
        self.assertTrue(result["found"])
        self.assertEqual(result["reports"][0]["currency"], "CNY")
        self.assertEqual(result["reports"][0]["report_period"], "2026-03-31")
        self.assertIsNone(result["reports"][0]["notice_date"])
        self.assertTrue(result["company_disclosures"])
        self.assertEqual(len(result["reports"]), 1)
        self.assertGreater(result["coverage"]["available_reports"], 1)

    def test_current_quotes_have_their_actual_coverage_and_units(self):
        research = FinancialResearch(ROOT / "data" / "finance", "2026-11-11")
        result = research.price_history("00700.HK", 3)
        self.assertTrue(result["found"])
        self.assertEqual(result["currency"], "HKD")
        self.assertEqual(result["volume_unit"], "shares")
        self.assertEqual(len(result["prices"]), 3)
        self.assertGreaterEqual(result["last_available_date"], "2026-11-10")
        self.assertEqual(FinancialResearch(ROOT / "data" / "finance", "2026-11-10").price_history("00700.HK"),
                         {"as_of": "2026-11-10", "found": False, "prices": []})

    def test_api_uses_the_same_time_rules_and_rejects_invalid_queries(self):
        client = TestClient(create_app(persist=False))
        self.assertEqual(client.get("/api/finance?as_of=2026-11-10").json()["companies"], [])
        result = client.get("/api/finance/688041.SH?as_of=2026-11-11&periods=1")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["reports"][0]["period_basis"], "cumulative_ytd_9m")
        self.assertEqual(client.get("/api/finance?as_of=2099-01-01").status_code, 422)
        self.assertEqual(client.get("/api/finance/688041.SH?periods=100").status_code, 422)
