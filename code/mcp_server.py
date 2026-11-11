"""FinGraph's read-only MCP server, using the official SDK's stdio transport."""
from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from research_tools import ResearchTools
from financial_tools import FinancialResearch

ROOT = Path(__file__).resolve().parents[1]
service = ResearchTools(ROOT / "data", os.getenv("FINGRAPH_AS_OF") or None)
financial = FinancialResearch(ROOT / "data" / "finance", service.as_of)
mcp = FastMCP("FinGraph")


@mcp.tool()
def overview() -> dict:
    """查看当前研究日期、资料范围和可查询的产业事件。"""
    return {**service.overview(), "financial_data": financial.overview()}


@mcp.tool()
def search_entities(query: str, limit: int = 8) -> dict:
    """查找模型、产品、公司及证券的标识，供后续关系查询使用。"""
    return service.search_entities(query, limit)


@mcp.tool()
def related_stocks(event_id: str) -> dict:
    """查询事件关联股票、产业角色、逐步关系路径及原文出处。"""
    return service.related_stocks(event_id)


@mcp.tool()
def read_source(source_id: str) -> dict:
    """读取当前研究时点可见的来源正文及其公开、采集日期。"""
    return service.read_source(source_id)


@mcp.tool()
def price_history(symbol: str, days: int = 30) -> dict:
    """读取已有历史日线与实际覆盖日期；不提供未来行情或补造价格。"""
    current = financial.price_history(symbol, days)
    if current["found"]:
        return current
    return service.price_history(symbol, days)


@mcp.tool()
def company_financials(symbol: str, periods: int = 4) -> dict:
    """查询上市公司财务指标、报告期、金额单位及来源；证券代码可先从 overview 查看。"""
    return financial.company_financials(symbol, periods)


if __name__ == "__main__":
    mcp.run(transport="stdio")
