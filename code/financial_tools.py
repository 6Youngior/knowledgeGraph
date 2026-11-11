"""Dated financial queries shared by the MCP server and Web API."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from finance import FinanceStore
from research_tools import CHINA, day


class FinancialResearch:
    def __init__(self, data_dir: Path, as_of: str | None = None):
        self.data_dir = Path(data_dir)
        self.as_of = as_of or datetime.now(CHINA).date().isoformat()
        if day(self.as_of) != self.as_of or self.as_of > datetime.now(CHINA).date().isoformat():
            raise ValueError("研究日期必须是有效且不晚于今天的 YYYY-MM-DD 日期")
        self.store = FinanceStore(self.data_dir)
        manifest_path = self.data_dir / "manifest.json"
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}

    def overview(self):
        snapshot = self.manifest.get("snapshot", {}).get("available_at")
        if not snapshot or snapshot > self.as_of:
            return {"as_of": self.as_of, "companies": [], "financial_records": 0}
        return {
            "as_of": self.as_of,
            "companies": self.store.list_companies(),
            "financial_records": self.manifest.get("counts", {}).get("financial_records", 0),
            "available_at": snapshot,
            "coverage": "上市公司财务指标的聚合数据快照；历史修订版本尚未补齐。",
        }

    def company_financials(self, symbol: str, periods: int = 4):
        if isinstance(periods, bool) or not isinstance(periods, int) or not 1 <= periods <= 8:
            raise ValueError("报告期数量应在 1—8 之间")
        if not self.overview()["companies"]:
            return {"as_of": self.as_of, "found": False, "reports": []}
        available = self.store.company_financials(symbol, self.as_of, 10000)
        if not available:
            return {"as_of": self.as_of, "found": False, "reports": []}
        rows = available[:periods]
        source_ids = {row["source_id"] for row in rows}
        sources = json.loads((self.data_dir / "sources.json").read_text(encoding="utf-8"))
        definitions = rows[0]["metric_definitions"]
        # Return shared definitions once rather than duplicating them per period.
        reports = [{k: v for k, v in row.items() if k != "metric_definitions"} for row in rows]
        disclosures = json.loads((self.data_dir / "disclosures.json").read_text(encoding="utf-8"))
        documents = [{k: v for k, v in row.items() if k not in {"sha256", "bytes", "pages"}}
                     for row in disclosures
                     if row["symbol"] == reports[0]["symbol"]
                     and (day(row.get("retrieved_at")) or "9999-12-31") <= self.as_of
                     and (day(row.get("published_at")) or "") <= self.as_of]
        return {
            "as_of": self.as_of, "found": True,
            "symbol": reports[0]["symbol"], "company": reports[0]["company"],
            "reports": reports, "metric_definitions": definitions,
            "coverage": {"available_reports": len(available), "returned_reports": len(reports),
                         "first_report_period": available[-1]["report_period"],
                         "last_report_period": available[0]["report_period"]},
            "sources": [source for source in sources if source["id"] in source_ids],
            "company_disclosures": documents,
            "note": "指标来自聚合接口；随附公司年报不一定对应本次查询报告期，引用前须核对。金额为人民币元，累计报告期不能当单季。",
        }

    def price_history(self, symbol: str, days: int = 30):
        if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 120:
            raise ValueError("行情天数应在 1—120 之间")
        companies = {row["symbol"]: row for row in self.overview()["companies"]}
        wanted = symbol.strip().upper()
        if wanted not in companies:
            return {"as_of": self.as_of, "found": False, "prices": []}
        rows = [json.loads(line) for line in (self.data_dir / "prices.jsonl").read_text(encoding="utf-8").splitlines() if line]
        visible = sorted((row for row in rows if row["symbol"] == wanted
                          and row["snapshot_available_at"] <= self.as_of
                          and row["date"] <= self.as_of), key=lambda row: row["date"])
        if not visible:
            return {"as_of": self.as_of, "found": False, "prices": []}
        latest = visible[-1]
        return {
            "as_of": self.as_of, "found": True, "symbol": wanted,
            "currency": latest["currency"], "adjusted": latest["adjustment"],
            "volume_unit": latest["volume_unit"], "source_id": latest["source_id"],
            "retrieved_at": self.manifest["snapshot"]["collected_at"],
            "last_available_date": latest["date"],
            "prices": [{k: row[k] for k in ("date", "open", "high", "low", "close", "volume", "amount")}
                       for row in visible[-days:]],
        }
