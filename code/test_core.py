"""Synthetic fixtures test temporal, semantic, and ingestion boundaries.

These are correctness checks, not measured financial or extraction performance.
Run: python -m unittest discover -s code -p 'test_*.py' -v
"""
import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import create_app
from graph_store import GraphStore, write_json
from market import MarketData
from extraction import ExtractionService
from research_tools import ResearchTools, CHINA


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = Path(self.temp.name)
        nodes = [
            {"id": "model:glm5", "label": "GLM-5", "type": "Model", "aliases": ["GLM5"]},
            {"id": "company:a", "label": "研发公司", "type": "Company"},
            {"id": "company:b", "label": "芯片公司", "type": "Company"},
            {"id": "company:c", "label": "同行公司", "type": "Company"},
            {"id": "product:gpu", "label": "MTT S5000", "type": "Product"},
            {"id": "industry:ai", "label": "人工智能", "type": "Industry"},
        ]
        for name in ("a", "b", "c"):
            nodes.append({"id": f"stock:{name}", "label": f"证券{name}", "type": "Stock",
                          "properties": {"symbol": f"{name}.SH", "market": "SH", "currency": "CNY"}})
        edges = []
        def edge(source, target, kind):
            edges.append({"id": f"edge:{len(edges)}", "source": source, "target": target, "type": kind,
                          "source_ids": ["src:base"], "disclosed_at": "2025-01-01", "evidence": "基础事实"})
        edge("model:glm5", "company:a", "DEVELOPED_BY")
        edge("company:b", "product:gpu", "PRODUCES")
        for name in ("a", "b", "c"):
            edge(f"company:{name}", f"stock:{name}", "LISTED_AS")
            edge(f"company:{name}", "industry:ai", "BELONGS_TO")
        self.event = {"id": "event:release", "title": "模型发布", "date": "2025-07-04", "event_at": "2025-07-04",
                      "entity_id": "model:glm5", "source_ids": ["src:base"], "type": "MODEL_RELEASE"}
        write_json(self.data / "knowledge_graph.json", {"nodes": nodes, "edges": edges, "events": [self.event]})
        self.document = {"id": "src:update", "title": "适配公告", "url": "https://example.com/notice",
                         "text": "MTT S5000 完成 GLM-5 的适配。", "published_at": "2025-07-07"}
        write_json(self.data / "sources.json", [{"id": "src:base", "title": "基础资料", "text": "基础事实", "published_at": "2025-01-01"}, self.document])
        self.extracted = {
            "entities": [{"id": "new:glm", "label": "GLM5", "type": "Model"},
                         {"id": "new:gpu", "label": "MTT S5000", "type": "Product"}],
            "relations": [{"source": "new:gpu", "target": "new:glm", "type": "SUPPORTS_MODEL",
                           "evidence": "MTT S5000 完成 GLM-5 的适配", "source_ids": ["src:update"],
                           "disclosed_at": "2025-07-07", "relation_group": "adaptation"}], "events": []}
        write_json(self.data / "extraction_samples.json", [{"id": "sample:gpu", "document_id": "src:update",
                    "title": self.document["title"], "text": self.document["text"], "url": self.document["url"],
                    "model": "synthetic fixture", "extraction": self.extracted}])
        market_dir = self.data / "market"
        market_dir.mkdir()
        dates = ["2025-07-01", "2025-07-02", "2025-07-03", "2025-07-04", "2025-07-07",
                 "2025-07-08", "2025-07-09", "2025-07-10", "2025-07-11"]
        with (market_dir / "a.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=["date", "close", "volume"])
            writer.writeheader()
            writer.writerows({"date": day, "close": 101 + i, "volume": 1000} for i, day in enumerate(dates))
        write_json(market_dir / "manifest.json", [{"symbol": "a.SH", "name": "合成测试证券", "market": "SH",
                    "currency": "CNY", "file": "market/a.csv", "provider": "unit-test-fixture", "adjusted": "none"}])
        self.store = GraphStore(self.data, persist=False)

    def tearDown(self):
        self.temp.cleanup()

    def test_shared_industry_does_not_imply_stock_association(self):
        results = self.store.related_stocks(self.event["id"])
        self.assertEqual([s["symbol"] for s in results], ["a.SH"])

    def test_alias_alignment_and_incremental_path_are_idempotent(self):
        result = self.store.align_extraction(self.extracted, self.document)
        self.assertEqual(result["preview"]["new_nodes"], 0)
        self.assertEqual(result["preview"]["new_edges"], 1)
        changes = self.store.ingest({**result, "document": self.document})
        self.assertEqual(changes["added_edges"], 1)
        results = self.store.related_stocks(self.event["id"])
        self.assertEqual([s["symbol"] for s in results], ["a.SH", "b.SH"])
        adaptation = results[1]
        self.assertEqual(adaptation["path"]["edges"][0]["source"], "product:gpu")
        again = self.store.ingest({**result, "document": self.document})
        self.assertEqual(sum(again[k] for k in ("added_nodes", "added_edges", "updated_nodes", "updated_edges")), 0)

    def test_disclosure_filter_excludes_later_association(self):
        result = self.store.align_extraction(self.extracted, self.document)
        self.store.ingest({**result, "document": self.document})
        self.assertEqual(len(self.store.related_stocks(self.event["id"], "2025-07-06")), 1)
        self.assertEqual(len(self.store.related_stocks(self.event["id"], "2025-07-07")), 2)

    def test_undated_fact_is_excluded_from_historical_cutoff(self):
        result = self.store.align_extraction(self.extracted, self.document)
        result["relations"][0]["disclosed_at"] = ""
        self.store.ingest({**result, "document": self.document})
        self.assertEqual(len(self.store.related_stocks(self.event["id"])), 2)
        self.assertEqual(len(self.store.related_stocks(self.event["id"], "2026-11-06")), 1)

    def test_cloud_service_path_retains_distribution_semantics(self):
        document = {**self.document, "text": "芯片公司提供云平台。云平台提供GLM-5推理服务。"}
        extracted = {"entities": [{"id": "product:cloud", "type": "Product", "label": "云平台"}],
                     "relations": [
                         {"source": "company:b", "target": "product:cloud", "type": "PRODUCES", "evidence": "芯片公司提供云平台"},
                         {"source": "product:cloud", "target": "model:glm5", "type": "HOSTS_MODEL", "evidence": "云平台提供GLM-5推理服务"}],
                     "events": []}
        aligned = self.store.align_extraction(extracted, document)
        self.store.ingest({**aligned, "document": document})
        stock = next(s for s in self.store.related_stocks(self.event["id"]) if s["symbol"] == "b.SH")
        self.assertEqual(stock["relation_group"], "distribution")
        self.assertEqual(stock["path"]["edges"][0]["type"], "HOSTS_MODEL")
        historical = self.store.event_detail(self.event["id"], "2025-07-06")
        self.assertEqual([s["symbol"] for s in historical["stocks"]], ["a.SH"])

    def test_unsupported_evidence_is_rejected(self):
        invalid = copy.deepcopy(self.extracted)
        invalid["relations"][0]["evidence"] = "两家公司宣布商业合作"
        with self.assertRaisesRegex(ValueError, "无法在来源中定位"):
            self.store.align_extraction(invalid, self.document)

    def test_schema_rejects_company_as_product(self):
        invalid = copy.deepcopy(self.extracted)
        invalid["relations"][0]["source"] = "company:b"
        with self.assertRaisesRegex(ValueError, "端点类型"):
            self.store.align_extraction(invalid, self.document)

    def test_evidence_does_not_erase_decimal_points(self):
        document = {**self.document, "text": "MTT S5000 完成 GLM-5 的适配，性能提升 1.5 倍。"}
        extraction = copy.deepcopy(self.extracted)
        extraction["relations"][0]["evidence"] = "MTT S5000 完成 GLM-5 的适配，性能提升 15 倍。"
        with self.assertRaisesRegex(ValueError, "无法在来源中定位"):
            self.store.align_extraction(extraction, document)

    def test_uploaded_text_is_observed_now_without_inventing_publication(self):
        self.store.persist = True
        service = ExtractionService(self.store, self.data)
        extraction = copy.deepcopy(self.extracted)
        for edge in extraction["relations"]:
            edge.pop("source_ids", None)
        service._generate = lambda _prompt: (json.dumps(extraction), "synthetic-test")
        before = datetime.now(timezone.utc)
        result = service.extract(text=self.document["text"], title="Uploaded evidence", mode="live")
        document = result["document"]
        captured = datetime.fromisoformat(document["retrieved_at"])
        self.assertLessEqual(before, captured)
        self.assertLessEqual(captured, datetime.now(timezone.utc))
        self.assertEqual(document["published_at"], "")
        service.ingest(result["extraction_id"])
        self.assertTrue(ResearchTools(self.data).read_source(document["id"])["found"])
        prior_day = (captured.astimezone(CHINA).date() - timedelta(days=1)).isoformat()
        self.assertFalse(ResearchTools(self.data, prior_day).read_source(document["id"])["found"])

    def test_date_only_anchor_skips_weekend_and_uses_prior_close(self):
        window = MarketData(self.data).event_window("a.SH", self.event)
        self.assertEqual(window["anchor_date"], "2025-07-07")
        self.assertAlmostEqual(window["returns"]["1"], 105 / 104 - 1)
        self.assertAlmostEqual(window["returns"]["3"], 107 / 104 - 1)
        self.assertAlmostEqual(window["returns"]["5"], 109 / 104 - 1)
        self.assertEqual(next(p["normalized"] for p in window["prices"] if p["relative_day"] == -1), 100)

    def test_verified_before_open_can_anchor_same_day(self):
        window = MarketData(self.data).event_window("a.SH", {**self.event, "known_before_open": True})
        self.assertEqual(window["anchor_date"], "2025-07-04")
        self.assertAlmostEqual(window["returns"]["1"], 104 / 103 - 1)

    def test_disclosure_later_than_occurrence_drives_anchor(self):
        window = MarketData(self.data).event_window("a.SH", {**self.event, "disclosed_at": "2025-07-07"})
        self.assertEqual(window["anchor_date"], "2025-07-08")

    def test_after_close_timestamp_advances_session(self):
        window = MarketData(self.data).event_window("a.SH", {**self.event, "market_known_at": "2025-07-04T16:30:00+08:00"})
        self.assertEqual(window["anchor_date"], "2025-07-07")

    def test_insufficient_future_window_returns_null(self):
        event = {**self.event, "date": "2025-07-09", "event_at": "2025-07-09"}
        window = MarketData(self.data).event_window("a.SH", event)
        self.assertIsNotNone(window["returns"]["1"])
        self.assertIsNone(window["returns"]["3"])
        self.assertIsNone(window["returns"]["5"])

    def test_replay_api_roundtrip_and_json_errors(self):
        with TestClient(create_app(self.data, persist=False)) as client:
            result = client.post("/api/extract", json={"sample_id": "sample:gpu", "mode": "replay"})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()["mode"], "replay")
            self.assertTrue(result.json()["validation"]["valid"])
            ingested = client.post("/api/ingest", json={"extraction_id": result.json()["extraction_id"]})
            self.assertEqual(ingested.json()["added_edges"], 1)
            missing = client.get("/api/events/missing")
            self.assertEqual(missing.status_code, 404)
            self.assertIn("detail", missing.json())
            no_replay = client.post("/api/extract", json={"mode": "replay", "text": "custom"})
            self.assertEqual(no_replay.status_code, 422)


if __name__ == "__main__":
    unittest.main(verbosity=2)
