"""Real SDK stdio calls: protocol, schemas and cutoff propagation; no LLM."""
import json
import sys
import unittest
from pathlib import Path

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


@unittest.skipUnless(MCP_AVAILABLE, "install code/requirements-agent.txt for MCP integration checks")
class McpIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, as_of, callback):
        params = StdioServerParameters(
            command=sys.executable, args=[str(ROOT / "code" / "mcp_server.py")],
            cwd=str(ROOT), env={"PYTHONUTF8": "1", "FINGRAPH_AS_OF": as_of},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await callback(session)

    async def test_current_graph_and_financial_tools_over_stdio(self):
        async def check(session):
            tools = await session.list_tools()
            self.assertEqual({t.name for t in tools.tools}, {
                "overview", "search_entities", "related_stocks", "read_source", "price_history", "company_financials",
            })
            overview = tool_value(await session.call_tool("overview", {}))
            self.assertEqual(len(overview["financial_data"]["companies"]), 5)
            related = await session.call_tool("related_stocks", {"event_id": "event:glm5-release"})
            self.assertFalse(related.isError)
            self.assertEqual({s["symbol"] for s in tool_value(related)["stocks"]}, {"02513.HK", "09988.HK"})
            reports = tool_value(await session.call_tool("company_financials", {"symbol": "688041.SH", "periods": 1}))
            self.assertEqual(reports["reports"][0]["report_period"], "2026-09-30")
        await self.exercise("2026-11-11", check)

    async def test_past_cutoff_is_applied_to_all_current_snapshots(self):
        async def check(session):
            overview = tool_value(await session.call_tool("overview", {}))
            self.assertEqual(overview["knowledge"]["documents"], 0)
            self.assertEqual(overview["financial_data"]["companies"], [])
            result = tool_value(await session.call_tool("company_financials", {"symbol": "09988.HK"}))
            self.assertEqual(result, {"as_of": "2026-02-12", "found": False, "reports": []})
            result = tool_value(await session.call_tool("related_stocks", {"event_id": "event:glm5-release"}))
            self.assertFalse(result["found"])
        await self.exercise("2026-02-12", check)
