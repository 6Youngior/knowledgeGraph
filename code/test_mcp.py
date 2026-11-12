"""Real SDK stdio calls: protocol, temporary refresh, schemas and cutoff.

The synthetic fixture has exact expected counts.  The real seed graph is used
only for structural/source checks, never as a fixed answer key.
"""
import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path

from graph_store import GraphStore, write_json

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

ROOT = Path(__file__).resolve().parents[1]


def tool_value(result):
    if result.structuredContent is not None:
        return result.structuredContent
    return json.loads(next(c.text for c in result.content if c.type == "text"))


def make_synthetic_data():
    """Create a small base graph whose event has no stock path yet."""
    temp = tempfile.TemporaryDirectory()
    data = Path(temp.name)
    base_source = {
        "id": "src:base", "title": "base", "publisher": "fixture",
        "text": "Base event source", "published_at": "2024-01-01",
        "retrieved_at": "2024-01-02T00:00:00+08:00",
    }
    graph = {
        "meta": {"title": "MCP fixture"},
        "nodes": [
            {"id": "model:base", "label": "BaseModel", "type": "Model", "source_ids": ["src:base"]},
        ],
        "edges": [],
        "events": [
            {"id": "event:base", "title": "Base event", "date": "2024-01-10",
             "event_at": "2024-01-10", "disclosed_at": "2024-01-10",
             "entity_id": "model:base", "source_ids": ["src:base"]},
        ],
    }
    write_json(data / "knowledge_graph.json", graph)
    write_json(data / "sources.json", [base_source])
    return temp, data


def new_extraction():
    text = "NewProduct supports BaseModel. NewCo produces NewProduct. NewCo is listed as NEW.SH."
    document = {
        "id": "src:new", "title": "new", "publisher": "fixture", "text": text,
        "published_at": "", "retrieved_at": "2024-02-02T00:00:00+08:00",
        "url": "https://fixture.test/new",
    }
    extraction = {
        "entities": [
            {"id": "product:new", "label": "NewProduct", "type": "Product", "source_ids": ["src:new"]},
            {"id": "company:new", "label": "NewCo", "type": "Company", "source_ids": ["src:new"]},
            {"id": "stock:new", "label": "NewStock", "type": "Stock", "source_ids": ["src:new"],
             "properties": {"symbol": "NEW.SH", "market": "SH", "currency": "CNY",
                            "listing_date": "2024-02-01"}},
        ],
        "relations": [
            {"source": "product:new", "target": "model:base", "type": "SUPPORTS_MODEL",
             "evidence": "NewProduct supports BaseModel", "source_ids": ["src:new"],
             "disclosed_at": "2024-02-02", "relation_group": "adaptation"},
            {"source": "company:new", "target": "product:new", "type": "PRODUCES",
             "evidence": "NewCo produces NewProduct", "source_ids": ["src:new"],
             "disclosed_at": "2024-02-02", "relation_group": "direct"},
            {"source": "company:new", "target": "stock:new", "type": "LISTED_AS",
             "evidence": "NewCo is listed as NEW.SH", "source_ids": ["src:new"],
             "disclosed_at": "2024-02-02", "relation_group": "direct"},
        ],
        "events": [],
    }
    return document, extraction


@unittest.skipUnless(MCP_AVAILABLE, "install code/requirements-agent.txt for MCP integration checks")
class McpIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, as_of, callback, data_dir=None):
        env = {"PYTHONUTF8": "1", "FINGRAPH_AS_OF": as_of}
        if data_dir is not None:
            env["FINGRAPH_DATA_DIR"] = str(data_dir)
        params = StdioServerParameters(
            command=sys.executable, args=[str(ROOT / "code" / "mcp_server.py")],
            cwd=str(ROOT), env=env,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await callback(session)

    async def test_current_seed_graph_structure_and_sources(self):
        async def check(session):
            tools = await session.list_tools()
            self.assertEqual({t.name for t in tools.tools}, {
                "overview", "search_entities", "related_stocks", "read_source",
                "price_history", "company_financials", "entity_relations",
            })
            overview = tool_value(await session.call_tool("overview", {}))
            self.assertIn("knowledge", overview)
            self.assertIn("financial_data", overview)
            related = await session.call_tool("related_stocks", {"event_id": "event:glm5-release"})
            self.assertFalse(related.isError)
            value = tool_value(related)
            self.assertTrue(value["found"])
            # Formal seed graph: structural/source checks only.  Do not encode
            # the current two GLM stocks as a permanent answer key.
            for stock in value["stocks"]:
                self.assertTrue(stock["paths"])
                for path in stock["paths"]:
                    for edge in path["edges"]:
                        self.assertTrue(edge["sources"])
            self.assertTrue(tool_value(await session.call_tool("search_entities", {"query": "GLM-5"}))["entities"])
            relations = tool_value(await session.call_tool("entity_relations", {"entity_id": "model:glm5"}))
            self.assertTrue(relations["found"])
            self.assertTrue(relations["relations"])
        await self.exercise("2026-11-11", check)

    async def test_past_cutoff_is_applied_to_all_current_snapshots(self):
        async def check(session):
            overview = tool_value(await session.call_tool("overview", {}))
            self.assertEqual(overview["as_of"], "2026-02-12")
            result = tool_value(await session.call_tool("related_stocks", {"event_id": "event:glm5-release"}))
            self.assertFalse(result["found"])
            self.assertEqual(result["stocks"], [])
            result = tool_value(await session.call_tool("company_financials", {"symbol": "09988.HK"}))
            self.assertEqual(result, {"as_of": "2026-02-12", "found": False, "reports": []})
        await self.exercise("2026-02-12", check)

    async def test_synthetic_ingest_refreshes_same_mcp_process(self):
        temp, data = make_synthetic_data()
        self.addCleanup(temp.cleanup)
        document, extraction = new_extraction()
        store = GraphStore(data, persist=True)
        aligned = store.align_extraction(extraction, document)
        self.assertTrue(aligned["validation"]["valid"])

        async def check(session):
            initial = tool_value(await session.call_tool("related_stocks", {"event_id": "event:base"}))
            self.assertTrue(initial["found"])
            self.assertEqual(initial["stocks"], [])

            first = store.ingest({**aligned, "document": document})
            self.assertEqual(first["added_nodes"], 3)
            self.assertEqual(first["added_edges"], 3)
            await asyncio.sleep(0.03)
            refreshed = tool_value(await session.call_tool("related_stocks", {"event_id": "event:base"}))
            self.assertEqual([stock["symbol"] for stock in refreshed["stocks"]], ["NEW.SH"])
            source = tool_value(await session.call_tool("read_source", {"source_id": "src:new"}))
            self.assertTrue(source["found"])
            self.assertEqual(source["published_at"], "")
            self.assertEqual(source["date_status"], "captured_only")
            self.assertEqual(source["available_at"], "2024-02-02")

            second = store.ingest({**aligned, "document": document})
            self.assertEqual(second["added_nodes"], 0)
            self.assertEqual(second["added_edges"], 0)
            again = tool_value(await session.call_tool("related_stocks", {"event_id": "event:base"}))
            self.assertEqual([stock["symbol"] for stock in again["stocks"]], ["NEW.SH"])

        await self.exercise("2024-06-01", check, data)

    async def test_synthetic_future_relation_stays_hidden(self):
        temp, data = make_synthetic_data()
        self.addCleanup(temp.cleanup)
        document, extraction = new_extraction()
        store = GraphStore(data, persist=True)
        aligned = store.align_extraction(extraction, document)

        async def check(session):
            initial = tool_value(await session.call_tool("related_stocks", {"event_id": "event:base"}))
            self.assertEqual(initial["stocks"], [])
            store.ingest({**aligned, "document": document})
            await asyncio.sleep(0.03)
            after = tool_value(await session.call_tool("related_stocks", {"event_id": "event:base"}))
            self.assertEqual(after["stocks"], [])
            source = tool_value(await session.call_tool("read_source", {"source_id": "src:new"}))
            self.assertFalse(source["found"])
        await self.exercise("2024-01-15", check, data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
