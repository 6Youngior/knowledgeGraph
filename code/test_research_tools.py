"""Tests for the read-only, cutoff-aware ResearchTools surface.

These tests use synthetic fixtures with explicit dates.  They intentionally do
not use the current graph as the expected answer.
"""
from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from graph_store import GraphStore, write_json
from research_tools import ResearchTools, source_available_on


CHINA = timezone(timedelta(hours=8))


class ResearchToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = Path(self.temp.name)
        self.make_fixture()

    def tearDown(self):
        self.temp.cleanup()

    def make_fixture(self):
        sources = [
            {"id": "src:old", "title": "old", "text": "old evidence", "published_at": "2024-01-01",
             "retrieved_at": "2024-01-02T00:00:00+08:00", "publisher": "P"},
            {"id": "src:old-listing", "title": "listing", "text": "listing evidence",
             "published_at": "2024-01-01", "retrieved_at": "2024-01-02T00:00:00+08:00", "publisher": "P"},
            {"id": "src:late-body", "title": "late body", "text": "new body",
             "published_at": "2024-01-01", "retrieved_at": "2026-01-05T00:00:00+08:00", "publisher": "P"},
            {"id": "src:undated", "title": "undated", "text": "undated evidence",
             "retrieved_at": "2024-01-02T00:00:00+08:00", "publisher": "P"},
            {"id": "src:no-capture", "title": "no capture", "text": "no capture body",
             "published_at": "2024-01-01", "publisher": "P"},
            {"id": "src:archive", "title": "archive", "text": "archived evidence",
             "available_at": "2024-01-01", "version_status": "archived_version",
             "retrieved_at": "2026-01-05T00:00:00+08:00", "publisher": "P"},
            {"id": "src:future", "title": "future", "text": "future evidence",
             "published_at": "2026-01-10", "retrieved_at": "2026-01-11T00:00:00+08:00", "publisher": "P"},
        ]
        nodes = [
            {"id": "model:old", "label": "OldModel", "type": "Model", "source_ids": ["src:old"]},
            {"id": "company:old", "label": "OldCo", "type": "Company", "source_ids": ["src:old"]},
            {"id": "product:old", "label": "OldProduct", "type": "Product", "source_ids": ["src:old"]},
            {"id": "stock:old", "label": "OldStock", "type": "Stock", "source_ids": ["src:old-listing"],
             "properties": {"symbol": "OLD.SH", "market": "SH", "currency": "CNY", "listing_date": "2024-02-01"}},
            {"id": "company:late", "label": "LateCo", "type": "Company", "source_ids": ["src:late-body"]},
            {"id": "stock:late", "label": "LateStock", "type": "Stock", "source_ids": ["src:late-body"],
             "properties": {"symbol": "LATE.SH", "listing_date": "2026-02-01"}},
            {"id": "company:archive", "label": "ArchiveCo", "type": "Company", "source_ids": ["src:archive"]},
            {"id": "stock:archive", "label": "ArchiveStock", "type": "Stock", "source_ids": ["src:archive"],
             "properties": {"symbol": "ARCH.SH", "listing_date": "2024-03-01"}},
            {"id": "model:future", "label": "FutureModel", "type": "Model", "source_ids": ["src:future"]},
            {"id": "company:future", "label": "FutureCo", "type": "Company", "source_ids": ["src:future"]},
            {"id": "stock:future", "label": "FutureStock", "type": "Stock", "source_ids": ["src:future"],
             "properties": {"symbol": "FUT.SH", "listing_date": "2026-02-01"}},
        ]
        edges = [
            {"id": "edge:release", "source": "event:old", "target": "model:old", "type": "RELEASED_MODEL",
             "source_ids": ["src:old"], "evidence": "old evidence", "disclosed_at": "2024-01-10"},
            {"id": "edge:develop", "source": "model:old", "target": "company:old", "type": "DEVELOPED_BY",
             "source_ids": ["src:old", "src:future"], "evidence": "old evidence", "disclosed_at": "2024-01-10",
             "evidence_records": [
                 {"source_ids": ["src:old"], "evidence": "old evidence", "disclosed_at": "2024-01-10"},
                 {"source_ids": ["src:old"], "evidence": "future evidence", "disclosed_at": "2026-01-10"},
                 {"source_ids": ["src:old"], "evidence": "undated evidence", "disclosed_at": ""},
             ]},
            {"id": "edge:listing", "source": "company:old", "target": "stock:old", "type": "LISTED_AS",
             "source_ids": ["src:old-listing"], "evidence": "listing evidence", "disclosed_at": "2024-01-01"},
            {"id": "edge:late", "source": "company:late", "target": "stock:late", "type": "LISTED_AS",
             "source_ids": ["src:late-body"], "evidence": "new body", "disclosed_at": "2024-01-10"},
            {"id": "edge:archive", "source": "company:archive", "target": "stock:archive", "type": "LISTED_AS",
             "source_ids": ["src:archive"], "evidence": "archived evidence", "disclosed_at": "2024-01-10"},
            {"id": "edge:undated", "source": "company:old", "target": "product:old", "type": "PRODUCES",
             "source_ids": ["src:undated"], "evidence": "undated evidence", "disclosed_at": ""},
            {"id": "edge:future", "source": "company:future", "target": "stock:future", "type": "LISTED_AS",
             "source_ids": ["src:future"], "evidence": "future evidence", "disclosed_at": "2026-01-10"},
        ]
        events = [
            {"id": "event:old", "title": "Old event", "date": "2024-01-10", "event_at": "2024-01-10",
             "disclosed_at": "2024-01-10", "entity_id": "model:old", "source_ids": ["src:old"]},
            {"id": "event:future", "title": "Future event", "date": "2026-01-10", "event_at": "2026-01-10",
             "disclosed_at": "2026-01-10", "entity_id": "model:future", "source_ids": ["src:future"]},
        ]
        write_json(self.data / "knowledge_graph.json", {"meta": {"title": "fixture"},
                                                        "nodes": nodes, "edges": edges, "events": events})
        write_json(self.data / "sources.json", sources)
        market = self.data / "market"
        market.mkdir()
        with (market / "OLD.SH.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=["date", "close", "volume"])
            writer.writeheader()
            writer.writerows([
                {"date": "2024-01-02", "close": 10, "volume": 100},
                {"date": "2024-01-03", "close": 11, "volume": 100},
                {"date": "2026-01-06", "close": 20, "volume": 100},
            ])
        write_json(market / "manifest.json", [{
            "symbol": "OLD.SH", "name": "OldStock", "market": "SH", "currency": "CNY",
            "file": "market/OLD.SH.csv", "adjusted": "qfq", "retrieved_at": "2026-01-10T00:00:00+08:00",
            "url": "https://example.test/prices",
        }])

    def test_historical_view_filters_sources_events_and_paths(self):
        tools = ResearchTools(self.data, "2024-06-01")
        self.assertIn("src:old", tools.sources)
        self.assertIn("src:archive", tools.sources)
        self.assertNotIn("src:late-body", tools.sources)
        self.assertNotIn("src:future", tools.sources)
        self.assertNotIn("src:no-capture", tools.sources)
        self.assertIn("src:undated", tools.sources)
        self.assertNotIn("event:future", tools.store.events)
        self.assertIn("event:old", tools.store.events)
        self.assertFalse(tools.read_source("src:late-body")["found"])
        self.assertEqual(tools.read_source("src:late-body"), tools.read_source("src:unknown"))
        self.assertTrue(tools.read_source("src:undated")["found"])
        self.assertEqual(tools.read_source("src:undated")["date_status"], "captured_only")
        self.assertTrue(tools.read_source("src:archive")["found"])

    def test_related_stocks_filters_future_evidence_records(self):
        tools = ResearchTools(self.data, "2024-06-01")
        result = tools.related_stocks("event:old")
        self.assertTrue(result["found"])
        self.assertEqual([s["symbol"] for s in result["stocks"]], ["OLD.SH"])
        sources = [citation["id"] for stock in result["stocks"] for path in stock["paths"]
                   for edge in path["edges"] for citation in edge["sources"]]
        self.assertNotIn("src:future", sources)
        self.assertTrue(all(s in tools.sources for s in sources))
        edge = next(edge for edge in result["stocks"][0]["paths"][0]["edges"] if edge["type"] == "DEVELOPED_BY")
        self.assertEqual(edge["evidence"], "old evidence")
        self.assertEqual([s["id"] for s in edge["sources"]], ["src:old"])
        raw_edge = tools.store.edges["edge:develop"]
        self.assertEqual(len(raw_edge["evidence_records"]), 1)
        self.assertEqual(raw_edge["evidence_records"][0]["evidence"], "old evidence")
        # The other quote does not occur in its claimed old source.

    def test_archive_cannot_precede_its_known_publication(self):
        path = self.data / "sources.json"
        sources = json.loads(path.read_text(encoding="utf-8"))
        sources.append({"id": "src:invalid-archive", "title": "Future announcement",
                        "text": "Not available yet", "published_at": "2025-01-01",
                        "available_at": "2024-01-01", "version_status": "archived_version"})
        write_json(path, sources)
        tools = ResearchTools(self.data, "2024-06-01")
        self.assertEqual(tools.read_source("src:invalid-archive"), tools.read_source("src:unknown"))

    def test_future_only_quote_cannot_hide_behind_an_old_source_id(self):
        path = self.data / "knowledge_graph.json"
        graph = json.loads(path.read_text(encoding="utf-8"))
        graph["edges"].append({"id": "edge:unsafe-quote", "source": "product:old", "target": "model:old",
                               "type": "SUPPORTS_MODEL", "source_ids": ["src:old", "src:future"],
                               "evidence": "future evidence", "disclosed_at": "2024-01-10"})
        write_json(path, graph)
        tools = ResearchTools(self.data, "2024-06-01")
        self.assertNotIn("edge:unsafe-quote", tools.store.edges)

    def test_modified_date_without_capture_does_not_prove_an_old_body(self):
        source = {"published_at": "2024-01-01", "modified_at": "2024-02-01", "text": "Current body"}
        self.assertEqual(source_available_on(source, "2026-01-01"), "2026-01-01")

    def test_late_observed_body_is_current_only(self):
        old = ResearchTools(self.data, "2024-06-01")
        current = ResearchTools(self.data, "2026-02-01")
        self.assertNotIn("src:late-body", old.sources)
        self.assertIn("src:late-body", current.sources)
        self.assertEqual(current.sources["src:late-body"]["body_status"], "observed_version")
        self.assertTrue(current.read_source("src:late-body")["found"])
        self.assertFalse(old.read_source("src:late-body")["found"])

    def test_undated_source_is_visible_only_after_capture(self):
        before_capture = ResearchTools(self.data, "2024-01-01")
        current = ResearchTools(self.data, "2024-06-01")
        self.assertNotIn("src:undated", before_capture.sources)
        self.assertFalse(before_capture.read_source("src:undated")["found"])
        self.assertIn("src:undated", current.sources)
        self.assertTrue(current.read_source("src:undated")["found"])
        self.assertEqual(current.read_source("src:undated")["date_status"], "captured_only")
        self.assertIn("edge:undated", current.store.edges)
        self.assertEqual(current.store.edges["edge:undated"]["disclosed_at"], "2024-01-02")

    def test_missing_capture_date_uses_observation_not_publication(self):
        past = ResearchTools(self.data, "2024-06-01")
        current = ResearchTools(self.data)
        self.assertNotIn("src:no-capture", past.sources)
        self.assertFalse(past.read_source("src:no-capture")["found"])
        self.assertIn("src:no-capture", current.sources)
        source = current.sources["src:no-capture"]
        self.assertEqual(source["published_at"], "2024-01-01")
        self.assertEqual(source["body_status"], "observed_current")
        self.assertGreaterEqual(source["available_at"], current.as_of)
        self.assertTrue(current.read_source("src:no-capture")["found"])

    def test_source_available_on_clock_semantics(self):
        self.assertEqual(
            source_available_on({"published_at": "2024-01-01"}, "2025-01-01"),
            "2025-01-01",
        )
        self.assertEqual(
            source_available_on({"retrieved_at": "2024-01-02T00:00:00+08:00"}, "2025-01-01"),
            "2024-01-02",
        )
        self.assertIsNone(source_available_on({}, "2025-01-01"))

    def test_initialization_does_not_modify_data_files(self):
        def digest_tree():
            result = {}
            for path in sorted(self.data.rglob("*")):
                if path.is_file():
                    result[str(path.relative_to(self.data))] = hashlib.sha256(path.read_bytes()).hexdigest()
            return result

        before = digest_tree()
        ResearchTools(self.data, "2024-06-01")
        after = digest_tree()
        self.assertEqual(before, after)

    def test_default_graph_store_load_is_read_only(self):
        def digest_tree():
            return {
                str(path.relative_to(self.data)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(self.data.rglob("*")) if path.is_file()
            }

        before = digest_tree()
        GraphStore(self.data)
        after = digest_tree()
        self.assertEqual(before, after)

    def test_runtime_overlay_read_is_explicit_and_read_only(self):
        base = self.data / "knowledge_graph.json"
        base_digest = hashlib.sha256(base.read_bytes()).hexdigest()
        write_json(self.data / "runtime" / "graph_state.json", {
            "base_digest": base_digest,
            "graph": {
                "nodes": [{"id": "company:runtime", "label": "Runtime", "type": "Company",
                           "source_ids": ["src:runtime"]}],
                "edges": [], "events": [],
            },
            "sources": [{"id": "src:runtime", "title": "runtime", "text": "runtime",
                         "published_at": "2024-01-01", "retrieved_at": "2024-01-02T00:00:00+08:00"}],
        })
        # Old default: persist=False still means "do not read runtime".
        base_only = GraphStore(self.data, persist=False)
        self.assertNotIn("company:runtime", base_only.nodes)
        # Default persist=True keeps the old read behavior.
        default_store = GraphStore(self.data)
        self.assertIn("company:runtime", default_store.nodes)
        # Explicit read is independent of write permission.
        read_only_overlay = GraphStore(self.data, persist=False, read_runtime=True)
        self.assertIn("company:runtime", read_only_overlay.nodes)
        tools = ResearchTools(self.data, "2024-06-01")
        self.assertIn("company:runtime", tools.store.nodes)
        self.assertTrue(tools.read_source("src:runtime")["found"])

    def test_runtime_overlay_with_stale_digest_is_ignored(self):
        write_json(self.data / "runtime" / "graph_state.json", {
            "base_digest": "bogus",
            "graph": {"nodes": [{"id": "node:runtime", "label": "Runtime", "type": "Company"}],
                      "edges": [], "events": []},
            "sources": [],
        })
        tools = ResearchTools(self.data, "2024-06-01")
        self.assertNotIn("node:runtime", tools.store.nodes)
        self.assertFalse(tools.read_source("src:runtime")["found"])

    def test_price_history_respects_snapshot_version(self):
        old = ResearchTools(self.data, "2024-06-01")
        current = ResearchTools(self.data, "2026-02-01")
        old_prices = old.price_history("OLD.SH", 30)
        current_prices = current.price_history("OLD.SH", 30)
        self.assertFalse(old_prices["found"])
        self.assertTrue(current_prices["found"])
        self.assertEqual(current_prices["retrieved_at"], "2026-01-10T00:00:00+08:00")
        self.assertTrue(all(row["date"] <= current.as_of for row in current_prices["prices"]))

    def test_search_entities_does_not_return_future_nodes_or_listing_fields(self):
        early = ResearchTools(self.data, "2024-01-15")
        current = ResearchTools(self.data, "2026-01-20")
        self.assertEqual(early.search_entities("FutureCo")["entities"], [])
        found = current.search_entities("LATE.SH")
        self.assertEqual([item["id"] for item in found["entities"]], ["stock:late"])
        # A listing date after the cutoff is not exposed in an entity payload.
        self.assertNotIn("listing_date", found["entities"][0]["properties"])

    def test_real_current_glm_query_is_structural_and_cutoff_safe(self):
        root = Path(__file__).resolve().parents[1]
        tools = ResearchTools(root / "data")
        overview = tools.overview()
        self.assertIn("event:glm5-release", [event["id"] for event in overview["events"]])
        result = tools.related_stocks("event:glm5-release")
        self.assertTrue(result["found"])
        symbols = {stock["symbol"] for stock in result["stocks"]}
        self.assertIn("02513.HK", symbols)
        if "09988.HK" in symbols:
            captured = [
                citation for stock in result["stocks"] if stock["symbol"] == "09988.HK"
                for path in stock["paths"] for edge in path["edges"]
                for citation in edge["sources"] if citation["id"] == "src:aliyun-glm5"
            ]
            self.assertTrue(captured)
            self.assertEqual(captured[0]["published_at"], "")
            self.assertEqual(captured[0]["date_status"], "captured_only")
        if result["stocks"]:
            for stock in result["stocks"]:
                for path in stock["paths"]:
                    for edge in path["edges"]:
                        for citation in edge["sources"]:
                            self.assertIn(citation["id"], tools.sources)
        # This is a real-data smoke test; it does not use the current graph's
        # answer as an externally verified ground truth.
        self.assertIn("GLM-5", [item["label"] for item in tools.search_entities("GLM-5")["entities"]])

    def test_invalid_and_future_cutoffs_are_rejected(self):
        with self.assertRaises(ValueError):
            ResearchTools(self.data, "not-a-date")
        future = (datetime.now(CHINA).date() + timedelta(days=2)).isoformat()
        with self.assertRaises(ValueError):
            ResearchTools(self.data, future)


if __name__ == "__main__":
    unittest.main(verbosity=2)
