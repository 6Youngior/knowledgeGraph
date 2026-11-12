"""FinGraph's read-only MCP server, using the official SDK's stdio transport."""
from __future__ import annotations

import argparse
import os
import threading
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from financial_tools import FinancialResearch
from research_tools import ResearchTools


ROOT = Path(__file__).resolve().parents[1]


def _startup_binding():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--data-dir", default=os.getenv("FINGRAPH_DATA_DIR") or str(ROOT / "data"))
    parser.add_argument("--as-of", default=os.getenv("FINGRAPH_AS_OF") or None)
    args, _ = parser.parse_known_args()
    return Path(args.data_dir).expanduser().resolve(), args.as_of


DATA_DIR, START_AS_OF = _startup_binding()


class ResearchToolsCache:
    """One process-local view, refreshed when source/runtime files change.

    The cutoff and data directory are fixed when the MCP process starts.  A
    tool call can never supply either value.  This is deliberately a small
    mtime/size cache, not an event bus or a second service.
    """

    def __init__(self, data_dir: Path, as_of: str | None):
        self.data_dir = Path(data_dir)
        self.as_of = as_of
        self._lock = threading.RLock()
        self._service = None
        self._fingerprint = None
        self._reload()

    def _data_fingerprint(self):
        # Graph/source/runtime changes affect the graph view.  Market files
        # are included so a deliberate cache refresh also updates prices.
        paths = [
            self.data_dir / "knowledge_graph.json",
            self.data_dir / "sources.json",
            self.data_dir / "runtime" / "graph_state.json",
            self.data_dir / "market" / "manifest.json",
        ]
        market = self.data_dir / "market"
        if market.exists():
            paths.extend(sorted(market.glob("*.csv")))
        stat_parts = []
        for path in paths:
            try:
                info = path.stat()
                stat_parts.append((str(path.relative_to(self.data_dir)), info.st_size, info.st_mtime_ns))
            except OSError:
                stat_parts.append((str(path.relative_to(self.data_dir)), None, None))
        return tuple(stat_parts)

    def _reload(self):
        for _ in range(3):
            before = self._data_fingerprint()
            service = ResearchTools(self.data_dir, self.as_of)
            after = self._data_fingerprint()
            if before != after:
                continue
            # Freeze the effective date and cache only a coherent file version.
            if self.as_of is None:
                self.as_of = service.as_of
            self._service = service
            self._fingerprint = after
            return
        raise RuntimeError("资料正在更新，请稍后重试。")

    def get(self):
        with self._lock:
            fingerprint = self._data_fingerprint()
            if self._service is None or fingerprint != self._fingerprint:
                self._reload()
            return self._service


research_cache = ResearchToolsCache(DATA_DIR, START_AS_OF)


class _ServiceProxy:
    """Compatibility view that always delegates to the refreshed cache."""

    def __getattr__(self, name):
        return getattr(research_cache.get(), name)


# Kept for callers that inspect the module during startup; unlike the old
# global snapshot, every attribute delegates to the current cache.
service = _ServiceProxy()
financial = FinancialResearch(DATA_DIR / "finance", service.as_of)

mcp = FastMCP("FinGraph")


@mcp.tool()
def overview() -> dict:
    """查看当前研究日期、资料范围和可查询的产业事件。"""
    return {**research_cache.get().overview(), "financial_data": financial.overview()}


@mcp.tool()
def search_entities(query: str, limit: int = 8) -> dict:
    """按模型、产品、公司或证券标识定位实体，供后续关系查询使用。"""
    return research_cache.get().search_entities(query, limit)


@mcp.tool()
def entity_relations(entity_id: str, limit: int = 12) -> dict:
    """查看公司、产品或模型的一跳关系及财报页码和原文证据；先用search_entities定位。"""
    return research_cache.get().entity_relations(entity_id, limit)


@mcp.tool()
def related_stocks(event_id: str) -> dict:
    """查询事件关联股票、产业角色、逐步关系路径和原文出处。"""
    return research_cache.get().related_stocks(event_id)


@mcp.tool()
def read_source(source_id: str) -> dict:
    """读取当前研究时点可见来源的正文片段、发布日期和采集日期。"""
    return research_cache.get().read_source(source_id)


@mcp.tool()
def price_history(symbol: str, days: int = 30) -> dict:
    """读取历史行情和实际复权日期，不提供未来价格。"""
    current = financial.price_history(symbol, days)
    if current["found"]:
        return current
    return research_cache.get().price_history(symbol, days)


@mcp.tool()
def company_financials(symbol: str, periods: int = 4) -> dict:
    """查询上市公司财务指标、报告期、单位、来源和证券代码。"""
    return financial.company_financials(symbol, periods)


if __name__ == "__main__":
    mcp.run(transport="stdio")
