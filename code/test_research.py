"""Research outputs must respect evidence, time and market-window boundaries."""
import copy
import csv
import unittest

from fastapi.testclient import TestClient

from app import create_app
from graph_store import read_json, write_json
from market import MarketData
from research import ResearchService
import test_core


class ResearchTests(unittest.TestCase):
    setUp = test_core.CoreTests.setUp
    tearDown = test_core.CoreTests.tearDown
    def test_historical_research_explains_missing_and_industry_only_candidates(self):
        aligned = self.store.align_extraction(self.extracted, self.document)
        self.store.ingest({**aligned, "document": self.document})
        result = ResearchService(self.store).detail(self.event["id"], "2025-07-06")
        excluded = {s["symbol"]: s["reason_code"] for s in result["excluded"]}
        self.assertEqual(excluded["b.SH"], "not_yet_disclosed")
        self.assertEqual(excluded["c.SH"], "industry_only")
        self.assertEqual(result["temporal"]["visible_count"], 1)
        self.assertEqual(result["temporal"]["current_count"], 2)

    def test_later_corroborating_source_does_not_leak_into_historical_evidence(self):
        document = {**self.document, "text": "GLM-5由研发公司开发。"}
        extracted = {"entities": [], "relations": [{"source": "model:glm5", "target": "company:a",
                     "type": "DEVELOPED_BY", "evidence": "GLM-5由研发公司开发"}], "events": []}
        aligned = self.store.align_extraction(extracted, document)
        self.store.ingest({**aligned, "document": document})
        current = self.store.related_stocks(self.event["id"])[0]
        historic = self.store.related_stocks(self.event["id"], "2025-07-06")[0]
        self.assertIn("src:update", current["source_ids"])
        self.assertNotIn("src:update", historic["source_ids"])
        self.assertEqual(historic["path"]["edges"][0]["evidence"], "基础事实")
        self.assertNotIn("https://example.com/notice", ResearchService(self.store).brief(self.event["id"], "2025-07-06")["markdown"])

    def test_multiple_roles_are_retained_for_the_same_security(self):
        document = {**self.document, "text": "研发公司提供云平台。云平台提供GLM-5推理服务。"}
        extracted = {"entities": [{"id": "product:cloud", "type": "Product", "label": "云平台"}],
                     "relations": [
                         {"source": "company:a", "target": "product:cloud", "type": "PRODUCES", "evidence": "研发公司提供云平台"},
                         {"source": "product:cloud", "target": "model:glm5", "type": "HOSTS_MODEL", "evidence": "云平台提供GLM-5推理服务"}], "events": []}
        aligned = self.store.align_extraction(extracted, document)
        self.store.ingest({**aligned, "document": document})
        stock = self.store.related_stocks(self.event["id"])[0]
        self.assertEqual(stock["relation_group"], "direct")
        self.assertEqual(set(stock["relation_groups"]), {"direct", "distribution"})
        self.assertEqual(stock["path_count"], 2)

    def test_static_mappings_require_evidence_available_at_the_cutoff(self):
        from graph_store import GraphStore
        original = read_json(self.data / "knowledge_graph.json")
        sources = read_json(self.data / "sources.json")
        for kind, symbol in (("DEVELOPED_BY", "a.SH"), ("LISTED_AS", "a.SH"), ("PRODUCES", "b.SH")):
            for captured in ("2025-07-10T10:00:00+08:00", None):
                with self.subTest(kind=kind, captured=captured):
                    graph = copy.deepcopy(original)
                    edge = next(e for e in graph["edges"] if e["type"] == kind and
                                (kind != "LISTED_AS" or e["source"] == "company:a"))
                    edge["source_ids"] = ["src:late-mapping"]
                    late = {"id": "src:late-mapping", "text": "基础事实"}
                    if captured:
                        late["retrieved_at"] = captured
                    write_json(self.data / "knowledge_graph.json", graph)
                    write_json(self.data / "sources.json", sources + [late])
                    store = GraphStore(self.data, persist=False)
                    aligned = store.align_extraction(self.extracted, self.document)
                    store.ingest({**aligned, "document": self.document})
                    self.assertIn(symbol, {s["symbol"] for s in store.related_stocks(self.event["id"])})
                    self.assertNotIn(symbol, {s["symbol"] for s in store.related_stocks(self.event["id"], "2025-07-08")})
                    if captured:
                        self.assertIn(symbol, {s["symbol"] for s in store.related_stocks(self.event["id"], "2025-07-10")})

    def test_model_cannot_backdate_a_verified_source(self):
        extracted = copy.deepcopy(self.extracted)
        extracted["relations"][0]["disclosed_at"] = "2024-01-01"
        result = self.store.align_extraction(extracted, self.document)
        self.assertEqual(result["relations"][0]["disclosed_at"], "2025-07-07")
        self.assertTrue(result["validation"]["warnings"])

    def test_model_group_cannot_turn_hardware_adaptation_into_cooperation(self):
        extracted = copy.deepcopy(self.extracted)
        extracted["relations"][0].update({"relation_group": "direct", "label": "商业合作"})
        result = self.store.align_extraction(extracted, self.document)
        self.assertEqual(result["relations"][0]["relation_group"], "adaptation")
        self.assertEqual(result["relations"][0]["label"], "技术适配")

    def test_market_cutoff_hides_unobserved_returns(self):
        result = MarketData(self.data).event_window("a.SH", self.event, as_of="2025-07-08")
        self.assertIsNotNone(result["returns"]["1"])
        self.assertIsNone(result["returns"]["3"])
        self.assertIsNone(result["returns"]["5"])
        self.assertTrue(all(p["date"] <= "2025-07-08" for p in result["prices"]))

    def test_excess_returns_use_identical_dates_and_prior_close(self):
        market = MarketData(self.data)
        rows, _ = market.rows("a.SH")
        with (self.data / "market" / "benchmark.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["date", "close", "volume"])
            writer.writeheader()
            writer.writerows({"date": r["date"], "close": 200 + i, "volume": 1} for i, r in enumerate(rows))
        manifest = read_json(self.data / "market" / "manifest.json")
        manifest[0]["benchmark_symbol"] = "bench.SH"
        manifest.append({"symbol": "bench.SH", "name": "合成基准", "file": "market/benchmark.csv"})
        write_json(self.data / "market" / "manifest.json", manifest)
        result = market.event_window("a.SH", self.event)
        self.assertAlmostEqual(result["benchmark_returns"]["1"], 204 / 203 - 1)
        self.assertAlmostEqual(result["excess_returns"]["1"], 105 / 104 - 204 / 203)
        self.assertEqual(result["window_dates"]["3"], "2025-07-09")

    def test_security_listed_after_event_has_no_event_price_window(self):
        manifest = read_json(self.data / "market" / "manifest.json")
        manifest[0]["listing_date"] = "2025-08-01"
        write_json(self.data / "market" / "manifest.json", manifest)
        with self.assertRaisesRegex(ValueError, "尚未上市"):
            MarketData(self.data).event_window("a.SH", self.event)

    def test_product_event_research_uses_its_explicit_model_topic(self):
        extracted = copy.deepcopy(self.extracted)
        extracted["entities"].append({"id": "event:adapt", "type": "Event", "label": "GPU适配公告"})
        extracted["relations"].append({"source": "event:adapt", "target": "new:glm", "type": "CONCERNS",
                                       "evidence": "MTT S5000 完成 GLM-5 的适配"})
        extracted["events"] = [{"id": "event:adapt", "title": "GPU适配公告", "entity_id": "new:gpu", "date": "2025-07-07"}]
        aligned = self.store.align_extraction(extracted, self.document)
        self.store.ingest({**aligned, "document": self.document})
        results = self.store.related_stocks("event:adapt")
        self.assertEqual({s["symbol"] for s in results}, {"a.SH", "b.SH"})
        self.assertEqual(self.store.query_graph("event:adapt")["focus_id"], "model:glm5")

    def test_brief_api_is_grounded_and_validates_calendar_dates(self):
        with TestClient(create_app(self.data, persist=False)) as client:
            result = client.post("/api/research/event:release/brief", json={"as_of": "2025-07-06"})
            self.assertEqual(result.status_code, 200)
            self.assertIn("基础事实", result.json()["markdown"])
            self.assertEqual(result.json()["stats"]["stocks"], 1)
            self.assertEqual(client.get("/api/research/event:release?as_of=2025-02-31").status_code, 422)
