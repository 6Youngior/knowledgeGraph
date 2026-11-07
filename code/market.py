"""Trading-session event windows over cached, auditable daily observations."""
from __future__ import annotations

import bisect
import csv
import math
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from graph_store import read_json


class MarketData:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self._cache = {}

    def manifest(self):
        items = read_json(self.data_dir / "market" / "manifest.json", [])
        if isinstance(items, dict):
            items = items.get("stocks", items.get("series", []))
        return {item["symbol"]: item for item in items}

    def rows(self, symbol):
        manifest = self.manifest()
        if symbol not in manifest:
            raise KeyError(f"尚无 {symbol} 的真实行情缓存")
        spec = manifest[symbol]
        path = (self.data_dir / spec["file"]).resolve()
        if not path.is_relative_to(self.data_dir.resolve()):
            raise ValueError("行情路径必须在 data 目录内")
        cache_key = (str(path), path.stat().st_mtime_ns)
        if cache_key not in self._cache:
            with path.open(encoding="utf-8-sig", newline="") as stream:
                values = list(csv.DictReader(stream))
            rows = []
            for row in values:
                day = row["date"][:10]
                datetime.strptime(day, "%Y-%m-%d")
                price = float(row["close"])
                if not math.isfinite(price) or price <= 0:
                    raise ValueError(f"无效收盘价：{symbol} {day}")
                parsed = {"date": day, "close": price, "volume": float(row.get("volume") or 0)}
                for name in ("open", "high", "low"):
                    if row.get(name):
                        parsed[name] = float(row[name])
                rows.append(parsed)
            dates = [r["date"] for r in rows]
            if dates != sorted(set(dates)):
                raise ValueError(f"行情存在重复或无序日期：{symbol}")
            self._cache[cache_key] = rows
        return self._cache[cache_key], spec

    @staticmethod
    def anchor(event, dates, market):
        # Market observability follows disclosure, not a retrospectively stated
        # occurrence date. Explicit intraday timestamps take precedence below.
        event_day = (event.get("disclosed_at") or event.get("event_at") or event["date"])[:10]
        known_at = event.get("market_known_at")
        if known_at:
            moment = datetime.fromisoformat(known_at.replace("Z", "+00:00"))
            if moment.tzinfo is None:
                raise ValueError("market_known_at 必须包含时区")
            local = moment.astimezone(ZoneInfo("Asia/Hong_Kong" if market == "HK" else "Asia/Shanghai"))
            event_day = local.date().isoformat()
            closing = time(16, 0) if market == "HK" else time(15, 0)
            after_close = local.time() >= closing
            index = bisect.bisect_right(dates, event_day) if after_close else bisect.bisect_left(dates, event_day)
            policy = "按已核实披露时刻映射：收盘后顺延至下一交易日"
        elif event.get("known_before_open") is True:
            index = bisect.bisect_left(dates, event_day)
            policy = "资料明确为开盘前公开，以当日或之后首个交易日为 T0"
        else:
            # A date alone does not establish that a document was known at the open.
            index = bisect.bisect_right(dates, event_day)
            policy = "披露时间仅精确到日，保守采用披露日之后首个交易日为 T0"
        if index >= len(dates):
            raise ValueError("缓存未覆盖事件后的首个交易日")
        if index == 0:
            raise ValueError("缓存缺少 T−1 收盘价，无法计算事件窗口")
        if dates[index] > event_day:
            from datetime import date
            if (date.fromisoformat(dates[index]) - date.fromisoformat(event_day)).days > 14:
                raise ValueError("行情窗口与事件相距超过两周，不能作为匹配的事件缓存")
        return index, policy

    def event_window(self, symbol, event, window=5, as_of=None):
        rows, spec = self.rows(symbol)
        listing_date = spec.get("listing_date")
        if listing_date and listing_date > (event.get("disclosed_at") or event.get("date", ""))[:10]:
            raise ValueError(f"该事件发生时证券尚未上市（上市日期 {listing_date}），没有可比较的事件行情")
        if as_of:
            from research import validate_cutoff
            validate_cutoff(as_of)
            rows = [r for r in rows if r["date"] <= as_of]
        dates = [r["date"] for r in rows]
        try:
            index, policy = self.anchor(event, dates, spec.get("market", ""))
        except ValueError as exc:
            if as_of and (not rows or rows[-1]["date"] <= (event.get("disclosed_at") or event["date"])[:10]):
                raise ValueError(f"截至 {as_of} 尚无披露后的完整交易日，取消历史日期可查看后续行情") from exc
            raise
        base = rows[index - 1]["close"]
        benchmark = None
        benchmark_prices = {}
        benchmark_base = None
        benchmark_symbol = spec.get("benchmark_symbol")
        notes = ["累计收益的基期为 T−1 收盘价；1/3/5 日分别覆盖 T0、T0 至 T+2、T0 至 T+4。",
                 "这是描述性事件窗口；多事件干扰和事后关联不能作为因果或可交易收益证明。"]
        if benchmark_symbol:
            try:
                benchmark_rows, benchmark_spec = self.rows(benchmark_symbol)
                if as_of:
                    benchmark_rows = [r for r in benchmark_rows if r["date"] <= as_of]
                benchmark_dates = [r["date"] for r in benchmark_rows]
                base_index = bisect.bisect_left(benchmark_dates, rows[index]["date"]) - 1
                if base_index >= 0:
                    benchmark_base = benchmark_rows[base_index]["close"]
                    benchmark_prices = {r["date"]: r["close"] for r in benchmark_rows}
                    benchmark = {"symbol": benchmark_symbol, "name": benchmark_spec["name"]}
            except (KeyError, ValueError, FileNotFoundError) as exc:
                notes.append(f"基准暂不可用：{exc}")
        prices = []
        for i in range(max(0, index - window), min(len(rows), index + window + 1)):
            row = rows[i]
            benchmark_price = benchmark_prices.get(row["date"])
            prices.append({**row, "relative_day": i - index, "normalized": round(row["close"] / base * 100, 6),
                           "benchmark_normalized": round(benchmark_price / benchmark_base * 100, 6)
                           if benchmark_price is not None and benchmark_base else None})
        returns = {str(horizon): rows[index + horizon - 1]["close"] / base - 1
                   if index + horizon - 1 < len(rows) else None for horizon in (1, 3, 5)}
        window_dates = {str(h): rows[index + h - 1]["date"] if index + h - 1 < len(rows) else None
                        for h in (1, 3, 5)}
        benchmark_returns = {h: benchmark_prices[end] / benchmark_base - 1
                             if end and end in benchmark_prices and benchmark_base else None
                             for h, end in window_dates.items()}
        excess_returns = {h: returns[h] - benchmark_returns[h]
                          if returns[h] is not None and benchmark_returns[h] is not None else None
                          for h in returns}
        return {"symbol": symbol, "name": spec.get("name", symbol), "currency": spec.get("currency", ""),
                "event_date": event.get("event_at", event["date"])[:10], "anchor_date": dates[index],
                "anchor_policy": policy, "prices": prices, "returns": returns, "benchmark": benchmark,
                "benchmark_returns": benchmark_returns, "excess_returns": excess_returns, "window_dates": window_dates,
                "excess_method": "股票累计收益减同一窗口基准累计收益（简单百分点差，非因果估计）",
                "as_of": as_of,
                "provider": spec.get("provider", ""), "source_url": spec.get("url", ""),
                "adjusted": spec.get("adjusted", "unknown"), "notes": notes}
